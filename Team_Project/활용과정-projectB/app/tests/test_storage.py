import storage

BASE = "https://www.bbc.com/korean/articles/"


def raw(i, method="crawl", category="국내", content=None, url=None):
    return {"title": f"기사 {i}", "url": url or f"{BASE}c{i:03d}", "content": content or f"본문 {i} " * 20,
            "published_at": "Wed, 09 Sep 2026 10:05:24 GMT", "source": "bbc_korean", "category": category,
            "collection_method": method, "collected_at": "2026-09-09 20:00:00"}


def setup_db(tmp_path, raw_rows=6):
    storage.configure(tmp_path / "news.db")
    storage.create_tables()
    for i in range(1, raw_rows + 1):  # FK(raw_id) 충족용 raw 행
        storage.save_raw_article(raw(i))


def test_raw_is_append_only_and_processed_flag(tmp_path):
    setup_db(tmp_path, raw_rows=0)
    a = storage.save_raw_article(raw(1))
    b = storage.save_raw_article(raw(1))
    assert a != b and len(storage.get_unprocessed_raw()) == 2
    storage.mark_raw_processed([a])
    assert [r["id"] for r in storage.get_unprocessed_raw()] == [b]
    assert len(storage.get_unprocessed_raw(all_raw=True)) == 2


def test_skip_and_upsert_policies(tmp_path):
    setup_db(tmp_path)
    from cleaner import clean_article
    first = clean_article(raw(1, content="긴 본문 " * 50), ["국내"])
    action, news_id = storage.save_clean_article(1, first, "skip")
    assert action == "inserted"
    assert storage.save_clean_article(2, first, "skip") == ("skipped", news_id)
    storage.save_summary(news_id, "요약문", "mock")

    # upsert: 본문이 같으면 요약 보존
    action, _ = storage.save_clean_article(3, {**first, "title": "제목 수정"}, "upsert")
    assert action == "updated"
    assert storage.get_news(news_id)["summary"] == "요약문"
    assert storage.get_news(news_id)["title"] == "제목 수정"

    # upsert: 더 짧은 본문(RSS 요약문)은 기존 본문을 덮어쓰지 않는다
    storage.save_clean_article(4, {**first, "content": "짧은 요약"}, "upsert")
    assert storage.get_news(news_id)["content"] == first["content"]

    # upsert: 본문이 실제로 바뀌면 요약 초기화
    storage.save_clean_article(5, {**first, "content": "완전히 새로운 본문 " * 60}, "upsert")
    assert storage.get_news(news_id)["summary"] is None


def test_find_category_by_url_and_list_pagination(tmp_path):
    setup_db(tmp_path, raw_rows=0)
    from cleaner import clean_article
    for i in range(1, 8):
        storage.save_raw_article(raw(i, category="세계"))
    assert storage.find_category_by_url(f"{BASE}c001") == "세계"
    for i in range(1, 8):
        storage.save_clean_article(i, clean_article(raw(i, category=["국내", "세계"][i % 2]), ["국내", "세계"]), "skip")
    rows, total = storage.list_news(page=2, page_size=3)
    assert total == 7 and len(rows) == 3
    rows, total = storage.list_news(category="세계", keyword="기사 3")
    assert total == 1 and rows[0]["category"] == "세계"
    assert storage.count_by_category() == [("세계", 4), ("국내", 3)]
    assert storage.quality_stats()["clean_total"] == 7


def test_get_news_for_summarize_modes(tmp_path):
    setup_db(tmp_path)
    from cleaner import clean_article
    for i in range(1, 4):
        storage.save_clean_article(i, clean_article(raw(i), ["국내"]), "skip")
    storage.save_summary(1, "요약", "mock")
    assert [r["id"] for r in storage.get_news_for_summarize("unsummarized")] == [2, 3]
    assert len(storage.get_news_for_summarize("all")) == 3
    assert [r["id"] for r in storage.get_news_for_summarize("id", [3, 99])] == [3]
