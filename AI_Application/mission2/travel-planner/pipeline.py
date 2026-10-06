"""여행 추천 파이프라인 — CLI(travel_planner.py)와 웹(web.py)이 같이 쓴다.

[1/3] LLM 1차 추천(JSON) → [2/3] 지역별 맛집 검색 → [3/3] LLM 최종 리포트(Markdown)

진행 상황은 emit(event) 콜백으로 알린다.
  {"kind": "step", "step": 1~3, "title": "..."}                      단계 시작
  {"kind": "log", "step": 1~3, "level": "info|warn|error", "text": "..."}
  {"kind": "notice", "level": "info|warn", "text": "..."}            단계 밖 안내 (캐시 등)
level — info: 정상 진행 · warn: 실패했지만 계속 진행 · error: 그 단계를 끝내지 못함
"""

import os
from datetime import datetime, timedelta, timezone

import config
import llm_api
import place_api
import report
from errors import AUTH_ERROR, EMPTY_RESULT, IO_ERROR, QUOTA_ERROR, ErrorLog

KST = timezone(timedelta(hours=9))
TOTAL_STEPS = 3


def print_event(event):
    """CLI 용 — 이벤트를 진행 로그 한 줄로 출력한다."""
    if event["kind"] == "step":
        print(f"[{event['step']}/{TOTAL_STEPS}] {event['title']}", flush=True)
    elif event["kind"] == "notice":
        print(event["text"], flush=True)
    else:
        print(f"    - {event['text']}", flush=True)


def run(date, cities=3, count=5, use_cache=True, emit=print_event):
    """파이프라인을 실행하고 결과를 dict 로 돌려준다.

    ok=False 는 1차 추천 실패처럼 리포트를 만들 수 없었던 경우다.
    saved=False 는 결과 파일 저장에 실패한 경우다 (리포트 본문은 markdown 에 있다).
    """
    errors = ErrorLog()
    raw_file = report.raw_path(config.RESULTS_DIR, date)
    report_file = report.report_path(config.RESULTS_DIR, date)
    failed_paths = set()

    def log(step, level, text):
        emit({"kind": "log", "step": step, "level": level, "text": text})

    def step(n, title):
        emit({"kind": "step", "step": n, "title": title})

    def notice(level, text):
        emit({"kind": "notice", "level": level, "text": text})

    def save(write, path, data, step_no):
        """저장 실패는 errors 에 경로당 1번만 남기고 계속 진행한다."""
        try:
            os.makedirs(config.RESULTS_DIR, exist_ok=True)
            write(path, data)
            return True
        except OSError as exc:
            if path not in failed_paths:
                failed_paths.add(path)
                errors.add("save", IO_ERROR, f"{display_path(path)} 저장 실패 — {exc.strerror or exc}")
                log(step_no, "error", f"오류: {display_path(path)} 저장 실패 ({exc.strerror or exc})")
            return False

    # 보너스: 캐싱 — 같은 날짜의 원본 JSON 이 있으면 [1/3]·[2/3] API 호출을 건너뛴다
    cached = _load_cache(raw_file, notice, cities, count) if use_cache else None

    if cached:
        recommendation = cached["recommendation"]
        places_by_city = cached["places"]
        for e in cached.get("errors", []):
            if e.get("step") != "report":
                errors.add(e["step"], e["type"], e["message"])
        step(1, "1차 추천 (캐시)")
        for c in recommendation["recommended_cities"]:
            log(1, "info", c["city"])
        step(2, "맛집 검색 (캐시)")
        for city, places in places_by_city.items():
            log(2, "info", f"{city}: {len(places)}곳")
    else:
        # [1/3] LLM 1차 추천 — 실패하면 다음 단계 입력이 없으므로 여기서 끝낸다
        step(1, f"1차 추천 생성 중(LLM · {config.GEMINI_MODEL})...")
        try:
            recommendation = llm_api.recommend(date, cities, errors, log=lambda t: log(1, "warn", t))
        except llm_api.LLMError as exc:
            errors.add("recommend", exc.error_type, str(exc))
            log(1, "error", f"오류: {exc.error_type} — {exc}")
            log(1, "error", "1차 추천을 만들지 못해 종료합니다. (원본 JSON 에 오류만 기록)")
            raw = _raw(date, cities, count, None, {}, errors)
            saved = save(report.save_raw, raw_file, raw, 1)
            return _result(False, date, raw_file, None, raw, None, cached=False, saved=saved)
        for c in recommendation["recommended_cities"]:
            log(1, "info", f'recommended_city: "{c["city"]}"')

        # [2/3] 지역별 맛집 검색 — 실패·0건이어도 계속 진행
        step(2, "맛집 검색 중(Kakao Local)...")
        places_by_city = {}
        stop = None   # 인증·쿼터 실패면 같은 키로 나머지 지역도 실패하므로 호출을 멈춘다
        for c in recommendation["recommended_cities"]:
            city = c["city"]
            if stop:
                errors.add(place_api.STEP, stop, f"앞 지역의 {stop} 로 검색 생략 (query={city} 맛집)")
                log(2, "warn", f"{city}: 앞 지역에서 {stop} — 같은 키라 검색을 건너뜁니다 (데이터 없음)")
                places_by_city[city] = []
                continue
            before = len(errors)
            places = place_api.search_restaurants(
                city, count, errors, log=lambda t, city=city: log(2, "warn", f"{city}: {t}"))
            places_by_city[city] = places
            if places:
                log(2, "info", f"{city}: 맛집 {len(places)}곳 검색 완료")
            elif len(errors) > before and errors.items[-1]["type"] in (AUTH_ERROR, QUOTA_ERROR):
                stop = errors.items[-1]["type"]

        save(report.save_raw, raw_file, _raw(date, cities, count, recommendation, places_by_city, errors), 2)

    # [3/3] LLM 최종 리포트 — 실패하면 데이터만으로 대체 리포트를 만든다
    step(3, "최종 리포트 생성 중(LLM)...")
    try:
        markdown = llm_api.write_report(date, recommendation, places_by_city, log=lambda t: log(3, "warn", t))
        log(3, "info", "리포트 생성 완료")
    except llm_api.LLMError as exc:
        errors.add("report", exc.error_type, str(exc))
        log(3, "warn", f"오류: {exc.error_type} — {exc}")
        log(3, "warn", "데이터만으로 대체 리포트를 생성합니다")
        markdown = report.fallback_report(date, recommendation, places_by_city)
    markdown = markdown.rstrip() + "\n\n" + report.errors_section(errors)
    report_saved = save(report.save_report, report_file, markdown, 3)
    # 리포트 단계 오류까지 포함해 원본 JSON 의 errors 를 최종 상태로 갱신
    raw = _raw(date, cities, count, recommendation, places_by_city, errors)
    raw_saved = save(report.save_raw, raw_file, raw, 3)
    if not raw_saved:
        raw["errors"] = list(errors)   # 저장 실패 기록까지 결과에 담는다
    return _result(True, date, raw_file, report_file, raw, markdown, cached=bool(cached),
                   saved=report_saved and raw_saved)


def _load_cache(raw_file, notice, cities, count):
    """캐시로 쓸 수 있는 원본 JSON 이면 dict, 아니면 None."""
    if not os.path.exists(raw_file):
        return None
    try:
        cached = report.load_raw(raw_file)
        reason = _cache_miss_reason(cached, cities, count)
    except (OSError, ValueError, AttributeError, KeyError, TypeError) as exc:
        reason = f"읽기 실패({type(exc).__name__}: {exc})"
    if reason:
        notice("info", f"[캐시] {display_path(raw_file)} 를 쓰지 않습니다 — {reason}. API 를 다시 호출합니다")
        return None
    notice("info", f"[캐시] {display_path(raw_file)} 발견 — 1차 추천·맛집 검색 API 호출을 건너뜁니다 (--no-cache 로 재호출)")
    return cached


def _cache_miss_reason(cached, cities, count):
    """저장된 원본 JSON 을 캐시로 쓸 수 없는 이유. 쓸 수 있으면 None.

    실패한 호출 결과를 캐시로 굳히지 않도록, 키를 고치거나 한도가 풀린 뒤 다시 실행하면 새로 호출한다.
    """
    recommendation = cached.get("recommendation")
    if not recommendation:
        return "이전 실행이 1차 추천에서 실패한 기록"
    failed = [e for e in cached.get("errors", [])
              if e.get("step") == "place_search" and e.get("type") != EMPTY_RESULT]
    if failed:
        return f"이전 실행에 맛집 검색 오류({failed[0]['type']}) 기록"
    if not isinstance(cached.get("places"), dict):
        return "places 형식이 올바르지 않음"
    # options 가 없는 예전 파일은 실제 지역 수로 비교하고, 맛집 수는 비교하지 않는다
    options = cached.get("options") or {}
    saved_cities = options.get("cities", len(recommendation["recommended_cities"]))
    if saved_cities != cities:
        return f"지역 수가 다름(저장 {saved_cities}곳 · 요청 {cities}곳)"
    if options.get("count", count) != count:
        return f"맛집 수가 다름(저장 {options['count']}곳 · 요청 {count}곳)"
    return None


def _raw(date, cities, count, recommendation, places_by_city, errors):
    """results/<날짜>_raw.json 에 저장하는 원본 데이터."""
    return {
        "date": date,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "llm_model": config.GEMINI_MODEL,
        "place_provider": "kakao_local_keyword",
        "options": {"cities": cities, "count": count},
        "recommendation": recommendation,
        "places": places_by_city,
        "errors": list(errors),
    }


def _result(ok, date, raw_file, report_file, raw, markdown, cached, saved):
    return {"ok": ok, "saved": saved, "date": date, "raw_path": raw_file, "report_path": report_file,
            "raw": raw, "markdown": markdown, "cached": cached}


def display_path(path):
    """현재 폴더 기준 상대 경로 — 폴더 밖이면 절대 경로를 그대로 보여 준다."""
    rel = os.path.relpath(path)
    return path if rel.startswith("..") else rel
