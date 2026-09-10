from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Iterable

from ai_client import AIClient
from repository import NewsRepository
from models import AnalysisScope, Article

logger = logging.getLogger(__name__)


SYSTEM_INSTRUCTIONS = """당신은 뉴스 데이터만을 근거로 분석하는 분석기다.
다음 원칙을 반드시 지킨다.
1. 제공된 기사 요약 또는 제공된 배치 분석 결과에 명시된 정보만 사용한다.
2. 외부 지식, 기억, 웹 정보, 상식에 기반한 새로운 사실을 추가하지 않는다.
3. 기사에 없는 기업명, 인물, 사건, 수치, 원인, 전망을 만들어내지 않는다.
4. 근거가 부족하면 과도하게 구체화하지 않는다.
5. 서로 의미가 거의 같은 항목은 중복해서 출력하지 않는다.
6. trends는 여러 기사에서 관찰되는 지속적 방향성 또는 변화다.
7. keywords는 기사 집합을 대표하는 핵심 개념·기술·기업·정책 용어다.
8. major_issues는 반복적으로 등장하거나 영향도가 큰 구체적인 사건·문제·논쟁이다.
9. trends 3개, keywords 6개, major_issues 4개를 정확히 반환한다.
10. trends와 major_issues가 같은 내용을 단순히 다른 표현으로 반복하지 않도록 한다.
"""


class InsightValidationError(ValueError):
    pass


def validate_insight_result(result: dict) -> dict:
    expected = {
        "trends": 3,
        "keywords": 6,
        "major_issues": 4,
    }

    if set(result.keys()) != set(expected.keys()):
        raise InsightValidationError(
            f"AI 결과 키가 예상과 다릅니다. expected={list(expected)}, actual={list(result)}"
        )

    for key, count in expected.items():
        values = result.get(key)
        if not isinstance(values, list):
            raise InsightValidationError(f"{key}는 list여야 합니다.")
        if len(values) != count:
            raise InsightValidationError(f"{key}는 정확히 {count}개여야 합니다. actual={len(values)}")
        if any(not isinstance(v, str) or not v.strip() for v in values):
            raise InsightValidationError(f"{key}에 비어 있거나 문자열이 아닌 항목이 있습니다.")

    return {
        "trends": [v.strip() for v in result["trends"]],
        "keywords": [v.strip() for v in result["keywords"]],
        "major_issues": [v.strip() for v in result["major_issues"]],
    }


def chunked(items: list[Article], batch_size: int) -> Iterable[list[Article]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def build_batch_prompt(batch: list[Article], batch_number: int) -> str:
    lines = [
        f"배치 번호: {batch_number}",
        f"기사 수: {len(batch)}",
        "아래 기사 요약들만 근거로 분석하라.",
        "여러 기사에서 반복되는 주제는 주요 이슈/트렌드 판단에서 중요하게 고려하되, 한 번만 등장해도 영향도가 큰 이슈는 배제하지 마라.",
        "",
    ]

    for idx, article in enumerate(batch, start=1):
        lines.extend(
            [
                f"[ARTICLE_{idx:02d}]",
                f"title: {article.title}",
                f"summary: {article.summary}",
                "",
            ]
        )

    lines.append("정확히 trends 3개, keywords 6개, major_issues 4개를 반환하라.")
    return "\n".join(lines)


def build_reduce_prompt(batch_results: list[dict]) -> str:
    lines = [
        f"배치 분석 결과 수: {len(batch_results)}",
        "아래 배치 분석 결과만 근거로 전체 뉴스의 최종 인사이트를 생성하라.",
        "서로 다른 배치에서 반복되는 의미의 항목은 전체 중요도가 높은 것으로 판단하라.",
        "동일하거나 유사한 표현은 하나로 통합하고 새로운 사실은 추가하지 마라.",
        "",
    ]
    for idx, result in enumerate(batch_results, start=1):
        lines.extend(
            [
                f"[BATCH_{idx:02d}]",
                f"trends: {result['trends']}",
                f"keywords: {result['keywords']}",
                f"major_issues: {result['major_issues']}",
                "",
            ]
        )
    lines.append("최종 결과도 정확히 trends 3개, keywords 6개, major_issues 4개를 반환하라.")
    return "\n".join(lines)


class InsightAnalyzer:
    def __init__(
        self,
        repository: NewsRepository,
        ai_client: AIClient,
        batch_size: int = 20,
        max_ai_attempts: int = 2,
    ):
        self.repository = repository
        self.ai_client = ai_client
        self.batch_size = batch_size
        self.max_ai_attempts = max_ai_attempts

    def _call_and_validate(self, prompt: str) -> dict:
        last_error: Exception | None = None
        for attempt in range(1, self.max_ai_attempts + 1):
            try:
                result = self.ai_client.generate_insight(SYSTEM_INSTRUCTIONS, prompt)
                return validate_insight_result(result)
            except Exception as exc:  # API 오류/JSON 검증 실패 모두 재시도
                last_error = exc
                logger.warning("AI 분석 시도 %s/%s 실패: %s", attempt, self.max_ai_attempts, exc)
        raise RuntimeError(f"AI 분석에 최종 실패했습니다: {last_error}") from last_error

    def analyze(self, scope: AnalysisScope) -> dict:
        articles = self.repository.fetch_articles(scope)
        if not articles:
            raise ValueError("조건에 맞는 clean 뉴스가 없습니다.")

        quantitative_result = self.repository.build_quantitative_result(articles)
        summarized_articles = [a for a in articles if a.summary]

        missing = len(articles) - len(summarized_articles)
        logger.info("선택된 clean 뉴스: %s건", len(articles))
        if missing:
            logger.warning("summary가 없는 뉴스 %s건은 정성 인사이트 분석에서 제외합니다.", missing)
        if not summarized_articles:
            raise ValueError("선택된 뉴스 중 summary가 존재하는 기사가 없어 정성 분석을 수행할 수 없습니다.")

        batch_results: list[dict] = []
        batches = list(chunked(summarized_articles, self.batch_size))
        logger.info("정성 분석 대상: %s건 / 배치 수: %s / 배치 크기: %s", len(summarized_articles), len(batches), self.batch_size)

        for batch_number, batch in enumerate(batches, start=1):
            logger.info("배치 분석 %s/%s (%s건)", batch_number, len(batches), len(batch))
            prompt = build_batch_prompt(batch, batch_number)
            batch_results.append(self._call_and_validate(prompt))

        if len(batch_results) == 1:
            final_result = batch_results[0]
        else:
            logger.info("배치 결과 종합(Reduce) 분석 시작")
            final_result = self._call_and_validate(build_reduce_prompt(batch_results))

        insight_id = self.repository.save_insight(
            scope=scope,
            quantitative_result=quantitative_result,
            batch_results=batch_results,
            insight_result=final_result,
        )

        return {
            "insight_id": insight_id,
            "scope": asdict(scope),
            "quantitative_result": quantitative_result,
            "batch_count": len(batch_results),
            "insight_result": final_result,
        }
