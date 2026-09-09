import storage
from ai_client import MockAIClient
from cleaner import clean_article
from config import AppConfig
from summarizer import run_summarize, summarize_text


class FailingClient(MockAIClient):
    def generate_text(self, instructions, prompt, max_output_tokens=None):
        raise RuntimeError("API down")


def make_config(tmp_path):
    return AppConfig(raw={"summary": {"max_chars": 300, "default_limit": 10, "max_ai_attempts": 2}}, base_dir=tmp_path)


def seed(tmp_path, n=3):
    storage.configure(tmp_path / "news.db")
    storage.create_tables()
    for i in range(1, n + 1):
        storage.save_raw_article({"title": f"기사 {i}", "url": f"https://x/{i}", "content": "본문", "collection_method": "crawl"})
        article = clean_article({"title": f"기사 {i}", "url": f"https://x/{i}", "content": "본문 " * 30,
                                 "published_at": "2026-09-09", "collected_at": "2026-09-09 10:00:00"}, [])
        storage.save_clean_article(i, article, "skip")


def test_summarize_text_returns_none_after_retries():
    assert summarize_text(FailingClient(), "t", "c", max_chars=100, max_attempts=2) is None


def test_run_summarize_skips_summarized_and_force(tmp_path):
    seed(tmp_path)
    config = make_config(tmp_path)
    assert run_summarize(config, MockAIClient(), mode="unsummarized", limit=2) == {"success": 2, "failed": 0, "skipped": 0}
    assert run_summarize(config, MockAIClient(), mode="all") == {"success": 1, "failed": 0, "skipped": 2}
    assert run_summarize(config, MockAIClient(), mode="id", news_ids=[1, 99], force=True) == {"success": 1, "failed": 1, "skipped": 0}
    assert storage.get_news(1)["summary_model"] == "MockAIClient"


def test_run_summarize_logs_and_skips_api_failure(tmp_path):
    seed(tmp_path, n=2)
    counts = run_summarize(make_config(tmp_path), FailingClient(), mode="unsummarized")
    assert counts == {"success": 0, "failed": 2, "skipped": 0}
    assert storage.get_news(1)["summary"] is None
