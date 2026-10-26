"""로컬 실행기 — Vercel 없이 정적 파일과 /api/* Python 함수를 같은 포트에서 띄운다.

    python3 scripts/dev_server.py            # http://localhost:3000
    PORT=8080 python3 scripts/dev_server.py

.env 의 GEMINI_API_KEY 를 읽는다(python-dotenv 가 있으면). Vercel 배포 동작을 흉내 내는 용도이며
배포에는 포함되지 않는다(vercel.json excludeFiles).
"""

import importlib.util
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_DIR = os.path.join(ROOT, "api")

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass


def load_handler(name):
    """api/<name>.py 의 `handler` 클래스를 불러온다 (Vercel 이 하는 일과 같음)."""
    path = os.path.join(API_DIR, f"{name}.py")
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location(f"api_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "handler", None)


class DevHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def _dispatch(self, method):
        route = self.path.split("?")[0]
        if route.startswith("/api/"):
            cls = load_handler(route[len("/api/"):].strip("/"))
            if cls is None or not hasattr(cls, method):
                self.send_error(404 if cls is None else 405)
                return True
            # Vercel 처럼 요청 한 건을 그 핸들러 클래스가 처리하게 위임한다
            # (이 요청 객체의 클래스를 api 핸들러로 바꿔 그 클래스의 메서드·헬퍼를 그대로 쓴다)
            self.__class__ = cls
            getattr(self, method)()
            return True
        return False

    def do_GET(self):
        if not self._dispatch("do_GET"):
            super().do_GET()

    def do_POST(self):
        if not self._dispatch("do_POST"):
            self.send_error(405)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "3000"))
    print(f"AITAG 시연 로컬 서버: http://localhost:{port}  (GEMINI_API_KEY {'설정됨' if os.getenv('GEMINI_API_KEY') else '없음'})")
    ThreadingHTTPServer(("", port), DevHandler).serve_forever()
