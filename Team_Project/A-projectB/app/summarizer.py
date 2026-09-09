"""AI 뉴스 요약 (담당: 진성 · Gemini 전환·통합 수정: owner).

- 대상 선택: --unsummarized(기본) / --all / --id
- 이미 요약된 뉴스는 기본 스킵, --force 로 재요약
- API 실패는 로깅 후 스킵하고 다음 뉴스를 계속 처리한다
- 요약 결과는 news.summary(+ summary_model, summarized_at)에 저장한다
"""

from __future__ import annotations

import logging

import storage
from ai_client import AIClient
from config import AppConfig

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTIONS = """당신은 뉴스 기사를 한국어로 요약하는 편집자다.
다음 조건을 반드시 지킨다.
1. 핵심 내용을 중심으로 3~5문장으로 요약한다.
2. 객관적인 문체를 사용하고 불필요한 수식·감탄을 제거한다.
3. 원문에 없는 내용, 수치, 인물, 전망을 추가하지 않는다.
4. 제목을 반복하지 말고 본문의 사실을 압축한다.
5. 요약문만 출력한다. 머리말·꼬리말·마크다운을 붙이지 않는다.
"""


def build_summary_prompt(title: str, content: str, max_chars: int, max_input_chars: int = 6000) -> str:
    body = content if len(content) <= max_input_chars else content[:max_input_chars] + " …(이하 생략)"
    return (
        f"다음 뉴스 기사를 {max_chars}자 이내로 요약하라.\n\n"
        f"[제목]\n{title}\n\n[본문]\n{body}\n"
    )


def summarize_text(
    client: AIClient,
    title: str,
    content: str,
    *,
    max_chars: int,
    max_attempts: int = 2,
) -> str | None:
    """요약문을 반환한다. 재시도 후에도 실패하면 None (호출부에서 스킵)."""
    prompt = build_summary_prompt(title, content, max_chars)
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            summary = client.generate_text(SYSTEM_INSTRUCTIONS, prompt, max_output_tokens=600)
            if summary:
                return summary
            raise RuntimeError("빈 응답")
        except Exception as error:  # SDK 오류·네트워크·빈 응답 모두 재시도
            last_error = error
            logger.warning("AI 요약 시도 %s/%s 실패: %s", attempt, max_attempts, error)
    logger.error("AI 요약 최종 실패: %s", last_error)
    return None


def run_summarize(
    config: AppConfig,
    client: AIClient,
    *,
    mode: str = "unsummarized",
    news_ids: list[int] | None = None,
    limit: int | None = None,
    force: bool = False,
) -> dict[str, int]:
    """요약 대상을 골라 AI 요약을 실행하고 저장한다. {success, failed, skipped} 반환."""
    summary_cfg = config.summary
    max_chars = int(summary_cfg.get("max_chars", 300))
    max_attempts = int(summary_cfg.get("max_ai_attempts", 2))
    limit = limit or (None if mode == "id" else int(summary_cfg.get("default_limit", 10)))

    targets = storage.get_news_for_summarize(mode, news_ids, limit, force)
    counts = {"success": 0, "failed": 0, "skipped": 0}

    if mode == "id" and news_ids:
        found = {row["id"] for row in targets}
        for missing in [i for i in news_ids if i not in found]:
            logger.error("ID=%s 인 뉴스를 찾을 수 없습니다.", missing)
            counts["failed"] += 1

    logger.info("요약 대상: %s건 (mode=%s, force=%s)", len(targets), mode, force)
    total = len(targets)
    for index, row in enumerate(targets, start=1):
        news_id = int(row["id"])
        if row.get("summary") and not force:
            counts["skipped"] += 1
            logger.info("[%s/%s] ID=%s 이미 요약됨 → 스킵", index, total, news_id)
            continue

        summary = summarize_text(client, row["title"], row["content"], max_chars=max_chars, max_attempts=max_attempts)
        if summary is None:
            counts["failed"] += 1
            logger.warning("[%s/%s] ID=%s 요약 실패 → 스킵", index, total, news_id)
            continue

        storage.save_summary(news_id, summary, getattr(client, "model", type(client).__name__))
        counts["success"] += 1
        logger.info("[%s/%s] ID=%s 요약 완료 (%s자 → %s자)", index, total, news_id, len(row["content"]), len(summary))

    logger.info("요약 완료: %s건 성공, %s건 실패, %s건 스킵", counts["success"], counts["failed"], counts["skipped"])
    return counts
