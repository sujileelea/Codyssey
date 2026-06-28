# Claude Code 구현 지시서: n8n 뉴스 요약 자동화 워크플로우

> **이 문서를 Claude Code에 그대로 전달하여 구현을 시작하세요.**
> Claude Code는 이 문서의 명세를 기반으로 아래 파일들을 생성해야 합니다.

---

## 1. 생성할 파일 목록

```
project/
├── workflow.json            # n8n Import용 워크플로우 (핵심 산출물)
├── create_notion_db.mjs     # Notion DB 생성 스크립트
├── validate.mjs             # 검증 보조 도구 (실행 현황 조회)
└── .env.example             # 환경변수 템플릿
```

---

## 2. 실행 환경

| 항목 | 내용 |
|---|---|
| n8n | **로컬 self-host** (무료) — `npx n8n` 또는 Docker |
| n8n 접속 주소 | `http://localhost:5678` |
| 자동화 플랫폼 버전 | n8n v1.x (커뮤니티 에디션) |
| AI 텍스트 모델 | OpenAI GPT-4o mini |
| AI 이미지 모델 | OpenAI DALL-E 3 |
| 저장 도구 | Notion API v2022-06-28 |
| 스크립트 런타임 | Node.js 18+ (ESM, .mjs) |

### n8n 로컬 실행 방법 (owner가 선택)

**방법 A — npx (Node.js만 있으면 됨)**
```bash
npx n8n
```

**방법 B — Docker**
```bash
docker run -it --rm --name n8n \
  -p 5678:5678 \
  -v ~/.n8n:/home/node/.n8n \
  n8nio/n8n
```

브라우저에서 `http://localhost:5678` 접속 후 최초 계정 생성.
스케줄 트리거가 자동 실행되려면 n8n이 실행 중이어야 하므로,
워크플로우를 테스트하는 동안 컴퓨터를 켜두어야 한다.

---

## 3. workflow.json 명세

### 3-1. 워크플로우 개요

n8n의 JSON Import 포맷으로 완성된 워크플로우를 생성한다.
파일을 n8n UI에서 `Settings → Import workflow`로 바로 불러올 수 있어야 한다.

### 3-2. 노드 구성 및 흐름

아래 순서대로 노드를 연결한다. 노드 type은 n8n 커뮤니티 v1.x 기준이며,
Claude Code가 실제 설치된 n8n 버전에 맞게 typeVersion을 조정할 수 있다.

```
[Node 1] Schedule Trigger
  type: n8n-nodes-base.scheduleTrigger
  - rule: CRON "0 8,20 * * *" (매일 8:00, 20:00)
  - timezone: Asia/Seoul

  → [Node 2a] Herald RSS Read
      type: n8n-nodes-base.rssFeedRead
      - url: "{{$env.HERALD_RSS_URL}}"

    → [Node 3a] Herald Keyword Filter
        type: n8n-nodes-base.filter
        - 조건: 제목(title) 또는 본문(content/contentSnippet)에
                포함 키워드 하나 이상 포함
                AND 단독 제외 키워드 없음
        - 포함 키워드(한국어): AI, 인공지능, 머신러닝, 딥러닝,
          생성형 AI, LLM, 클라우드, 사이버보안, 소프트웨어,
          자동화, 데이터센터, IT, 테크, 플랫폼
        - 단독 제외 키워드: 임베디드, 하드웨어, 로봇
          (단, "AI 로봇"처럼 포함 키워드와 함께 있으면 통과)
        - 필수 필드 검사: title, link, pubDate, content 또는
          contentSnippet 모두 비어있지 않을 것

      → [Node 4a] Herald Limit
          type: n8n-nodes-base.limit
          - maxItems: 5

  → [Node 2b] BBC RSS Read
      type: n8n-nodes-base.rssFeedRead
      - url: "{{$env.BBC_RSS_URL}}"

    → [Node 3b] BBC Keyword Filter
        type: n8n-nodes-base.filter
        - 포함 키워드(영문): AI, artificial intelligence,
          machine learning, deep learning, generative AI,
          LLM, cloud, cybersecurity, cyber security, software,
          automation, data center, tech, technology, platform
        - 단독 제외 키워드: embedded, hardware, robotics, robot
          (단, "AI robot"처럼 포함 키워드와 함께 있으면 통과)
        - 필수 필드 검사 동일

      → [Node 4b] BBC Limit
          type: n8n-nodes-base.limit
          - maxItems: 5

[Node 5] Merge
  type: n8n-nodes-base.merge
  - mode: append (4a, 4b의 결과를 단순 합산)

  → [Node 6] Add Source & AI Score
      type: n8n-nodes-base.set
      - 아래 필드를 추가한다:
        source: link에 "herald" 포함 시 "헤럴드", 나머지 "BBC"
        ai_score: title 또는 content에 아래 AI 핵심 키워드 포함 시 1, 아니면 0
                  핵심 키워드: AI, artificial intelligence, 인공지능, 생성형 AI,
                               generative AI, LLM, 머신러닝, machine learning
        pub_date_str: pubDate를 ISO 8601 문자열로 정규화

      → [Node 7] Sort
          type: n8n-nodes-base.sort
          - 1순위: ai_score 내림차순
          - 2순위: pubDate 내림차순

        → [Node 8] Select 1 Article
            type: n8n-nodes-base.limit
            - maxItems: 1

          → [Node 9] Generate URL Hash
              type: n8n-nodes-base.crypto
              - action: Hash
              - type: SHA256
              - value: "{{$json.link}}"
              - field name: url_hash

            → [Node 10] Build Dedup Key
                type: n8n-nodes-base.set
                - dedup_key: "{{$json.url_hash}}|{{$json.guid ?? ''}}"
                  (GUID가 없으면 url_hash만 사용: "{{$json.url_hash}}|")

              → [Node 11] Notion Dedup Check
                  type: n8n-nodes-base.notion
                  - operation: Database Page: Get Many
                  - databaseId: "{{$env.NOTION_DATABASE_ID}}"
                  - filter: 중복 방지 키 (Text) equals "{{$json.dedup_key}}"
                  - On Error: Continue (결과 없어도 다음 단계 진행)

                → [Node 12] Is Duplicate?
                    type: n8n-nodes-base.if
                    - 조건: Notion Get Many 결과 배열 길이 > 0
                    - true (중복) → [Node 12-skip] No Operation (스킵, 로그)
                    - false (신규) → [Node 13] OpenAI Summary

                  [Node 13] OpenAI Summary
                    type: n8n-nodes-base.openAi
                    - operation: Text: Message a Model
                    - model: gpt-4o-mini
                    - On Error: Retry (maxTries: 2)
                    - prompt: (아래 §3-3 참고)

                  → [Node 14] Parse AI JSON
                      type: n8n-nodes-base.set
                      - is_target: JSON.parse($json.content).is_target
                      - summary_lines: JSON.parse($json.content).summary
                      - image_prompt: JSON.parse($json.content).image_prompt
                      - ai_reason: JSON.parse($json.content).reason

                    → [Node 15] Is AI/IT Target?
                        type: n8n-nodes-base.if
                        - 조건: is_target === true
                        - false → [Node 15-skip] No Operation (스킵, 로그)
                        - true → [Node 16] OpenAI Image Generate

                      [Node 16] OpenAI Image Generate
                        type: n8n-nodes-base.openAi
                        - operation: Image: Generate an Image
                        - model: dall-e-3
                        - prompt: "{{$json.image_prompt}}"
                        - size: 1024x1024
                        - On Error: Retry (maxTries: 2)

                      → [Node 17] Download JPEG
                          type: n8n-nodes-base.httpRequest
                          - method: GET
                          - url: "{{$json.data[0].url}}"
                          - responseFormat: file
                          - On Error: Retry (maxTries: 2)

                        → [Node 18] Normalize Fields
                            type: n8n-nodes-base.set
                            - notion_title: $json.title (trim)
                            - notion_summary: summary_lines.join('\n') (trim, 최대 3줄)
                            - notion_url: $json.link
                            - notion_date: pub_date_str (YYYY-MM-DD 형식)
                            - notion_source: $json.source
                            - notion_dedup_key: $json.dedup_key

                          → [Node 19] Notion Save
                              type: n8n-nodes-base.notion
                              - operation: Database Page: Create
                              - databaseId: "{{$env.NOTION_DATABASE_ID}}"
                              - On Error: Retry (maxTries: 2)
                              - properties:
                                  제목 (Title): notion_title
                                  요약문 (Text): notion_summary
                                  원문 링크 (URL): notion_url
                                  발행 일시 (Date): notion_date
                                  출처 (Select): notion_source
                                  중복 방지 키 (Text): notion_dedup_key
                              - 썸네일 (Files & media):
                                  Node 17의 binary 데이터를 파일로 첨부

[Error Handler] 워크플로우 레벨 Error Trigger
  type: n8n-nodes-base.errorTrigger
  → 실패 정보를 n8n 실행 로그에 기록
  → 알림 노드는 No Operation placeholder로 두고
    owner가 필요 시 Slack/Email 노드로 교체할 수 있도록 주석 남기기
```

### 3-3. OpenAI 요약 프롬프트 (Node 13)

```
System: 당신은 IT 뉴스 분류기이자 뉴스 요약기입니다.

User:
아래 기사 제목과 내용을 읽고 AI/IT/소프트웨어/클라우드/사이버보안/IT기업 관련 뉴스인지 판단하세요.
임베디드, 하드웨어, 로봇 단독 주제는 제외하세요.

규칙:
1. AI/IT 뉴스가 아니면 is_target을 false, summary는 빈 배열로 둡니다.
2. AI/IT 뉴스이면 is_target을 true, summary에 한국어 3줄 이내 요약을 작성합니다.
3. 원문에 없는 내용을 추가하지 않습니다.
4. 과장된 해석이나 추측을 넣지 않습니다.
5. image_prompt는 썸네일 이미지 생성용 영어 프롬프트입니다.
6. 반드시 아래 JSON 형식만 출력합니다.

출력 형식:
{
  "is_target": true,
  "summary": ["첫 번째 요약", "두 번째 요약", "세 번째 요약"],
  "reason": "AI/IT 뉴스로 판단한 근거",
  "image_prompt": "Editorial thumbnail for tech news, no text, modern clean style, topic: [뉴스 주제 한 줄 요약]"
}

제목: {{$json.title}}
본문: {{$json.content ?? $json.contentSnippet ?? ''}}
원문 링크: {{$json.link}}
```

### 3-4. 노드 공통 설정

- **API 호출 노드** (Node 11, 13, 16, 17, 19): `On Error → Retry, maxTries: 2`
- **워크플로우 설정**: `Settings → Save Execution Progress: true`
- **Credentials 이름**: workflow JSON 내 credential 참조 이름을
  `"openai_credential"`, `"notion_credential"`로 통일
  (owner가 import 후 실제 credential로 교체)

---

## 4. create_notion_db.mjs 명세

Node.js ESM 스크립트. `NOTION_TOKEN`과 `NOTION_PARENT_PAGE_ID` 환경변수를 읽어
아래 스키마로 Notion 데이터베이스를 생성하고, 생성된 DB ID를 출력한다.

### 실행 방법
```bash
NOTION_TOKEN=secret_xxx NOTION_PARENT_PAGE_ID=페이지ID node create_notion_db.mjs
```

### 생성할 Notion DB 속성

| 속성명 | 타입 | 설정 |
|---|---|---|
| 제목 | title | 기본 title 속성 |
| 요약문 | rich_text | - |
| 원문 링크 | url | - |
| 발행 일시 | date | - |
| 출처 | select | options: [{name:"헤럴드"}, {name:"BBC"}] |
| 중복 방지 키 | rich_text | - |
| 썸네일 | files | - |

스크립트 실행 후 출력 예시:
```
✅ Notion DB 생성 완료
Database ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
→ .env의 NOTION_DATABASE_ID에 위 ID를 입력하세요.
```

---

## 5. validate.mjs 명세

n8n API와 Notion API를 조회하여 워크플로우 실행 현황을 터미널에 출력하는 검증 보조 도구.

### 실행 방법
```bash
node validate.mjs
```

### 출력할 정보

```
=== 워크플로우 실행 현황 ===
최근 5회 실행:
  [2025-01-20 08:00] ✅ 성공 - AI 에이전트의 미래와 전망 저장됨
  [2025-01-19 20:00] ⏭️  스킵 - 중복 기사
  [2025-01-19 08:00] ❌ 실패 - 이미지 생성 오류 (2회 재시도 후 실패)

=== Notion DB 최근 저장 결과 ===
총 저장 건수: 12
최근 저장:
  [2025-01-20] AI 에이전트의 미래와 전망 | BBC | 썸네일 ✅
  [2025-01-18] GPT-5 출시 임박 | 헤럴드 | 썸네일 ✅

=== 중복 방지 키 목록 (최근 10건) ===
  hash_abc123|guid_xyz
  hash_def456|
  ...
```

### 조회 API
- n8n REST API: `GET http://localhost:5678/api/v1/executions?workflowId={{N8N_WORKFLOW_ID}}&limit=5`
  → `N8N_BASE_URL`(기본값 `http://localhost:5678`), `N8N_API_KEY`, `N8N_WORKFLOW_ID` 환경변수 사용
- Notion API: `POST https://api.notion.com/v1/databases/{{NOTION_DATABASE_ID}}/query`
  → 최근 저장 순으로 정렬, 최대 10건 조회

---

## 6. .env.example 명세

```dotenv
# ─── RSS 피드 URL ────────────────────────────────────────
# 아래 URL은 예시입니다. owner가 실제 유효한 URL로 교체하세요.
HERALD_RSS_URL=https://biz.heraldcorp.com/rss/index.xml
BBC_RSS_URL=http://feeds.bbci.co.uk/news/technology/rss.xml

# ─── OpenAI ──────────────────────────────────────────────
OPENAI_API_KEY=sk-...

# ─── Notion ──────────────────────────────────────────────
NOTION_TOKEN=secret_...
# create_notion_db.mjs 실행 전: DB를 만들 상위 페이지 ID 입력
NOTION_PARENT_PAGE_ID=
# create_notion_db.mjs 실행 후: 출력된 DB ID 입력
NOTION_DATABASE_ID=

# ─── n8n (validate.mjs용) ────────────────────────────────
N8N_BASE_URL=http://localhost:5678
# n8n UI → Settings → API → Create API Key
N8N_API_KEY=
# workflow.json import 후 브라우저 URL에서 확인
N8N_WORKFLOW_ID=
```

---

## 7. 구현 시 주의사항

1. **workflow.json credential 참조**: credential 이름을 `"openai_credential"`,
   `"notion_credential"`로 통일하고 JSON 내 placeholder로 처리.
   owner가 import 후 n8n UI에서 실제 credential로 교체.

2. **JPEG 다운로드 (Node 17)**: HTTP Request 노드 응답 형식을 반드시
   `file` (바이너리)로 설정. JSON 형식으로 설정하면 Notion 파일 업로드 불가.

3. **Notion 썸네일 업로드**: Notion n8n 노드에서 바이너리 파일 업로드를
   지원하지 않는 경우, HTTP Request 노드로
   Notion Files Upload API(`POST https://api.notion.com/v1/files/upload`)를
   호출하는 방식으로 대체.

4. **중복 방지 키 구분자**: `url_hash + "|" + guid` 형태.
   GUID가 없으면 `url_hash + "|"`. Notion Filter는 Text equals 방식.

5. **ai_score 계산**: n8n Set 노드 JavaScript 표현식 사용 가능.
   예: `$json.title.toLowerCase().includes('ai') || $json.title.includes('인공지능') ? 1 : 0`

6. **workflow.json 유효성**: import 시 오류 없이 로드되어야 함.
   모든 node id는 UUID v4 형식.

7. **코드 노드 금지**: Code 노드, Execute Command 노드 사용 금지.
   HTTP Request 노드는 이미지 다운로드(Node 17)와 Notion 파일 업로드(필요 시)에만 허용.

---

## 8. 완료 기준 체크리스트

- [ ] `workflow.json`을 n8n에 import했을 때 노드 연결 오류 없음
- [ ] Schedule Trigger가 Asia/Seoul 타임존 08:00, 20:00으로 설정됨
- [ ] Herald 필터에 한국어 키워드, BBC 필터에 영문 키워드가 각각 설정됨
- [ ] Crypto 노드가 URL을 SHA-256으로 해시함
- [ ] OpenAI 텍스트 노드 프롬프트가 §3-3과 일치함
- [ ] OpenAI 이미지 노드가 DALL-E 3을 사용함
- [ ] HTTP Request 노드가 바이너리 응답 형식으로 설정됨
- [ ] API 호출 노드(13, 16, 17, 19) 모두 maxTries: 2로 설정됨
- [ ] `create_notion_db.mjs` 실행 시 Notion DB 7개 속성이 올바르게 생성됨
- [ ] `validate.mjs`가 n8n API와 Notion API 조회 결과를 출력함
- [ ] `.env.example`에 모든 필수 환경변수가 포함됨

---

## 9. Owner 실행 체크리스트

> Claude Code가 파일을 생성한 후, owner가 순서대로 실행한다.

### Phase 1 — 사전 준비 (구현 시작 전)

- [ ] **1** Node.js 18 이상 설치 확인 (`node -v`)
- [ ] **2** OpenAI API 키 발급 — [platform.openai.com](https://platform.openai.com) → API Keys
  - GPT-4o mini + DALL-E 3 사용 가능한 잔액 확인 ($5 내외면 충분)
- [ ] **3** Notion integration 생성 — [notion.so/my-integrations](https://www.notion.so/my-integrations)
  - Integration 이름 입력 → Submit → **Internal Integration Token** 복사
- [ ] **4** Notion에 뉴스 저장용 상위 페이지 생성
  - 해당 페이지 우측 상단 `...` → `Connections` → 위에서 만든 integration 추가
  - 페이지 URL에서 페이지 ID 복사 (32자리 hex)
- [ ] **5** 헤럴드 뉴스 RSS URL 유효성 확인 (브라우저에서 직접 접속해 XML 응답 확인)
- [ ] **6** BBC Technology RSS URL 유효성 확인 (`http://feeds.bbci.co.uk/news/technology/rss.xml`)

### Phase 2 — 환경 설정

- [ ] **7** `.env.example`을 `.env`로 복사
  ```bash
  cp .env.example .env
  ```
- [ ] **8** `.env`에 아래 값 입력
  - `HERALD_RSS_URL` — Phase 1-5에서 확인한 URL
  - `BBC_RSS_URL` — Phase 1-6에서 확인한 URL
  - `OPENAI_API_KEY` — Phase 1-2에서 복사한 키
  - `NOTION_TOKEN` — Phase 1-3에서 복사한 토큰
  - `NOTION_PARENT_PAGE_ID` — Phase 1-4에서 복사한 페이지 ID

### Phase 3 — Notion DB 생성

- [ ] **9** Notion DB 생성 스크립트 실행
  ```bash
  node create_notion_db.mjs
  ```
- [ ] **10** 출력된 Database ID를 `.env`의 `NOTION_DATABASE_ID`에 입력
- [ ] **11** Notion에서 DB가 올바르게 생성됐는지 확인 (7개 속성 존재 여부)

### Phase 4 — n8n 설정

- [ ] **12** n8n 실행
  ```bash
  npx n8n
  # 또는 Docker 사용 시:
  # docker run -it --rm --name n8n -p 5678:5678 -v ~/.n8n:/home/node/.n8n n8nio/n8n
  ```
- [ ] **13** `http://localhost:5678` 접속 → 최초 계정 생성
- [ ] **14** n8n에 OpenAI credential 등록
  - `Settings → Credentials → Add Credential → OpenAI` → API Key 입력
  - 이름: `openai_credential`
- [ ] **15** n8n에 Notion credential 등록
  - `Settings → Credentials → Add Credential → Notion` → Integration Token 입력
  - 이름: `notion_credential`
- [ ] **16** `workflow.json` import
  - 좌측 상단 메뉴 → `Import from file` → `workflow.json` 선택
- [ ] **17** import된 워크플로우에서 credential 연결
  - OpenAI 노드(13, 16) → credential을 `openai_credential`로 설정
  - Notion 노드(11, 19) → credential을 `notion_credential`로 설정
- [ ] **18** n8n API Key 생성 및 `.env` 입력
  - `Settings → API → Create an API key` → 복사
  - `.env`의 `N8N_API_KEY`에 입력
- [ ] **19** 워크플로우 ID 확인 및 `.env` 입력
  - 브라우저 URL: `http://localhost:5678/workflow/[ID]`
  - `.env`의 `N8N_WORKFLOW_ID`에 입력

### Phase 5 — 테스트 및 검증

- [ ] **20** 워크플로우 수동 테스트 실행
  - `Execute Workflow` 버튼 클릭 → 각 노드 결과 확인
- [ ] **21** Notion DB에 기사가 정상 저장됐는지 확인
  - 7개 속성(제목/요약문/원문링크/발행일시/출처/중복방지키/썸네일) 모두 채워졌는지 확인
- [ ] **22** 썸네일 이미지가 JPEG 파일로 저장됐는지 확인
- [ ] **23** 같은 기사로 워크플로우 재실행 → 중복 저장이 안 되는지 확인
- [ ] **24** 검증 보조 도구 실행 및 결과 확인
  ```bash
  node validate.mjs
  ```

### Phase 6 — 활성화 및 제출 준비

- [ ] **25** 워크플로우 `Activate` 버튼 클릭 (스케줄 자동 실행 시작)
- [ ] **26** 스크린샷 촬영
  - n8n 워크플로우 전체 화면
  - 주요 노드 설정 화면 (Trigger, RSS, Filter, OpenAI, HTTP Request, Notion)
  - Notion DB 저장 결과 화면
  - validate.mjs 실행 결과 터미널 화면
- [ ] **27** 스크린샷에 API 키·토큰이 노출되지 않았는지 확인 후 제출
