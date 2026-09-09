# 뉴스 AI 파이프라인 CLI

## 0. 개요

- BBC News 코리아 뉴스를 **수집(RSS + 크롤링) → 정제 → AI 요약 → AI 인사이트 분석 → 시각화·리포트 → 내보내기**까지 하나의 CLI로 연결한 Python 애플리케이션
	- 필수 서브커맨드 6개 + 보너스 3개(`sentiment` `list` `show`)
	- 저장소 SQLite, AI는 Gemini 무료 티어(`gemini-3.5-flash-lite`)

```text
fetch ──▶ raw_news ──▶ clean ──▶ news ──▶ summarize ──▶ analyze ──▶ insights
  (RSS·크롤링)          (정제·중복)        (요약)          (배치→종합)      │
                                              │                              ▼
                                              ├──▶ sentiment ──▶ sentiment_results
                                              ▼
                                        report / export / list / show
```

| 팀원 | 파트 | 모듈 |
| --- | --- | --- |
| **수지** | CLI · 설정 · 로깅 · 수집 · 리포트 · 내보내기 · 통합 | `main.py` `config.py` `log.py` `collector/` `report/` |
| **혜민** | 데이터 저장/정제 | `storage.py` `cleaner.py` `clean_service.py` |
| **진성** | AI 요약 | `summarizer.py` |
| **경학** | AI 인사이트 분석 · 감성 분석(보너스) | `ai_client.py` `repository.py` `insight_analyzer.py` `sentiment_analyzer.py` `models.py` |

---

## 1. 설치

- Python **3.10 이상**

```bash
cd app
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # GEMINI_API_KEY=... 입력 (Google AI Studio 무료 키)
```

- API 키는 코드·`config.json`에 두지 않음 — `config.json`의 `ai.api_key_env`에는 **환경변수 이름**만, 값은 `.env` 또는 셸 환경변수
- `.env` · `data/` · `logs/` · `.venv/`는 git 제외
- 키 없이 파이프라인만 확인: `config.json`의 `ai.provider`를 `"mock"`으로 변경

---

## 2. 실행 순서

```bash
python main.py fetch --limit 10                 # 1. 수집: 섹션 5개 × 10건 크롤링 + RSS 10건 (본문 보강)
python main.py clean                            # 2. 정제·중복 처리 → news
python main.py summarize --unsummarized         # 3. AI 요약 (기본 10건, --limit 로 조정)
python main.py analyze                          # 4. AI 인사이트 분석 (요약된 기사 종합)
python main.py sentiment --limit 20             # 5. [보너스] 감성 분석
python main.py report                           # 6. 리포트 + 차트 (output/)
python main.py export --format xlsx             # 7. 내보내기 (output/exports/)
```

- `analyze`는 **요약이 있는 기사만** 정성 분석에 사용 → `summarize` 선행 필요

---

## 3. 서브커맨드

| 명령 | 주요 옵션 | 설명 |
| --- | --- | --- |
| `fetch` | `--source {rss,crawl,all}` `--limit N` `--category C` `--no-body` | 방법 1(RSS) + 방법 2(크롤링) 수집 → `raw_news`. RSS 건은 기사 페이지 크롤링으로 본문 보강 |
| `clean` | `--duplicate-policy {skip,upsert}` `--all` `--limit N` | 필수 필드 검증 · 텍스트 정규화 · 날짜 통일 · 결측 처리 → 중복 정책 → `news` |
| `summarize` | `--unsummarized`(기본) `--all` `--id ID…` `--limit N` `--force` | Gemini 요약 → `news.summary`. 기요약 건 스킵, 실패는 로깅 후 다음 건 |
| `analyze` | `--date-from` `--date-to` `--category` `--limit` `--sort` `--show ID` `--list` | 조건별 기사를 20건 배치로 분석 후 종합 → `insights` (트렌드 3 · 키워드 6 · 주요 이슈 4) |
| `sentiment` | `--unsentimented`(기본) `--all` `--id ID` + 기간·카테고리·`--limit` | [보너스] 긍정/중립/부정 + score + 근거 → `sentiment_results` |
| `report` | 기간·카테고리 `--top N` `--format {md,txt}` `--out` `--no-charts` | 품질 지표 8종 · TOP N(카테고리·키워드·일자) · 최신 AI 인사이트 · 감성 분포 · 차트 4장 |
| `export` | `--format {csv,jsonl,xlsx}` `--status {all,clean,summarized}` + 기간·카테고리 `--out` | 필터된 뉴스를 파일로 |
| `list` | 기간·카테고리 `--keyword` `--status` `--page` `--page-size` `--sort` | [보너스] 목록 조회 + 페이지네이션 |
| `show` | `ID` | [보너스] 상세 조회 (본문 · 요약 · 감성) |

- 공통 옵션 `--config PATH` · `--verbose`
- 종료 코드 0 성공 · 1 부분 실패 · 2 설정/인자 오류

### 실행 예시

```text
$ python main.py fetch --limit 10
[INFO] 뉴스 수집 시작: source=all, limit=10, category=전체
[INFO] 섹션 페이지 요청: https://www.bbc.com/korean/topics/cxnyk3v82rgt
[INFO] 기사 링크 10개 추출
[INFO] [국내 1/10] 수집 완료: 네팔 홍수 실종 한국인 근무 발전소 터널서 생존자 구조…
...
[INFO] 크롤링 수집: 50건 성공, 0건 실패
[INFO] RSS 요청: https://feeds.bbci.co.uk/korean/rss.xml
[INFO] RSS 항목 10건 파싱
[INFO] RSS 본문 보강: 크롤링 raw와 겹치는 8건은 재요청 생략
[INFO] 수집 완료: 60건 성공, 0건 실패
[INFO] raw 저장소에 저장 완료: …/data/news.db

$ python main.py summarize --unsummarized --limit 3
[INFO] 요약 대상: 3건 (mode=unsummarized, force=False)
[INFO] [1/3] ID=1 요약 완료 (494자 → 225자)
[INFO] [2/3] ID=2 요약 완료 (508자 → 243자)
[INFO] [3/3] ID=3 요약 완료 (3045자 → 236자)
[INFO] 요약 완료: 3건 성공, 0건 실패, 0건 스킵

$ python main.py analyze --category 세계 --date-from 2026-08-01 --date-to 2026-09-09
=== AI 인사이트 분석 결과 ===
저장 ID: 2
조건: 2026-08-01 ~ 2026-09-09 · 카테고리 세계
선택 뉴스: 9건 · 요약 사용 뉴스: 9건

[주요 트렌드]
- 각국 정부 및 국제기구의 제재와 정책 변화가 이어지고 있다
...
```

- 전체 실행 로그와 산출물: `../제출물/실행 결과.md`

---

## 4. 설계

### 뉴스 소스 (BBC News 코리아, 단일 소스)

| 방법 | 대상 | 얻는 것 | 못 얻는 것 |
| --- | --- | --- | --- |
| 1. RSS | `https://feeds.bbci.co.uk/korean/rss.xml` | 제목 · 요약문 · 링크 · 발행시각(RFC 2822) | 카테고리 · 본문 |
| 2. 크롤링 | 섹션 페이지 `bbc.com/korean/topics/<id>` 5개(국내·세계·북한·건강·과학·문화) → 기사 페이지 | 카테고리(섹션) · 본문 전문 · 발행시각(JSON-LD) | — |

- RSS 건의 본문은 기사 페이지 크롤링으로 보강, 카테고리는 정제 단계에서 같은 URL의 크롤링 raw 행을 참조해 보충 (없으면 `기타`)
- RSS 링크의 추적 파라미터(`at_medium=RSS…`)는 URL 정규화로 제거 → 크롤링 건과 같은 URL로 중복 처리
- 기사 본문의 CSS class가 해시형이라 구조 선택자(`main p`)만 사용, `figure` · 바이라인 · 캡션 제외

### 크롤링 정책 준수

- `robots.txt`(2026-09-09 확인): `/korean/` 경로에 차단 규칙 없음
- 요청 간 최소 1.5초 지연(`http.delay_seconds`) · 타임아웃 10초 · 재시도 2회 · 식별 가능한 User-Agent
- 기본 `--limit 10`(섹션당) → 전체 수집 시 약 60회 요청, 학습 목적의 소량 수집만 수행

### 저장소 (SQLite `data/news.db`)

| 테이블 | 역할 | 담당 |
| --- | --- | --- |
| `raw_news` | 수집 원본 · append-only · `collected_at` `source` `collection_method` `raw_data`(원본 JSON) `processed` | 혜민 |
| `news` | 정제 완료(clean) · `url` UNIQUE가 중복 키 · 요약(`summary` `summary_model` `summarized_at`) 포함 | 혜민 · 진성 |
| `insights` | 인사이트 분석 결과 (정량 JSON · 배치 JSON · 최종 JSON) | 경학 |
| `sentiment_results` | 기사별 감성 (`news_id` UNIQUE, upsert) | 경학 |

- raw/clean 분리 이유: 정제 규칙이 바뀌거나 버그가 있어도 raw에서 재정제 가능(`clean --all`), 하류 단계는 clean만 읽어 데이터 계약 단순화

### 정제 규칙과 중복 정책

- **필수 필드**: 제목 · URL · 본문 — 하나라도 없으면 WARNING 후 탈락 (raw는 보존)
- **정규화**: HTML 엔티티·태그 제거 · 공백 정리 · URL 추적 파라미터 제거
- **날짜**: RFC 2822 / ISO 8601 / `YYYY.MM.DD` 등 → `YYYY-MM-DD HH:MM:SS`(KST), 발행일 없으면 수집 시각으로 대체
- **결측**: 소스 → `unknown`, 카테고리 → `기타`
- **`skip`**(기본): 같은 URL이 있으면 저장 안 함 / **`upsert`**: 메타 갱신, 본문은 더 긴 쪽 유지, 본문이 실제로 바뀐 경우에만 요약 초기화

### AI 호출

- Gemini `gemini-3.5-flash-lite` (google-genai SDK) — 인사이트·감성은 JSON Schema 응답, 요약은 자유 텍스트
- 무료 티어 분당 한도 대응: 호출 간격 4.5초 + 429 수신 시 서버 안내 시간만큼 대기 후 재시도 (`ai.min_interval_seconds` `ai.rate_limit_retries`)
- 요약·감성은 건별 실패를 로깅하고 다음 건 계속, 분석은 배치 단위 재시도 후 실패 시 중단
- `provider: mock` → 키 없이 동작 (테스트 · 파이프라인 점검용)

### 리포트

- **품질 지표**: 수집 원본 수(방법별) · 정제 통과 수 · 중복 제거율 · 요약 완료율 · 평균 본문/요약 길이(압축률) · 날짜 결측 · 감성 완료 수
- **TOP N**: 카테고리별 건수 · AI 핵심 키워드 · 일자별 수집 건수
- **AI 인사이트**: 조건에 맞는 최신 `insights` 행 (전체 리포트는 전체 대상 분석 우선)
- **차트**(PNG): 카테고리별 뉴스 수 · 일자별 수집 추이 · 일자별 발행 추이 · 감성 분포 — 한글 폰트 자동 탐지 (macOS AppleGothic / Windows Malgun Gothic / Linux NanumGothic)

---

## 5. 정기 실행 (cron)

- 매일 08:00 · 18:00에 수집 → 정제 → 요약 → 감성 → 리포트, 매주 월요일 09:00에 최근 7일 인사이트 분석 (경로는 실제 위치로 변경)

```bash
crontab -e
```

```cron
# m h dom mon dow  command
0 8,18 * * *  cd /path/to/A-projectB/app && .venv/bin/python main.py fetch --limit 10 >> logs/cron.log 2>&1 \
  && .venv/bin/python main.py clean >> logs/cron.log 2>&1 \
  && .venv/bin/python main.py summarize --unsummarized --limit 20 >> logs/cron.log 2>&1 \
  && .venv/bin/python main.py sentiment --limit 20 >> logs/cron.log 2>&1 \
  && .venv/bin/python main.py report >> logs/cron.log 2>&1
0 9 * * 1  cd /path/to/A-projectB/app && .venv/bin/python main.py analyze --date-from "$(date -v-7d +\%F)" --date-to "$(date +\%F)" >> logs/cron.log 2>&1
```

- cron은 `.env`를 자동으로 읽지 않지만 `config.py`가 `app/.env`를 직접 읽으므로 그대로 동작 — 환경변수로 줄 경우 crontab 상단에 `GEMINI_API_KEY=...`
- `%`는 cron 특수문자라 `\%`로 이스케이프 · Linux `date`는 `-v-7d` 대신 `-d '7 days ago'`
- 같은 URL은 `skip` 정책으로 걸러지므로 하루 두 번 실행해도 중복 저장 없음
- Windows: 작업 스케줄러에 `python main.py fetch …` 작업을 같은 순서로 등록

---

## 6. 테스트

```bash
python -m pytest -q          # 27개: 정제 규칙 · 저장 정책 · 수집 파서 · 요약 흐름 · 분석/감성(Mock)
```

---

## 7. 디렉터리

```text
app/
├── main.py  config.py  log.py  config.json  requirements.txt  .env.example
├── collector/   http_client.py  rss.py  crawler.py  __init__.py(run_fetch)
├── storage.py  cleaner.py  clean_service.py
├── ai_client.py  summarizer.py  repository.py  insight_analyzer.py  sentiment_analyzer.py  models.py
├── report/      charts.py  report.py  exporter.py
├── tests/
├── output/      report.md  report.txt  charts/*.png  exports/*.csv|jsonl|xlsx
├── data/        news.db (gitignore)
└── logs/        app.log (gitignore)
```
