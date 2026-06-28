// create_notion_db.mjs
// Notion 데이터베이스를 명세된 7개 속성으로 생성하고 DB ID를 출력한다.
//
// 실행 방법:
//   NOTION_TOKEN=secret_xxx NOTION_PARENT_PAGE_ID=페이지ID node create_notion_db.mjs
//
// 또는 .env 파일에 값을 채운 뒤:
//   node --env-file=.env create_notion_db.mjs   (Node 20.6+)
//
// Node.js 18+ (글로벌 fetch 사용, 외부 의존성 없음)

const NOTION_TOKEN = process.env.NOTION_TOKEN;
const NOTION_PARENT_PAGE_ID = process.env.NOTION_PARENT_PAGE_ID;
const NOTION_VERSION = '2022-06-28';

function fail(msg) {
  console.error(`❌ ${msg}`);
  process.exit(1);
}

if (!NOTION_TOKEN) fail('환경변수 NOTION_TOKEN 이 설정되지 않았습니다.');
if (!NOTION_PARENT_PAGE_ID) fail('환경변수 NOTION_PARENT_PAGE_ID 가 설정되지 않았습니다.');

// 명세 §4: 생성할 Notion DB 속성 (7개)
const properties = {
  '제목': { title: {} },
  '요약문': { rich_text: {} },
  '원문 링크': { url: {} },
  '발행 일시': { date: {} },
  '출처': {
    select: {
      options: [
        { name: '헤럴드', color: 'blue' },
        { name: 'BBC', color: 'red' },
      ],
    },
  },
  '중복 방지 키': { rich_text: {} },
  '썸네일': { files: {} },
};

const body = {
  parent: { type: 'page_id', page_id: NOTION_PARENT_PAGE_ID },
  title: [
    { type: 'text', text: { content: '뉴스 요약 자동화 DB' } },
  ],
  properties,
};

const res = await fetch('https://api.notion.com/v1/databases', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${NOTION_TOKEN}`,
    'Notion-Version': NOTION_VERSION,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify(body),
});

const data = await res.json();

if (!res.ok) {
  console.error('❌ Notion DB 생성 실패');
  console.error(`HTTP ${res.status} ${res.statusText}`);
  console.error(JSON.stringify(data, null, 2));
  if (data.code === 'object_not_found') {
    console.error('\n→ NOTION_PARENT_PAGE_ID 가 올바른지, 그리고 해당 페이지에');
    console.error('  integration이 Connections로 추가되었는지 확인하세요.');
  }
  process.exit(1);
}

console.log('✅ Notion DB 생성 완료');
console.log(`Database ID: ${data.id}`);
console.log('→ .env의 NOTION_DATABASE_ID에 위 ID를 입력하세요.');
