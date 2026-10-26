# AITAG 시연 — 사진 + 프롬프트 매트릭스 → 대체텍스트

- 사진을 올리고 **분야·콘텐츠 유형·이미지 유형·카테고리·톤** 다섯 축(프롬프트 매트릭스)을 고르면, 축별 프롬프트 블록을 합성해 AI(Gemini)가 스크린리더용 **대체텍스트(alt text)** 를 만들어 주는 웹 서비스
- 프론트는 순수 HTML/CSS/JavaScript, 백엔드는 Vercel Serverless Functions(Python), 프레임워크 없음
- Codyssey AI_Application 미션3 산출물 · **배포 URL: <https://aitag-demo-gamma.vercel.app>** (Vercel 프로젝트 `aitag-demo`)

```text
[브라우저]  사진 선택 → 캔버스 축소(1,600px) → base64
   │  fetch GET  /api/options      ← 매트릭스 선택지(축·기본값)
   │  fetch POST /api/alt_text     → {image, mime, matrix, context}
   ▼
[Vercel Python]  api/alt_text.py  검증(400/413) → 블록 합성(_lib.py) → Gemini generateContent(이미지+프롬프트, JSON 스키마)
   │                                  ↳ 504 지연 · 429 한도 · 502 상류 오류 · 500 키 미설정
   ▼
[브라우저]  alt_text · 보충 설명 · 감지 텍스트 · 장식 여부 · 매트릭스 키 · 사용 블록 · 실제 프롬프트 표시
```

## 페이지

| 페이지 | 파일 | 내용 |
| --- | --- | --- |
| 홈 | `index.html` | 서비스 소개 · 왜 매트릭스인가 · 동작 흐름 |
| 시연 | `demo.html` | 사진 업로드(드래그·붙여넣기·샘플 3종) · 매트릭스 7개 선택 · 컨텍스트 · 결과 카드 |
| 프롬프트 매트릭스 | `matrix.html` | 축별 선택지 표(`/api/options` 실시간) · 합성 순서 · 예시 조합 → 시연 프리셋 |
| FAQ | `faq.html` | 대체텍스트·저장 여부·오류 안내·기술 스택 |

- 상단 내비게이션으로 이동, 모바일에서는 ☰ 메뉴. 🌙/☀️ 다크 모드 토글(기기 설정 → 저장값 순, 보너스)
- 방문자 분석: Vercel Web Analytics 스크립트(`/_vercel/insights/script.js`) — 프로젝트 대시보드에서 Analytics 를 켜면 집계됨(보너스)

## 기술 스택

| 층 | 기술 | 비고 |
| --- | --- | --- |
| 프론트 | HTML5 · CSS3(커스텀 속성, grid, `prefers-color-scheme`) · JavaScript(ES5 호환, `fetch`·`AbortController`·Canvas) | 외부 라이브러리 0 |
| 백엔드 | Vercel Serverless Functions — Python 3.12, `BaseHTTPRequestHandler` 기반 파일 함수 | `api/options.py`(GET) · `api/alt_text.py`(POST) · `api/_lib.py`(공유, `_` 접두라 엔드포인트 아님) |
| AI | Google Gemini `gemini-3.5-flash-lite` REST(`generateContent`, 이미지 inline + `responseSchema`) | `requests` 만 사용 |
| 배포 | Vercel + GitHub 연동(모노레포 하위 폴더를 Root Directory 로 지정) | `vercel.json`: 함수 30초, 테스트·샘플 제외, 폴더 변경 없으면 빌드 생략 |

## 로컬 실행

```bash
cd AI_Application/mission3/aitag-demo
python3 -m pip install -r requirements.txt python-dotenv   # python-dotenv 는 로컬 .env 읽기용
cp .env.example .env                                        # GEMINI_API_KEY 채우기
python3 scripts/dev_server.py                               # http://localhost:3000
python3 -m pytest tests -q                                  # 네트워크 없이 API 검증 15건
```

- `scripts/dev_server.py` 는 정적 파일과 `api/*.py` 를 Vercel 과 같은 경로로 띄우는 로컬 실행기(배포에 포함되지 않음). `vercel dev` 로도 실행 가능

## 배포 (Vercel)

1. Vercel → **Add New Project** → GitHub `Codyssey` 저장소 import
2. **Root Directory** = `AI_Application/mission3/aitag-demo` · Framework Preset = Other · Build Command 없음
3. **Environment Variables** 에 `GEMINI_API_KEY` 등록(Production·Preview 모두)
4. Deploy → `main` 브랜치 push 가 프로덕션, 다른 브랜치 push 는 프리뷰 URL
5. (보너스) 프로젝트 **Analytics** 탭에서 Enable

- 문제가 생기면: Vercel **Deployments → 해당 배포 → Functions 로그**에서 `api/alt_text` 오류 확인 → 수정 → push 하면 자동 재배포

## 환경 변수

| 이름 | 필수 | 설명 |
| --- | --- | --- |
| `GEMINI_API_KEY` | 예 | [Google AI Studio](https://aistudio.google.com/) → Get API key (무료 티어) |
| `GEMINI_MODEL` | 아니오 | 기본 `gemini-3.5-flash-lite` |
| `UPSTREAM_TIMEOUT` | 아니오 | Gemini 호출 타임아웃(초), 기본 25 |

- **키는 코드·README·스크린샷·커밋에 넣지 않는다.** 로컬은 `.env`(저장소 `.gitignore` 로 제외), 배포는 Vercel 환경 변수. 키는 서버 함수 안에서만 쓰여 브라우저로 내려오지 않는다
- 유출이 의심되면 AI Studio 에서 키를 삭제·재발급하고 Vercel 환경 변수를 교체한다. 커밋에 섞였다면 해당 커밋을 되돌리는 것으로는 부족하며(이력에 남음) `git filter-repo` 등으로 이력에서 제거한 뒤 강제 push 해야 한다
- 무료 티어는 분당 호출 한도가 있어 초과 시 429 → 화면에 "1분 뒤 다시 시도" 안내

## AI 기능 — 입력 / 출력 / 실패 처리

| 구분 | 내용 |
| --- | --- |
| 입력 | 이미지(JPEG·PNG·WebP·GIF, 브라우저에서 1,600px·JPEG 로 축소, 4MB 이하) · 매트릭스 7축(분야·콘텐츠 유형·이미지 유형·카테고리·톤·길이·언어) · 컨텍스트(선택, 500자) |
| 출력 | `alt_text` · `long_description` · `detected_text`(이미지 안 글 전문) · `is_decorative` · `matrix_key` · `blocks`(합성에 쓰인 블록) · `prompt`(실제 프롬프트) · `model` · `elapsed_ms` |
| 빈 입력 | 사진 없이 생성 → "사진을 올려 주세요" (프론트 + 서버 400 `EMPTY_IMAGE` 이중) |
| 형식·크기 | 지원하지 않는 형식 400 `BAD_MIME` · 4MB 초과 413 `IMAGE_TOO_LARGE` |
| API 오류 | Gemini 4xx/5xx → 502 `UPSTREAM_ERROR` 메시지 표시 · 429 → "1분 뒤 다시 시도" · 키 미설정 500 `NO_API_KEY` |
| 지연 | 서버 25초 → 504 `UPSTREAM_TIMEOUT` · 브라우저 30초 `AbortController` → "응답이 30초 안에 오지 않았습니다" |
| 알 수 없는 선택값 | 기본값으로 대체하고 결과에 `replaced` 로 표시 |

## 구조

```text
aitag-demo/
├── index.html · demo.html · matrix.html · faq.html   # 페이지 4개 (공통 헤더·푸터)
├── css/style.css                                     # 토큰·다크 모드·반응형(860px 분기)
├── js/common.js · demo.js · matrix.js                # 내비·테마 / 업로드·fetch·결과 / 축 표·프리셋
├── images/favicon.svg · samples/*.jpg                # 샘플 이미지 3종(PIL 로 생성한 가상 데이터)
├── api/_lib.py · options.py · alt_text.py            # 매트릭스 정의·합성 / GET / POST
├── requirements.txt · vercel.json · .python-version · .env.example
├── scripts/dev_server.py                             # 로컬 실행기
└── tests/test_api.py                                 # 오프라인 테스트 15건
```

## HTML · CSS · JS 는 각각 무슨 일을 하나

- **HTML** 은 내용과 구조(제목·폼·버튼·결과 영역). **CSS** 는 보이는 방식(색·간격·다크 모드·화면 크기별 배치). **JavaScript** 는 동작(사진 읽기·축소·`fetch` 요청·응답을 DOM 에 반영·오류 안내)
- 사용자 입력 → `fetch('/api/alt_text', {method:'POST', body: JSON})` → 서버 함수 → JSON 응답 → `render()` 가 결과 카드를 채움. 로컬(`dev_server.py`)과 배포(Vercel)에서 같은 경로(`/api/...`)를 쓰므로 프론트 코드는 환경에 따라 바뀌지 않는다
