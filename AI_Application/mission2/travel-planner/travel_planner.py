"""국내 여행 추천 CLI — LLM(Gemini) + 지도(Kakao Local) API 조합.

    python3 travel_planner.py -date "YYYY-MM-DD" [--cities N] [--count N] [--no-cache]

흐름: [1/3] LLM 1차 추천(JSON) → [2/3] 지역별 맛집 검색 → [3/3] LLM 최종 리포트(Markdown)
결과: results/<날짜>_raw.json · results/<날짜>_travel_plan.md
"""

import argparse
import os
import sys
from datetime import datetime, timezone, timedelta

import config
import llm_api
import place_api
import report
from errors import ErrorLog, LLM_ERROR

KST = timezone(timedelta(hours=9))


def valid_date(text):
    """argparse 타입 검사 — YYYY-MM-DD 가 아니면 사용법과 함께 종료된다."""
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError(f"날짜 형식이 올바르지 않습니다: '{text}' (예: 2026-10-03)")
    return text


def build_parser():
    parser = argparse.ArgumentParser(
        prog="travel_planner.py",
        description="여행 날짜를 입력하면 LLM 이 지역을 추천하고, 지도 API 로 맛집을 찾아 여행 리포트를 만든다.",
    )
    parser.add_argument("-date", "--date", required=True, type=valid_date, metavar='"YYYY-MM-DD"',
                        help="여행 날짜 (필수)")
    parser.add_argument("--cities", type=int, default=3, choices=[1, 2, 3],
                        help="추천 지역 수 (기본 3, 보너스: 복수 지역)")
    parser.add_argument("--count", type=int, default=5,
                        help="지역당 맛집 검색 수 (기본 5)")
    parser.add_argument("--no-cache", action="store_true",
                        help="같은 날짜의 저장된 원본 JSON 이 있어도 API 를 다시 호출한다")
    return parser


def run(args):
    errors = ErrorLog()
    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    raw_file = report.raw_path(config.RESULTS_DIR, args.date)
    report_file = report.report_path(config.RESULTS_DIR, args.date)

    # 보너스: 캐싱 — 같은 날짜의 원본 JSON 이 있으면 [1/3]·[2/3] API 호출을 건너뛴다
    cached = None
    if not args.no_cache and os.path.exists(raw_file):
        try:
            cached = report.load_raw(raw_file)
            if not cached.get("recommendation"):
                cached = None   # 이전 실행이 1차 추천에서 실패한 기록 — 캐시로 쓰지 않는다
            else:
                print(f"[캐시] {os.path.relpath(raw_file)} 발견 — 1차 추천·맛집 검색 API 호출을 건너뜁니다 (--no-cache 로 재호출)")
        except (OSError, ValueError, AttributeError) as exc:
            print(f"[캐시] 읽기 실패({exc}) — API 를 다시 호출합니다")

    if cached:
        recommendation = cached["recommendation"]
        places_by_city = cached["places"]
        for e in cached.get("errors", []):
            if e.get("step") != "report":
                errors.add(e["step"], e["type"], e["message"])
        print(f"[1/3] 1차 추천 (캐시)")
        for c in recommendation["recommended_cities"]:
            print(f"    - {c['city']}")
        print(f"[2/3] 맛집 검색 (캐시)")
        for city, places in places_by_city.items():
            print(f"    - {city}: {len(places)}곳")
    else:
        # [1/3] LLM 1차 추천 — 실패하면 다음 단계 입력이 없으므로 종료
        print(f"[1/3] 1차 추천 생성 중(LLM · {config.GEMINI_MODEL})...")
        try:
            recommendation = llm_api.recommend(args.date, args.cities, log=print)
        except llm_api.LLMError as exc:
            errors.add("recommend", exc.error_type, str(exc))
            print(f"  - 오류: {exc.error_type} — {exc}")
            print("1차 추천을 만들지 못해 종료합니다. (원본 JSON 에 오류만 기록)")
            report.save_raw(raw_file, _raw(args, None, {}, errors))
            return 1
        for c in recommendation["recommended_cities"]:
            print(f"    - recommended_city: \"{c['city']}\"")

        # [2/3] 지역별 맛집 검색 — 실패·0건이어도 계속 진행
        print("[2/3] 맛집 검색 중(Kakao Local)...")
        places_by_city = {}
        for c in recommendation["recommended_cities"]:
            places = place_api.search_restaurants(c["city"], args.count, errors, log=print)
            places_by_city[c["city"]] = places
            if places:
                print(f"    - {c['city']}: 맛집 {len(places)}곳 검색 완료")

        report.save_raw(raw_file, _raw(args, recommendation, places_by_city, errors))

    # [3/3] LLM 최종 리포트 — 실패하면 데이터만으로 대체 리포트를 만든다
    print("[3/3] 최종 리포트 생성 중(LLM)...")
    try:
        markdown = llm_api.write_report(args.date, recommendation, places_by_city)
        print("    - 리포트 생성 완료")
    except llm_api.LLMError as exc:
        errors.add("report", exc.error_type, str(exc))
        print(f"  - 오류: {exc.error_type} — {exc}")
        print("    - 데이터만으로 대체 리포트를 생성합니다")
        markdown = report.fallback_report(args.date, recommendation, places_by_city)
    markdown = markdown.rstrip() + "\n\n" + report.errors_section(errors)
    report.save_report(report_file, markdown)
    # 리포트 단계 오류까지 포함해 원본 JSON 의 errors 를 최종 상태로 갱신
    report.save_raw(raw_file, _raw(args, recommendation, places_by_city, errors))

    print(f"\n완료! {os.path.relpath(report_file)} 를 확인하세요.")
    print(f"      원본 데이터: {os.path.relpath(raw_file)}")
    if len(errors):
        print(f"      오류 {len(errors)}건 — 리포트 끝 '오류 요약(errors)' 참고")
    return 0


def _raw(args, recommendation, places_by_city, errors):
    """results/<날짜>_raw.json 에 저장하는 원본 데이터."""
    return {
        "date": args.date,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "llm_model": config.GEMINI_MODEL,
        "place_provider": "kakao_local_keyword",
        "recommendation": recommendation,
        "places": places_by_city,
        "errors": list(errors),
    }


def main():
    args = build_parser().parse_args()   # 날짜 형식 오류 → 사용법 출력 후 종료(exit 2)
    config.require_keys()                # 키 미설정 → 설정 안내 후 종료(exit 1)
    sys.exit(run(args))


if __name__ == "__main__":
    main()
