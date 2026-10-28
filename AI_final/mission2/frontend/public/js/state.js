// 화면 간 공유 상태 — 데이터 목록 · 요약을 한 번 받아 두고, 바뀌면 구독한 화면에 알린다.
import { api } from "./api.js";

export const state = { points: [], summary: null };
const listeners = new Set();

export function subscribe(fn) {
  listeners.add(fn);
}

function emit() {
  for (const fn of listeners) fn(state);
}

// 데이터가 바뀐 뒤(추가 · 수정 · 삭제) 목록과 요약을 함께 다시 받는다
export async function refresh() {
  const [list, summary] = await Promise.all([api.listData(), api.summary()]);
  state.points = list.items;
  state.summary = summary;
  emit();
  return state;
}
