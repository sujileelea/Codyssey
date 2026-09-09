"""`fetch` 서브커맨드 실행: RSS(방법 1) + 크롤링(방법 2) → raw_news."""

from __future__ import annotations

import logging

import storage
from cleaner import normalize_url
from collector.crawler import crawl_topics, enrich_body
from collector.http_client import FetchError, HttpClient
from collector.rss import fetch_rss
from config import AppConfig

logger = logging.getLogger(__name__)


def _save_records(records: list[dict]) -> int:
    saved = 0
    for record in records:
        storage.save_raw_article(record)
        saved += 1
    return saved


def run_fetch(
    config: AppConfig,
    *,
    source: str = "all",
    limit: int = 20,
    category: str | None = None,
    with_body: bool = True,
) -> tuple[int, int]:
    """뉴스를 수집해 raw 저장소에 저장한다. (성공 건수, 실패 건수) 반환."""
    client = HttpClient(config.http)
    crawl_cfg = config.sources["crawl"]
    rss_cfg = config.sources["rss"]
    success = 0
    failed = 0

    logger.info("뉴스 수집 시작: source=%s, limit=%s, category=%s", source, limit, category or "전체")

    if source in ("crawl", "all"):
        categories = [category] if category else None
        records, crawl_failed = crawl_topics(crawl_cfg, client, categories=categories, limit_per_topic=limit)
        failed += crawl_failed
        success += _save_records(records)
        logger.info("크롤링 수집: %s건 성공, %s건 실패", len(records), crawl_failed)

    if source in ("rss", "all"):
        try:
            records = fetch_rss(rss_cfg, client, limit=limit)
        except FetchError as error:
            logger.error("RSS 수집 실패: %s", error)
            records = []
            failed += 1
        if with_body and records:
            # 같은 기사를 크롤링에서 이미 받아왔다면 본문을 재요청하지 않는다 (요청 최소화).
            need_body = [r for r in records if not storage.raw_url_exists(normalize_url(r["url"]))]
            reuse = len(records) - len(need_body)
            if reuse:
                logger.info("RSS 본문 보강: 크롤링 raw와 겹치는 %s건은 재요청 생략", reuse)
            failed += enrich_body(need_body, crawl_cfg, client)
        # 저장 시 URL은 추적 파라미터를 뗀 정규화 값으로 둔다 (raw_data에는 원본 링크 보존).
        for record in records:
            record["original_link"] = record["url"]
            record["url"] = normalize_url(record["url"])
        success += _save_records(records)
        logger.info("RSS 수집: %s건 저장", len(records))

    logger.info("수집 완료: %s건 성공, %s건 실패", success, failed)
    logger.info("raw 저장소에 저장 완료: %s", storage.DB_PATH)
    return success, failed
