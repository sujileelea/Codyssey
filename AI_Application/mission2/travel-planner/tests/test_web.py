"""웹 서버(web.py) — 실제 HTTP 로 요청하되 Gemini·Kakao 는 가짜 응답으로 바꾼다.

    python3 -m pytest tests -q
"""

import http.client
import json
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import llm_api  # noqa: E402
import net  # noqa: E402
import place_api  # noqa: E402
import web  # noqa: E402
from test_offline import GOOD_RECOMMENDATION, FakeResponse, gemini_text, good_report  # noqa: E402


@pytest.fixture
def server(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "secret-gemini")
    monkeypatch.setattr(config, "KAKAO_REST_API_KEY", "secret-kakao")
    monkeypatch.setattr(config, "KAKAO_JS_KEY", "")
    monkeypatch.setattr(config, "RESULTS_DIR", str(tmp_path))
    monkeypatch.setattr(net, "RETRY_DELAY", 0)

    def post(*a, **k):
        is_json_mode = "responseSchema" in k["json"]["generationConfig"]
        return gemini_text(json.dumps(GOOD_RECOMMENDATION, ensure_ascii=False) if is_json_mode else good_report())

    monkeypatch.setattr(llm_api.requests, "post", post)
    monkeypatch.setattr(place_api.requests, "get", lambda *a, **k: FakeResponse(200, {"documents": [
        {"place_name": "A식당", "address_name": "주소", "x": "126.5", "y": "33.5"}]}))
    monkeypatch.setattr(web.Handler, "log_message", lambda *a: None)
    httpd = web.ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def request(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(method, path, body=json.dumps(body) if body is not None else None,
                 headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    data = response.read().decode("utf-8")
    conn.close()
    return response.status, response.getheader("Content-Type"), data


def test_plan_streams_progress_then_result(server):
    status, ctype, body = request(server, "POST", "/api/plan", {"date": "2026-10-03", "cities": 2, "count": 3})
    events = [json.loads(line) for line in body.splitlines()]
    assert status == 200 and ctype.startswith("application/x-ndjson")
    assert [e["step"] for e in events if e["kind"] == "step"] == [1, 2, 3]
    result = events[-1]
    assert result["kind"] == "result" and result["ok"] and result["saved"]
    assert result["raw"]["places"]["제주"][0]["name"] == "A식당"
    assert result["markdown"].startswith("# 2026-10-03 국내 여행 추천 리포트")
    assert result["files"]["report"] == "results/2026-10-03_travel_plan.md"


@pytest.mark.parametrize("body, field", [({"date": "2026-1-5"}, "date"),
                                         ({"date": "2026-10-03", "cities": 4}, "cities"),
                                         ({"date": "2026-10-03", "cities": True}, "cities"),
                                         ({"date": "2026-10-03", "count": 99}, "count")])
def test_plan_validates_like_cli(server, body, field):
    status, _, data = request(server, "POST", "/api/plan", body)
    assert status == 400 and json.loads(data)["field"] == field


def test_plan_rejects_while_another_runs(server):
    assert web.RUN_LOCK.acquire(blocking=False)
    try:
        status, _, data = request(server, "POST", "/api/plan", {"date": "2026-10-03"})
    finally:
        web.RUN_LOCK.release()
    assert status == 409 and "만드는 중" in json.loads(data)["error"]


def test_saved_results_list_and_detail(server):
    request(server, "POST", "/api/plan", {"date": "2026-10-03", "cities": 2})
    status, _, data = request(server, "GET", "/api/results")
    listed = json.loads(data)["results"]
    assert status == 200 and listed[0]["date"] == "2026-10-03" and listed[0]["cities"] == ["제주", "강릉"]
    status, _, data = request(server, "GET", "/api/results/2026-10-03")
    detail = json.loads(data)
    assert status == 200 and detail["source"] == "saved" and detail["markdown"].startswith("# 2026-10-03")
    assert request(server, "GET", "/api/results/2026-1-5")[0] == 400
    assert request(server, "GET", "/api/results/2027-01-01")[0] == 404


def test_errors_carry_hints(server, monkeypatch):
    monkeypatch.setattr(place_api.requests, "get", lambda *a, **k: FakeResponse(401, {}))
    _, _, body = request(server, "POST", "/api/plan", {"date": "2026-11-07", "cities": 1})
    result = json.loads(body.splitlines()[-1])
    assert result["errors"][0]["type"] == "AUTH_ERROR" and "키 값" in result["errors"][0]["hint"]


def test_config_never_exposes_server_keys(server):
    status, _, data = request(server, "GET", "/api/config")
    assert status == 200 and json.loads(data)["max_count"] == 15
    assert "secret-gemini" not in data and "secret-kakao" not in data


@pytest.mark.parametrize("path", ["/static/../config.py", "/static/%2e%2e/.env", "/static/nope.js", "/nope"])
def test_static_blocks_traversal_and_unknown(server, path):
    assert request(server, "GET", path)[0] == 404


def test_stream_survives_client_disconnect():
    class Broken:
        def write(self, _):
            raise BrokenPipeError

        def flush(self):
            pass

    stream = web.EventStream(Broken())
    stream.send({"kind": "log"})
    stream.send({"kind": "log"})   # 두 번째부터는 조용히 건너뛴다
    assert stream.closed
