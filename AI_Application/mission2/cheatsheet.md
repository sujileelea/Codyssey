# 치트시트 — 국내 여행 추천 프로그램 (AI_Application 미션2)

> 평가 방법 → 시연 명령어 순서 → 질문별로 설명할 내용. 코드 위치는 `travel-planner/` 기준

---

## 1. 평가 방법

- 평가 4개 항목, 항목별 PASS / FAIL 판정
- 항목 1 = **동작 확인** — 평가자 앞에서 실행·결과 파일 확인 (명령어 시연)
- 항목 2 = **설계 설명** — 모듈 분리 · 1차 JSON 검증 · 지도 제공자 교체 구조 · errors 누적
- 항목 3 = **개념 설명** — GET/POST · JSON 강제 이유 · 401/403 원인과 디버깅 순서 · `.env` 관리 이유
- 항목 4 = **응용·What-if** — 깨진 JSON 대응 · 0건 리포트 정책 · 반복 실행 비용 절감 · 넓은 지역명 정규화
- 항목 1 은 터미널 시연, 항목 2~4 는 말로 설명 + 에디터에서 해당 함수 제시
- 준비물: 터미널(`travel-planner/` 폴더) · 에디터(코드) · `results/` 샘플 · `.env` 채워 둔 상태(화면 공유 시 `.env` 창 닫기)
- 근거 문서: `평가 지침.md`(문항별 확인 방법 표) · `실행 로그.md`(실제 출력)

---

## 2. 명령어 입력 순서 (시연)

```bash
cd travel-planner
```

| 순서 | 명령 | 보여 줄 것 | 문항 |
| --- | --- | --- | --- |
| 1 | `python3 travel_planner.py -h` | 옵션 · 사용 예시 · 종료 코드 | 1-① |
| 2 | `python3 travel_planner.py -date 2026-13-01` | `usage:` + 형식 오류 안내 후 종료 (exit 2) | 1-① |
| 3 | `GEMINI_API_KEY= KAKAO_REST_API_KEY= python3 travel_planner.py -date 2026-10-03` | 키 미설정 즉시 종료 + 원인·설정 방법 (`.env` 는 그대로) | 3-④ |
| 4 | `python3 travel_planner.py -date 2026-11-20` | `[1/3]` 추천 3곳 → `[2/3]` 지역별 맛집 → `[3/3]` 리포트 → 저장 경로 | 1-②③④ |
| 5 | `python3 -c "import json; r = json.load(open('results/2026-11-20_raw.json')); print(list(r['recommendation'])[:4], r['errors'])"` | 필수 4키 `recommended_city weather events reason` · errors 배열 | 1-② |
| 6 | `cat results/2026-11-20_travel_plan.md` | 추천 지역 · 추천 이유 · 날씨 · 행사 · 맛집 · 1일 일정 · 오류 요약 | 1-④ |
| 7 | `python3 travel_planner.py -date 2026-11-20` | `[캐시] ... 발견` → 추천·검색 API 호출 생략, 리포트만 재생성 | 4-③ |
| 8 | `KAKAO_REST_API_KEY=wrongkey python3 travel_planner.py -date 2026-12-24` | 401 → 맛집 `데이터 없음` → 리포트 계속 생성 → 오류 요약·조치 안내 | 1-③ · 3-③ |
| 9 | `python3 -m pytest tests -q` | 깨진 JSON 재시도 1회 · 0건 · 503 대체 리포트 등 오류 경로 전부 통과 | 4-①② |
| 10 | `git status --short .` → `git ls-files . \| xargs grep -nE "AIza\|AQ\.[0-9A-Za-z_-]{20,}\|KakaoAK [0-9a-f]{32}"` | `.env` 미추적 · 키 패턴 0건 | 1-⑤ |
| 11 | (추가) `python3 web.py` → 브라우저 `http://localhost:8000` | 같은 파이프라인의 웹 화면 — 저장된 결과 `2027-03-15` 클릭 · 진행 표시 · 맛집 지도 | 2-① |

- 4번은 샘플에 없는 날짜 사용 — 샘플 날짜면 캐시가 먼저 동작
- 시간이 없으면 4번 대신 `results/2027-03-15_*` 샘플로 설명

---

## 3. 설명해야 하는 것

### 3-1. 흐름의 함수/모듈 분리 (항목 2)

- `travel_planner.py` — 입력(argparse·검증)과 출력(경로 안내·종료 코드)만 담당
- `pipeline.run()` — 3단계 순서 조립 담당
  · [1/3] `llm_api.recommend()` → 1차 추천 dict
  · [2/3] 지역마다 `place_api.search_restaurants()` → `places_by_city`
  · [3/3] `llm_api.write_report()` → Markdown → `report.save_raw()` · `save_report()`
- 단계 사이 데이터 = 파이썬 dict — 앞 단계 출력이 곧 다음 단계 입력 (`recommended_city` → 검색어)
- 진행 출력은 `emit` 콜백으로 분리 — CLI 는 `print`, 웹(`web.py`)은 같은 이벤트를 브라우저로 스트리밍 → 흐름 코드 1벌을 두 화면이 공유
- 공통 관심사는 별도 모듈 — `errors`(오류 목록) · `net`(재시도) · `config`(키) · `report`(저장·대체 리포트)
- 장점: 단계별 단독 테스트(가짜 응답) · 제공자 교체 · 재사용

### 3-2. 1차 JSON 스키마 검증 (항목 2)

- 1단계 생성 강제 — `responseMimeType: application/json` + `responseSchema`(`recommend_schema()`): 필수 4키 `required`, `events` 1~3개(`minItems`/`maxItems`)
- 2단계 파싱 — `parse_json_text()`: 코드 펜스 제거 → `json.loads` → 실패 시 첫 `{` ~ 마지막 `}` 재해석
- 3단계 검증 — `_check_city()`
  · 필수 키 존재 확인, 빠진 키 이름을 오류 메시지에 명시
  · 타입 확인: `recommended_city`·`weather`·`reason` = 비어 있지 않은 문자열, `events` = 문자열 1개 이상 배열(3개 초과는 잘라냄)
  · 복수 지역 `other_cities` 각 항목도 같은 규칙, 위치 표기(`other_cities[0]`)
- 실패 처리 — `ValueError` → 프롬프트 수정 재시도 1회 → 그래도 실패면 `PARSE_ERROR` 후 종료(다음 단계 입력 없음)
- 테스트 — 키 누락·타입 오류·문자열 events·항목 누락 4가지 (`test_recommend_validation_names_the_problem`)

### 3-3. 지도 제공자 교체 시 변경 최소화 구조 (항목 2)

- 공통 창구 `place_api.py` — 파이프라인이 부르는 유일한 함수 `search_restaurants(city, count, errors, log)`
- 공통 창구가 맡는 일: 검색어 보정 · HTTP 호출·재시도 · 401/403/429/네트워크/0건 처리 · errors 기록
- 제공자 모듈 `place_kakao.py` · `place_naver.py` — 같은 이름의 함수 4개만 보유
  · `build_request()`(헤더·파라미터 모양) · `documents()`(응답에서 목록 꺼내기) · `normalize()`(공통 필드로 정리) · `search_url()`(지도 검색 링크)
- 반환 모양 고정 — 항상 `{name, address, category, url, x, y, phone}` 목록 → 파이프라인·리포트 코드 변경 0
- 교체 방법 — `.env` 에 `PLACE_PROVIDER=naver` + 네이버 키 2개 (코드 수정 없음)
- 새 제공자 추가 — 파일 1개 + `PROVIDERS` 등록 1줄 + `config.PROVIDER_KEYS` 1줄
- 차이 흡수 예: Kakao `place_name` ↔ Naver `title`(`<b>` 태그 제거) · Kakao `x/y` 실수 ↔ Naver `mapx/mapy`(정수 ÷ 10⁷) · 상한 15 ↔ 5
- 테스트 — Naver 로 바꿔도 출력 모양 동일 (`test_naver_provider_same_output_shape`, 네이버 키가 없어 오프라인으로만 확인)

### 3-4. errors 누적과 리포트 반영 (항목 2)

- `errors.ErrorLog` — `{"step", "type", "message"}` 딕셔너리 목록, `pipeline.run()` 시작 시 1개 생성
- 각 단계 함수에 인자로 전달 → 실패 시 예외 대신 `errors.add()` 후 빈 목록·대체값 반환
- LLM 단계는 `LLMError` 를 `run()` 이 잡아서 기록 (1차 실패 = 종료, 리포트 실패 = 대체 리포트)
- 유형 — `AUTH_ERROR` `QUOTA_ERROR` `NETWORK_ERROR` `HTTP_ERROR` `PARSE_ERROR` `EMPTY_RESULT` `LLM_ERROR` `IO_ERROR`
- 반영 2곳
  · 리포트 끝 `## 오류 요약(errors)` — `report.errors_section()`, 오류 없으면 `- 없음`
  · 원본 JSON `errors` 배열 — 리포트 단계 오류까지 담으려고 마지막에 다시 저장
- CLI 끝에 유형별 조치 안내(`errors.HINTS`) 출력
- 재시도로 복구된 파싱 실패도 기록 — "실패가 있었다"는 사실 보존

### 3-5. GET / POST 사용처와 이유 (항목 3)

- REST 요청 = 메서드 + URL(+쿼리스트링) + 헤더(인증·형식) + 본문(JSON) · 응답 = 상태 코드 + 헤더 + 본문(JSON)
- 장소 검색(Kakao `keyword.json` · Naver `local.json`) = **GET**
  · 서버 상태를 바꾸지 않는 조회
  · 검색어·개수를 URL 쿼리스트링(`params`)으로 전달
  · 같은 요청 반복이 안전(멱등) — 재시도·캐시에 유리
- Gemini `generateContent` = **POST**
  · 긴 프롬프트·JSON 스키마·생성 설정을 요청 본문(JSON)으로 전달 — URL 에 담을 수 없는 크기·구조
  · 호출마다 새 결과 생성(비멱등)·과금 대상
- 인증은 둘 다 헤더 — `Authorization: KakaoAK <키>` · `x-goog-api-key: <키>` (URL 에 키를 넣지 않음)
- 웹 서버도 같은 기준 — 조회 `GET /api/results` · 생성(API 호출·파일 저장) `POST /api/plan`

### 3-6. LLM 출력을 JSON 으로 강제한 이유와 장점 (항목 3)

- 이유: 다음 단계(장소 검색)가 `recommended_city` 를 코드로 정확히 꺼내야 함 — 자유 텍스트는 매번 문장 모양이 달라 추출 불안정
- 장점
  · 키·타입 검증 가능 → 실패 감지와 재시도 기준 명확
  · 원본 JSON 저장 → 캐시 재사용·디버깅 근거
  · 리포트 단계에 구조화 데이터로 전달 → 환각 감소(데이터에 있는 맛집만 사용)
  · 다른 소비자(화면 등) 재사용 용이
- 방법: 프롬프트 지시 + JSON 모드 + 스키마 + 코드 검증의 4중 장치
- 대비: 최종 리포트는 사람이 읽는 Markdown — 대신 필수 항목 검사(`check_report()`)로 형식 보장

### 3-7. 외부 API 401/403 원인과 디버깅 순서 (항목 3)

- 401 = 인증 실패 — 키 누락·오타·만료, 헤더 이름·형식 오류(`KakaoAK` 뒤 공백), 키 종류 오류(Kakao JavaScript 키 사용)
- 403 = 인증은 됐지만 권한 없음 — 서비스 비활성(카카오맵 활성화 OFF), API 사용 설정 누락(네이버 검색 API), 도메인·플랫폼 미등록, 정책 차단
- (Gemini 는 잘못된 키를 400 "API key not valid" 로 돌려줌 → 코드에서 `AUTH_ERROR` 로 분류)
- 디버깅 순서
  1. 상태 코드 + 응답 본문 메시지 확인 (`wrong appKey` · `disabled OPEN_MAP_AND_LOCAL service` · `KA Header is required`)
  2. 키가 실제로 로드됐는지 — `.env` 위치, 빈 값, 셸 빈 변수의 가림 (프로그램이 원인 3가지 구분 안내)
  3. 키 종류 — REST API 키인지
  4. 헤더 이름·형식 — `Authorization: KakaoAK <키>` · `X-Naver-Client-Id/Secret` · `x-goog-api-key`
  5. 콘솔 설정 — 카카오맵 활성화 ON · 검색 API 사용 설정 · 도메인 등록
  6. 프로그램 밖 최소 요청(curl)으로 키만 단독 검증
- 재시도 무의미 — 같은 키면 결과 동일 → 첫 401 뒤 나머지 지역 호출 생략, 키 확인 안내
- 실제 겪은 사례 2건: JavaScript 키 → 401 · 카카오맵 비활성 → 403 (`실행 로그.md` §1)

### 3-8. API 키를 .env/환경변수로 관리하는 이유 (항목 3)

- 보안
  · 코드·Git 이력·README·스크린샷으로의 키 유출 차단 (`.gitignore` 로 `.env` 제외, `.env.example` 만 공유)
  · 공개 저장소 노출 시 즉시 악용·과금 위험 — Git 이력은 지워도 남음
  · Gemini 키를 헤더로 전송 — 로그·오류 메시지에 URL 이 찍혀도 키 미노출
- 운영
  · 키 교체(회전)·환경별 값 변경에 코드 수정·재배포 불필요 — 설정과 코드 분리
  · 사람·서버마다 다른 키 사용 가능
  · 과금·쿼터 걸린 서비스의 사고 예방
- 이 프로그램의 장치: 셸 환경변수가 `.env` 보다 우선 · 키 미설정이면 즉시 종료 + 원인 안내 · `cp -n` 안내(덮어쓰기 사고 실제 경험)

### 3-9. LLM 이 깨진 JSON 을 낼 때 (항목 4)

- 예방 — JSON 모드 + `responseSchema` 로 생성 단계에서 형식 강제
- 파싱 전략 — 코드 펜스 제거 → `json.loads` → 실패 시 앞뒤 설명문을 잘라 첫 `{` ~ 마지막 `}` 재해석
- 재시도 프롬프트 변경 — 원래 프롬프트 + "이전 응답은 JSON 으로 해석되지 않았습니다 — <실패 이유>. 필수 키 recommended_city·weather·events·reason 만 담은 순수 JSON 을 다시 출력, 문장이 길면 줄여서라도 JSON 을 끝까지 닫을 것"
  · 실패 이유 전달 → 같은 실수 반복 방지
  · "짧게·끝까지 닫기" → 길이 제한으로 잘린 불완전 JSON 대비
- 횟수 — 최대 1회 (`for attempt in (1, 2)`), 2회 실패 시 `PARSE_ERROR` 로 종료 — 무한 재시도 금지
- 기록 — 복구돼도 첫 실패를 errors 에 보존
- 코드 — `llm_api.recommend()` · `_recommend_prompt(retry_reason)` · `parse_json_text()`

### 3-10. 검색 결과 0건일 때 유용한 리포트 (항목 4)

- 중단 없음 — 빈 목록 + `EMPTY_RESULT` 기록 후 리포트 단계 진행
- 표기 — `- 데이터 없음 (장소 검색 결과 0건)`: 지어낸 맛집이 없다는 사실을 명시
- 대안 제공 — `- 직접 찾기: [지도에서 '<지역> 맛집' 검색](링크)` (Kakao/Naver 지도 검색 URL)
- 일정 — 특정 상호 없이 지역 대표 음식 위주의 식사 제안, 추천 이유·날씨·행사·일정은 그대로 → 리포트 가치 유지
- 보장 — `check_report()` 가 0건 지역의 `데이터 없음` 표기 확인, 빠지면 데이터만으로 대체 리포트
- 재검색 안 함(과제 정책) — 대신 검색 전 검색어 보정으로 0건 자체를 줄임
- CLI 조치 안내 — "리포트의 '직접 찾기' 링크로 지도에서 찾아보기"

### 3-11. 같은 날짜 반복 실행 비용 줄이기 — 캐싱 (항목 4)

- 방법 — 원본 JSON(`results/<날짜>_raw.json`) 재사용: 파일명 = 캐시 키
- 효과 — 2회째부터 Gemini 1차 추천 1회 + 지도 검색 3회 생략, 리포트(Gemini 1회)만 재생성
- 코드 위치 — `pipeline.run()` 시작부의 `_load_cache()` → 쓸 수 있으면 [1/3]·[2/3] 건너뜀
- 캐시를 쓰지 않는 조건(`_cache_miss_reason()`) — 실패를 캐시로 굳히지 않기 위해
  · 1차 추천 실패 기록 · 맛집 검색 오류(인증·쿼터·네트워크) 기록 · 지역 수/맛집 수 옵션 불일치 · 깨진 파일
- 강제 갱신 — `--no-cache`
- 더 줄이는 제안 — 리포트도 재사용: [3/3] 앞에서 같은 입력(raw 내용 해시)으로 만든 `.md` 가 있으면 LLM 호출 생략 → 재실행 호출 0회

### 3-12. (What-if) 추천 지역이 너무 넓거나 애매할 때 — 검색어 정규화 (항목 4)

- 1차 예방 — 프롬프트에 "시·군 단위, 도 단위 금지" 명시
- 2차 보정 — `place_api.normalize_city()` (검색어에만 적용, 리포트의 지역명은 그대로)
  · 괄호 설명 제거: `제주(서귀포)` → `제주`
  · 복수 표기는 첫 지역: `여수/순천` → `여수`
  · 여러 단어는 가장 구체적인 마지막 단어: `경북 경주시` → `경주` · `부산 해운대` → `해운대`
  · 행정구역 접미사 제거: `부산광역시` → `부산` · `서울특별시` → `서울` · `강릉시` → `강릉` · `양양군` → `양양`
  · 도 단위는 대표 여행 도시로: `강원도` → `강릉` · `경상북도` → `경주` · `전라남도` → `여수` (표 `PROVINCE_TO_CITY` 만 고치면 기준 변경)
- 보정 사실을 로그에 표시 — `경상북도: 검색어 보정: '경상북도' → '경주 맛집'`
- 확장 아이디어
  · 주소 검색 API 로 지역 중심 좌표를 먼저 얻고, 키워드 검색에 좌표·반경(`x`, `y`, `radius`)을 걸어 범위 제한
  · LLM 에 대표 동네까지 출력시키기(`제주 애월`)
  · 결과의 주소가 추천 지역과 다른 시·도면 걸러 내기

---

## 4. 과제 목표 4가지 — 한 줄 답

- REST 요청/응답과 GET/POST — 조회는 GET(쿼리스트링), 생성·긴 입력은 POST(JSON 본문), 응답은 상태 코드 + JSON 본문
- LLM 출력 구조화 흐름 — JSON 모드·스키마로 받은 `recommended_city` 를 `"<지역> 맛집"` 검색어로 바꿔 지도 API 입력으로 사용
- 대표 오류와 대응 원칙 — 인증(키 점검·재시도 안 함) · 쿼터(대기·캐시) · 네트워크(타임아웃·1회 재시도) · 파싱(프롬프트 수정 1회 재시도) → 실패 단계만 격리, 리포트는 항상 생성, errors 에 기록
- `.env`/환경변수 — 키 유출 방지 + 코드 수정 없는 키 교체 + 과금 사고 예방

---

## 5. 예상 꼬리 질문

- SDK 대신 `requests` 직접 호출 이유 — 요청/응답 구조(메서드·헤더·본문·상태 코드)가 코드에 그대로 보이게
- 재시도를 1회로 제한한 이유 — 과제 조건(무한 재시도 금지) · 무료 쿼터·비용 보호
- 일시 오류만 재시도하는 이유 — 5xx·연결 실패는 다시 보내면 성공할 수 있음, 401·429 는 결과 동일·한도만 소모
- 파일명이 실행 날짜가 아닌 여행 날짜인 이유 — 과제 예시(`results/20XX-03-15_travel_plan.md`)와 같은 규칙, 같은 `-date` 캐싱의 키
- 대표 지역 = 최상위 4키, 나머지 = `other_cities` 인 이유 — 과제 최소 스키마를 LLM 응답 그대로 만족 + 보너스 확장
- 테스트가 네트워크 없이 도는 방법 — `requests.get/post` 를 가짜 응답 함수로 교체(monkeypatch)
