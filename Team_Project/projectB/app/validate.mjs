// validate.mjs
// n8n API와 Notion API를 조회하여 워크플로우 실행 현황을 터미널에 출력하는 검증 보조 도구.
//
// 실행 방법:
//   node validate.mjs
//   (또는 Node 20.6+:  node --env-file=.env validate.mjs)
//
// 필요한 환경변수:
//   N8N_BASE_URL (기본값 http://localhost:5678), N8N_API_KEY, N8N_WORKFLOW_ID
//   NOTION_TOKEN, NOTION_DATABASE_ID
//
// Node.js 18+ (글로벌 fetch 사용, 외부 의존성 없음)

const N8N_BASE_URL = process.env.N8N_BASE_URL || 'http://localhost:5678';
const N8N_API_KEY = process.env.N8N_API_KEY;
const N8N_WORKFLOW_ID = process.env.N8N_WORKFLOW_ID;
const NOTION_TOKEN = process.env.NOTION_TOKEN;
const NOTION_DATABASE_ID = process.env.NOTION_DATABASE_ID;
const NOTION_VERSION = '2022-06-28';

function fmtDate(iso) {
  if (!iso) return '----';
  // 'YYYY-MM-DD HH:mm' 형태로 출력 (로컬 타임존)
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fmtDay(iso) {
  if (!iso) return '----';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// ── n8n 실행 현황 조회 ────────────────────────────────────
async function showExecutions() {
  console.log('=== 워크플로우 실행 현황 ===');

  if (!N8N_API_KEY || !N8N_WORKFLOW_ID) {
    console.log('  (N8N_API_KEY 또는 N8N_WORKFLOW_ID 미설정 — 건너뜀)\n');
    return;
  }

  const url = `${N8N_BASE_URL}/api/v1/executions?workflowId=${encodeURIComponent(N8N_WORKFLOW_ID)}&limit=5`;
  try {
    const res = await fetch(url, {
      headers: { 'X-N8N-API-KEY': N8N_API_KEY, 'accept': 'application/json' },
    });
    if (!res.ok) {
      console.log(`  ⚠️  n8n API 조회 실패: HTTP ${res.status} ${res.statusText}\n`);
      return;
    }
    const json = await res.json();
    const executions = json.data || [];
    if (executions.length === 0) {
      console.log('  실행 이력이 없습니다.\n');
      return;
    }

    console.log(`최근 ${executions.length}회 실행:`);
    for (const ex of executions) {
      const when = fmtDate(ex.startedAt || ex.createdAt);
      let status;
      if (ex.finished && (ex.status === 'success' || !ex.status)) {
        status = '✅ 성공';
      } else if (ex.status === 'error' || ex.stoppedAt && !ex.finished) {
        status = '❌ 실패';
      } else if (ex.status === 'waiting' || ex.status === 'running') {
        status = '⏳ 진행중';
      } else {
        status = `• ${ex.status || 'unknown'}`;
      }
      console.log(`  [${when}] ${status} (id: ${ex.id})`);
    }
    console.log('');
  } catch (err) {
    console.log(`  ⚠️  n8n API 연결 실패: ${err.message}`);
    console.log(`  → n8n이 ${N8N_BASE_URL} 에서 실행 중인지 확인하세요.\n`);
  }
}

// ── Notion DB 최근 저장 결과 조회 ─────────────────────────
async function showNotion() {
  console.log('=== Notion DB 최근 저장 결과 ===');

  if (!NOTION_TOKEN || !NOTION_DATABASE_ID) {
    console.log('  (NOTION_TOKEN 또는 NOTION_DATABASE_ID 미설정 — 건너뜀)\n');
    return;
  }

  const url = `https://api.notion.com/v1/databases/${NOTION_DATABASE_ID}/query`;
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${NOTION_TOKEN}`,
        'Notion-Version': NOTION_VERSION,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        sorts: [{ property: '발행 일시', direction: 'descending' }],
        page_size: 10,
      }),
    });

    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      console.log(`  ⚠️  Notion API 조회 실패: HTTP ${res.status} ${res.statusText}`);
      if (errBody.message) console.log(`     ${errBody.message}`);
      console.log('');
      return;
    }

    const json = await res.json();
    const pages = json.results || [];

    console.log(`총 저장 건수: ${pages.length}${pages.length === 10 ? '+ (최근 10건만 조회)' : ''}`);

    if (pages.length === 0) {
      console.log('  저장된 기사가 없습니다.\n');
      return;
    }

    console.log('최근 저장:');
    const dedupKeys = [];
    for (const page of pages) {
      const props = page.properties || {};
      const title = (props['제목']?.title || []).map((t) => t.plain_text).join('') || '(제목 없음)';
      const source = props['출처']?.select?.name || '?';
      const day = fmtDay(props['발행 일시']?.date?.start);
      const hasThumb = (props['썸네일']?.files || []).length > 0;
      console.log(`  [${day}] ${title} | ${source} | 썸네일 ${hasThumb ? '✅' : '❌'}`);

      const key = (props['중복 방지 키']?.rich_text || []).map((t) => t.plain_text).join('');
      if (key) dedupKeys.push(key);
    }
    console.log('');

    console.log('=== 중복 방지 키 목록 (최근 10건) ===');
    if (dedupKeys.length === 0) {
      console.log('  (없음)');
    } else {
      for (const k of dedupKeys) console.log(`  ${k}`);
    }
    console.log('');
  } catch (err) {
    console.log(`  ⚠️  Notion API 연결 실패: ${err.message}\n`);
  }
}

await showExecutions();
await showNotion();
