from collector.crawler import extract_article_links, parse_article
from collector.rss import parse_rss

RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>BBC News 코리아</title>
<item><title><![CDATA[제목 A]]></title><description><![CDATA[요약 A]]></description>
<link>https://www.bbc.com/korean/articles/aaa?at_medium=RSS</link><guid>https://www.bbc.com/korean/articles/aaa#0</guid>
<pubDate>Wed, 09 Sep 2026 10:05:24 GMT</pubDate></item>
<item><title>제목 B</title><link>https://www.bbc.com/korean/articles/bbb</link><pubDate>Tue, 08 Sep 2026 08:07:29 GMT</pubDate></item>
</channel></rss>"""

TOPIC_HTML = """<html><body><nav><a href="/korean/topics/cxnyk3v82rgt">국내</a></nav>
<a href="https://www.bbc.com/korean/articles/aaa">A</a><a href="/korean/articles/bbb?x=1">B</a>
<a href="https://www.bbc.com/korean/articles/aaa">A again</a></body></html>"""

ARTICLE_HTML = """<html><head><script type="application/ld+json">{"@graph":[{"@type":"ReportageNewsArticle",
"headline":"제목 A","datePublished":"2026-09-09T10:05:24.542Z"}]}</script></head><body>
<main><h1 class="article-heading">제목 A</h1><figure><p>사진 캡션</p></figure>
<p data-testid="byline">기자 홍길동</p><p class="css-xh3tzq">첫 문단입니다.</p><p class="css-xh3tzq">둘째 문단입니다.</p></main></body></html>"""

CRAWL_CFG = {"name": "bbc_korean", "body_selector": "main p",
             "exclude_selectors": ["figure", "[data-testid=byline]"]}


def test_parse_rss_fields_and_limit():
    records = parse_rss(RSS, source_name="bbc_korean")
    assert len(records) == 2
    assert records[0]["title"] == "제목 A" and records[0]["content"] == "요약 A"
    assert records[0]["collection_method"] == "rss" and records[0]["category"] is None
    assert records[0]["published_at"] == "Wed, 09 Sep 2026 10:05:24 GMT"
    assert len(parse_rss(RSS, source_name="x", limit=1)) == 1


def test_extract_article_links_dedupes_and_absolutizes():
    links = extract_article_links(TOPIC_HTML, "https://www.bbc.com", "/korean/articles/")
    assert links == ["https://www.bbc.com/korean/articles/aaa", "https://www.bbc.com/korean/articles/bbb"]
    assert extract_article_links(TOPIC_HTML, "https://www.bbc.com", "/korean/articles/", limit=1) == links[:1]


def test_parse_article_extracts_body_and_excludes_captions():
    article = parse_article(ARTICLE_HTML, "https://www.bbc.com/korean/articles/aaa", CRAWL_CFG)
    assert article["title"] == "제목 A"
    assert article["content"] == "첫 문단입니다.\n둘째 문단입니다."
    assert article["published_at"] == "2026-09-09T10:05:24.542Z"
    assert article["collection_method"] == "crawl"
    assert parse_article("<html><main></main></html>", "u", CRAWL_CFG) is None
