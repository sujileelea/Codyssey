from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Article:
    id: int
    title: str
    content: str | None
    summary: str | None
    category: str | None
    source: str | None
    published_at: str | None


@dataclass(frozen=True)
class AnalysisScope:
    date_from: str | None = None
    date_to: str | None = None
    category: str | None = None
    limit: int = 50
    sort: str = "latest"


@dataclass(frozen=True)
class SentimentScope:
    date_from: str | None = None
    date_to: str | None = None
    category: str | None = None
    limit: int = 20
    sort: str = "latest"
    article_id: int | None = None
    mode: str = "unsentimented"  # unsentimented | all | id


InsightResult = dict[str, list[str]]
QuantitativeResult = dict[str, Any]
SentimentResult = dict[str, Any]
