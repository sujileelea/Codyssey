import pytest

from cleaner import clean_article, map_category, normalize_date, normalize_text, normalize_url


def test_normalize_text_strips_html_and_spaces():
    assert normalize_text("<p>기업들의\n\n  AI &amp; 반도체</p>") == "기업들의 AI & 반도체"


def test_normalize_url_removes_tracking_params_and_fragment():
    raw = "HTTPS://WWW.BBC.com/korean/articles/czrz6y535neo?at_medium=RSS&at_campaign=rss#0"
    assert normalize_url(raw) == "https://www.bbc.com/korean/articles/czrz6y535neo"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Wed, 09 Sep 2026 10:05:24 GMT", "2026-09-09 19:05:24"),   # RSS pubDate (RFC 2822) → KST
        ("2026-09-09T10:05:24.542Z", "2026-09-09 19:05:24"),        # JSON-LD ISO (UTC) → KST
        ("2026.09.09", "2026-09-09 00:00:00"),
        ("2026-09-09 15:00:00", "2026-09-09 15:00:00"),
    ],
)
def test_normalize_date_formats(value, expected):
    assert normalize_date(value) == expected


def test_normalize_date_falls_back_to_collected_at():
    assert normalize_date(None, "2026-09-09 15:00:00") == "2026-09-09 15:00:00"
    assert normalize_date("not a date") is None


def test_map_category_defaults_to_etc():
    cats = ["국내", "세계"]
    assert map_category("세계", cats) == "세계"
    assert map_category("비디오", cats) == "기타"
    assert map_category(None, cats) == "기타"
    assert map_category("IT과학", ["IT"], {"IT과학": "IT"}) == "IT"


def test_clean_article_requires_title_url_content():
    base = {"title": "제목", "url": "https://example.com/a?utm_source=x", "content": "<p>본문</p>",
            "published_at": "2026.09.09", "collected_at": "2026-09-09 15:00:00", "source": "", "category": ""}
    cleaned = clean_article(base, ["국내"])
    assert cleaned["url"] == "https://example.com/a"
    assert cleaned["source"] == "unknown" and cleaned["category"] == "기타"
    assert cleaned["published_at"] == "2026-09-09 00:00:00"
    for missing in ("title", "url", "content"):
        with pytest.raises(ValueError):
            clean_article({**base, missing: None}, ["국내"])
