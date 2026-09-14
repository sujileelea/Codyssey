"""네트워크 없이 /api 함수의 입력 검증·오류 처리·프롬프트 합성을 검사한다.

    python3 -m pytest tests -q
"""

import base64
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api"))

import _lib  # noqa: E402
import alt_text  # noqa: E402

PNG_1PX = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")


def body(**over):
    data = {"image": base64.b64encode(PNG_1PX).decode(), "mime": "image/png", "matrix": {"domain": "press"}}
    data.update(over)
    return json.dumps(data).encode()


class FakeResp:
    def __init__(self, status, payload=None, text=""):
        self.status_code, self._payload, self.text = status, payload, text or json.dumps(payload or {})

    def json(self):
        if self._payload is None:
            raise ValueError
        return self._payload


def gemini_ok(result):
    return FakeResp(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(result, ensure_ascii=False)}]}}]})


# --- 매트릭스 라이브러리 ---

def test_options_has_all_axes_and_defaults():
    opt = _lib.options()
    for axis in ("domain", "content_type", "image_kind", "category", "tone", "length", "language"):
        assert opt[axis] and {"key", "label"} <= set(opt[axis][0])
        assert opt["defaults"][axis] in {o["key"] for o in opt[axis]}


def test_normalize_replaces_unknown_values():
    sel, replaced = _lib.normalize({"domain": "press", "tone": "shouting", "category": ""})
    assert sel["domain"] == "press" and sel["tone"] == "plain" and sel["category"] == "general"
    assert replaced == ["tone=shouting→plain"]


def test_compose_prompt_blocks_follow_selection():
    sel, _ = _lib.normalize({"domain": "ecommerce", "image_kind": "poster", "category": "food", "tone": "formal"})
    prompt, blocks = _lib.compose_prompt(sel, "가을 신상품")
    assert blocks[0] == "공통 접근성 규칙" and "요청 컨텍스트" in blocks and blocks[-1] == "출력 형식"
    assert "알레르기" in prompt and "포스터" in prompt and "격식" in prompt and "가을 신상품" in prompt
    assert _lib.matrix_key(sel) == "ecommerce.product.poster.food.formal"


# --- 입력 검증 (400/413) ---

@pytest.mark.parametrize("raw, code", [
    (b"not json", "BAD_JSON"),
    (b"[]", "BAD_JSON"),
    (json.dumps({"image": ""}).encode(), "EMPTY_IMAGE"),
    (json.dumps({"image": "@@@"}).encode(), "BAD_IMAGE"),
    (body(mime="image/tiff"), "BAD_MIME"),
])
def test_bad_requests(raw, code):
    with pytest.raises(alt_text.ApiError) as exc:
        alt_text.generate(raw, "key")
    assert exc.value.code == code and exc.value.status == 400


def test_image_too_large():
    big = base64.b64encode(b"\0" * (alt_text.MAX_IMAGE_BYTES + 1)).decode()
    with pytest.raises(alt_text.ApiError) as exc:
        alt_text.generate(json.dumps({"image": big}).encode(), "key")
    assert exc.value.status == 413


def test_data_url_prefix_is_stripped(monkeypatch):
    monkeypatch.setattr(alt_text.requests, "post", lambda *a, **k: gemini_ok({"alt_text": "x", "long_description": "", "detected_text": "", "is_decorative": False}))
    out = alt_text.generate(body(image="data:image/png;base64," + base64.b64encode(PNG_1PX).decode()), "key")
    assert out["alt_text"] == "x"


def test_missing_key_is_500():
    with pytest.raises(alt_text.ApiError) as exc:
        alt_text.generate(body(), "")
    assert exc.value.status == 500 and exc.value.code == "NO_API_KEY"


# --- 상류(Gemini) 오류 매핑 ---

def test_upstream_timeout_504(monkeypatch):
    def boom(*a, **k):
        raise alt_text.requests.Timeout()
    monkeypatch.setattr(alt_text.requests, "post", boom)
    with pytest.raises(alt_text.ApiError) as exc:
        alt_text.generate(body(), "key")
    assert exc.value.status == 504


def test_upstream_429(monkeypatch):
    monkeypatch.setattr(alt_text.requests, "post", lambda *a, **k: FakeResp(429, {"error": {"message": "quota"}}))
    with pytest.raises(alt_text.ApiError) as exc:
        alt_text.generate(body(), "key")
    assert exc.value.status == 429 and exc.value.code == "RATE_LIMITED"


def test_upstream_bad_json_502(monkeypatch):
    monkeypatch.setattr(alt_text.requests, "post", lambda *a, **k: FakeResp(200, {"candidates": [{"content": {"parts": [{"text": "not json"}]}}]}))
    with pytest.raises(alt_text.ApiError) as exc:
        alt_text.generate(body(), "key")
    assert exc.value.code == "UPSTREAM_PARSE"


# --- 정상 경로: 요청 본문 구성과 응답 모양 ---

def test_success_payload_and_request_shape(monkeypatch):
    sent = {}

    def post(url, json=None, timeout=None, headers=None):
        sent.update(url=url, body=json, headers=headers)
        return gemini_ok({"alt_text": "빨간 사과 세 개", "long_description": "", "detected_text": "", "is_decorative": False})
    monkeypatch.setattr(alt_text.requests, "post", post)
    out = alt_text.generate(body(matrix={"domain": "ecommerce", "category": "food"}, context="과일 코너"), "key")

    parts = sent["body"]["contents"][0]["parts"]
    assert parts[1]["inline_data"]["mime_type"] == "image/png"
    assert sent["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert sent["headers"]["x-goog-api-key"] == "key" and "key" not in sent["url"]
    assert out["alt_text"] == "빨간 사과 세 개" and out["matrix_key"] == "ecommerce.product.photo.food.plain"
    assert "알레르기" in out["prompt"] and "과일 코너" in out["prompt"] and out["replaced"] == []
