"""네트워크 없이 오류 처리 경로를 검증한다 — requests 를 가짜 응답으로 바꾼다.

    python3 -m pytest tests -q
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import llm_api  # noqa: E402
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


GOOD_RECOMMENDATION = {"recommended_cities": [
    {"city": "제주", "weather": "온화", "events": ["유채꽃 축제"], "reason": "봄꽃."},
    {"city": "강릉", "weather": "선선", "events": ["커피축제"], "reason": "바다."},
]}


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
    assert [c["city"] for c in result["recommended_cities"]] == ["제주", "강릉"]
    # 재시도로 복구됐어도 첫 실패는 errors 에 남는다
    assert [(e["step"], e["type"]) for e in errors] == [("recommend", PARSE_ERROR)]
    assert errors.items[0]["message"].startswith("시도 1:")


def test_recommend_rejects_empty_events_then_retries(monkeypatch):
    empty = {"recommended_cities": [{"city": "제주", "weather": "온화", "events": [], "reason": "봄꽃."}]}
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
    events = sent[0]["generationConfig"]["responseSchema"]["properties"]["recommended_cities"]["items"]["properties"]["events"]
    assert (events["minItems"], events["maxItems"]) == (1, 3)


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
    rec = {"recommended_cities": [{"city": "제주"}, {"city": "강릉"}]}
    places = {"제주": [{"name": "A"}], "강릉": []}
    with pytest.raises(ValueError, match="데이터 없음"):
        llm_api.check_report(good_report(), "2026-10-03", rec, places)
    llm_api.check_report(good_report(no_places=True), "2026-10-03", rec, places)


def test_report_drops_llm_written_errors_section(monkeypatch):
    text = good_report() + "\n\n## 오류 요약(errors)\n- 지어낸 오류"
    monkeypatch.setattr(llm_api.requests, "post", lambda *a, **k: gemini_text(text))
    rec = {"recommended_cities": [{"city": "제주"}, {"city": "강릉"}]}
    md = llm_api.write_report("2026-10-03", rec, {"제주": [{"name": "A"}], "강릉": [{"name": "B"}]})
    assert "오류 요약" not in md
