"""대화 기록 규칙 — 제목 · 미리보기 · 메시지 수를 문서에 함께 저장해 목록을 messages 없이 그린다."""
import re
from datetime import datetime, timezone

from ..errors import AppError

MAX_MESSAGES = 200       # 문서 한 개 1MiB 한도 안쪽으로
TITLE_LEN = 30
PREVIEW_LEN = 60


def _clip(text: str, n: int) -> str:
    text = " ".join(re.sub(r"\*\*|__|`|^#+\s*", "", text, flags=re.M).split())   # 미리보기에 마크다운 기호를 남기지 않는다
    return text if len(text) <= n else text[: n - 1] + "…"


def _plain(messages: list) -> list[dict]:
    """Pydantic Message 또는 dict → Firestore 에 넣을 dict(시각 채움, 빈 tool_calls 제거)."""
    out = []
    for m in messages:
        d = m.model_dump(exclude_none=True) if hasattr(m, "model_dump") else {k: v for k, v in m.items() if v is not None}
        d.setdefault("created_at", datetime.now(timezone.utc))
        if not d.get("tool_calls"):
            d.pop("tool_calls", None)
        out.append(d)
    return out


class ConversationService:
    def __init__(self, repo):
        self.repo = repo

    def list(self, limit: int = 20) -> dict:
        items = self.repo.list(limit)
        return {"count": len(items), "items": items}

    def get(self, conv_id: str) -> dict:
        conv = self.repo.get(conv_id)
        if conv is None:
            raise AppError(404, "NOT_FOUND", "해당 대화를 찾을 수 없습니다. 이미 삭제됐을 수 있습니다.")
        return conv

    def create(self, messages: list, title: str | None = None) -> dict:
        msgs = _plain(messages)
        if len(msgs) > MAX_MESSAGES:
            raise AppError(413, "TOO_LONG", f"한 대화는 메시지 {MAX_MESSAGES}개까지 저장합니다.")
        first_question = next((m["content"] for m in msgs if m["role"] == "user"), msgs[0]["content"])
        return self.repo.create({
            "title": _clip(title or first_question, TITLE_LEN if not title else 100),
            "messages": msgs,
            "message_count": len(msgs),
            "preview": _clip(msgs[-1]["content"], PREVIEW_LEN),
        })

    def append(self, conv_id: str, messages: list) -> dict:
        conv = self.get(conv_id)
        msgs = conv.get("messages", []) + _plain(messages)
        if len(msgs) > MAX_MESSAGES:
            raise AppError(413, "TOO_LONG", f"한 대화는 메시지 {MAX_MESSAGES}개까지 저장합니다. 새 대화를 시작해 주세요.")
        return self.repo.update(conv_id, {"messages": msgs, "message_count": len(msgs),
                                          "preview": _clip(msgs[-1]["content"], PREVIEW_LEN)})

    def delete(self, conv_id: str) -> dict:
        self.get(conv_id)
        self.repo.delete(conv_id)
        return {"id": conv_id, "deleted": True}
