# 국내 여행 추천 프로그램 (travel-planner)

- 여행 날짜를 입력하면 **LLM(Gemini)** 이 그 시기에 좋은 국내 지역을 추천하고, **지도/장소 API(Kakao Local)** 로 맛집을 찾은 뒤, LLM 이 **최종 여행 리포트(Markdown)** 를 쓰는 CLI 프로그램
- 여러 API 를 엮는 흐름이 핵심 — LLM 출력을 **구조화(JSON)** 해 다음 단계(장소 검색)의 입력으로 넘긴다
- Codyssey AI_Application 미션2 산출물

```text
-date "YYYY-MM-DD"
   │
   ▼
[1/3] Gemini ─ POST generateContent ──▶ 1차 추천 JSON {recommended_city, weather, events, reason}
   │                                    (보너스: other_cities → recommended_cities 3곳)
   ▼
[2/3] Kakao Local ─ GET keyword.json ─▶ 지역별 맛집 5곳 [{name, address, category, url, x, y}]
   │   (검색어 보정: 부산광역시→부산 · 강원도→강릉)   (실패·0건 → "데이터 없음" 으로 계속 진행)
   ▼
[3/3] Gemini ─ POST generateContent ──▶ 최종 리포트 Markdown (+ 오류 요약 섹션)
   │                                    (필수 항목 누락·LLM 실패 → 데이터만으로 대체 리포트)
   ▼
results/<날짜>_raw.json · results/<날짜>_travel_plan.md
```

## 실행 방법

- Python **3.10 이상**, 인터넷 연결

```bash
cd AI_Application/mission2/travel-planner
python3 -m pip install -r requirements.txt     # requests · python-dotenv
cp -n .env.example .env                        # -n: 이미 있는 .env 를 덮어쓰지 않음 → 키 채우기 (아래 참고)
python3 travel_planner.py -date "2026-10-03"   # Windows: python travel_planner.py -date "2026-10-03"
```

| 옵션 | 설명 |
| --- | --- |
| `-date "YYYY-MM-DD"` | **필수**. 0 채움 형식만 허용(`2026-1-5` 거부), 형식이 틀리면 사용법을 출력하고 종료 (`--date` 도 가능) |
| `--cities N` | 추천 지역 수 1~3 (기본 3) — 보너스: 복수 지역 |
| `--count N` | 지역당 맛집 검색 수 (기본 5, Kakao 1~15 · Naver 1~5) |
| `--no-cache` | 같은 날짜의 `results/<날짜>_raw.json` 이 있어도 API 를 다시 호출 — 보너스: 캐싱 |
| `-h` | 도움말 · 사용 예시 · 종료 코드 |

```text
$ python3 travel_planner.py -date "2027-03-15"
[1/3] 1차 추천 생성 중(LLM · gemini-3.5-flash-lite)...
    - recommended_city: "제주"
    - recommended_city: "강릉"
    - recommended_city: "경주"
[2/3] 맛집 검색 중(Kakao Local)...
    - 제주: 맛집 5곳 검색 완료
    - 강릉: 맛집 5곳 검색 완료
    - 경주: 맛집 5곳 검색 완료
[3/3] 최종 리포트 생성 중(LLM)...
    - 리포트 생성 완료

완료! results/2027-03-15_travel_plan.md 를 확인하세요.
      원본 데이터: results/2027-03-15_raw.json
```

- 종료 코드: `0` 완료 · `1` 키 미설정·1차 추천 실패·저장 실패 · `2` 입력 형식 오류 · `130` Ctrl+C 중단

## API 키 설정

| 키 | 발급 | 비용 |
| --- | --- | --- |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/) → **Get API key** | 무료 티어 (카드 등록 불필요) |
| `KAKAO_REST_API_KEY` | [Kakao Developers](https://developers.kakao.com/) → 내 애플리케이션 → 애플리케이션 추가 → **앱 키 → REST API 키** (JavaScript 키 아님). 그리고 **앱 설정 → 카카오맵 → 활성화 설정 ON** (꺼져 있으면 403) | 무료 |
| (선택) `PLACE_PROVIDER=naver` + `NAVER_CLIENT_ID` · `NAVER_CLIENT_SECRET` | [Naver Developers](https://developers.naver.com/) → 애플리케이션 등록 → 사용 API **검색** | 무료 |

- 방법 1 — `.env` 파일 (권장): `cp -n .env.example .env` 후 값 채우기

  ```text
  GEMINI_API_KEY=여기에_키
  KAKAO_REST_API_KEY=여기에_키
  ```

- 방법 2 — 환경변수 (현재 터미널 세션에만 적용, `.env` 보다 우선)

  ```bash
  export GEMINI_API_KEY="YOUR_KEY"        # macOS/Linux
  $env:GEMINI_API_KEY="YOUR_KEY"          # Windows PowerShell
  ```

- 키가 하나라도 없으면 프로그램은 **즉시 종료**하고 설정 방법과 원인을 안내한다 — `.env` 없음 / `.env` 값 비어 있음 / 셸에 빈 값으로 export 된 변수가 `.env` 를 가림(`unset` 안내)

### 키가 유출되지 않도록

- 키를 **코드·README·결과 파일·스크린샷에 쓰지 않는다**. 저장소 `.gitignore` 가 `.env` 를 제외하며, 커밋 전 `git status` 로 `.env` 가 없는지 확인한다
- `cp .env.example .env` 를 다시 실행하면 채워 둔 `.env` 가 템플릿으로 **덮어써진다** → 항상 `cp -n`
- 공유·발표용 화면에서는 `.env` 내용과 `env` 출력을 가린다. 실수로 노출됐다면 콘솔에서 **키를 재발급(회전)** 하고 옛 키를 삭제한다
- Gemini 키는 URL 쿼리(`?key=`)가 아니라 **헤더**(`x-goog-api-key`)로 보낸다 — 오류 메시지·로그에 URL 이 찍혀도 키가 남지 않는다
- 왜 환경변수/.env 인가 — 협업·공유 시 실수 노출 방지 · 키를 바꿔도 코드 수정 불필요 · 과금·쿼터 사고 예방

## 결과물 확인

| 파일 | 내용 |
| --- | --- |
| `results/<날짜>_raw.json` | 원본 데이터 — `recommendation`(1차 추천 JSON 파싱 결과: 최상위 `recommended_city` `weather` `events` `reason` + 보너스 `recommended_cities`) · `places`(지역별 맛집, 0건 가능) · `errors`(오류 요약 배열, 빈 배열 가능) · `options` · `generated_at` · `llm_model` · `place_provider` |
| `results/<날짜>_travel_plan.md` | 최종 리포트 — `추천 지역` 요약 + 지역별 `추천 이유 · 날씨 요약 · 행사/축제 · 맛집 추천 · 1일 일정 제안` + 끝에 `오류 요약(errors)` |

- 파일명은 **입력한 여행 날짜** 기준 — 과제 예시 `results/20XX-03-15_travel_plan.md` 와 같은 규칙이며, 같은 `-date` 재실행 시 캐시의 키가 된다
- 제출 샘플 4세트

| 날짜 | 상황 |
| --- | --- |
| `2027-03-15` | 정상 — 3지역 · 맛집 15곳 · errors 없음 (현재 스키마) |
| `2026-10-03` · `2026-11-07` | 정상 — 3지역 · 맛집 15곳 (초기 버전 실행, 읽을 때 현재 형식으로 맞춤) |
| `2026-12-24` | 지도 API 인증 실패(잘못된 키) — 맛집 `데이터 없음` · `AUTH_ERROR` |

## 웹 화면 (선택)

- CLI 와 **같은 파이프라인**을 브라우저에서 실행·조회하는 로컬 화면 (과제 필수는 CLI, 웹은 추가 기능)

```bash
python3 web.py                  # → http://localhost:8000  (종료: Ctrl+C, 다른 포트: --port 8001)
```

| 기능 | 내용 |
| --- | --- |
| 조건 입력 | 날짜 · 지역 수(1~3) · 지역당 맛집 수 · 저장 결과 무시 — CLI 와 같은 검증, 틀린 칸에 바로 안내 |
| 진행 표시 | 3단계(지역 추천 · 맛집 검색 · 리포트 작성)의 진행 중/완료/캐시/경고/실패 + 실시간 로그 · 경과 시간 |
| 결과 | 리포트 · 맛집 지도(지역별 색 핀, 지역 필터, 목록과 연동) · 오류 유형별 조치 안내 · `.md`/`.json` 내려받기 |
| 저장된 결과 | `results/` 의 지난 결과를 API 호출 없이 다시 보기 |
| 지도 | `.env` 에 `KAKAO_JS_KEY`(카카오 **JavaScript 키**) + 카카오 콘솔 → 플랫폼 → Web 에 `http://localhost:8000` 등록 시 카카오맵, 없거나 실패하면 OpenStreetMap |

| 요청 | 용도 |
| --- | --- |
| `GET /api/config` · `GET /api/results` · `GET /api/results/<날짜>` | 조회 — 설정 · 저장 결과 목록 · 상세 |
| `POST /api/plan` | 생성 — 본문 `{date, cities, count, no_cache}` → 진행 이벤트를 한 줄씩(NDJSON) 보내고 마지막 줄이 결과 |

- 기본 `127.0.0.1` 에서만 열림(이 컴퓨터만 접속) · 생성은 한 번에 1건(동시 요청 409) · REST/Gemini 키는 화면으로 내보내지 않음(카카오 JavaScript 키는 원래 브라우저용 공개 키)
- 표준 라이브러리 `http.server` + 순수 HTML/CSS/JS — 추가 설치 없음

## 오류 처리 정책

| 상황 | 동작 | `errors` 기록 |
| --- | --- | --- |
| API 키 미설정 | 즉시 종료(exit 1) + 설정 방법·원인 안내 | — |
| 날짜·옵션 형식 오류 | 사용법 출력 후 종료 (exit 2) | — |
| LLM 1차 추천 JSON 파싱 실패 | 실패 이유를 넣어 "필수 키만 다시 JSON 으로" 프롬프트 수정 후 **1회만** 재시도, 그래도 실패면 종료 | `recommend / PARSE_ERROR` (복구돼도 기록) |
| LLM 인증·쿼터·네트워크·차단 | [1/3] 이면 종료(다음 단계 입력이 없음), [3/3] 이면 데이터만으로 **대체 리포트** | `AUTH_ERROR` `QUOTA_ERROR` `NETWORK_ERROR` `HTTP_ERROR` `LLM_ERROR` |
| LLM 리포트 필수 항목 누락 | 데이터만으로 **대체 리포트** | `report / PARSE_ERROR` |
| 지도 API 실패(401/403/429/네트워크) | 그 지역 맛집 = **데이터 없음**, 리포트 생성 계속. 인증·쿼터 실패 뒤 나머지 지역은 같은 키라 호출 생략 | `place_search / AUTH_ERROR …` |
| 지도 검색 0건 | **데이터 없음** + 지도에서 **직접 찾기** 링크, 일정 식사는 지역 대표 음식 위주 | `place_search / EMPTY_RESULT` |
| 일시 오류(5xx·연결 실패) | 1.5초 뒤 **1회만** 재시도 (인증·쿼터·응답 대기 초과는 재시도 안 함) | 재시도도 실패하면 기록 |
| 결과 파일 저장 실패 | 리포트를 화면에 출력, exit 1 | `save / IO_ERROR` |
| Ctrl+C · 예상하지 못한 오류 | 안내 후 종료(130 / 1), 완료된 단계의 결과는 `results/` 에 남음 | — |

- 모든 API 호출·파싱은 `try-except` 로 감싸고, 오류는 `errors.ErrorLog` 에 `{"step", "type", "message"}` 로 쌓아 원본 JSON 과 리포트 끝 섹션에 남긴다. CLI 는 끝에 오류 유형별 조치 안내를 함께 출력

## 구조

| 파일 | 역할 |
| --- | --- |
| `travel_planner.py` | CLI — argparse(입력 검증) · 결과 안내 · 종료 코드 |
| `pipeline.py` | 3단계 흐름 조립 — 진행 이벤트 · 캐시 판단 · 결과 저장 |
| `llm_api.py` | Gemini `generateContent` **POST** — 1차 추천(JSON 모드 + 스키마 + 검증 + 재시도 1회) · 리포트(필수 항목 검사) |
| `place_api.py` | 장소 검색 공통 창구 — 검색어 보정 · 호출 · 오류/0건 처리 · 공통 필드 반환 |
| `place_kakao.py` · `place_naver.py` | 제공자별 요청 모양·응답 정리만 (Kakao 기본, `PLACE_PROVIDER=naver` 로 교체) |
| `report.py` | 원본 JSON · 리포트 저장, 오류 요약 섹션, 대체 리포트, 예전 결과 파일 형식 맞춤 |
| `errors.py` · `net.py` · `config.py` | 오류 유형·조치 안내·`ErrorLog` / 일시 오류 1회 재시도 / `.env` 로드·키 확인 |
| `web.py` · `web/` | (선택) 로컬 웹 화면 — 같은 `pipeline.run()` 을 브라우저에서 |
| `tests/` | 네트워크 없이 정상·오류 경로·웹 서버 검증 (`python3 -m pytest tests -q`) |

- **GET vs POST** — Kakao 검색은 "조회"라 검색어를 URL 쿼리스트링에 실어 **GET**, Gemini 는 프롬프트·스키마를 요청 **본문(JSON)** 에 담아 보내야 하므로 **POST**. 인증은 둘 다 헤더(`Authorization: KakaoAK …` / `x-goog-api-key: …`)
- **JSON 강제** — `responseMimeType: application/json` + `responseSchema`(필수 4키·`events` 1~3개) → `json.loads` → 키·타입 검사. 자유 텍스트는 매번 모양이 달라 다음 단계(장소 검색)의 입력으로 쓸 수 없다
- **제공자 교체** — 파이프라인은 `place_api.search_restaurants()` 만 부르고 결과는 항상 공통 필드. 새 제공자는 `build_request · documents · normalize · search_url` 을 가진 파일 1개 + `PROVIDERS` 등록 1줄
- SDK 없이 `requests` 로 REST 엔드포인트를 직접 호출해 요청/응답 구조가 코드에 그대로 보인다

## 테스트

```bash
python3 -m pip install pytest
python3 -m pytest tests -q          # 네트워크·키 없이 실행 (requests 를 가짜 응답으로 바꿈)
```
