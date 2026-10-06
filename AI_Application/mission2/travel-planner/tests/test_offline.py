"""네트워크 없이 오류 처리 경로를 검증한다 — requests 를 가짜 응답으로 바꾼다.

    python3 -m pytest tests -q
"""

import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import llm_api  # noqa: E402
import net  # noqa: E402
import place_api  # noqa: E402
import report  # noqa: E402
import travel_planner  # noqa: E402
from errors import AUTH_ERROR, EMPTY_RESULT, ErrorLog, NETWORK_ERROR, PARSE_ERROR  # noqa: E402


class FakeResponse:
    def __init__(self, status_code, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload, ensure_ascii=False)

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def gemini_text(text):
    return FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": text}]}}]})


# LLM 1차 응답 — 최상위 = 과제 필수 4키, 복수 지역은 other_cities
GOOD_RECOMMENDATION = {
    "recommended_city": "제주", "weather": "온화", "events": ["유채꽃 축제"], "reason": "봄꽃.",
    "other_cities": [{"recommended_city": "강릉", "weather": "선선", "events": ["커피축제"], "reason": "바다."}],
}


def good_report(date="2026-10-03", cities=("제주", "강릉"), no_places=False):
    """check_report 를 통과하는 최소 리포트."""
    lines = [f"# {date} 국내 여행 추천 리포트", "", "## 추천 지역"] + [f"- {c} — 요약" for c in cities]
    for i, c in enumerate(cities, start=1):
        lines += [f"## {i}. {c}"] + [f"### {s}\n- 내용" for s in llm_api.REPORT_SECTIONS]
    if no_places:
        lines.append("- 데이터 없음 (장소 검색 결과 0건)")
    return "\n".join(lines)


@pytest.fixture(autouse=True)
def keys(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test")
    monkeypatch.setattr(config, "KAKAO_REST_API_KEY", "test")
    monkeypatch.setattr(config, "RESULTS_DIR", str(tmp_path))
    monkeypatch.setattr(net, "RETRY_DELAY", 0)


# --- 입력 검증 ---------------------------------------------------------------

@pytest.mark.parametrize("bad", ["2026-13-01", "2026-1-5", "20261003", "2026-02-30", "next week"])
def test_date_must_be_zero_padded_yyyy_mm_dd(bad, capsys):
    with pytest.raises(SystemExit) as exc:
        travel_planner.build_parser().parse_args(["-date", bad])
    assert exc.value.code == 2
    assert "usage:" in capsys.readouterr().err


@pytest.mark.parametrize("bad", ["0", "-1", "16", "abc"])
def test_count_must_be_1_to_15(bad):
    with pytest.raises(SystemExit) as exc:
        travel_planner.build_parser().parse_args(["-date", "2026-10-03", "--count", bad])
    assert exc.value.code == 2


# --- 지도 API ---------------------------------------------------------------

def test_kakao_auth_error_returns_empty_and_logs(monkeypatch):
    monkeypatch.setattr(place_api.requests, "get", lambda *a, **k: FakeResponse(401, {"message": "wrong appKey"}))
    errors = ErrorLog()
    assert place_api.search_restaurants("제주", 5, errors, log=lambda *_: None) == []
    assert errors.items == [{"step": "place_search", "type": AUTH_ERROR, "message": "HTTP 401 (query=제주 맛집)"}]


def test_kakao_empty_result(monkeypatch):
    monkeypatch.setattr(place_api.requests, "get", lambda *a, **k: FakeResponse(200, {"documents": []}))
    errors = ErrorLog()
    assert place_api.search_restaurants("무인도", 5, errors, log=lambda *_: None) == []
    assert errors.items[0]["type"] == EMPTY_RESULT


def test_kakao_network_error(monkeypatch):
    def boom(*a, **k):
        raise place_api.requests.ConnectionError("dns")
    monkeypatch.setattr(place_api.requests, "get", boom)
    errors = ErrorLog()
    assert place_api.search_restaurants("제주", 5, errors, log=lambda *_: None) == []
    assert errors.items[0]["type"] == NETWORK_ERROR


def test_kakao_normalizes_fields(monkeypatch):
    doc = {"place_name": "A식당", "road_address_name": "제주 도로 1", "address_name": "제주 지번 1",
           "category_name": "음식점 > 한식", "place_url": "http://place", "x": "126.5", "y": "33.5", "phone": ""}
    monkeypatch.setattr(place_api.requests, "get", lambda *a, **k: FakeResponse(200, {"documents": [doc]}))
    places = place_api.search_restaurants("제주", 5, ErrorLog(), log=lambda *_: None)
    assert places == [{"name": "A식당", "address": "제주 도로 1", "category": "음식점 > 한식",
                       "url": "http://place", "x": 126.5, "y": 33.5, "phone": ""}]


# --- LLM 1차 추천 -------------------------------------------------------------

def test_recommend_retries_once_after_parse_failure(monkeypatch):
    replies = iter([gemini_text("이건 JSON 이 아님"), gemini_text(json.dumps(GOOD_RECOMMENDATION, ensure_ascii=False))])
    calls = []
    monkeypatch.setattr(llm_api.requests, "post", lambda *a, **k: calls.append(k["json"]) or next(replies))
    errors = ErrorLog()
    result = llm_api.recommend("2026-10-03", 2, errors, log=lambda *_: None)
    assert len(calls) == 2
    assert "다시 출력" in calls[1]["contents"][0]["parts"][0]["text"]
    assert result["recommended_city"] == "제주" and result["events"] == ["유채꽃 축제"]
    assert [c["recommended_city"] for c in result["recommended_cities"]] == ["제주", "강릉"]
    # 재시도로 복구됐어도 첫 실패는 errors 에 남는다
    assert [(e["step"], e["type"]) for e in errors] == [("recommend", PARSE_ERROR)]
    assert errors.items[0]["message"].startswith("시도 1:")


def test_recommend_rejects_empty_events_then_retries(monkeypatch):
    empty = {"recommended_city": "제주", "weather": "온화", "events": [], "reason": "봄꽃."}
    replies = iter([gemini_text(json.dumps(empty, ensure_ascii=False)),
                    gemini_text(json.dumps(GOOD_RECOMMENDATION, ensure_ascii=False))])
    monkeypatch.setattr(llm_api.requests, "post", lambda *a, **k: next(replies))
    errors = ErrorLog()
    assert llm_api.recommend("2026-10-03", 1, errors, log=lambda *_: None)["events"] == ["유채꽃 축제"]
    assert "events" in errors.items[0]["message"]


def test_recommend_schema_limits_events_1_to_3(monkeypatch):
    sent = []
    monkeypatch.setattr(llm_api.requests, "post",
                        lambda *a, **k: sent.append(k["json"]) or gemini_text(json.dumps(GOOD_RECOMMENDATION)))
    llm_api.recommend("2026-10-03", 1, ErrorLog(), log=lambda *_: None)
    schema = sent[0]["generationConfig"]["responseSchema"]
    assert schema["required"] == ["recommended_city", "weather", "events", "reason"]
    assert (schema["properties"]["events"]["minItems"], schema["properties"]["events"]["maxItems"]) == (1, 3)
    assert "other_cities" not in schema["properties"]          # 1곳이면 과제 최소 스키마 그대로


def test_recommend_gives_up_after_two_failures(monkeypatch):
    monkeypatch.setattr(llm_api.requests, "post", lambda *a, **k: gemini_text("{\"recommended_cities\": []}"))
    with pytest.raises(llm_api.LLMError) as exc:
        llm_api.recommend("2026-10-03", 2, ErrorLog(), log=lambda *_: None)
    assert exc.value.error_type == PARSE_ERROR


def test_recommend_strips_code_fence(monkeypatch):
    fenced = "```json\n" + json.dumps(GOOD_RECOMMENDATION, ensure_ascii=False) + "\n```"
    monkeypatch.setattr(llm_api.requests, "post", lambda *a, **k: gemini_text(fenced))
    assert llm_api.recommend("2026-10-03", 1, ErrorLog(), log=lambda *_: None)["recommended_city"] == "제주"


def test_gemini_invalid_key_is_auth_error(monkeypatch):
    monkeypatch.setattr(llm_api.requests, "post",
                        lambda *a, **k: FakeResponse(400, {"error": {"message": "API key not valid."}}))
    with pytest.raises(llm_api.LLMError) as exc:
        llm_api.recommend("2026-10-03", 1, ErrorLog(), log=lambda *_: None)
    assert exc.value.error_type == AUTH_ERROR
    assert str(exc.value) == "HTTP 400 API key not valid."


# --- 전체 흐름 -------------------------------------------------------------

def make_args(date="2026-10-03", **overrides):
    args = travel_planner.build_parser().parse_args(["-date", date])
    for k, v in overrides.items():
        setattr(args, k, v)
    return args


def test_pipeline_report_fallback_and_errors_section(monkeypatch, tmp_path, capsys):
    posts = iter([gemini_text(json.dumps(GOOD_RECOMMENDATION, ensure_ascii=False)),
                  FakeResponse(429, {"error": {"message": "quota"}})])
    monkeypatch.setattr(llm_api.requests, "post", lambda *a, **k: next(posts))
    monkeypatch.setattr(place_api.requests, "get", lambda *a, **k: FakeResponse(403, {"message": "disabled"}))

    assert travel_planner.run(make_args()) == 0
    raw = json.load(open(tmp_path / "2026-10-03_raw.json", encoding="utf-8"))
    md = open(tmp_path / "2026-10-03_travel_plan.md", encoding="utf-8").read()

    assert raw["recommendation"]["recommended_city"] == "제주"
    assert raw["places"] == {"제주": [], "강릉": []}
    assert [e["type"] for e in raw["errors"]] == [AUTH_ERROR, AUTH_ERROR, "QUOTA_ERROR"]
    assert md.startswith("# 2026-10-03 국내 여행 추천 리포트")
    assert "데이터 없음 (장소 검색 결과 0건)" in md
    assert "## 오류 요약(errors)" in md and "`report` · `QUOTA_ERROR`" in md
    assert "완료!" in capsys.readouterr().out


def test_pipeline_uses_cache_on_rerun(monkeypatch, tmp_path):
    calls = {"post": 0, "get": 0}

    def post(*a, **k):
        calls["post"] += 1
        is_json_mode = "responseSchema" in k["json"]["generationConfig"]
        return gemini_text(json.dumps(GOOD_RECOMMENDATION, ensure_ascii=False) if is_json_mode else good_report())

    def get(*a, **k):
        calls["get"] += 1
        return FakeResponse(200, {"documents": [{"place_name": "A", "address_name": "B", "x": "1", "y": "2"}]})

    monkeypatch.setattr(llm_api.requests, "post", post)
    monkeypatch.setattr(place_api.requests, "get", get)

    assert travel_planner.run(make_args()) == 0
    assert calls == {"post": 2, "get": 2}
    assert travel_planner.run(make_args()) == 0          # 캐시 — 추천·검색 건너뜀, 리포트만 재생성
    assert calls == {"post": 3, "get": 2}
    assert travel_planner.run(make_args(no_cache=True)) == 0
    assert calls == {"post": 5, "get": 4}
    assert json.load(open(tmp_path / "2026-10-03_raw.json", encoding="utf-8"))["errors"] == []


def test_failed_recommendation_is_not_reused_as_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(llm_api.requests, "post", lambda *a, **k: FakeResponse(500, {"error": {"message": "down"}}))
    assert travel_planner.run(make_args()) == 1
    assert json.load(open(tmp_path / "2026-10-03_raw.json", encoding="utf-8"))["recommendation"] is None
    assert travel_planner.run(make_args()) == 1   # 캐시로 쓰지 않고 다시 호출 → 여전히 실패


# --- LLM 응답 · 리포트 검증 ------------------------------------------------------

def test_gemini_prompt_block_is_llm_error(monkeypatch):
    monkeypatch.setattr(llm_api.requests, "post",
                        lambda *a, **k: FakeResponse(200, {"promptFeedback": {"blockReason": "SAFETY"}}))
    with pytest.raises(llm_api.LLMError) as exc:
        llm_api.recommend("2026-10-03", 1, ErrorLog(), log=lambda *_: None)
    assert exc.value.error_type == "LLM_ERROR" and "SAFETY" in str(exc.value)


def test_gemini_skips_thought_parts(monkeypatch):
    body = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
        {"text": "생각 중...", "thought": True},
        {"text": json.dumps(GOOD_RECOMMENDATION, ensure_ascii=False)}]}}]}
    monkeypatch.setattr(llm_api.requests, "post", lambda *a, **k: FakeResponse(200, body))
    assert llm_api.recommend("2026-10-03", 1, ErrorLog(), log=lambda *_: None)["recommended_city"] == "제주"


def test_report_missing_sections_falls_back(monkeypatch, tmp_path):
    posts = iter([gemini_text(json.dumps(GOOD_RECOMMENDATION, ensure_ascii=False)), gemini_text("# 아무 리포트")])
    monkeypatch.setattr(llm_api.requests, "post", lambda *a, **k: next(posts))
    monkeypatch.setattr(place_api.requests, "get",
                        lambda *a, **k: FakeResponse(200, {"documents": [{"place_name": "A식당", "address_name": "주소"}]}))
    assert travel_planner.run(make_args()) == 0
    md = open(tmp_path / "2026-10-03_travel_plan.md", encoding="utf-8").read()
    raw = json.load(open(tmp_path / "2026-10-03_raw.json", encoding="utf-8"))
    assert "수집 데이터로만 구성한 리포트" in md and "## 추천 지역" in md and "A식당에서 점심" in md
    assert raw["errors"][0]["step"] == "report" and raw["errors"][0]["type"] == PARSE_ERROR
    assert "필수 항목 누락" in raw["errors"][0]["message"]


def test_check_report_requires_no_data_mark_for_empty_city():
    rec = {"recommended_cities": [{"recommended_city": "제주"}, {"recommended_city": "강릉"}]}
    places = {"제주": [{"name": "A"}], "강릉": []}
    with pytest.raises(ValueError, match="데이터 없음"):
        llm_api.check_report(good_report(), "2026-10-03", rec, places)
    llm_api.check_report(good_report(no_places=True), "2026-10-03", rec, places)


def test_report_drops_llm_written_errors_section(monkeypatch):
    text = good_report() + "\n\n## 오류 요약(errors)\n- 지어낸 오류"
    monkeypatch.setattr(llm_api.requests, "post", lambda *a, **k: gemini_text(text))
    rec = {"recommended_cities": [{"recommended_city": "제주"}, {"recommended_city": "강릉"}]}
    md = llm_api.write_report("2026-10-03", rec, {"제주": [{"name": "A"}], "강릉": [{"name": "B"}]})
    assert "오류 요약" not in md


# --- 일시 오류 재시도 -------------------------------------------------------------

def counting(responses):
    """호출마다 다음 응답을 돌려주고(예외면 raise) 호출 수를 센다."""
    seq = iter(responses)
    calls = []

    def fake(*a, **k):
        calls.append(1)
        item = next(seq)
        if isinstance(item, Exception):
            raise item
        return item
    return fake, calls


def test_gemini_503_is_retried_once_then_succeeds(monkeypatch):
    fake, calls = counting([FakeResponse(503, {"error": {"message": "overloaded"}}),
                            gemini_text(json.dumps(GOOD_RECOMMENDATION, ensure_ascii=False))])
    monkeypatch.setattr(llm_api.requests, "post", fake)
    notes = []
    assert llm_api.recommend("2026-10-03", 1, ErrorLog(), log=notes.append)["recommended_city"] == "제주"
    assert len(calls) == 2 and "HTTP 503" in notes[0]


def test_gemini_503_twice_gives_http_error(monkeypatch):
    fake, calls = counting([FakeResponse(503, {"error": {"message": "overloaded"}})] * 2)
    monkeypatch.setattr(llm_api.requests, "post", fake)
    with pytest.raises(llm_api.LLMError) as exc:
        llm_api.recommend("2026-10-03", 1, ErrorLog(), log=lambda *_: None)
    assert len(calls) == 2 and exc.value.error_type == "HTTP_ERROR"


@pytest.mark.parametrize("first", [FakeResponse(401, {}), FakeResponse(429, {}),
                                   place_api.requests.ReadTimeout("slow")])
def test_auth_quota_readtimeout_are_not_retried(monkeypatch, first):
    fake, calls = counting([first])
    monkeypatch.setattr(place_api.requests, "get", fake)
    assert place_api.search_restaurants("제주", 5, ErrorLog(), log=lambda *_: None) == []
    assert len(calls) == 1


def test_kakao_connection_error_recovers_on_retry(monkeypatch):
    fake, calls = counting([place_api.requests.ConnectionError("reset"),
                            FakeResponse(200, {"documents": [{"place_name": "A", "address_name": "B"}]})])
    monkeypatch.setattr(place_api.requests, "get", fake)
    errors = ErrorLog()
    assert len(place_api.search_restaurants("제주", 5, errors, log=lambda *_: None)) == 1
    assert len(calls) == 2 and not errors.items


# --- 캐시 조건 -----------------------------------------------------------------

def stub_pipeline(monkeypatch, kakao):
    """1차 추천·리포트는 성공, Kakao 응답은 kakao() 로 정한다. 호출 수를 센다."""
    calls = {"post": 0, "get": 0}

    def post(*a, **k):
        calls["post"] += 1
        is_json_mode = "responseSchema" in k["json"]["generationConfig"]
        return gemini_text(json.dumps(GOOD_RECOMMENDATION, ensure_ascii=False) if is_json_mode
                           else good_report(no_places=True))

    def get(*a, **k):
        calls["get"] += 1
        return kakao()

    monkeypatch.setattr(llm_api.requests, "post", post)
    monkeypatch.setattr(place_api.requests, "get", get)
    return calls


def test_place_search_failure_is_not_reused_as_cache(monkeypatch, tmp_path, capsys):
    replies = iter([FakeResponse(401, {})] + [FakeResponse(200, {"documents": [{"place_name": "A"}]})] * 2)
    calls = stub_pipeline(monkeypatch, lambda: next(replies))
    assert travel_planner.run(make_args()) == 0                 # 잘못된 키 → 맛집 데이터 없음
    assert travel_planner.run(make_args()) == 0                 # 키를 고친 뒤 → 캐시 대신 다시 검색
    assert calls["get"] == 3                                    # 1회차는 첫 지역 401 뒤 나머지 생략
    assert "맛집 검색 오류(AUTH_ERROR)" in capsys.readouterr().out
    raw = json.load(open(tmp_path / "2026-10-03_raw.json", encoding="utf-8"))
    assert raw["errors"] == [] and raw["places"]["제주"][0]["name"] == "A"


def test_cache_requires_same_options(monkeypatch, tmp_path):
    calls = stub_pipeline(monkeypatch, lambda: FakeResponse(200, {"documents": [{"place_name": "A"}]}))
    assert travel_planner.run(make_args(cities=2)) == 0
    raw = json.load(open(tmp_path / "2026-10-03_raw.json", encoding="utf-8"))
    assert raw["options"] == {"cities": 2, "count": 5}
    assert travel_planner.run(make_args(cities=2)) == 0          # 같은 옵션 → 캐시
    assert calls["post"] == 3
    assert travel_planner.run(make_args(cities=1)) == 0          # 지역 수 다름 → 다시 호출
    assert travel_planner.run(make_args(cities=1, count=3)) == 0  # 맛집 수 다름 → 다시 호출
    assert calls["post"] == 7


def test_corrupt_cache_is_ignored(monkeypatch, tmp_path, capsys):
    (tmp_path / "2026-10-03_raw.json").write_text("{깨진 JSON", encoding="utf-8")
    stub_pipeline(monkeypatch, lambda: FakeResponse(200, {"documents": [{"place_name": "A"}]}))
    assert travel_planner.run(make_args()) == 0
    assert "읽기 실패" in capsys.readouterr().out


def test_auth_error_skips_remaining_cities(monkeypatch, tmp_path):
    calls = stub_pipeline(monkeypatch, lambda: FakeResponse(401, {}))
    assert travel_planner.run(make_args()) == 0
    raw = json.load(open(tmp_path / "2026-10-03_raw.json", encoding="utf-8"))
    assert calls["get"] == 1
    assert [e["type"] for e in raw["errors"]] == [AUTH_ERROR, AUTH_ERROR]
    assert "검색 생략 (query=강릉 맛집)" in raw["errors"][1]["message"]
    assert raw["places"] == {"제주": [], "강릉": []}


# --- 저장 실패 · 중단 · 예상하지 못한 오류 -----------------------------------------------

def test_report_save_failure_prints_report_and_exits_1(monkeypatch, tmp_path, capsys):
    stub_pipeline(monkeypatch, lambda: FakeResponse(200, {"documents": [{"place_name": "A"}]}))

    def deny(path, markdown):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(report, "save_report", deny)
    assert travel_planner.run(make_args()) == 1
    out = capsys.readouterr().out
    assert "저장하지 못해 리포트를 화면에 출력" in out and "# 2026-10-03 국내 여행 추천 리포트" in out
    assert "IO_ERROR" in out and "쓰기 권한" in out
    raw = json.load(open(tmp_path / "2026-10-03_raw.json", encoding="utf-8"))
    assert raw["errors"][-1]["type"] == "IO_ERROR"


def test_cli_summary_shows_hint(monkeypatch, capsys):
    stub_pipeline(monkeypatch, lambda: FakeResponse(401, {}))
    travel_planner.run(make_args())
    assert "→ 키 값·권한을 확인하세요" in capsys.readouterr().out


@pytest.mark.parametrize("exc, code, text", [(KeyboardInterrupt(), 130, "중단했습니다"),
                                             (RuntimeError("뜻밖"), 1, "예상하지 못한 오류")])
def test_main_handles_interrupt_and_unexpected(monkeypatch, capsys, exc, code, text):
    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(travel_planner.pipeline, "run", boom)
    monkeypatch.setattr(sys, "argv", ["travel_planner.py", "-date", "2026-10-03"])
    monkeypatch.delenv("TRAVEL_DEBUG", raising=False)
    with pytest.raises(SystemExit) as caught:
        travel_planner.main()
    assert caught.value.code == code and text in capsys.readouterr().err


# --- 1차 JSON 스키마 (필수 4키) ----------------------------------------------------

def test_recommend_keeps_required_four_keys_at_top(monkeypatch):
    monkeypatch.setattr(llm_api.requests, "post", lambda *a, **k: gemini_text(json.dumps(GOOD_RECOMMENDATION)))
    result = llm_api.recommend("2026-10-03", 2, ErrorLog(), log=lambda *_: None)
    assert list(result)[:4] == ["recommended_city", "weather", "events", "reason"]
    assert isinstance(result["events"], list) and isinstance(result["reason"], str)
    assert [c["recommended_city"] for c in result["recommended_cities"]] == ["제주", "강릉"]


@pytest.mark.parametrize("broken, why", [
    ({"weather": "w", "events": ["e"], "reason": "r"}, "필수 키 없음: recommended_city"),
    ({"recommended_city": "제주", "weather": 3, "events": ["e"], "reason": "r"}, "weather"),
    ({"recommended_city": "제주", "weather": "w", "events": "축제", "reason": "r"}, "events"),
    ({"recommended_city": "제주", "weather": "w", "events": ["e"], "reason": "r",
      "other_cities": [{"recommended_city": "강릉"}]}, "other_cities[0]"),
])
def test_recommend_validation_names_the_problem(broken, why):
    with pytest.raises(ValueError, match=re.escape(why)):
        llm_api._validate_recommendation(broken, 2)


def test_parse_strips_prose_around_json():
    text = '추천 결과입니다:\n{"recommended_city": "제주", "weather": "w", "events": ["e"], "reason": "r"}\n이상입니다.'
    assert llm_api.parse_json_text(text)["recommended_city"] == "제주"


def test_retry_prompt_carries_failure_reason(monkeypatch):
    sent = []
    replies = iter([gemini_text('{"recommended_city": "제주", "weather": "w", "events": ["e"], "reason": "r"'),   # 닫는 괄호 없음
                    gemini_text(json.dumps(GOOD_RECOMMENDATION))])
    monkeypatch.setattr(llm_api.requests, "post", lambda *a, **k: sent.append(k["json"]) or next(replies))
    llm_api.recommend("2026-10-03", 1, ErrorLog(), log=lambda *_: None)
    retry_prompt = sent[1]["contents"][0]["parts"][0]["text"]
    assert "JSON 으로 해석되지 않았습니다 —" in retry_prompt and "끝까지 닫으세요" in retry_prompt


def test_old_raw_files_are_upgraded_on_load(tmp_path):
    old = {"recommendation": {"recommended_city": "제주", "recommended_cities": [{"city": "제주", "weather": "w"}]}}
    (tmp_path / "old.json").write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    item = report.load_raw(str(tmp_path / "old.json"))["recommendation"]["recommended_cities"][0]
    assert item == {"recommended_city": "제주", "weather": "w"}

