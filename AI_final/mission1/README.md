# AI 쇼핑 관심도 시계열 분석

Google Trends 검색 관심도로 'AI를 활용한 쇼핑'에 대한 관심이 언제·얼마나 커졌는지, 왜 꺾였는지 분석한다.

- 분석 리포트: [`REPORT.md`](REPORT.md)
- 주 데이터: 미국 'AI shopping' 계열 검색어 5종, 주간 261주(2021-10-24~2026-10-18)
- 산출물: 그림 9장(`images/`) · 표(`outputs/`) · 대시보드(`dashboard/index.html`)와 스크린샷 12장(시나리오 7 + 인사이트 설명 화면 5)

## 폴더 구조

```
mission1/
├── REPORT.md                 분석 리포트
├── README.md                 실행 방법 · 데이터 출처 · 요구사항 대조
├── 과제 요약.md               과제 요구사항 · 체크리스트 · 핵심 개념
├── 실행 로그.md               환경 · 데이터 탐색/수집 · 분석 · 고친 오류 · 재현 확인 기록
├── 평가 지침.md               평가자용 확인 순서 · 대시보드 시연 · 설명 질문 대응
├── requirements.txt          의존성(버전 고정)
├── collect.py                데이터 수집(Google Trends · Wikimedia Pageviews)
├── analysis.py               정제 · 분석 · 그림 9장 · 표
├── build_dashboard.py        대시보드 HTML 생성
├── clean.py                  생성 산출물 정리(평가 전 초기화)
├── data/
│   ├── raw/                  수집 원본 CSV 7개(분석 기준 데이터)
│   ├── metadata.json         파일별 출처 · 검색어 · 기간 · 수집 시각
│   └── processed/            정제한 주 데이터 + 파생 지표
├── images/                   그림 01~09
├── outputs/                  표(CSV)와 리포트 수치(key_numbers.json)
└── dashboard/
    ├── index.html            대시보드(파일 하나, 서버·인터넷 불필요)
    └── screenshots/          시나리오별 화면 7장 + 인사이트 설명 화면 5장(insight_1~5)
```

## 실행 방법

개발 환경: macOS · Python 3.13.11(pandas 3.x 가 Python 3.11 이상 필요).

```bash
cd mission1
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python analysis.py          # 그림 9장 · 표 · key_numbers.json 생성(약 10초)
python build_dashboard.py   # dashboard/index.html 생성
open dashboard/index.html   # 브라우저로 열기(Windows 는 start, Linux 는 xdg-open)
```

- `data/raw/` 에 수집 원본이 들어 있어 `collect.py` 없이 바로 재현된다.

### 평가 전 초기화 — 처음부터 다시 만들어 보기

```bash
python clean.py --dry-run   # 지울 목록만 보기
python clean.py             # 생성 산출물 삭제: images/ · outputs/ · data/processed/ · dashboard/index.html · __pycache__/
python analysis.py && python build_dashboard.py   # 다시 생성
git status --short .        # 변경 없음 = 커밋된 결과와 바이트 단위로 같게 재현됨
```

- 지우지 않는 것: 수집 원본(`data/raw/` · `data/metadata.json`) · 대시보드 캡처(`dashboard/screenshots/`) · 코드 · 문서
- 되돌리기: 위 '다시 생성' 명령, 또는 `git restore .`
- 데이터를 새로 받으려면 `python collect.py --force` — Google Trends 요청 사이에 20초씩 쉬어 2~5분 걸린다. 새로 받은 값은 표본이 달라 리포트 수치와 조금 다를 수 있다.

## 데이터 출처 · 수집 방법 · 라이선스

| 파일 | 출처 | 대상 | 기간 · 단위 | 역할 |
|---|---|---|---|---|
| `trends_us_weekly.csv` | Google Trends | 미국 · AI shopping · AI shopping assistant · ChatGPT shopping · agentic commerce · Amazon Rufus | 2021-10-24~2026-10-25 · 주간 | 주 데이터 |
| `trends_us_controls_longtail.csv` | Google Trends | 미국 · AI shopping · online shopping · price comparison · shopping list | 같은 기간 · 주간 | 대조(비슷한 규모의 비AI 쇼핑 검색어) |
| `trends_us_controls_highvol.csv` | Google Trends | 미국 · ChatGPT · Amazon · weather | 같은 기간 · 주간 | 대조(검색량이 큰 일반 검색어) |
| `trends_kr_weekly.csv` | Google Trends | 한국 · AI 쇼핑 | 같은 기간 · 주간 | 한국 비교 |
| `trends_us_daily_2026.csv` | Google Trends | 미국 · AI shopping · price comparison · online shopping | 2026-05-01~2026-09-30 · 일간 | 급락 시점 · 요일 패턴 |
| `wiki_en_agentic_commerce.csv` | Wikimedia Pageviews API | 영어 위키백과 Agentic commerce 문서 · 사용자 조회 | 2025-12-13(문서 생성)~2026-10-25 · 일간 | Google 과 독립된 교차 확인 |
| `wiki_en_online_shopping.csv` | Wikimedia Pageviews API | 영어 위키백과 Online shopping 문서 · 사용자 조회 | 2025-01-01~2026-10-25 · 일간 | 교차 확인 |

- 수집: `collect.py`. Google Trends 는 비공식 클라이언트 `pytrends` 로 웹 화면과 같은 값을 받는다(공식 API 는 비공개 알파). 위키백과는 Wikimedia REST API(`/metrics/pageviews/per-article`, agent=user).
- Google Trends 값: 요청마다 '기간·지역 안 최댓값 = 100' 으로 정규화한 상대 지수. 같은 요청 안의 검색어끼리만 높이를 비교할 수 있고, 0 은 '검색량이 임계값 미만' 이라는 뜻이다. 표본 기반이라 같은 조건으로 다시 받아도 값이 조금 다르다.
- 라이선스 · 주의:
  - Google Trends 데이터는 [Google 서비스 약관](https://policies.google.com/terms) 아래에서 쓸 수 있고, 재사용할 때 출처를 밝혀야 한다 — "Data source: Google Trends (https://www.google.com/trends)" ([Google 도움말](https://support.google.com/trends/answer/4365538)). `pytrends` 는 Google 이 제공하는 도구가 아니므로 짧은 간격의 반복 · 대량 요청을 하지 않는다(429 응답 시 대기 후 재시도).
  - Wikimedia 조회수 데이터는 [CC0](https://dumps.wikimedia.org/other/pageviews/readme.html) 로 공개돼 있다. API 호출 시 `User-Agent` 를 밝힌다.
  - 저장소의 CSV 는 학습 목적의 분석 재현용이며, 원 데이터의 권리는 각 제공자에게 있다.

## 대시보드

`dashboard/index.html` 하나로 동작한다(데이터가 파일 안에 들어 있음, 외부 라이브러리 없음).

- 인사이트로 보기 1~5: 리포트의 인사이트가 드러나는 화면으로 바뀌고 쉬운 설명 · 근거 수치 · 강조 구간이 뜬다(주소 `?insight=1`)
- 묶음: 미국 AI 쇼핑 검색어 5종 · 미국 vs 한국 · 대조(쇼핑 소량 검색어) · 대조(대형 일반 검색어) · 위키백과 조회수 · 교차 확인(Google vs 위키백과)
- 보기: 원값 · 지수(기간 첫 4개 평균 = 100) · 직전 대비 변화율 · 전년 같은 시기 대비
- 집계 단위: 주 · 월 평균 · 분기 평균 / 이동평균: 없음 · 3 · 4 · 8 · 13
- 기간: 시작 · 끝 날짜, 빠른 기간(전체 · 2025~ · 최근 52주 · 급락 전후)
- 계열 켜기/끄기, 사건 · 단절 구간 표시, 마우스 · 방향키 툴팁, 선택 기간 요약 표, 전체 값 표
- 화면 상태는 주소의 `?` 뒤에 저장된다. 예: `dashboard/index.html?g=longtail&view=index&from=2026-03-01` (`at=날짜` 를 붙이면 그 시점 툴팁이 열린다)

시나리오별 화면과 설명은 [`REPORT.md` 8-3절](REPORT.md#8-3-대시보드)에 있다.

## 요구사항 대조

| 요구사항 | 충족 내용 | 위치 |
|---|---|---|
| 시계열 1개 · 100개 이상 · 출처와 기간 | Google Trends 미국 주간 261주(5개 검색어), 출처 · 기간 명시 | REPORT 3절 |
| 분석 질문 3개 이상 | 5개(그래프 확인형 3 · 추가 해석형 2) | REPORT 2절 |
| 기본 정보 · 결측치 · 이상치 처리 기준 | 날짜 누락 · NaN · 0 · 진행 중 주 · 급등 · 구조 단절 기준 | REPORT 4절 · `outputs/data_quality.csv` |
| 시계열 기법 2개 이상 | 이동평균 · 변화율 · 구간 통계 · 변동성 · 요일/분기 집계 · 대조군 지수화 | REPORT 5절 |
| 시각화 2개 이상(권장 3개 이상) | 9장 | `images/` · REPORT 6절 |
| 인사이트 3개 이상(관찰 수치 포함) | 5개, 관찰(Fact) · 해석(가설) · 행동(Action) 구분 | REPORT 7절 |
| 결론 · 한계점 | 질문별 답 · 한계 7가지 | REPORT 9절 |
| AI 사용 로그(작업 · 이유 · 검증) | 작업별 표 + AI 결과를 고친 사례 | REPORT 10절 |
| 재현성(의존성 · 실행 방법 · 출처 · 라이선스) | `requirements.txt` · 이 문서 | README |
| 보너스: 대시보드 | 기간 · 조건을 바꾸는 HTML 대시보드 + 스크린샷 12장(인사이트 설명 화면 5장 포함) + 시나리오 | `dashboard/` · REPORT 8-3 |
| 보너스: 분해 · 예측 | STL 분해(그림 8) · 베이스라인 예측(그림 9) | REPORT 8-1 · 8-2 |
