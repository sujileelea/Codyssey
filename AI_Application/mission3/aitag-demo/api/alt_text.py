"""POST /api/alt_text — 사진 + 프롬프트 매트릭스 → Gemini → 대체텍스트 JSON.

요청(JSON): {"image": "<base64>", "mime": "image/jpeg", "matrix": {...}, "context": "..."}
응답(JSON): {"alt_text", "long_description", "detected_text", "is_decorative",
             "matrix_key", "blocks", "prompt", "model", "elapsed_ms"}
오류: 400(입력 누락·형식) · 413(이미지 너무 큼) · 500(키 미설정) · 502(AI 응답 오류) · 504(AI 지연) · 429(한도)
"""

import base64
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _lib import OUTPUT_SCHEMA, compose_prompt, matrix_key, normalize  # noqa: E402

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
UPSTREAM_TIMEOUT = float(os.getenv("UPSTREAM_TIMEOUT", "25"))   # 초 — 프론트 타임아웃(30초)보다 짧게
MAX_IMAGE_BYTES = 4 * 1024 * 1024                              # Vercel 요청 본문 한도(4.5MB) 안
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def parse_request(raw):
    """본문을 검사해 (이미지 bytes, mime, 매트릭스, 컨텍스트) 를 돌려준다."""
    try:
        data = json.loads(raw or b"{}")
    except ValueError:
        raise ApiError(400, "BAD_JSON", "요청 본문이 JSON 이 아닙니다.")
    if not isinstance(data, dict):
        raise ApiError(400, "BAD_JSON", "요청 본문은 JSON 객체여야 합니다.")
    image = str(data.get("image") or "")
    if not image:
        raise ApiError(400, "EMPTY_IMAGE", "사진을 올려 주세요. 대체텍스트를 만들 이미지가 없습니다.")
    if "," in image[:64] and image.startswith("data:"):
        image = image.split(",", 1)[1]      # data URL 접두 제거
    try:
        image_bytes = base64.b64decode(image, validate=True)
    except Exception:
        raise ApiError(400, "BAD_IMAGE", "이미지 데이터를 읽을 수 없습니다. 다른 파일로 다시 시도해 주세요.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ApiError(413, "IMAGE_TOO_LARGE", "이미지가 너무 큽니다(4MB 초과). 더 작은 사진으로 시도해 주세요.")
    mime = str(data.get("mime") or "image/jpeg").lower()
    if mime not in ALLOWED_MIME:
        raise ApiError(400, "BAD_MIME", "JPEG·PNG·WebP·GIF 이미지만 지원합니다.")
    return image_bytes, mime, data.get("matrix") or {}, str(data.get("context") or "")


def call_gemini(api_key, prompt, image_b64, mime):
    """Gemini generateContent 를 호출해 파싱된 JSON 을 돌려준다."""
    body = {
        "contents": [{"role": "user", "parts": [
            {"text": prompt},
            {"inline_data": {"mime_type": mime, "data": image_b64}},
        ]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "responseSchema": OUTPUT_SCHEMA,
        },
    }
    try:
        resp = requests.post(GEMINI_URL.format(model=MODEL), json=body, timeout=UPSTREAM_TIMEOUT,
                             headers={"x-goog-api-key": api_key, "Content-Type": "application/json"})
    except requests.Timeout:
        raise ApiError(504, "UPSTREAM_TIMEOUT", "AI 응답이 늦어지고 있습니다. 잠시 후 다시 시도해 주세요.")
    except requests.RequestException as exc:
        raise ApiError(502, "UPSTREAM_NETWORK", f"AI 서버에 연결하지 못했습니다({type(exc).__name__}).")
    if resp.status_code == 429:
        raise ApiError(429, "RATE_LIMITED", "지금 요청이 많습니다. 1분 뒤 다시 시도해 주세요.")
    if resp.status_code != 200:
        try:
            detail = resp.json()["error"]["message"]
        except Exception:
            detail = resp.text[:120]
        raise ApiError(502, "UPSTREAM_ERROR", f"AI 서버 오류(HTTP {resp.status_code}): {detail}")
    try:
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except (ValueError, KeyError, IndexError, TypeError):
        raise ApiError(502, "UPSTREAM_PARSE", "AI 응답을 해석하지 못했습니다. 다시 시도해 주세요.")


def generate(raw_body, api_key):
    """요청 본문 → 응답 딕셔너리. 테스트에서 직접 호출한다."""
    if not api_key:
        raise ApiError(500, "NO_API_KEY", "서버에 GEMINI_API_KEY 가 설정되지 않았습니다. 운영자에게 문의하세요.")
    image_bytes, mime, matrix, context = parse_request(raw_body)
    sel, replaced = normalize(matrix)
    prompt, blocks = compose_prompt(sel, context)
    started = time.time()
    result = call_gemini(api_key, prompt, base64.b64encode(image_bytes).decode("ascii"), mime)
    return {
        "alt_text": str(result.get("alt_text", "")).strip(),
        "long_description": str(result.get("long_description", "")).strip(),
        "detected_text": str(result.get("detected_text", "")).strip(),
        "is_decorative": bool(result.get("is_decorative", False)),
        "matrix": sel,
        "matrix_key": matrix_key(sel),
        "replaced": replaced,
        "blocks": blocks,
        "prompt": prompt,
        "model": MODEL,
        "elapsed_ms": int((time.time() - started) * 1000),
    }


class handler(BaseHTTPRequestHandler):
    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            self._json(200, generate(raw, os.getenv("GEMINI_API_KEY", "").strip()))
        except ApiError as exc:
            self._json(exc.status, {"error": exc.code, "message": exc.message})
        except Exception as exc:  # 예상 못 한 오류도 JSON 으로
            self._json(500, {"error": "INTERNAL", "message": f"서버 내부 오류({type(exc).__name__})."})

    def do_GET(self):
        self._json(405, {"error": "METHOD_NOT_ALLOWED", "message": "POST 로 이미지를 보내 주세요."})

    def log_message(self, *args):
        pass
