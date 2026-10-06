"""로컬 웹 화면 — CLI 와 같은 파이프라인을 브라우저에서 실행·조회한다 (표준 라이브러리만 사용).

    python3 web.py [--port 8000] [--host 127.0.0.1]   →   http://localhost:8000

  GET  /                     화면 (web/index.html)
  GET  /static/<파일>         CSS·JS
  GET  /api/config           기본값·지도 설정
  POST /api/plan             {date, cities, count, no_cache} → 진행 이벤트 스트림(NDJSON), 마지막 줄 = 결과
  GET  /api/results          저장된 결과 목록
  GET  /api/results/<날짜>     저장된 원본 JSON + 리포트 Markdown

조회는 GET, 새 결과를 만드는(API 를 호출하고 파일을 쓰는) 요청은 POST 로 나눴다.
"""

import argparse
import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

import config
import pipeline
import place_api
import report
import travel_planner
from errors import hint

WEB_DIR = os.path.join(config.BASE_DIR, "web")
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}
RAW_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})_raw\.json$")
MAX_BODY = 4096
DEFAULTS = {"cities": 3, "count": 5}
# 한 번에 1건만 생성한다 — 같은 날짜 파일 동시 쓰기와 무료 쿼터 낭비를 막는다
RUN_LOCK = threading.Lock()


class ApiError(Exception):
    """클라이언트에 JSON 으로 돌려줄 오류. field 가 있으면 화면이 해당 입력칸에 표시한다."""

    def __init__(self, status, message, field=None):
        super().__init__(message)
        self.status = status
        self.field = field


def parse_plan_request(body):
    """POST /api/plan 본문을 CLI 와 같은 규칙으로 검증해 pipeline.run 인자로 바꾼다."""
    try:
        data = json.loads(body or b"{}")
    except ValueError:
        raise ApiError(400, "요청 본문이 JSON 이 아닙니다")
    if not isinstance(data, dict):
        raise ApiError(400, "요청 본문은 JSON 객체여야 합니다")
    try:
        date = travel_planner.valid_date(str(data.get("date", "")))
    except argparse.ArgumentTypeError as exc:
        raise ApiError(400, str(exc), field="date")
    cities = data.get("cities", DEFAULTS["cities"])
    if isinstance(cities, bool) or cities not in (1, 2, 3):
        raise ApiError(400, "추천 지역 수는 1~3 중 하나여야 합니다", field="cities")
    try:
        count = travel_planner.valid_count(str(data.get("count", DEFAULTS["count"])))
    except argparse.ArgumentTypeError as exc:
        raise ApiError(400, str(exc), field="count")
    return {"date": date, "cities": cities, "count": count, "use_cache": not data.get("no_cache", False)}


def to_payload(raw, markdown, source, cached=False, saved=True):
    """화면에 넘길 결과 — 실행 직후든 저장 파일이든 같은 모양. 로컬 절대 경로는 넣지 않는다."""
    date = raw.get("date")
    errors = [dict(e, hint=hint(e.get("type"))) for e in raw.get("errors", [])]
    return {
        "ok": raw.get("recommendation") is not None,
        "saved": saved,
        "cached": cached,
        "source": source,
        "date": date,
        "raw": raw,
        "markdown": markdown,
        "errors": errors,
        "files": {"raw": f"results/{date}_raw.json", "report": f"results/{date}_travel_plan.md"},
    }


def list_results():
    """results/ 의 저장된 결과 요약 — 최신 여행 날짜 순."""
    items = []
    if not os.path.isdir(config.RESULTS_DIR):
        return items
    for name in os.listdir(config.RESULTS_DIR):
        match = RAW_FILE.match(name)
        if not match:
            continue
        date = match.group(1)
        try:
            raw = report.load_raw(os.path.join(config.RESULTS_DIR, name))
            recommendation = raw.get("recommendation") or {}
            places = raw.get("places") or {}
            items.append({
                "date": date,
                "generated_at": raw.get("generated_at"),
                "cities": [c.get("recommended_city") for c in recommendation.get("recommended_cities", [])],
                "places": sum(len(v) for v in places.values()),
                "errors": len(raw.get("errors", [])),
                "ok": bool(recommendation),
                "has_report": os.path.exists(report.report_path(config.RESULTS_DIR, date)),
            })
        except (OSError, ValueError, AttributeError, TypeError):
            items.append({"date": date, "broken": True})
    return sorted(items, key=lambda item: item["date"], reverse=True)


def load_result(date_text):
    """저장된 결과 1건. 날짜 형식이 틀리면 400, 없으면 404."""
    try:
        date = travel_planner.valid_date(date_text)
    except argparse.ArgumentTypeError as exc:
        raise ApiError(400, str(exc))
    raw_file = report.raw_path(config.RESULTS_DIR, date)
    if not os.path.exists(raw_file):
        raise ApiError(404, f"{date} 의 저장된 결과가 없습니다")
    try:
        raw = report.load_raw(raw_file)
    except (OSError, ValueError) as exc:
        raise ApiError(500, f"저장된 원본 JSON 을 읽지 못했습니다: {exc}")
    report_file = report.report_path(config.RESULTS_DIR, date)
    markdown = None
    if os.path.exists(report_file):
        with open(report_file, encoding="utf-8") as f:
            markdown = f.read()
    return to_payload(raw, markdown, source="saved")


class EventStream:
    """NDJSON 한 줄씩 보낸다. 브라우저가 연결을 끊어도 파이프라인은 끝까지 돌아 결과를 저장한다."""

    def __init__(self, wfile):
        self.wfile = wfile
        self.closed = False

    def send(self, event):
        if self.closed:
            return
        try:
            self.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.closed = True


class Handler(BaseHTTPRequestHandler):
    server_version = "TravelPlanner/1.0"

    # --- 응답 도우미 ---------------------------------------------------------

    def _send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status, data):
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, exc):
        self._json(exc.status, {"error": str(exc), "field": exc.field})

    def log_message(self, fmt, *args):   # 접근 로그를 짧게
        sys.stderr.write(f"[web] {fmt % args}\n")

    # --- 라우팅 ---------------------------------------------------------------

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        try:
            if path == "/":
                return self._static("index.html")
            if path.startswith("/static/"):
                return self._static(path[len("/static/"):])
            if path == "/api/config":
                return self._json(200, {
                    "model": config.GEMINI_MODEL,
                    "defaults": DEFAULTS,
                    "max_count": place_api.MAX_SIZE,
                    # JavaScript 키는 브라우저용 공개 키(등록한 도메인에서만 동작). REST·Gemini 키는 절대 내보내지 않는다
                    "kakao_js_key": config.KAKAO_JS_KEY or None,
                })
            if path == "/api/results":
                return self._json(200, {"results": list_results()})
            if path.startswith("/api/results/"):
                return self._json(200, load_result(path[len("/api/results/"):]))
            raise ApiError(404, "없는 주소입니다")
        except ApiError as exc:
            self._error(exc)

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/plan":
            return self._error(ApiError(404, "없는 주소입니다"))
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ApiError(413, "요청 본문이 너무 큽니다")
            params = parse_plan_request(self.rfile.read(length))
        except ValueError:
            return self._error(ApiError(400, "Content-Length 가 올바르지 않습니다"))
        except ApiError as exc:
            return self._error(exc)
        if not RUN_LOCK.acquire(blocking=False):
            return self._error(ApiError(409, "다른 추천을 만드는 중입니다. 끝난 뒤 다시 시도하세요"))
        try:
            self._stream_plan(params)
        finally:
            RUN_LOCK.release()

    def _stream_plan(self, params):
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        stream = EventStream(self.wfile)
        try:
            result = pipeline.run(params["date"], params["cities"], params["count"],
                                  use_cache=params["use_cache"], emit=stream.send)
            stream.send(dict(kind="result", **to_payload(result["raw"], result["markdown"], source="run",
                                                         cached=result["cached"], saved=result["saved"])))
        except Exception as exc:   # 예상하지 못한 오류 — 화면에 요약을 보내고 서버는 계속 동작
            self.log_error("plan 실패: %s: %s", type(exc).__name__, exc)
            stream.send({"kind": "fatal", "text": f"예상하지 못한 오류: {type(exc).__name__}: {exc}"})

    def _static(self, name):
        # web/ 바로 아래의 허용된 확장자 파일만 — ../ 같은 경로 이동을 막는다
        ext = os.path.splitext(name)[1]
        full = os.path.normpath(os.path.join(WEB_DIR, name))
        if os.path.dirname(full) != WEB_DIR or ext not in STATIC_TYPES or not os.path.isfile(full):
            raise ApiError(404, "없는 파일입니다")
        with open(full, "rb") as f:
            self._send(200, f.read(), STATIC_TYPES[ext])


def build_parser():
    parser = argparse.ArgumentParser(prog="web.py", description="여행 추천 웹 화면을 로컬에서 띄운다.")
    parser.add_argument("--host", default="127.0.0.1", help="기본 127.0.0.1 — 이 컴퓨터에서만 접속")
    parser.add_argument("--port", type=int, default=8000, help="기본 8000")
    return parser


def main():
    args = build_parser().parse_args()
    config.require_keys()   # CLI 와 같은 정책 — 키가 없으면 안내 후 종료
    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        print(f"서버를 열 수 없습니다 ({args.host}:{args.port}) — {exc.strerror or exc}\n"
              f"다른 포트로 실행: python3 web.py --port {args.port + 1}", file=sys.stderr)
        sys.exit(1)
    local = args.host in ("127.0.0.1", "localhost", "::1")
    url = f"http://localhost:{args.port}" if local else f"http://{args.host}:{args.port}"
    print(f"여행 추천 웹 화면: {url}   (종료: Ctrl+C)")
    if not local:
        print("  주의: 이 컴퓨터 밖에서도 접속할 수 있습니다 — 누구나 내 API 키로 호출하게 됩니다")
    if config.KAKAO_JS_KEY:
        print(f"  지도: 카카오 지도 (카카오 콘솔 → 플랫폼 → Web 에 {url} 등록 필요, 실패 시 OpenStreetMap)")
    else:
        print("  지도: OpenStreetMap (카카오 지도를 쓰려면 .env 에 KAKAO_JS_KEY)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n웹 서버를 종료했습니다.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
