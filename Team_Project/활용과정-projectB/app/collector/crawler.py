"""방법 2 — 뉴스 사이트 크롤링 (BBC News 코리아, BeautifulSoup).

- 섹션(topic) 페이지에서 기사 링크 목록을 얻는다 → 카테고리는 여기서 부여한다.
- 기사 페이지에서 제목(h1)·본문(main p)·발행시각(JSON-LD datePublished)을 추출한다.
- 본문 `<p>`의 class는 해시형이라 구조 선택자(`main p`)만 쓰고, 캡션·바이라인은 제외한다.
- 모든 요청은 HttpClient의 타임아웃·재시도·지연을 거친다 (robots.txt: /korean/ 허용 확인, 2026-09-09).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from collector.http_client import FetchError, HttpClient

logger = logging.getLogger(__name__)


def extract_article_links(html_text: str, base_url: str, link_pattern: str, limit: int | None = None) -> list[str]:
    """목록 페이지 HTML에서 기사 URL을 순서 유지·중복 제거로 뽑는다."""
    soup = BeautifulSoup(html_text, "html.parser")
    seen: list[str] = []
    for anchor in soup.select(f'a[href*="{link_pattern}"]'):
        href = anchor.get("href") or ""
        url = urljoin(base_url, href).split("?")[0].split("#")[0]
        if url not in seen:
            seen.append(url)
        if limit and len(seen) >= limit:
            break
    return seen


def fetch_topic_links(base_url: str, topic_id: str, client: HttpClient, link_pattern: str, limit: int | None) -> list[str]:
    url = f"{base_url}/korean/topics/{topic_id}"
    logger.info("섹션 페이지 요청: %s", url)
    response = client.get(url)
    links = extract_article_links(response.text, base_url, link_pattern, limit)
    logger.info("기사 링크 %s개 추출", len(links))
    return links


def _json_ld_published(soup: BeautifulSoup) -> str | None:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (TypeError, ValueError):
            continue
        nodes = data.get("@graph", [data]) if isinstance(data, dict) else data
        for node in nodes if isinstance(nodes, list) else []:
            if isinstance(node, dict) and node.get("datePublished"):
                return str(node["datePublished"])
    meta = soup.find("meta", attrs={"property": "article:published_time"})
    return meta.get("content") if meta else None


def parse_article(html_text: str, url: str, crawl_config: dict) -> dict | None:
    """기사 HTML → raw dict. 본문을 못 찾으면 None."""
    soup = BeautifulSoup(html_text, "html.parser")

    heading = soup.select_one("h1")
    title = heading.get_text(" ", strip=True) if heading else ""

    for selector in crawl_config.get("exclude_selectors", []):
        for node in soup.select(selector):
            node.decompose()

    paragraphs = [
        p.get_text(" ", strip=True)
        for p in soup.select(crawl_config.get("body_selector", "main p"))
    ]
    paragraphs = [text for text in paragraphs if len(text) >= 2]
    content = "\n".join(paragraphs).strip()
    if not title or not content:
        return None

    return {
        "title": title,
        "url": url,
        "content": content,
        "published_at": _json_ld_published(soup),
        "source": crawl_config.get("name", "crawl"),
        "category": None,
        "collection_method": "crawl",
        "collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def fetch_article(url: str, crawl_config: dict, client: HttpClient) -> dict | None:
    """기사 한 건을 크롤링한다. 실패는 FetchError로 올린다."""
    response = client.get(url)
    return parse_article(response.text, url, crawl_config)


def crawl_topics(
    crawl_config: dict,
    client: HttpClient,
    *,
    categories: list[str] | None,
    limit_per_topic: int | None,
) -> tuple[list[dict], int]:
    """섹션별 목록 → 기사 본문. (raw 목록, 실패 건수) 반환."""
    base_url = crawl_config["base_url"].rstrip("/")
    topics: dict[str, str] = crawl_config["topics"]
    link_pattern = crawl_config.get("article_link_pattern", "/korean/articles/")
    selected = {name: tid for name, tid in topics.items() if not categories or name in categories}

    records: list[dict] = []
    failed = 0
    for category, topic_id in selected.items():
        try:
            links = fetch_topic_links(base_url, topic_id, client, link_pattern, limit_per_topic)
        except FetchError as error:
            logger.error("섹션 '%s' 목록 수집 실패: %s", category, error)
            failed += 1
            continue
        for index, link in enumerate(links, start=1):
            try:
                article = fetch_article(link, crawl_config, client)
            except FetchError as error:
                failed += 1
                logger.warning("[%s %s/%s] 기사 수집 실패: %s", category, index, len(links), error)
                continue
            if article is None:
                failed += 1
                logger.warning("[%s %s/%s] 본문 추출 실패(구조 불일치): %s", category, index, len(links), link)
                continue
            article["category"] = category
            records.append(article)
            logger.info("[%s %s/%s] 수집 완료: %s", category, index, len(links), article["title"][:40])
    return records, failed


def enrich_body(records: list[dict], crawl_config: dict, client: HttpClient) -> int:
    """RSS 항목의 본문을 기사 페이지 크롤링으로 보강한다. 보강 실패 건수 반환."""
    failed = 0
    for index, record in enumerate(records, start=1):
        url = re.sub(r"[?#].*$", "", record["url"])
        try:
            article = fetch_article(url, crawl_config, client)
        except FetchError as error:
            failed += 1
            logger.warning("[%s/%s] 본문 보강 실패: %s", index, len(records), error)
            continue
        if article is None:
            failed += 1
            logger.warning("[%s/%s] 본문 보강 실패(구조 불일치): %s", index, len(records), url)
            continue
        record["content"] = article["content"]
        record["published_at"] = record.get("published_at") or article.get("published_at")
        logger.info("[%s/%s] 본문 보강 완료 (%s자)", index, len(records), len(article["content"]))
    return failed
