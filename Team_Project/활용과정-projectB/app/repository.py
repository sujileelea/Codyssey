"""분석·감성용 저장소 (담당: 경학, 구 database.py).

clean 뉴스(`news`)는 읽기만 하고, `insights`·`sentiment_results` 테이블은 이 모듈이 소유한다.
테이블·컬럼명은 config.json `database` 섹션으로 매핑한다.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Iterable

from models import AnalysisScope, Article, QuantitativeResult, SentimentScope

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_identifier(value: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"허용되지 않는 SQL 식별자입니다: {value!r}")
    return value


class NewsRepository:
    """Clean 뉴스 조회 + insight/sentiment 결과 저장을 담당한다.

    팀 DB 스키마가 확정되면 config.json의 테이블/컬럼 매핑만 변경하도록 설계했다.
    """

    def __init__(self, db_config: dict):
        self.db_path = Path(db_config["path"])
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.news_table = _safe_identifier(db_config.get("news_table", "news"))
        self.insights_table = _safe_identifier(db_config.get("insights_table", "insights"))
        self.sentiments_table = _safe_identifier(db_config.get("sentiments_table", "sentiment_results"))

        columns = db_config.get("columns", {})
        self.col = {
            "id": _safe_identifier(columns.get("id", "id")),
            "title": _safe_identifier(columns.get("title", "title")),
            "content": _safe_identifier(columns.get("content", "content")),
            "summary": _safe_identifier(columns.get("summary", "summary")),
            "category": _safe_identifier(columns.get("category", "category")),
            "source": _safe_identifier(columns.get("source", "source")),
            "published_at": _safe_identifier(columns.get("published_at", "published_at")),
        }

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_insights_table(self) -> None:
        sql = f"""
        CREATE TABLE IF NOT EXISTS {self.insights_table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_from TEXT,
            date_to TEXT,
            category TEXT,
            article_limit INTEGER NOT NULL,
            sort_order TEXT NOT NULL,
            selected_article_count INTEGER NOT NULL,
            summarized_article_count INTEGER NOT NULL,
            quantitative_result_json TEXT NOT NULL,
            batch_result_json TEXT NOT NULL,
            insight_result_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
        with self.connect() as conn:
            conn.execute(sql)
            conn.commit()

    def ensure_sentiments_table(self) -> None:
        sql = f"""
        CREATE TABLE IF NOT EXISTS {self.sentiments_table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            news_id INTEGER NOT NULL UNIQUE,
            sentiment_result_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
        """
        with self.connect() as conn:
            conn.execute(sql)
            conn.commit()

    def _row_to_article(self, row: sqlite3.Row) -> Article:
        return Article(
            id=int(row["id"]),
            title=(row["title"] or "").strip(),
            content=(row["content"] or "").strip() or None,
            summary=(row["summary"] or "").strip() or None,
            category=(row["category"] or "").strip() or None,
            source=(row["source"] or "").strip() or None,
            published_at=(row["published_at"] or "").strip() or None,
        )

    def fetch_articles(self, scope: AnalysisScope) -> list[Article]:
        c = self.col
        sql = f"""
        SELECT
            {c['id']} AS id,
            {c['title']} AS title,
            {c['content']} AS content,
            {c['summary']} AS summary,
            {c['category']} AS category,
            {c['source']} AS source,
            {c['published_at']} AS published_at
        FROM {self.news_table}
        WHERE 1=1
        """
        params: list[object] = []

        if scope.date_from:
            sql += f" AND date({c['published_at']}) >= date(?)"
            params.append(scope.date_from)
        if scope.date_to:
            sql += f" AND date({c['published_at']}) <= date(?)"
            params.append(scope.date_to)
        if scope.category:
            sql += f" AND {c['category']} = ?"
            params.append(scope.category)

        direction = "DESC" if scope.sort == "latest" else "ASC"
        sql += f" ORDER BY {c['published_at']} {direction}, {c['id']} {direction} LIMIT ?"
        params.append(scope.limit)

        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_article(row) for row in rows]

    def fetch_sentiment_articles(self, scope: SentimentScope) -> list[Article]:
        self.ensure_sentiments_table()
        c = self.col
        sql = f"""
        SELECT
            n.{c['id']} AS id,
            n.{c['title']} AS title,
            n.{c['content']} AS content,
            n.{c['summary']} AS summary,
            n.{c['category']} AS category,
            n.{c['source']} AS source,
            n.{c['published_at']} AS published_at
        FROM {self.news_table} n
        LEFT JOIN {self.sentiments_table} s
          ON s.news_id = n.{c['id']}
        WHERE 1=1
        """
        params: list[object] = []

        if scope.article_id is not None:
            sql += f" AND n.{c['id']} = ?"
            params.append(scope.article_id)
        else:
            if scope.date_from:
                sql += f" AND date(n.{c['published_at']}) >= date(?)"
                params.append(scope.date_from)
            if scope.date_to:
                sql += f" AND date(n.{c['published_at']}) <= date(?)"
                params.append(scope.date_to)
            if scope.category:
                sql += f" AND n.{c['category']} = ?"
                params.append(scope.category)
            if scope.mode == "unsentimented":
                sql += " AND s.news_id IS NULL"

        direction = "DESC" if scope.sort == "latest" else "ASC"
        sql += f" ORDER BY n.{c['published_at']} {direction}, n.{c['id']} {direction} LIMIT ?"
        params.append(1 if scope.article_id is not None else scope.limit)

        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_article(row) for row in rows]

    @staticmethod
    def build_quantitative_result(articles: Iterable[Article]) -> QuantitativeResult:
        items = list(articles)
        category_counts = Counter(a.category or "unknown" for a in items)
        source_counts = Counter(a.source or "unknown" for a in items)
        daily_counts = Counter(
            (a.published_at[:10] if a.published_at and len(a.published_at) >= 10 else "unknown")
            for a in items
        )
        summarized_count = sum(1 for a in items if a.summary)

        return {
            "selected_article_count": len(items),
            "summarized_article_count": summarized_count,
            "unsummarized_article_count": len(items) - summarized_count,
            "category_counts": dict(sorted(category_counts.items())),
            "source_counts": dict(source_counts.most_common()),
            "daily_counts": dict(sorted(daily_counts.items())),
        }

    def save_insight(
        self,
        scope: AnalysisScope,
        quantitative_result: QuantitativeResult,
        batch_results: list[dict],
        insight_result: dict,
    ) -> int:
        self.ensure_insights_table()
        sql = f"""
        INSERT INTO {self.insights_table} (
            date_from, date_to, category, article_limit, sort_order,
            selected_article_count, summarized_article_count,
            quantitative_result_json, batch_result_json, insight_result_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        values = (
            scope.date_from,
            scope.date_to,
            scope.category,
            scope.limit,
            scope.sort,
            quantitative_result["selected_article_count"],
            quantitative_result["summarized_article_count"],
            json.dumps(quantitative_result, ensure_ascii=False),
            json.dumps(batch_results, ensure_ascii=False),
            json.dumps(insight_result, ensure_ascii=False),
        )

        with self.connect() as conn:
            cursor = conn.execute(sql, values)
            conn.commit()
            return int(cursor.lastrowid)

    def get_insight(self, insight_id: int) -> dict | None:
        """저장된 인사이트 1건 조회 (`analyze --show`)."""
        self.ensure_insights_table()
        with self.connect() as conn:
            row = conn.execute(f"SELECT * FROM {self.insights_table} WHERE id = ?", (insight_id,)).fetchone()
        return self._row_to_insight(row) if row else None

    def latest_insight(self, category: str | None = None) -> dict | None:
        """가장 최근 인사이트 (리포트용). category가 있으면 그 카테고리 분석 중 최신."""
        self.ensure_insights_table()
        with self.connect() as conn:
            if category:
                row = conn.execute(
                    f"SELECT * FROM {self.insights_table} WHERE category = ? ORDER BY id DESC LIMIT 1", (category,)
                ).fetchone()
            else:  # 전체 리포트는 전체 대상 분석을 우선하고, 없으면 가장 최근 분석
                row = conn.execute(
                    f"SELECT * FROM {self.insights_table} WHERE category IS NULL ORDER BY id DESC LIMIT 1"
                ).fetchone() or conn.execute(
                    f"SELECT * FROM {self.insights_table} ORDER BY id DESC LIMIT 1"
                ).fetchone()
        return self._row_to_insight(row) if row else None

    def list_insights(self, limit: int = 20) -> list[dict]:
        self.ensure_insights_table()
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self.insights_table} ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_insight(row) for row in rows]

    @staticmethod
    def _row_to_insight(row: sqlite3.Row) -> dict:
        record = dict(row)
        for key in ("quantitative_result_json", "batch_result_json", "insight_result_json"):
            try:
                record[key.replace("_json", "")] = json.loads(record.get(key) or "null")
            except ValueError:
                record[key.replace("_json", "")] = None
        return record

    def save_sentiment(self, news_id: int, sentiment_result: dict) -> int:
        self.ensure_sentiments_table()
        payload = json.dumps(sentiment_result, ensure_ascii=False)
        sql = f"""
        INSERT INTO {self.sentiments_table} (news_id, sentiment_result_json)
        VALUES (?, ?)
        ON CONFLICT(news_id) DO UPDATE SET
            sentiment_result_json = excluded.sentiment_result_json,
            updated_at = datetime('now', 'localtime')
        """
        with self.connect() as conn:
            conn.execute(sql, (news_id, payload))
            row = conn.execute(
                f"SELECT id FROM {self.sentiments_table} WHERE news_id = ?",
                (news_id,),
            ).fetchone()
            conn.commit()
        return int(row["id"])
