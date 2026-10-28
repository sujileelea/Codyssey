// Vercel 빌드 단계 — 환경 변수 API_BASE_URL(백엔드 주소)을 public/js/config.js 로 써 넣는다.
// 프레임워크 없는 정적 사이트라 브라우저가 환경 변수를 직접 읽을 수 없으므로, 빌드 때 파일로 굳힌다.
import { writeFileSync } from "node:fs";

const url = (process.env.API_BASE_URL || "").trim().replace(/\/+$/, "");
if (!/^https?:\/\/[^\s"'<>]+$/.test(url)) {
  console.error("API_BASE_URL 환경 변수가 없거나 형식이 올바르지 않습니다(예: https://my-api.onrender.com).");
  process.exit(1);
}
const file = new URL("../public/js/config.js", import.meta.url);
writeFileSync(file, `// 빌드 때 생성됨(scripts/build-config.mjs) — 직접 고치지 않는다.\nwindow.APP_CONFIG = { API_BASE_URL: ${JSON.stringify(url)} };\n`);
console.log("config.js →", url);
