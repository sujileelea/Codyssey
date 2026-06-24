"""
공고 분석 챗봇 — FastAPI 백엔드
------------------------------------------------------------
기능
1) /api/analyze : 공고 URL을 받아 본문 텍스트 + 포스터 이미지를 추출하고,
   Vision LLM으로 핵심 항목(제목/장소/날짜/참여조건/상금/주관기관 등)을 구조화한다.
2) /api/chat    : 추출된 공고 컨텍스트에 근거(grounding)해 사용자의 질문에 답한다.
   컨텍스트에 없는 내용은 지어내지 않고 "확인되지 않음"으로 답하는 환각 안전장치를 둔다.
3) 3개 모델(Gemma 4 E4B / Llama 4 Scout / Qwen 3.6)을 .env 설정으로 전환 가능.

설계 메모
- LLM 호출은 OpenAI 호환 Chat Completions 규격(/v1/chat/completions)을 사용한다.
  → Ollama(로컬), OpenRouter, vLLM, LM Studio 등 대부분의 서빙 백엔드와 호환된다.
- 멀티모달(Vision)은 messages content 배열에 image_url(base64 data URI)를 넣는 방식.
"""

import base64
import json
import os
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
MAX_TEXT_CHARS = int(os.getenv("MAX_TEXT_CHARS", "8000"))
# 출력 토큰 상한. 미지정 시 일부 제공자(OpenRouter)가 모델 최대치를 통째로
# 예약해 402(크레딧 부족)가 날 수 있어 합리적 상한을 둔다.
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "2048"))
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# 본문 포스터가 아닌 장식용 이미지(로고/아이콘/SNS 등)를 거르기 위한 힌트
SKIP_IMG_HINTS = (
    "logo", "icon", "sprite", "avatar", "favicon", "blank", "spacer",
    "pixel", "button", "badge", "share", "sns", "footer", "header",
)


# ---------------------------------------------------------------------------
# 모델 설정: .env 로 base_url / model / api_key 를 바꿔 끼운다.
# ---------------------------------------------------------------------------
def _model_cfg(idx: int, default_label: str, default_model: str) -> dict:
    return {
        "key": f"model{idx}",
        "label": os.getenv(f"MODEL{idx}_LABEL", default_label),
        "base_url": os.getenv(f"MODEL{idx}_BASE_URL", "http://localhost:11434/v1"),
        "model": os.getenv(f"MODEL{idx}_MODEL", default_model),
        "api_key": os.getenv(f"MODEL{idx}_API_KEY", "ollama"),
    }


MODELS = {
    cfg["key"]: cfg
    for cfg in (
        _model_cfg(1, "Gemma 4 E4B (31B)", "gemma3:27b"),
        _model_cfg(2, "Llama 4 Scout", "llama4:scout"),
        _model_cfg(3, "Qwen 3.6", "qwen2.5vl:32b"),
    )
}
DEFAULT_MODEL_KEY = os.getenv("DEFAULT_MODEL_KEY", "model1")


# ---------------------------------------------------------------------------
# 프롬프트
# ---------------------------------------------------------------------------
EXTRACT_FIELDS = [
    "제목",
    "주관기관",
    "주최/주관/후원",
    "일정/날짜",
    "장소",
    "참여 대상/조건",
    "상금/시상 내역",
    "접수/신청 방법",
    "접수 마감일",
    "문의처",
    "기타 핵심사항",
]

EXTRACT_SYSTEM_PROMPT = (
    "당신은 한국어 공고/모집요강을 분석하는 정보추출 전문가입니다.\n"
    "주어진 공고 본문 텍스트와 포스터 이미지를 함께 분석하여, 아래 항목을 JSON으로만 출력하세요.\n"
    f"항목(키): {', '.join(EXTRACT_FIELDS)}\n\n"
    "규칙:\n"
    "1) 본문/이미지에서 '확인 가능한 사실'만 적습니다. 추측하거나 지어내지 마세요.\n"
    "2) 해당 정보가 자료에 없으면 값으로 정확히 \"정보 없음\"을 적습니다.\n"
    "3) 날짜·금액·조건은 원문 표기를 그대로 옮깁니다(임의 환산/요약 금지).\n"
    "4) 출력은 설명 없이 순수 JSON 객체 하나만. 코드블록 표시도 쓰지 마세요.\n"
)

CHAT_SYSTEM_PROMPT_TEMPLATE = (
    "당신은 '공고 분석 도우미'입니다. 역할은 사용자가 올린 하나의 공고에 대해 정확하게 답하는 것입니다.\n\n"
    "[페르소나]\n"
    "- 말투: 간결하고 정중한 존댓말. 핵심부터 답합니다.\n"
    "- 우선순위: 친절함보다 '정확성'이 항상 우선입니다.\n\n"
    "[답변 규칙]\n"
    "1) 아래 <공고 컨텍스트>에 근거해서만 답합니다. 컨텍스트 밖 지식으로 사실을 만들지 않습니다.\n"
    "2) 컨텍스트에 없거나 불명확하면 '공고에서 확인되지 않습니다'라고 명시하고, "
    "어디서 확인하면 되는지(예: 주최측 문의처/원문 링크)를 제안합니다.\n"
    "3) 날짜·금액·참여조건 등 수치/사실은 원문 표기를 그대로 인용합니다. 임의 계산/환산 금지.\n"
    "4) 답변은 핵심 위주로 짧게. 필요 시 항목명을 함께 제시합니다(예: '장소: ...').\n"
    "5) 질문의 전제가 모호하면 임의로 단정하지 말고 한 번 되물어 확인합니다.\n\n"
    "<공고 컨텍스트>\n"
    "{context}\n"
    "</공고 컨텍스트>\n"
)


# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------
def fetch_html(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding
    return resp.text


def extract_main_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    cleaned = "\n".join(lines)
    return cleaned[:MAX_TEXT_CHARS]


def find_poster_url(soup: BeautifulSoup, page_url: str) -> Optional[str]:
    # 1) Open Graph / Twitter 이미지 우선 (공고/기사 페이지 대부분이 대표 이미지로 지정)
    for prop in ("og:image", "twitter:image", "og:image:url"):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            return urljoin(page_url, tag["content"])
    # 2) 메타태그가 없으면 본문 <img> 중 대표 이미지를 추정한다.
    #    - 로고/아이콘/SNS 등 장식 이미지는 키워드로 제외
    #    - svg/gif 및 작은 이미지(선언 크기 100px 미만)는 제외
    #    - 선언된 크기가 클수록 우선, 동점이면 먼저 나온(보통 본문) 이미지를 유지
    best = None
    best_score = -1
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original")
        if not src or src.startswith("data:"):
            continue
        hay = " ".join(
            str(img.get(attr, "")) for attr in ("src", "class", "id", "alt")
        ).lower()
        if any(hint in hay for hint in SKIP_IMG_HINTS):
            continue
        if src.lower().split("?")[0].endswith((".svg", ".gif")):
            continue
        try:
            w = int(img.get("width", 0))
            h = int(img.get("height", 0))
        except (TypeError, ValueError):
            w = h = 0
        if (w and w < 100) or (h and h < 100):
            continue
        score = w * h
        if score > best_score:
            best_score = score
            best = urljoin(page_url, src)
    return best


def image_to_data_uri(img_url: str) -> Optional[str]:
    try:
        resp = requests.get(
            img_url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
        if "image" not in content_type:
            return None
        b64 = base64.b64encode(resp.content).decode("utf-8")
        return f"data:{content_type};base64,{b64}"
    except requests.RequestException:
        return None


_REASONING_RE = re.compile(
    r"<(thought|think|reasoning)>.*?</\1>", re.DOTALL | re.IGNORECASE
)


def strip_reasoning(text: str) -> str:
    """일부 모델(예: Gemma 4)이 답변 앞에 붙이는 <thought>...</thought> 추론 블록을 제거한다."""
    out = _REASONING_RE.sub("", text)
    # 균형이 맞지 않는(잘린) 추론 태그 잔여물 정리
    out = re.sub(
        r"^.*?</(?:thought|think|reasoning)>", "", out, flags=re.DOTALL | re.IGNORECASE
    )
    out = re.sub(
        r"<(?:thought|think|reasoning)>.*$", "", out, flags=re.DOTALL | re.IGNORECASE
    )
    return out.strip()


def call_llm(model_key: str, messages: list, temperature: float = 0.2) -> str:
    cfg = MODELS.get(model_key) or MODELS[DEFAULT_MODEL_KEY]
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if cfg["api_key"]:
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": MAX_OUTPUT_TOKENS,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return strip_reasoning(data["choices"][0]["message"]["content"])


def build_vision_user_content(text: str, poster_data_uri: Optional[str]) -> list:
    content = [
        {
            "type": "text",
            "text": "다음은 공고 페이지에서 추출한 본문 텍스트입니다.\n\n" + text,
        }
    ]
    if poster_data_uri:
        content.append(
            {"type": "image_url", "image_url": {"url": poster_data_uri}}
        )
    return content


def safe_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1:
        raw = raw[start : end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_parse_error": True, "_raw": raw}


# ---------------------------------------------------------------------------
# 스키마
# ---------------------------------------------------------------------------
class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    url: str
    model_key: str = DEFAULT_MODEL_KEY


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    messages: list[ChatMessage]
    context: str
    model_key: str = DEFAULT_MODEL_KEY


# ---------------------------------------------------------------------------
# 앱
# ---------------------------------------------------------------------------
app = FastAPI(title="공고 분석 챗봇")


@app.get("/api/models")
def list_models():
    return {
        "default": DEFAULT_MODEL_KEY,
        "models": [{"key": k, "label": v["label"]} for k, v in MODELS.items()],
    }


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    parsed = urlparse(req.url)
    if parsed.scheme not in ("http", "https"):
        return {"ok": False, "error": "http/https URL을 입력하세요."}

    try:
        html = fetch_html(req.url)
    except requests.RequestException as e:
        return {"ok": False, "error": f"페이지를 가져오지 못했습니다: {e}"}

    soup = BeautifulSoup(html, "html.parser")
    text = extract_main_text(soup)
    poster_url = find_poster_url(soup, req.url)
    poster_data_uri = image_to_data_uri(poster_url) if poster_url else None

    messages = [
        {"role": "system", "content": EXTRACT_SYSTEM_PROMPT},
        {"role": "user", "content": build_vision_user_content(text, poster_data_uri)},
    ]
    try:
        raw = call_llm(req.model_key, messages, temperature=0.1)
    except requests.RequestException as e:
        return {"ok": False, "error": f"모델 호출 실패: {e}", "poster_url": poster_url}

    fields = safe_json(raw)

    # 챗봇이 근거로 쓸 컨텍스트(구조화 결과 + 본문 일부)
    context = "■ 구조화된 핵심 정보(JSON)\n" + json.dumps(
        fields, ensure_ascii=False, indent=2
    ) + "\n\n■ 공고 본문(발췌)\n" + text[:4000]

    return {
        "ok": True,
        "poster_url": poster_url,
        "poster_data_uri": poster_data_uri,
        "fields": fields,
        "context": context,
        "source_url": req.url,
    }


@app.post("/api/chat")
def chat(req: ChatRequest):
    system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(context=req.context)
    messages = [{"role": "system", "content": system_prompt}]
    for m in req.messages:
        messages.append({"role": m.role, "content": m.content})
    try:
        answer = call_llm(req.model_key, messages, temperature=0.2)
    except requests.RequestException as e:
        return {"ok": False, "error": f"모델 호출 실패: {e}"}
    return {"ok": True, "answer": answer}


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
