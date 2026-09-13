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
    {"city": "강릉", "weather": "선선", "events": [], "reason": "바다."},
]}


@pytest.fixture(autouse=True)
def keys(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test")
    monkeypatch.setattr(config, "KAKAO_REST_API_KEY", "test")
    monkeypatch.setattr(config, "RESULTS_DIR", str(tmp_path))


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
    result = llm_api.recommend("2026-10-03", 2, log=lambda *_: None)
    assert len(calls) == 2
    assert "다시 출력" in calls[1]["contents"][0]["parts"][0]["text"]
    assert result["recommended_city"] == "제주" and result["events"] == ["유채꽃 축제"]
    assert [c["city"] for c in result["recommended_cities"]] == ["제주", "강릉"]


def test_recommend_gives_up_after_two_failures(monkeypatch):
    monkeypatch.setattr(llm_api.requests, "post", lambda *a, **k: gemini_text("{\"recommended_cities\": []}"))
    with pytest.raises(llm_api.LLMError) as exc:
        llm_api.recommend("2026-10-03", 2, log=lambda *_: None)
    assert exc.value.error_type == PARSE_ERROR


def test_recommend_strips_code_fence(monkeypatch):
    fenced = "```json\n" + json.dumps(GOOD_RECOMMENDATION, ensure_ascii=False) + "\n```"
    monkeypatch.setattr(llm_api.requests, "post", lambda *a, **k: gemini_text(fenced))
    assert llm_api.recommend("2026-10-03", 1, log=lambda *_: None)["recommended_city"] == "제주"


def test_gemini_invalid_key_is_auth_error(monkeypatch):
    monkeypatch.setattr(llm_api.requests, "post",
                        lambda *a, **k: FakeResponse(400, {"error": {"message": "API key not valid."}}))
    with pytest.raises(llm_api.LLMError) as exc:
        llm_api.recommend("2026-10-03", 1, log=lambda *_: None)
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
        return gemini_text(json.dumps(GOOD_RECOMMENDATION, ensure_ascii=False) if is_json_mode else "# 리포트")

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
