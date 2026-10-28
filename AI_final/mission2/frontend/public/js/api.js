// 백엔드 API 호출 — 주소는 config.js 의 API_BASE_URL(배포 때 Vercel 환경 변수로 생성).
// 모든 오류를 { status, code, message } 로 맞춰 화면이 그대로 보여 줄 수 있게 한다.

const BASE = String((window.APP_CONFIG && window.APP_CONFIG.API_BASE_URL) || "http://localhost:8000").replace(/\/+$/, "");

export const apiBase = BASE;

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function request(path, { method = "GET", body, timeout = 60000, signal } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  if (signal) signal.addEventListener("abort", () => ctrl.abort(), { once: true });
  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    });
  } catch (e) {
    const timedOut = ctrl.signal.aborted;
    throw new ApiError(0, timedOut ? "TIMEOUT" : "NETWORK",
      timedOut ? "서버 응답이 늦습니다. 잠시 뒤 다시 시도해 주세요." : "서버에 연결하지 못했습니다. 네트워크와 서버 상태를 확인해 주세요.");
  } finally {
    clearTimeout(timer);
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const d = data && data.detail;
    const message = (d && d.message) || (typeof d === "string" ? d : `요청이 실패했습니다(${res.status}).`);
    throw new ApiError(res.status, (d && d.code) || "HTTP_" + res.status, message);
  }
  return data;
}

export const api = {
  health: (timeout) => request("/health", { timeout }),
  summary: () => request("/api/data/summary"),
  statistics: (maWindow) => request(`/api/data/statistics?ma_window=${maWindow}`),
  prompt: () => request("/api/chat/prompt"),
  listData: () => request("/api/data?order=asc&limit=1000"),
  createData: (row) => request("/api/data", { method: "POST", body: row }),
  updateData: (id, row) => request(`/api/data/${encodeURIComponent(id)}`, { method: "PUT", body: row }),
  deleteData: (id) => request(`/api/data/${encodeURIComponent(id)}`, { method: "DELETE" }),
  listConversations: () => request("/api/conversations?limit=50"),
  getConversation: (id) => request(`/api/conversations/${encodeURIComponent(id)}`),
  saveConversation: (title, messages) => request("/api/conversations", { method: "POST", body: { title: title || null, messages } }),
  deleteConversation: (id) => request(`/api/conversations/${encodeURIComponent(id)}`, { method: "DELETE" }),
  chat: (payload) => request("/api/chat", { method: "POST", body: payload, timeout: 90000 }),
};
