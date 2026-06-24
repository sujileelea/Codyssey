# 공고 분석 챗봇 (Announcement Analyzer Chatbot)

공고(모집요강) **URL을 입력하면 포스터 이미지와 문안을 분석**해 핵심 정보를 구조화하고,
그 내용에 **근거(grounding)** 해서 챗봇과 문답을 주고받는 웹 서비스입니다.
제목·장소·날짜·참여조건·상금·주관기관 등을 질문으로 받아 답합니다.

## 구성

```
app/
├── main.py            # FastAPI 백엔드 (URL 분석 + 챗봇)
├── static/index.html  # 웹 UI (단일 페이지)
├── requirements.txt
├── .env.example       # 모델/엔드포인트 설정 예시
└── README.md
```

## 동작 방식

1. **분석** — 입력한 URL의 HTML을 서버가 가져와 본문 텍스트와 포스터 이미지(og:image 우선)를 추출합니다.
2. **구조화** — 본문 + 포스터 이미지를 Vision LLM에 보내 핵심 항목을 JSON으로 추출합니다.
   자료에 없는 항목은 지어내지 않고 `"정보 없음"` 으로 표시합니다(환각 안전장치).
3. **문답** — 추출된 컨텍스트에만 근거해 질문에 답합니다. 컨텍스트에 없으면
   "공고에서 확인되지 않습니다"라고 답하고 확인처를 제안합니다.

## 모델 설정 (Gemma 4 E4B / Llama 4 Scout / Qwen 3.6)

LLM 호출은 **OpenAI 호환 Chat Completions** 규격을 사용하므로
Ollama(로컬)·OpenRouter·vLLM·LM Studio 등과 모두 연동됩니다.
`.env` 에서 모델 3종의 `BASE_URL / MODEL / API_KEY` 를 바꿔 끼우면 UI 드롭다운으로 전환됩니다.

## 실행 방법

```bash
cd app
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # 값 채우기

# (Ollama 사용 시) 멀티모달 모델 준비
#   ollama serve
#   ollama pull gemma3:27b   등

uvicorn main:app --reload --port 8000
```

브라우저에서 http://localhost:8000 접속 → 공고 URL 입력 → 분석 → 질문.

## API

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/api/models` | 설정된 모델 목록 |
| POST | `/api/analyze` | `{url, model_key}` → 포스터/구조화 필드/컨텍스트 |
| POST | `/api/chat` | `{messages, context, model_key}` → 답변 |

## 주의

- 일부 공고 사이트는 로그인/자바스크립트 렌더링이 필요해 정적 HTML 추출이 제한될 수 있습니다.
  그 경우 포스터/본문 일부만 추출되며, 챗봇은 추출된 범위 안에서만 답합니다.
- 개인정보(실명·연락처 등)는 입력/로그에 포함하지 마세요.
