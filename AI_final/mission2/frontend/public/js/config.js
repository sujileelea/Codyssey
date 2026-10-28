// 로컬 개발용 기본값. Vercel 배포에서는 빌드 때 scripts/build-config.mjs 가 환경 변수 API_BASE_URL 로 다시 쓴다.
window.APP_CONFIG = { API_BASE_URL: "http://localhost:8000" };
