from pathlib import Path
import json
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai_client import MockAIClient
from repository import NewsRepository
from insight_analyzer import InsightAnalyzer, validate_insight_result
from models import AnalysisScope, SentimentScope
from sentiment_analyzer import SentimentAnalyzer, validate_sentiment_result


def make_db(tmp_path: Path, article_count: int = 45, missing_summaries: int = 2) -> Path:
    db_path = tmp_path / "news.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE news (
                id INTEGER PRIMARY KEY,
                title TEXT,
                content TEXT,
                summary TEXT,
                category TEXT,
                source TEXT,
                published_at TEXT
            )
            """
        )
        for i in range(1, article_count + 1):
            summary = None if i <= missing_summaries else f"기사 {i} 요약 내용"
            conn.execute(
                "INSERT INTO news VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    i,
                    f"기사 {i}",
                    f"기사 {i}의 clean 본문 내용입니다.",
                    summary,
                    "AI" if i % 2 else "반도체",
                    "테스트뉴스",
                    f"2026-09-{((i - 1) % 7) + 1:02d} 09:00:00",
                ),
            )
        conn.commit()
    return db_path


def repo_for(db_path: Path) -> NewsRepository:
    return NewsRepository(
        {
            "path": str(db_path),
            "news_table": "news",
            "insights_table": "insights",
            "sentiments_table": "sentiment_results",
            "columns": {
                "id": "id",
                "title": "title",
                "content": "content",
                "summary": "summary",
                "category": "category",
                "source": "source",
                "published_at": "published_at",
            },
        }
    )


def test_exact_output_counts():
    result = MockAIClient().generate_insight("", "")
    validated = validate_insight_result(result)
    assert len(validated["trends"]) == 3
    assert len(validated["keywords"]) == 6
    assert len(validated["major_issues"]) == 4


def test_45_articles_become_3_batches(tmp_path):
    db_path = make_db(tmp_path, article_count=45, missing_summaries=0)
    repo = repo_for(db_path)
    analyzer = InsightAnalyzer(repo, MockAIClient(), batch_size=20)

    result = analyzer.analyze(AnalysisScope(limit=45, sort="latest"))

    assert result["batch_count"] == 3
    assert result["quantitative_result"]["selected_article_count"] == 45
    assert result["quantitative_result"]["summarized_article_count"] == 45


def test_missing_summary_is_excluded_only_from_qualitative(tmp_path):
    db_path = make_db(tmp_path, article_count=10, missing_summaries=2)
    repo = repo_for(db_path)
    analyzer = InsightAnalyzer(repo, MockAIClient(), batch_size=20)

    result = analyzer.analyze(AnalysisScope(limit=10))

    assert result["quantitative_result"]["selected_article_count"] == 10
    assert result["quantitative_result"]["summarized_article_count"] == 8
    assert result["quantitative_result"]["unsummarized_article_count"] == 2
    assert result["batch_count"] == 1


def test_category_and_limit_and_latest_filter(tmp_path):
    db_path = make_db(tmp_path, article_count=20, missing_summaries=0)
    repo = repo_for(db_path)

    articles = repo.fetch_articles(AnalysisScope(category="AI", limit=3, sort="latest"))

    assert len(articles) == 3
    assert all(article.category == "AI" for article in articles)
    assert articles[0].published_at >= articles[-1].published_at


def test_sentiment_validation():
    result = validate_sentiment_result(
        {"sentiment": "negative", "score": -0.72, "reason": "규제 강화와 사업 불확실성"}
    )
    assert result["sentiment"] == "negative"
    assert result["score"] == -0.72


def test_sentiment_uses_clean_content_and_saves_separate_json(tmp_path):
    db_path = make_db(tmp_path, article_count=1, missing_summaries=0)
    repo = repo_for(db_path)

    class CaptureAI(MockAIClient):
        def __init__(self):
            self.prompt = ""

        def generate_sentiment(self, instructions: str, prompt: str) -> dict:
            self.prompt = prompt
            return {"sentiment": "positive", "score": 0.6, "reason": "투자 확대 내용"}

    ai = CaptureAI()
    analyzer = SentimentAnalyzer(repo, ai)
    result = analyzer.analyze(SentimentScope(limit=1, mode="unsentimented"))

    assert "clean 본문 내용" in ai.prompt
    assert "요약 내용" not in ai.prompt
    assert result["analyzed_article_count"] == 1

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT news_id, sentiment_result_json FROM sentiment_results"
        ).fetchone()
    assert row[0] == 1
    saved = json.loads(row[1])
    assert saved == {"sentiment": "positive", "score": 0.6, "reason": "투자 확대 내용"}


def test_unsentimented_skips_already_analyzed_article(tmp_path):
    db_path = make_db(tmp_path, article_count=2, missing_summaries=0)
    repo = repo_for(db_path)
    repo.save_sentiment(2, {"sentiment": "neutral", "score": 0.0, "reason": "기존 결과"})

    articles = repo.fetch_sentiment_articles(
        SentimentScope(limit=10, mode="unsentimented", sort="latest")
    )
    assert [a.id for a in articles] == [1]


def test_gemini_client_builds_structured_requests(monkeypatch):
    import types as pytypes

    from ai_client import GeminiClient

    captured_calls = []

    class FakeModels:
        def generate_content(self, **kwargs):
            captured_calls.append(kwargs)
            schema = kwargs["config"].kwargs["response_json_schema"]
            if "trends" in schema["properties"]:
                payload = {
                    "trends": ["t1", "t2", "t3"],
                    "keywords": ["k1", "k2", "k3", "k4", "k5", "k6"],
                    "major_issues": ["i1", "i2", "i3", "i4"],
                }
            else:
                payload = {"sentiment": "neutral", "score": 0.0, "reason": "fact report"}
            return pytypes.SimpleNamespace(text=json.dumps(payload, ensure_ascii=False))

    class FakeClient:
        def __init__(self, api_key, http_options=None):
            self.api_key = api_key
            self.models = FakeModels()

    class FakeGenerateContentConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeOpt:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_google = pytypes.ModuleType("google")
    fake_genai = pytypes.ModuleType("google.genai")
    fake_genai.Client = FakeClient
    fake_types = pytypes.ModuleType("google.genai.types")
    fake_types.GenerateContentConfig = FakeGenerateContentConfig
    fake_types.HttpOptions = FakeOpt
    fake_types.AutomaticFunctionCallingConfig = FakeOpt
    fake_genai.types = fake_types
    fake_google.genai = fake_genai

    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    client = GeminiClient(
        {
            "api_key_env": "GEMINI_API_KEY",
            "model": "gemini-3.5-flash-lite",
            "max_output_tokens": 1800,
            "min_interval_seconds": 0,
        }
    )
    insight = client.generate_insight("system rules", "news summaries")
    sentiment = client.generate_sentiment("sentiment rules", "clean content")

    assert len(captured_calls) == 2
    assert captured_calls[0]["model"] == "gemini-3.5-flash-lite"
    assert captured_calls[0]["contents"] == "news summaries"
    assert captured_calls[0]["config"].kwargs["response_mime_type"] == "application/json"
    assert captured_calls[0]["config"].kwargs["response_json_schema"]["properties"]["trends"]["minItems"] == 3
    assert captured_calls[1]["config"].kwargs["response_json_schema"]["properties"]["sentiment"]["enum"] == ["positive", "neutral", "negative"]
    assert insight["keywords"] == ["k1", "k2", "k3", "k4", "k5", "k6"]
    assert sentiment["sentiment"] == "neutral"
