from __future__ import annotations

import logging
from dataclasses import asdict

from ai_client import AIClient
from repository import NewsRepository
from models import Article, SentimentScope

logger = logging.getLogger(__name__)

SENTIMENT_SYSTEM_INSTRUCTIONS = """당신은 뉴스 기사의 감성 방향성을 분류하는 분석기다.
다음 규칙을 반드시 지킨다.
1. 제공된 기사 제목과 clean 본문만 근거로 판단한다.
2. 외부 지식, 기억, 웹 정보, 기사에 없는 사실을 추가하지 않는다.
3. 여기서 sentiment는 기자의 문체가 아니라, 기사가 다루는 핵심 사건/이슈가 사회·산업·기업 관점에서 전달하는 전반적 방향성이다.
4. positive / neutral / negative 중 하나만 선택한다.
5. score는 -1.0(매우 부정)부터 +1.0(매우 긍정)까지이며, 중립에 가까울수록 0에 가깝게 한다.
6. reason은 기사 안의 근거만 이용해 짧게 설명한다.
7. 사실 전달 중심이고 긍정/부정 방향성이 불명확하면 neutral로 판단한다.
"""


class SentimentValidationError(ValueError):
    pass


def validate_sentiment_result(result: dict) -> dict:
    expected_keys = {"sentiment", "score", "reason"}
    if set(result.keys()) != expected_keys:
        raise SentimentValidationError(
            f"감성 결과 키가 예상과 다릅니다. expected={sorted(expected_keys)}, actual={sorted(result.keys())}"
        )

    sentiment = result.get("sentiment")
    if sentiment not in {"positive", "neutral", "negative"}:
        raise SentimentValidationError("sentiment는 positive/neutral/negative 중 하나여야 합니다.")

    score = result.get("score")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise SentimentValidationError("score는 숫자여야 합니다.")
    score = float(score)
    if not -1.0 <= score <= 1.0:
        raise SentimentValidationError("score는 -1.0 이상 1.0 이하여야 합니다.")

    reason = result.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise SentimentValidationError("reason은 비어 있지 않은 문자열이어야 합니다.")

    return {
        "sentiment": sentiment,
        "score": round(score, 4),
        "reason": reason.strip(),
    }


def build_sentiment_prompt(article: Article) -> str:
    return "\n".join(
        [
            f"[ARTICLE_{article.id}]",
            f"title: {article.title}",
            "clean_content:",
            article.content or "",
            "",
            "이 기사 하나에 대해 sentiment, score, reason을 반환하라.",
        ]
    )


class SentimentAnalyzer:
    def __init__(
        self,
        repository: NewsRepository,
        ai_client: AIClient,
        max_ai_attempts: int = 2,
    ):
        self.repository = repository
        self.ai_client = ai_client
        self.max_ai_attempts = max_ai_attempts

    def _call_and_validate(self, article: Article) -> dict:
        last_error: Exception | None = None
        prompt = build_sentiment_prompt(article)
        for attempt in range(1, self.max_ai_attempts + 1):
            try:
                result = self.ai_client.generate_sentiment(
                    SENTIMENT_SYSTEM_INSTRUCTIONS,
                    prompt,
                )
                return validate_sentiment_result(result)
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "감성 분석 ID=%s 시도 %s/%s 실패: %s",
                    article.id,
                    attempt,
                    self.max_ai_attempts,
                    exc,
                )
        raise RuntimeError(f"뉴스 ID={article.id} 감성 분석에 최종 실패했습니다: {last_error}") from last_error

    def analyze(self, scope: SentimentScope) -> dict:
        articles = self.repository.fetch_sentiment_articles(scope)
        if not articles:
            if scope.mode == "unsentimented":
                raise ValueError("조건에 맞는 미분석 감성 뉴스가 없습니다.")
            raise ValueError("조건에 맞는 clean 뉴스가 없습니다.")

        logger.info("감성 분석 대상: %s건", len(articles))
        results: list[dict] = []
        skipped_no_content = 0
        failed = 0

        for index, article in enumerate(articles, start=1):
            if not article.content:
                skipped_no_content += 1
                logger.warning("[%s/%s] ID=%s clean content 없음 → 스킵", index, len(articles), article.id)
                continue

            try:
                sentiment_result = self._call_and_validate(article)
            except RuntimeError as error:  # API 최종 실패: 로깅 후 다음 기사 계속
                failed += 1
                logger.error("[%s/%s] ID=%s 감성 분석 실패 → 스킵: %s", index, len(articles), article.id, error)
                continue
            sentiment_id = self.repository.save_sentiment(article.id, sentiment_result)
            results.append(
                {
                    "sentiment_id": sentiment_id,
                    "news_id": article.id,
                    "sentiment_result": sentiment_result,
                }
            )
            logger.info(
                "[%s/%s] ID=%s 감성 분석 완료: %s (%.2f)",
                index,
                len(articles),
                article.id,
                sentiment_result["sentiment"],
                sentiment_result["score"],
            )

        if not results:
            raise ValueError("clean content가 있는 뉴스가 없어 감성 분석 결과를 생성하지 못했습니다.")

        return {
            "scope": asdict(scope),
            "selected_article_count": len(articles),
            "analyzed_article_count": len(results),
            "skipped_no_content_count": skipped_no_content,
            "failed_count": failed,
            "results": results,
        }
