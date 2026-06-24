# 인수인계 (HANDOFF) — 공고 분석 챗봇

> 목적: 사용자 컴퓨터의 Claude Code 세션이 이 프로젝트를 이어받아 **실제로 서버를 띄우고 검증**할 수 있도록 현재 상태·실행법·남은 작업을 정리한다.

## 0. 프로젝트 요약

공고 URL을 입력하면 포스터 이미지 + 본문을 분석해 핵심 정보(제목·장소·날짜·참여조건·상금·주관기관 등)를 구조화하고, 그 컨텍스트에 근거해 문답하는 웹 서비스. 3개 모델(Gemma 4 E4B / Llama 4 Scout / Qwen 3.6)을 대화창 상단 **토글**로 전환하며 비교하고, **모델별 대화 내역이 각각 보존**된다. "모든 모델에 동시 질문" 옵션 있음.

## 1. 위치 / 파일 구조

```
AI_Tools_Essentials/mission1/
├── HANDOFF.md                      ← 이 문서
├── 과제 요약.md
├── 시스템 설계 문서.md              ← 설계/프롬프트/Few-shot/환각검증 (작성 완료)
├── LLM 모델 비교·선정 보고서.md     ← 평가축/틀 완료, 점수·날짜는 실측 후 기입 필요
├── 실행 로그.md                     ← 예시 11턴, 실제 대화로 교체 필요
└── app/
    ├── main.py                     # FastAPI: /api/analyze, /api/chat, /api/models
    ├── static/index.html           # 3모델 토글 비교 UI
    ├── requirements.txt
    ├── .env                        # 실제 키 (gitignore됨, 커밋 금지)
    ├── .env.example                # 템플릿 (커밋 OK)
    ├── start.command               # macOS 더블클릭 실행 런처
    └── README.md
```

## 2. 현재까지 검증된 것 (이전 환경/샌드박스)

- 백엔드 import·라우팅 OK: `GET /` 200(HTML), `/api/models` 3개 모델 반환, `/static` 정상.
- uvicorn 기동 OK (HTTP 200 확인).
- URL 검증, HTML 본문 추출, 포스터 og:image 절대경로 변환, JSON 파싱(코드블록/깨진 JSON) 단위 확인.
- **미검증**: 실제 LLM 호출(외부망 차단 환경이라 OpenRouter 호출 불가). → **사용자 컴퓨터에서 이 부분을 검증해야 함.**

## 3. 실행 방법 (사용자 컴퓨터)

방법 A — 더블클릭: Finder에서 `app/start.command` 더블클릭 (venv 생성→의존성 설치→브라우저 자동 오픈).
최초 1회 권한이 필요하면 터미널에서 `chmod +x app/start.command`.

방법 B — 수동:
```bash
cd AI_Tools_Essentials/mission1/app
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 -m uvicorn main:app --reload --port 8000
# 브라우저: http://localhost:8000  (file:// 로 열지 말 것)
```

## 4. ⚠️ 먼저 해결해야 할 이슈

### (1) MODEL1 API 키 형식 불일치 — 우선 확인
`.env`의 `MODEL1_API_KEY`가 `AQ.Ab8RN6...` 로 시작한다. 이는 **OpenRouter 키 형식(`sk-or-v1-...`)이 아니다.** `MODEL1_BASE_URL`이 OpenRouter로 설정돼 있어 이대로면 model1 호출이 401(인증 실패)날 가능성이 높다.
- 해결 옵션 ①: model1도 OpenRouter로 쓸 거면 `MODEL1_API_KEY`를 model2/3과 동일한 `sk-or-v1-...` 키로 교체.
- 해결 옵션 ②: 이 `AQ.` 키가 다른 제공자(예: Google) 키라면 `MODEL1_BASE_URL`/`MODEL1_MODEL`을 그 제공자 규격에 맞게 변경.
- **Claude Code 첫 작업**: 아래 5장 검증 스크립트로 모델별 인증/응답을 확인하고, 실패 시 위 옵션으로 수정.

### (2) 모델 슬러그 유효성
`google/gemma-3-27b-it`, `meta-llama/llama-4-scout`, `qwen/qwen-2.5-vl-72b-instruct`는 후보 예시다. OpenRouter https://openrouter.ai/models 에서 **실제 제공 슬러그**로 확인/교체. 404(model not found)면 슬러그 문제.
※ "Vision 분석"이 필요하므로 멀티모달 지원 모델인지도 확인.

### (3) git 잠금 (커밋 시)
이전 환경에서 `.git/index.lock`·`HEAD.lock`이 권한 문제로 남아 있을 수 있다. 커밋이 막히면:
```bash
cd <repo 루트>; rm -f .git/index.lock .git/HEAD.lock .git/objects/maintenance.lock
```

## 5. 인계 직후 권장 작업 순서 (Claude Code용 체크리스트)

1. 서버 기동(3장) 후 브라우저 접속 확인.
2. 모델 3종 실제 호출 검증 — 아래 스니펫 실행, 401/404 처리:
   ```bash
   cd AI_Tools_Essentials/mission1/app && source .venv/bin/activate
   python3 -c "
   import main, requests
   for k,c in main.MODELS.items():
       try:
           print(k, c['model'], '->', main.call_llm(k, [{'role':'user','content':'reply: pong'}], 0).strip()[:60])
       except requests.HTTPError as e:
           print(k, 'HTTP', e.response.status_code, e.response.text[:140])
       except Exception as e:
           print(k, 'ERR', type(e).__name__, str(e)[:140])
   "
   ```
3. 실제 공고 URL 1건으로 `분석` → 포스터/필드 추출 확인 → 토글로 3모델 문답 비교.
4. 과제 산출물 실측 채우기:
   - `LLM 모델 비교·선정 보고서.md`: 평가축 점수(1~5)·근거, 재현성 표(요금제/날짜/설정), 무료 제한 1줄, 최종 선정 결론 3줄.
   - `시스템 설계 문서.md` 10-4: 환각 검증 6문항 Pass/Fail 실측 기입.
   - `실행 로그.md`: 실제 10턴+ 대화 전문으로 교체(조건 변경·추가 정보 포함), 원본 로그 별도 보존.
5. 커밋(민감 파일 제외 확인): `.env`는 gitignore됨. `git status`로 `.env` 미포함 확인 후 커밋.

## 6. API / 동작 메모

| 메서드 | 경로 | 입력 | 출력 |
| --- | --- | --- | --- |
| GET | /api/models | — | {default, models[]} |
| POST | /api/analyze | {url, model_key} | {ok, poster_url, poster_data_uri, fields, context} |
| POST | /api/chat | {messages[], context, model_key} | {ok, answer} |

- 환각 안전장치: 추출 시 없는 값은 `"정보 없음"`, 응답 시 컨텍스트 밖이면 "확인되지 않습니다" + 확인처 제안, 날짜·금액은 원문 인용·임의계산 금지. (프롬프트 전문: `시스템 설계 문서.md` 12장)
- 모델 전환은 `.env`의 `MODELn_*`만 바꾸면 됨(코드 수정 불필요).

## 7. 보안

- `.env`에는 **실제 API 키**가 있다. `.gitignore`에 `.env`/`*.env`/시크릿류 포함됨 → 절대 커밋 금지.
- 키가 노출됐다고 판단되면 OpenRouter에서 해당 키를 폐기(rotate)할 것.
