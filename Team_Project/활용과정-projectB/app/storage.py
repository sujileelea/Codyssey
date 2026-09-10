"""SQLite 영구 저장소 (담당: 혜민 · 통합 수정: owner).

- `raw_news`: 수집 원본 (append-only). 수집 시각·소스·수집 방법·원본 JSON을 함께 보관한다.
- `news`: 정제 완료 데이터 (clean). URL 기준 UNIQUE, 요약 결과도 이 행에 저장한다.
- `news`·`raw_news` 쓰기는 이 모듈만 한다. 분석·감성 테이블은 `repository.py`가 맡는다.

DB 경로는 `configure(db_path)`로 한 번 주입한다 (config.json `database.path`).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

DB_PATH = Path("data/news.db")

RAW_COLUMNS = (
    "title", "url", "content", "published_at", "source",
    "category", "collection_method", "collected_at",
)


def configure(db_path: str | Path) -> None:
    """DB 파일 경로를 설정한다. 디렉터리가 없으면 만든다."""
    global DB_PATH
    DB_PATH = Path(db_path)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect_db() -> sqlite3.Connection:
    """SQLite 데이터베이스에 연결합니다."""
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_tables() -> None:
    """원본 뉴스와 정제 뉴스 테이블을 생성합니다 (없을 때만)."""
    with connect_db() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                url TEXT,
                content TEXT,
                published_at TEXT,
                source TEXT,
                category TEXT,
                collection_method TEXT,
                collected_at TEXT,
                raw_data TEXT,
                processed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_id INTEGER,
                title TEXT NOT NULL,
                url TEXT UNIQUE,
                content TEXT NOT NULL,
                summary TEXT,
                summary_model TEXT,
                summarized_at TEXT,
                category TEXT DEFAULT '기타',
                source TEXT DEFAULT 'unknown',
                published_at TEXT,
                collected_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (raw_id) REFERENCES raw_news(id)
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_raw_news_url ON raw_news(url)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_news_category ON news(category)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_news_published ON news(published_at)")
        connection.commit()


# ---------------------------------------------------------------------------
# raw 저장소
# ---------------------------------------------------------------------------

def save_raw_article(article: dict) -> int:
    """수집한 원본 뉴스 한 건을 raw_news에 저장합니다 (항상 새 행)."""
    raw_data = json.dumps(article, ensure_ascii=False, default=str)
    with connect_db() as connection:
        cursor = connection.execute(
            """
            INSERT INTO raw_news (
                title, url, content, published_at, source,
                category, collection_method, collected_at, raw_data
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(article.get(column) for column in RAW_COLUMNS) + (raw_data,),
        )
        connection.commit()
        return int(cursor.lastrowid)


def raw_url_exists(url: str) -> bool:
    with connect_db() as connection:
        row = connection.execute("SELECT 1 FROM raw_news WHERE url = ? LIMIT 1", (url,)).fetchone()
    return row is not None


def get_unprocessed_raw(limit: int | None = None, all_raw: bool = False) -> list[dict]:
    """정제 대상 raw 행을 조회합니다. 기본은 미처리분만."""
    sql = "SELECT * FROM raw_news"
    if not all_raw:
        sql += " WHERE processed = 0"
    sql += " ORDER BY id"
    params: list[Any] = []
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with connect_db() as connection:
        rows = connection.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def mark_raw_processed(raw_ids: list[int]) -> None:
    if not raw_ids:
        return
    with connect_db() as connection:
        connection.executemany("UPDATE raw_news SET processed = 1 WHERE id = ?", [(i,) for i in raw_ids])
        connection.commit()


def find_category_by_url(url: str) -> str | None:
    """같은 URL의 크롤링 raw 행에서 카테고리를 찾습니다 (RSS 건 보강용)."""
    with connect_db() as connection:
        row = connection.execute(
            """
            SELECT category FROM raw_news
            WHERE url = ? AND category IS NOT NULL AND category != ''
            ORDER BY id DESC LIMIT 1
            """,
            (url,),
        ).fetchone()
    return row["category"] if row else None


# ---------------------------------------------------------------------------
# clean 저장소
# ---------------------------------------------------------------------------

def save_clean_article(raw_id: int, article: dict, duplicate_policy: str = "skip") -> tuple[str, int]:
    """정제된 뉴스를 news 테이블에 저장합니다.

    반환: ('inserted' | 'updated' | 'skipped', news_id)
    upsert 시 본문이 바뀐 경우에만 기존 요약을 초기화하고, 같으면 요약을 보존합니다.
    """
    if duplicate_policy not in ("skip", "upsert"):
        raise ValueError("중복 정책은 skip 또는 upsert만 가능합니다.")

    with connect_db() as connection:
        existing = connection.execute(
            "SELECT id, content FROM news WHERE url = ?",
            (article.get("url"),),
        ).fetchone()

        if existing:
            news_id = int(existing["id"])
            if duplicate_policy == "skip":
                return "skipped", news_id

            # 본문은 더 풍부한 쪽을 유지한다 (RSS 요약문이 크롤링 본문을 덮어쓰지 않도록).
            old_content = existing["content"] or ""
            new_content = article.get("content") or ""
            content = new_content if len(new_content) >= len(old_content) else old_content
            content_changed = content != old_content
            reset_summary = ", summary = NULL, summary_model = NULL, summarized_at = NULL" if content_changed else ""
            connection.execute(
                f"""
                UPDATE news
                SET raw_id = ?, title = ?, content = ?, category = ?, source = ?,
                    published_at = ?, collected_at = ?, updated_at = ?{reset_summary}
                WHERE id = ?
                """,
                (
                    raw_id, article.get("title"), content, article.get("category"),
                    article.get("source"), article.get("published_at"), article.get("collected_at"),
                    now_text(), news_id,
                ),
            )
            connection.commit()
            return "updated", news_id

        cursor = connection.execute(
            """
            INSERT INTO news (raw_id, title, url, content, category, source, published_at, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                raw_id, article.get("title"), article.get("url"), article.get("content"),
                article.get("category"), article.get("source"), article.get("published_at"),
                article.get("collected_at"),
            ),
        )
        connection.commit()
        return "inserted", int(cursor.lastrowid)


# ---------------------------------------------------------------------------
# 조회 (요약·list/show·리포트 공용)
# ---------------------------------------------------------------------------

def _filters_sql(
    *,
    category: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    alias: str = "n",
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if category:
        clauses.append(f"{alias}.category = ?")
        params.append(category)
    if date_from:
        clauses.append(f"date({alias}.published_at) >= date(?)")
        params.append(date_from)
    if date_to:
        clauses.append(f"date({alias}.published_at) <= date(?)")
        params.append(date_to)
    if status == "summarized":
        clauses.append(f"{alias}.summary IS NOT NULL")
    elif status == "clean":
        clauses.append(f"{alias}.summary IS NULL")
    if keyword:
        clauses.append(f"({alias}.title LIKE ? OR {alias}.content LIKE ? OR {alias}.summary LIKE ?)")
        like = f"%{keyword}%"
        params.extend([like, like, like])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def get_news(news_id: int) -> dict | None:
    with connect_db() as connection:
        row = connection.execute("SELECT * FROM news WHERE id = ?", (news_id,)).fetchone()
    return dict(row) if row else None


def get_news_for_summarize(
    mode: str = "unsummarized",
    news_ids: list[int] | None = None,
    limit: int | None = None,
    force: bool = False,
) -> list[dict]:
    """요약 대상을 고른다.

    - unsummarized: summary IS NULL 인 것만
    - all: 전건 (force가 아니면 요약된 건은 호출부에서 스킵 처리)
    - id: 지정 ID
    """
    sql = "SELECT * FROM news n"
    params: list[Any] = []
    if mode == "id":
        if not news_ids:
            return []
        placeholders = ",".join("?" for _ in news_ids)
        sql += f" WHERE n.id IN ({placeholders})"
        params.extend(news_ids)
    elif mode == "unsummarized" or (mode == "all" and not force):
        sql += " WHERE n.summary IS NULL" if mode == "unsummarized" else ""
    sql += " ORDER BY n.id"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with connect_db() as connection:
        rows = connection.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def save_summary(news_id: int, summary: str, model: str) -> None:
    with connect_db() as connection:
        connection.execute(
            "UPDATE news SET summary = ?, summary_model = ?, summarized_at = ?, updated_at = ? WHERE id = ?",
            (summary, model, now_text(), now_text(), news_id),
        )
        connection.commit()


def list_news(
    *,
    category: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
    order: str = "latest",
) -> tuple[list[dict], int]:
    """조건 필터 + 페이지네이션 목록. (rows, total) 반환."""
    where, params = _filters_sql(
        category=category, date_from=date_from, date_to=date_to, status=status, keyword=keyword
    )
    direction = "DESC" if order == "latest" else "ASC"
    offset = max(page - 1, 0) * page_size
    with connect_db() as connection:
        total = connection.execute(f"SELECT COUNT(*) FROM news n{where}", params).fetchone()[0]
        rows = connection.execute(
            f"""
            SELECT n.*, s.sentiment_result_json
            FROM news n
            LEFT JOIN sentiment_results s ON s.news_id = n.id
            {where}
            ORDER BY n.published_at {direction}, n.id {direction}
            LIMIT ? OFFSET ?
            """
            if _table_exists(connection, "sentiment_results")
            else f"SELECT n.*, NULL AS sentiment_result_json FROM news n{where} ORDER BY n.published_at {direction}, n.id {direction} LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()
    return [dict(row) for row in rows], int(total)


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# 집계 (리포트·차트)
# ---------------------------------------------------------------------------

def count_by_category(**filters: Any) -> list[tuple[str, int]]:
    where, params = _filters_sql(**filters)
    with connect_db() as connection:
        rows = connection.execute(
            f"SELECT n.category, COUNT(*) AS c FROM news n{where} GROUP BY n.category ORDER BY c DESC, n.category",
            params,
        ).fetchall()
    return [(row["category"] or "기타", int(row["c"])) for row in rows]


def count_by_source(**filters: Any) -> list[tuple[str, int]]:
    where, params = _filters_sql(**filters)
    with connect_db() as connection:
        rows = connection.execute(
            f"SELECT n.source, COUNT(*) AS c FROM news n{where} GROUP BY n.source ORDER BY c DESC",
            params,
        ).fetchall()
    return [(row["source"] or "unknown", int(row["c"])) for row in rows]


def count_by_collected_date(**filters: Any) -> list[tuple[str, int]]:
    """일자별 수집 추이: 수집 시각(collected_at) 기준."""
    where, params = _filters_sql(**filters)
    with connect_db() as connection:
        rows = connection.execute(
            f"SELECT date(n.collected_at) AS d, COUNT(*) AS c FROM news n{where} GROUP BY d ORDER BY d",
            params,
        ).fetchall()
    return [(row["d"] or "unknown", int(row["c"])) for row in rows]


def count_by_published_date(**filters: Any) -> list[tuple[str, int]]:
    where, params = _filters_sql(**filters)
    with connect_db() as connection:
        rows = connection.execute(
            f"SELECT date(n.published_at) AS d, COUNT(*) AS c FROM news n{where} GROUP BY d ORDER BY d",
            params,
        ).fetchall()
    return [(row["d"] or "unknown", int(row["c"])) for row in rows]


def count_by_sentiment(**filters: Any) -> list[tuple[str, int]]:
    """감성 분포 (sentiment_results JOIN). 테이블이 없으면 빈 목록."""
    where, params = _filters_sql(**filters)
    with connect_db() as connection:
        if not _table_exists(connection, "sentiment_results"):
            return []
        rows = connection.execute(
            f"""
            SELECT json_extract(s.sentiment_result_json, '$.sentiment') AS label, COUNT(*) AS c
            FROM sentiment_results s JOIN news n ON n.id = s.news_id
            {where}
            GROUP BY label ORDER BY c DESC
            """,
            params,
        ).fetchall()
    return [(row["label"] or "unknown", int(row["c"])) for row in rows]


def quality_stats(**filters: Any) -> dict[str, Any]:
    """리포트 품질 지표.

    - raw_total / raw_processed: 수집·정제 처리 건수
    - clean_total: 정제 통과 건수, invalid = 필수 필드 미충족으로 탈락한 raw 건수
    - summarized / summarized_ratio: 요약 완료율
    - avg_content_len / avg_summary_len / compression_ratio
    - rss_count / crawl_count: 수집 방법 분포
    """
    where, params = _filters_sql(**filters)
    with connect_db() as connection:
        raw_total = connection.execute("SELECT COUNT(*) FROM raw_news").fetchone()[0]
        raw_processed = connection.execute("SELECT COUNT(*) FROM raw_news WHERE processed = 1").fetchone()[0]
        raw_distinct_url = connection.execute("SELECT COUNT(DISTINCT url) FROM raw_news").fetchone()[0]
        row = connection.execute(
            f"""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN n.summary IS NOT NULL THEN 1 ELSE 0 END) AS summarized,
                   AVG(LENGTH(n.content)) AS avg_content_len,
                   AVG(LENGTH(n.summary)) AS avg_summary_len,
                   SUM(CASE WHEN n.collected_at IS NULL OR n.published_at IS NULL THEN 1 ELSE 0 END) AS missing_dates
            FROM news n{where}
            """,
            params,
        ).fetchone()
        methods = connection.execute(
            "SELECT collection_method, COUNT(*) AS c FROM raw_news GROUP BY collection_method"
        ).fetchall()
        sentiment_total = 0
        if _table_exists(connection, "sentiment_results"):
            sentiment_total = connection.execute("SELECT COUNT(*) FROM sentiment_results").fetchone()[0]

    total = int(row["total"] or 0)
    summarized = int(row["summarized"] or 0)
    avg_content = float(row["avg_content_len"] or 0)
    avg_summary = float(row["avg_summary_len"] or 0)
    clean_total_all = _count_all_news()
    return {
        "raw_total": int(raw_total),
        "raw_processed": int(raw_processed),
        "raw_distinct_url": int(raw_distinct_url),
        "clean_total_all": clean_total_all,
        "dedup_ratio": round(1 - clean_total_all / raw_total, 4) if raw_total else 0.0,
        "clean_total": total,
        "summarized": summarized,
        "summarized_ratio": round(summarized / total, 4) if total else 0.0,
        "avg_content_len": round(avg_content, 1),
        "avg_summary_len": round(avg_summary, 1),
        "compression_ratio": round(avg_summary / avg_content, 4) if avg_content else 0.0,
        "missing_dates": int(row["missing_dates"] or 0),
        "methods": {r["collection_method"] or "unknown": int(r["c"]) for r in methods},
        "sentiment_total": int(sentiment_total),
    }


def _count_all_news() -> int:
    with connect_db() as connection:
        return int(connection.execute("SELECT COUNT(*) FROM news").fetchone()[0])


def export_rows(**filters: Any) -> list[dict]:
    """내보내기용 전체 행 (필터 적용, 페이지 없음)."""
    rows, _ = list_news(page=1, page_size=1_000_000, order="oldest", **filters)
    return rows


if __name__ == "__main__":
    create_tables()
    print(f"DB 준비 완료: {DB_PATH}")
