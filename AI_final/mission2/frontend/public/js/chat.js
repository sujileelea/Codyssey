// AI 채팅 + 대화 기록.
// 저장 규칙: 새 대화는 '자동 저장' 이 켜져 있으면 첫 답과 함께 저장되고(POST /api/chat 이 저장),
// 꺼져 있으면 브라우저에만 두었다가 '대화 저장' 으로 저장한다(POST /api/conversations). 저장된 대화는 이어서 자동 저장된다.
import { api } from "./api.js";
import { $, confirmClick, el, fmt, timeAgo, toast } from "./ui.js";

const current = { id: null, title: "새 대화", messages: [] };
let sending = false;

// ── 답변 표시(간단한 마크다운: 문단 · 목록 · **굵게**) — DOM 으로만 만든다 ──
function inline(text) {
  const out = [];
  text.split(/(\*\*[^*]+\*\*)/g).forEach((part) => {
    if (/^\*\*[^*]+\*\*$/.test(part)) out.push(el("b", { text: part.slice(2, -2) }));
    else if (part) out.push(document.createTextNode(part));
  });
  return out;
}
function richText(text) {
  const frag = document.createDocumentFragment();
  for (const block of text.trim().split(/\n{2,}/)) {
    const lines = block.split("\n");
    const isList = lines.every((l) => /^\s*([-*•]|\d+[.)])\s+/.test(l));
    if (isList) {
      const ordered = /^\s*\d/.test(lines[0]);
      frag.append(el(ordered ? "ol" : "ul", {}, lines.map((l) => el("li", {}, inline(l.replace(/^\s*([-*•]|\d+[.)])\s+/, ""))))));
    } else {
      const p = el("p");
      lines.forEach((l, i) => { if (i) p.append(el("br")); p.append(...inline(l)); });
      frag.append(p);
    }
  }
  return frag;
}

function toolLabel(call) {
  const a = call.arguments || {};
  const range = a.start || a.end ? ` ${a.start || "…"} ~ ${a.end || "…"}` : "";
  const extra = a.ma_window ? ` 이동평균 ${a.ma_window}` : a.conversation_id ? " 대화 1건" : "";
  return call.name + range + extra;
}

function messageNode(m, extra = {}) {
  const node = el("div", { class: `msg ${m.role}${extra.error ? " error" : ""}` },
    el("div", { class: "bubble" }, m.role === "assistant" ? richText(m.content) : m.content));
  const meta = [];
  for (const call of m.tool_calls || []) meta.push(el("span", { class: "tag tool", title: JSON.stringify(call.arguments), text: toolLabel(call) }));
  if (extra.context) meta.push(el("span", { text: `요약 주입: ${extra.context.period || "데이터 없음"} · ${fmt(extra.context.count)}개` }));
  if (extra.usage) meta.push(el("span", { text: `토큰 ${fmt(extra.usage.total_tokens)}` }));
  if (meta.length) node.append(el("div", { class: "msg-meta" }, meta));
  return node;
}

function scrollDown() {
  const box = $("messages");
  box.scrollTop = box.scrollHeight;
}

// 주소에 열린 대화를 남겨 새로 고침 · 링크 공유 때 같은 대화를 다시 연다(?c=<대화 ID>)
function syncUrl() {
  const url = new URL(location.href);
  if (current.id) url.searchParams.set("c", current.id);
  else url.searchParams.delete("c");
  history.replaceState(null, "", url);
}

function render() {
  const box = $("messages");
  box.replaceChildren();
  if (!current.messages.length) box.append(welcome);
  for (const m of current.messages) box.append(messageNode(m));
  $("chat-heading").textContent = current.title;
  syncSaveUi();
  syncUrl();
  scrollDown();
}

function syncSaveUi() {
  const saved = !!current.id;
  const auto = $("autosave");
  auto.disabled = saved;
  auto.closest("label").title = saved ? "저장된 대화는 이어서 자동 저장됩니다" : "질문과 답을 자동으로 대화 기록에 저장";
  if (saved) auto.checked = true;
  $("save-chat").hidden = saved || auto.checked || !current.messages.length;
  if ($("save-chat").hidden) $("save-form").hidden = true;
  document.querySelectorAll(".conv-item").forEach((li) => li.classList.toggle("active", li.dataset.id === current.id));
}

// ── 보내기 ──
async function send(text) {
  const question = text.trim();
  if (!question || sending) return;
  sending = true;
  $("send").disabled = true;
  $("question").value = "";
  const box = $("messages");
  if (welcome.isConnected) welcome.remove();

  const userMsg = { role: "user", content: question };
  box.append(messageNode(userMsg));
  const typing = el("div", { class: "msg assistant", "aria-label": "답변 생성 중" },
    el("div", { class: "bubble" }, el("span", { class: "typing" }, el("i"), el("i"), el("i")),
      el("span", { class: "muted", text: "  데이터 요약을 넣어 답을 만드는 중…" })));
  box.append(typing);
  scrollDown();
  const slowNote = setTimeout(() => {
    typing.querySelector(".muted").textContent = "  서버가 깨어나는 중이면 1분 가까이 걸릴 수 있어요…";
  }, 12000);

  const autosave = $("autosave").checked;
  const payload = { message: question, save: autosave || !!current.id };
  if (current.id) payload.conversation_id = current.id;
  else payload.history = current.messages.slice(-20).map(({ role, content }) => ({ role, content }));

  try {
    const res = await api.chat(payload);
    const reply = { role: "assistant", content: res.reply, tool_calls: res.tool_calls };
    current.messages.push(userMsg, reply);
    typing.replaceWith(messageNode(reply, { context: res.context, usage: res.usage }));
    if (res.saved && !current.id) {
      current.id = res.conversation_id;
      current.title = question.length > 30 ? question.slice(0, 29) + "…" : question;
      $("chat-heading").textContent = current.title;
      syncUrl();
    }
    if (res.notice) toast(res.notice, true);
    if (res.saved) loadConversations();
  } catch (e) {
    typing.replaceWith(messageNode({ role: "assistant", content: `⚠ ${e.message}` }, { error: true }));
    $("question").value = question;              // 다시 보낼 수 있게 질문을 돌려놓는다
    box.lastElementChild.previousElementSibling.classList.add("failed");
  } finally {
    clearTimeout(slowNote);
    sending = false;
    $("send").disabled = false;
    syncSaveUi();
    scrollDown();
    $("question").focus();
  }
}

// ── 대화 기록 ──
async function loadConversations() {
  const list = $("conv-list");
  try {
    const { items } = await api.listConversations();
    list.replaceChildren(...items.map((c) => {
      const del = el("button", { class: "conv-del", type: "button", "aria-label": `${c.title} 삭제`, text: "삭제" });
      del.addEventListener("click", () => confirmClick(del, "확인", () => removeConversation(c.id)));
      return el("li", { class: "conv-item", "data-id": c.id },
        el("button", { class: "conv-open", type: "button", onclick: () => openConversation(c.id) },
          el("span", { class: "conv-title", text: c.title }),
          el("span", { class: "conv-meta", text: `메시지 ${c.message_count} · ${timeAgo(c.updated_at)} · ${c.preview}` })),
        del);
    }));
    $("conv-empty").hidden = items.length > 0;
    syncSaveUi();
  } catch (e) {
    list.replaceChildren(el("li", { class: "empty", text: e.message }));
  }
}

async function openConversation(id) {
  if (sending) return;
  try {
    const conv = await api.getConversation(id);
    current.id = conv.id;
    current.title = conv.title;
    current.messages = conv.messages;
    render();
  } catch (e) {
    toast(e.message, true);
    loadConversations();
  }
}

async function removeConversation(id) {
  try {
    await api.deleteConversation(id);
    toast("대화를 삭제했습니다.");
    if (current.id === id) newChat();
    loadConversations();
  } catch (e) {
    toast(e.message, true);
  }
}

function newChat() {
  current.id = null;
  current.title = "새 대화";
  current.messages = [];
  $("autosave").checked = true;
  render();
  $("question").focus();
}

async function saveConversation(title) {
  try {
    const conv = await api.saveConversation(title, current.messages.map(({ role, content, tool_calls }) =>
      (tool_calls && tool_calls.length ? { role, content, tool_calls } : { role, content })));
    current.id = conv.id;
    current.title = conv.title;
    $("chat-heading").textContent = conv.title;
    syncUrl();
    toast(`저장했습니다: ${conv.title} (메시지 ${conv.message_count}개)`);
    loadConversations();
  } catch (e) {
    toast(e.message, true);
  }
}

let welcome;
export function initChat() {
  welcome = $("welcome");
  $("composer").addEventListener("submit", (e) => { e.preventDefault(); send($("question").value); });
  $("question").addEventListener("keydown", (e) => {
    // 한글 조합 중 Enter 는 글자 확정이므로 보내지 않는다
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
      e.preventDefault();
      send($("question").value);
    }
  });
  $("examples").addEventListener("click", (e) => { if (e.target.matches(".chip")) send(e.target.textContent); });
  $("new-chat").addEventListener("click", newChat);
  $("autosave").addEventListener("change", syncSaveUi);
  $("save-chat").addEventListener("click", () => {
    $("save-form").hidden = false;
    $("save-title").focus();
  });
  $("save-cancel").addEventListener("click", () => { $("save-form").hidden = true; });
  $("save-form").addEventListener("submit", (e) => {
    e.preventDefault();
    saveConversation($("save-title").value.trim());
    $("save-title").value = "";
  });
  render();
}

export { loadConversations, openConversation };
