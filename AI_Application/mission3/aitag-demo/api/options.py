"""GET /api/options — 프롬프트 매트릭스 선택지를 돌려준다 (프론트 select 초기화용).

파일 기반 Vercel Python 함수: `handler` 클래스가 진입점이다.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _lib import options  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(options(), ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # Vercel 로그 소음 줄이기
        pass
