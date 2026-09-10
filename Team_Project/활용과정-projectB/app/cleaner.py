"""정제 규칙 (담당: 혜민 · 통합 수정: owner).

- 필수 필드 검증: 제목·URL·본문 (없으면 ValueError → 정제 탈락)
- 텍스트 정규화: HTML 엔티티·태그 제거, 공백 정리
- URL 정규화: 스킴·호스트 소문자, 추적 파라미터(at_*, utm_* 등) 제거, fragment 제거
- 날짜 형식 통일: RFC 2822(RSS) · ISO 8601(JSON-LD) · 'YYYY.MM.DD' 등 → 'YYYY-MM-DD HH:MM:SS' (KST)
- 결측값 처리: 소스 → 'unknown', 카테고리 → '기타', 발행일 없음 → 수집 시각으로 대체
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

KST = timezone(timedelta(hours=9))
TRACKING_PREFIXES = ("at_", "utm_", "fbclid", "gclid", "xtor", "ocid")
DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
    "%Y.%m.%d %H:%M",
    "%Y.%m.%d",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
    "%Y년 %m월 %d일",
)


def normalize_text(text: object) -> str:
    """HTML 엔티티·태그, 줄바꿈, 여러 공백을 정리합니다."""
    if text is None:
        return ""
    value = html.unescape(str(text))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_url(url: object) -> str:
    """중복 판정에 쓸 수 있도록 URL을 정규화합니다."""
    value = normalize_text(url)
    if not value:
        return ""
    parts = urlsplit(value)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if not k.lower().startswith(TRACKING_PREFIXES)
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def _to_kst_text(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=KST)
    return value.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")


def parse_datetime(date_text: object) -> datetime | None:
    """다양한 날짜 문자열을 datetime으로 해석합니다. 실패하면 None."""
    if not date_text:
        return None
    text = str(date_text).strip()
    if not text:
        return None

    # RFC 2822 (RSS pubDate): 'Wed, 09 Sep 2026 10:05:24 GMT'
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        pass

    # ISO 8601 (JSON-LD, meta): '2026-09-09T10:05:24.542Z'
    iso = text.replace("Z", "+00:00") if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        pass

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def normalize_date(date_text: object, collected_at: object = None) -> str | None:
    """날짜를 'YYYY-MM-DD HH:MM:SS' (KST) 형식으로 통일합니다. 발행일이 없으면 수집 시각으로 대체."""
    parsed = parse_datetime(date_text) or parse_datetime(collected_at)
    return _to_kst_text(parsed) if parsed else None


def map_category(raw_category: object, categories: list[str] | None = None, category_map: dict | None = None) -> str:
    """소스 카테고리를 표준 카테고리로 매핑합니다. 표준 목록에 없으면 '기타'."""
    value = normalize_text(raw_category)
    if category_map and value in category_map:
        value = category_map[value]
    if not value:
        return "기타"
    if categories and value not in categories:
        return "기타"
    return value


def clean_article(
    article: dict,
    categories: list[str] | None = None,
    category_map: dict | None = None,
) -> dict:
    """원본 뉴스 한 건을 검사하고 정제합니다. 필수 필드가 없으면 ValueError."""
    title = normalize_text(article.get("title"))
    url = normalize_url(article.get("url"))
    content = normalize_text(article.get("content"))

    if not title:
        raise ValueError("제목이 없습니다.")
    if not url:
        raise ValueError("URL이 없습니다.")
    if not content:
        raise ValueError("본문이 없습니다.")

    collected_at = normalize_date(article.get("collected_at"))
    published_at = normalize_date(article.get("published_at"), article.get("collected_at"))

    return {
        "title": title,
        "url": url,
        "content": content,
        "category": map_category(article.get("category"), categories, category_map),
        "source": normalize_text(article.get("source")) or "unknown",
        "published_at": published_at,
        "collected_at": collected_at,
    }
