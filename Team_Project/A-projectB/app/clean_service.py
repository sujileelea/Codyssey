"""`clean` 서브커맨드 실행 (담당: 혜민 · 통합 수정: owner).

raw_news → 정제 규칙 → 중복 정책 → news. 한 건의 실패가 전체를 중단시키지 않는다.
"""

from __future__ import annotations

import logging

import storage
from cleaner import clean_article, normalize_url
from config import AppConfig

logger = logging.getLogger(__name__)


def clean_saved_articles(
    config: AppConfig,
    duplicate_policy: str | None = None,
    *,
    all_raw: bool = False,
    limit: int | None = None,
) -> dict[str, int]:
    """저장된 원본 뉴스를 정제하여 news 테이블에 저장합니다."""
    policy = duplicate_policy or config.cleaning.get("duplicate_policy", "skip")
    categories = config.categories
    category_map = config.cleaning.get("category_map", {})

    raw_articles = storage.get_unprocessed_raw(limit=limit, all_raw=all_raw)
    counts = {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0}
    processed_ids: list[int] = []

    logger.info("정제 대상: %s건 (정책=%s)", len(raw_articles), policy)

    for row in raw_articles:
        raw_id = int(row["id"])
        article = dict(row)
        try:
            # RSS 건은 섹션(카테고리) 정보가 없으므로 같은 URL의 크롤링 raw 행에서 보강한다.
            if not article.get("category"):
                article["category"] = storage.find_category_by_url(normalize_url(article.get("url")))

            cleaned = clean_article(article, categories, category_map)
            action, news_id = storage.save_clean_article(raw_id, cleaned, policy)
            counts[action] += 1
            logger.info("raw_id=%s 처리 완료: %s, news_id=%s", raw_id, action, news_id)
        except ValueError as error:
            counts["failed"] += 1
            logger.warning("raw_id=%s 정제 실패: %s", raw_id, error)
        finally:
            processed_ids.append(raw_id)

    storage.mark_raw_processed(processed_ids)
    logger.info(
        "정제 완료: 신규 %s건, 수정 %s건, 중복 %s건, 실패 %s건",
        counts["inserted"], counts["updated"], counts["skipped"], counts["failed"],
    )
    return counts
