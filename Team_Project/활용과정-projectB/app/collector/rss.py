"""방법 1 — RSS 피드 수집 (BBC News 코리아).

RSS 항목에는 제목·요약(description)·링크·발행시각만 있고 카테고리·본문이 없다.
본문은 `--no-body`가 아니면 크롤러로 보강하고, 카테고리는 정제 단계에서 같은 URL의
크롤링 raw 행을 참조해 채운다.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime

from collector.http_client import HttpClient

logger = logging.getLogger(__name__)


def parse_rss(xml_text: str, *, source_name: str, limit: int | None = None) -> list[dict]:
    """RSS XML을 raw dict 목록으로 바꾼다."""
    root = ET.fromstring(xml_text)
    items = root.findall("./channel/item")
    records: list[dict] = []
    collected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for item in items:
        record = {
            "title": (item.findtext("title") or "").strip(),
            "url": (item.findtext("link") or "").strip(),
            "content": (item.findtext("description") or "").strip(),
            "published_at": (item.findtext("pubDate") or "").strip(),
            "source": source_name,
            "category": None,
            "collection_method": "rss",
            "collected_at": collected_at,
            "guid": (item.findtext("guid") or "").strip(),
        }
        if record["url"]:
            records.append(record)
        if limit and len(records) >= limit:
            break
    return records


def fetch_rss(rss_config: dict, client: HttpClient, limit: int | None = None) -> list[dict]:
    """RSS 피드를 요청해 raw dict 목록을 반환한다. 실패 시 FetchError."""
    url = rss_config["url"]
    logger.info("RSS 요청: %s", url)
    response = client.get(url)
    records = parse_rss(response.text, source_name=rss_config.get("name", "rss"), limit=limit)
    logger.info("RSS 항목 %s건 파싱", len(records))
    return records
