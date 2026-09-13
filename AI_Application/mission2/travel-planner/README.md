# 국내 여행 추천 프로그램 (travel-planner)

- 여행 날짜를 입력하면 **LLM(Gemini)** 이 그 시기에 좋은 국내 지역을 추천하고, **지도 API(Kakao Local)** 로 맛집을 찾은 뒤, LLM 이 **최종 여행 리포트(Markdown)** 를 쓰는 CLI 프로그램
- 여러 API 를 엮는 흐름이 핵심 — LLM 출력을 **구조화(JSON)** 해 다음 단계(장소 검색)의 입력으로 넘긴다
- Codyssey AI_Application 미션2 산출물

```text
-date "YYYY-MM-DD"
   │
   ▼
[1/3] Gemini ─ POST generateContent ──▶ 1차 추천 JSON {recommended_city, weather, events, reason}
   │                                    (보너스: recommended_cities 2~3곳)
   ▼
[2/3] Kakao Local ─ GET keyword.json ─▶ 지역별 맛집 5곳 [{name, address, category, url, x, y}]
   │                                    (실패·0건 → "데이터 없음" 으로 계속 진행)
   ▼
[3/3] Gemini ─ POST generateContent ──▶ 최종 리포트 Markdown (+ 오류 요약 섹션)
   │
   ▼
results/<날짜>_raw.json · results/<날짜>_travel_plan.md
```

## 실행 방법

- Python **3.10 이상**, 인터넷 연결

```bash
cd AI_Application/mission2/travel-planner
python3 -m pip install -r requirements.txt     # requests · python-dotenv
cp .env.example .env                           # 키 채우기 (아래 참고)
python3 travel_planner.py -date "2026-10-03"   # Windows: python travel_planner.py -date "2026-10-03"
```

| 옵션 | 설명 |
| --- | --- |
| `-date "YYYY-MM-DD"` | **필수**. 형식이 틀리면 사용법을 출력하고 종료 (`--date` 도 가능) |
| `--cities N` | 추천 지역 수 1~3 (기본 3) — 보너스: 복수 지역 |
| `--count N` | 지역당 맛집 검색 수 (기본 5) |
| `--no-cache` | 같은 날짜의 `results/<날짜>_raw.json` 이 있어도 API 를 다시 호출 — 보너스: 캐싱 |

```text
$ python3 travel_planner.py -date "2026-10-03"
[1/3] 1차 추천 생성 중(LLM · gemini-3.5-flash-lite)...
    - recommended_city: "경주"
    - recommended_city: "강릉"
    - recommended_city: "전주"
[2/3] 맛집 검색 중(Kakao Local)...
    - 경주: 맛집 5곳 검색 완료
    - 강릉: 맛집 5곳 검색 완료
    - 전주: 맛집 5곳 검색 완료
[3/3] 최종 리포트 생성 중(LLM)...
    - 리포트 생성 완료

완료! results/2026-10-03_travel_plan.md 를 확인하세요.
      원본 데이터: results/2026-10-03_raw.json
```

## API 키 설정

| 키 | 발급 | 비용 |
| --- | --- | --- |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/) → **Get API key** | 무료 티어 (카드 등록 불필요) |
| `KAKAO_REST_API_KEY` | [Kakao Developers](https://developers.kakao.com/) → 내 애플리케이션 → 애플리케이션 추가 → **앱 키 → REST API 키**. 그리고 **앱 설정 → 카카오맵 → 활성화 설정 ON** (꺼져 있으면 403) | 무료 |

- 방법 1 — `.env` 파일 (권장): `.env.example` 을 `.env` 로 복사하고 값을 채운다

  ```text
  GEMINI_API_KEY=여기에_키
  KAKAO_REST_API_KEY=여기에_키
  ```

- 방법 2 — 환경변수 (현재 터미널 세션에만 적용, `.env` 보다 우선)

  ```bash
  export GEMINI_API_KEY="YOUR_KEY"        # macOS/Linux
  $env:GEMINI_API_KEY="YOUR_KEY"          # Windows PowerShell
  ```

- 키가 하나라도 없으면 프로그램은 **즉시 종료**하고 위 설정 방법을 안내한다

### 키가 유출되지 않도록

- 키를 **코드·README·결과 파일·스크린샷에 쓰지 않는다**. 이 저장소의 `.gitignore` 가 `.env` 를 제외하며, 커밋 전 `git status` 로 `.env` 가 없는지 확인한다
- 공유·발표용 화면에서는 `.env` 내용과 `env` 출력을 가린다. 실수로 노출됐다면 콘솔에서 **키를 재발급(회전)** 하고 옛 키를 삭제한다
- 왜 환경변수/.env 인가 — 협업·공유 시 실수 노출 방지 · 키를 바꿔도 코드 수정 불필요 · 과금·쿼터 사고 예방

## 결과물 확인

| 파일 | 내용 |
| --- | --- |
| `results/<날짜>_raw.json` | 원본 데이터 — `recommendation`(1차 추천 JSON 파싱 결과) · `places`(지역별 맛집 목록, 0건 가능) · `errors`(오류 요약 배열, 빈 배열 가능) · `generated_at` · `llm_model` |
| `results/<날짜>_travel_plan.md` | 최종 리포트 — 지역별 `추천 이유 · 날씨 요약 · 행사/축제 · 맛집 추천 · 1일 일정 제안` + 끝에 `오류 요약(errors)` |

- 파일명은 **입력한 여행 날짜** 기준. 같은 날짜로 다시 실행하면 원본 JSON 을 캐시로 써서 [1/3]·[2/3] API 호출을 건너뛰고 리포트만 다시 만든다

## 오류 처리 정책

| 상황 | 동작 | `errors` 기록 |
| --- | --- | --- |
| API 키 미설정 | 즉시 종료 + 설정 방법 안내 | — |
| 날짜 형식 오류 | 사용법 출력 후 종료 (exit 2) | — |
| LLM 1차 추천 JSON 파싱 실패 | "필수 키만 다시 JSON 으로" 프롬프트를 고쳐 **1회만** 재시도, 그래도 실패면 종료 | `recommend / PARSE_ERROR` |
| LLM 인증·쿼터·네트워크 실패 | [1/3] 이면 종료(다음 단계 입력이 없음), [3/3] 이면 데이터만으로 **대체 리포트** 생성 | `AUTH_ERROR` `QUOTA_ERROR` `NETWORK_ERROR` `HTTP_ERROR` |
| 지도 API 실패(401/403/429/네트워크) · 0건 | 그 지역 맛집 = **데이터 없음** 으로 두고 리포트 생성 계속 | `place_search / AUTH_ERROR …` · `EMPTY_RESULT` |

- 모든 API 호출·파싱은 `try-except` 로 감싸고, 오류는 `errors.ErrorLog` 에 `{"step", "type", "message"}` 로 쌓아 원본 JSON 과 리포트 끝 섹션에 남긴다

## 구조

| 파일 | 역할 |
| --- | --- |
| `travel_planner.py` | CLI(argparse) · 3단계 파이프라인 · 캐싱 · 결과 저장 |
| `llm_api.py` | Gemini `generateContent` **POST** — 1차 추천(JSON 모드 + 스키마, 재시도 1회) · 최종 리포트 |
| `place_api.py` | Kakao Local 키워드 검색 **GET** — `<지역> 맛집`, 응답을 최소 필드로 정리, 실패 시 빈 목록 |
| `report.py` | 원본 JSON · 리포트 저장, 오류 요약 섹션, LLM 실패 시 대체 리포트 |
| `config.py` | `.env`/환경변수 로드, 키 확인, 모델·타임아웃 설정 |
| `errors.py` | 오류 유형 상수 · `ErrorLog` · HTTP 상태/예외 → 유형 분류 |
| `tests/test_offline.py` | 네트워크 없이 오류 경로 검증 (`python3 -m pytest tests -q`) |

- **GET vs POST** — Kakao 검색은 "조회"라 검색어를 URL 쿼리스트링에 실어 **GET**, Gemini 는 프롬프트·설정을 요청 **본문(JSON)** 에 담아 보내야 하므로 **POST**. 인증은 둘 다 헤더(`Authorization: KakaoAK …` / `x-goog-api-key: …`)
- SDK 없이 `requests` 로 REST 엔드포인트를 직접 호출해 요청/응답 구조가 코드에 그대로 보인다
