"""인사이트 리포트 생성: 품질 지표 + TOP N 집계 + AI 인사이트 + 감성 분포 → 콘솔 / TXT / MD."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import storage
from config import AppConfig
from report.charts import chart_by_category, chart_by_date, chart_by_sentiment, setup_korean_font
from repository import NewsRepository

logger = logging.getLogger(__name__)

SENTIMENT_LABELS = {"positive": "긍정", "neutral": "중립", "negative": "부정"}


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _scope_text(date_from: str | None, date_to: str | None, category: str | None) -> str:
    period = f"{date_from or '처음'} ~ {date_to or '현재'}"
    return f"기간 {period} · 카테고리 {category or '전체'}"


def build_report(
    *,
    stats: dict,
    top_n: int,
    categories: list[tuple[str, int]],
    sources: list[tuple[str, int]],
    dates: list[tuple[str, int]],
    sentiments: list[tuple[str, int]],
    insight: dict | None,
    charts: dict[str, str],
    scope: str,
    fmt: str = "md",
) -> str:
    md = fmt == "md"
    h1 = (lambda t: f"# {t}") if md else (lambda t: f"=== {t} ===")
    h2 = (lambda t: f"## {t}") if md else (lambda t: f"[{t}]")
    bullet = "- " if md else "  - "
    lines: list[str] = []

    lines += [h1("뉴스 AI 인사이트 리포트"), "", f"생성 시각: {datetime.now():%Y-%m-%d %H:%M:%S}", f"조건: {scope}", ""]

    lines += [h2("1. 품질 지표"), ""]
    if md:
        lines += ["| 지표 | 값 | 설명 |", "|---|---:|---|"]
        rows = [
            ("수집 원본(raw)", f"{stats['raw_total']}건", f"RSS {stats['methods'].get('rss', 0)} · 크롤링 {stats['methods'].get('crawl', 0)}"),
            ("정제 통과(clean)", f"{stats['clean_total_all']}건", "필수 필드 검증·정규화·중복 처리 후 저장된 뉴스"),
            ("중복 제거율", _pct(stats["dedup_ratio"]), f"raw {stats['raw_total']}건 중 같은 URL로 걸러진 비율 (skip/upsert)"),
            ("요약 완료율", _pct(stats["summarized_ratio"]), f"{stats['summarized']}/{stats['clean_total']}건 (조건 범위)"),
            ("평균 본문 길이", f"{stats['avg_content_len']:.0f}자", "clean 본문 기준"),
            ("평균 요약 길이", f"{stats['avg_summary_len']:.0f}자", f"압축률 {_pct(stats['compression_ratio'])}"),
            ("날짜 결측", f"{stats['missing_dates']}건", "발행·수집 시각이 비어 있는 건수"),
            ("감성 분석 완료", f"{stats['sentiment_total']}건", "보너스 · sentiment_results"),
        ]
        lines += [f"| {a} | {b} | {c} |" for a, b, c in rows]
    else:
        lines += [
            f"{bullet}수집 원본(raw): {stats['raw_total']}건 (RSS {stats['methods'].get('rss', 0)} · 크롤링 {stats['methods'].get('crawl', 0)})",
            f"{bullet}정제 통과(clean): {stats['clean_total_all']}건",
            f"{bullet}중복 제거율: {_pct(stats['dedup_ratio'])}",
            f"{bullet}요약 완료율: {_pct(stats['summarized_ratio'])} ({stats['summarized']}/{stats['clean_total']}건)",
            f"{bullet}평균 본문 길이: {stats['avg_content_len']:.0f}자 · 평균 요약 길이: {stats['avg_summary_len']:.0f}자 (압축률 {_pct(stats['compression_ratio'])})",
            f"{bullet}날짜 결측: {stats['missing_dates']}건 · 감성 분석 완료: {stats['sentiment_total']}건",
        ]
    lines.append("")

    lines += [h2(f"2. TOP {top_n} 집계"), ""]
    lines += [f"{'### ' if md else ''}카테고리별 뉴스 수"]
    lines += [f"{bullet}{i}. {name}: {count}건" for i, (name, count) in enumerate(categories[:top_n], start=1)] or [f"{bullet}(없음)"]
    lines.append("")
    if insight and insight.get("insight_result"):
        keywords = insight["insight_result"].get("keywords", [])[:top_n]
        lines += [f"{'### ' if md else ''}핵심 키워드 TOP {len(keywords)} (AI 분석)"]
        lines += [f"{bullet}{i}. {kw}" for i, kw in enumerate(keywords, start=1)]
        lines.append("")
    lines += [f"{'### ' if md else ''}일자별 수집 건수"]
    lines += [f"{bullet}{day}: {count}건" for day, count in dates[-top_n:]] or [f"{bullet}(없음)"]
    lines.append("")

    lines += [h2("3. AI 인사이트 분석 결과"), ""]
    if insight and insight.get("insight_result"):
        result = insight["insight_result"]
        lines += [
            f"분석 ID {insight['id']} · 기간 {insight.get('date_from') or '처음'} ~ {insight.get('date_to') or '현재'} · "
            f"카테고리 {insight.get('category') or '전체'} · 대상 {insight.get('selected_article_count')}건 "
            f"(요약 사용 {insight.get('summarized_article_count')}건) · 생성 {insight.get('created_at')}",
            "",
            f"{'### ' if md else ''}주요 트렌드",
            *[f"{bullet}{t}" for t in result.get("trends", [])],
            "",
            f"{'### ' if md else ''}핵심 키워드",
            ", ".join(result.get("keywords", [])),
            "",
            f"{'### ' if md else ''}주요 이슈",
            *[f"{bullet}{t}" for t in result.get("major_issues", [])],
        ]
    else:
        lines.append("저장된 인사이트가 없습니다. 먼저 `python main.py analyze`를 실행하세요.")
    lines.append("")

    if sentiments:
        lines += [h2("4. 감성 분포 (보너스)"), ""]
        total = sum(c for _, c in sentiments) or 1
        lines += [f"{bullet}{SENTIMENT_LABELS.get(label, label)}: {count}건 ({count / total * 100:.1f}%)" for label, count in sentiments]
        lines.append("")

    if charts:
        lines += [h2("5. 차트"), ""]
        for name, path in charts.items():
            lines.append(f"![{name}]({path})" if md else f"{bullet}{name}: {path}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def run_report(
    config: AppConfig,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    category: str | None = None,
    top_n: int | None = None,
    fmt: str = "md",
    out: str | None = None,
    with_charts: bool = True,
) -> str:
    """리포트를 만들어 콘솔에 출력하고 파일로 저장한다. 리포트 텍스트 반환."""
    report_cfg = config.report
    top_n = top_n or int(report_cfg.get("top_n", 5))
    output_dir = config.resolve(report_cfg.get("output_dir", "output"))
    filters = {"category": category, "date_from": date_from, "date_to": date_to}

    stats = storage.quality_stats(**filters)
    categories = storage.count_by_category(**filters)
    sources = storage.count_by_source(**filters)
    dates = storage.count_by_collected_date(**filters)
    sentiments = storage.count_by_sentiment(**filters)
    insight = NewsRepository(_db_config(config)).latest_insight(category)

    charts: dict[str, str] = {}
    if with_charts:
        font = setup_korean_font(report_cfg.get("font_family"))
        logger.info("차트 한글 폰트: %s", font)
        chart_dir = output_dir / "charts"
        charts["카테고리별 뉴스 수"] = _rel(chart_by_category(categories, chart_dir / "category_counts.png"), output_dir)
        charts["일자별 수집 추이"] = _rel(chart_by_date(dates, chart_dir / "daily_collected.png"), output_dir)
        charts["일자별 발행 추이"] = _rel(
            chart_by_date(storage.count_by_published_date(**filters), chart_dir / "daily_published.png",
                          title="일자별 발행 추이 (published_at)"), output_dir)
        if sentiments:
            charts["감성 분포"] = _rel(chart_by_sentiment(sentiments, chart_dir / "sentiment_counts.png"), output_dir)

    text = build_report(
        stats=stats, top_n=top_n, categories=categories, sources=sources, dates=dates,
        sentiments=sentiments, insight=insight, charts=charts,
        scope=_scope_text(date_from, date_to, category), fmt=fmt,
    )

    out_path = Path(out) if out else output_dir / f"report.{fmt}"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    logger.info("리포트 저장: %s", out_path)
    print(text)
    return text


def _rel(path: str, base: Path) -> str:
    try:
        return str(Path(path).relative_to(base))
    except ValueError:
        return path


def _db_config(config: AppConfig) -> dict:
    db = dict(config.database)
    db["path"] = str(config.db_path)
    return db
