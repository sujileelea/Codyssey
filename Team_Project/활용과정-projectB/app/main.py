"""뉴스 AI 파이프라인 CLI 진입점 (argparse 서브커맨드).

필수: fetch · clean · summarize · analyze · report · export
보너스: sentiment · list · show

종료 코드: 0 성공 · 1 부분 실패(또는 실행 오류) · 2 설정·인자 오류
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date

import storage
from config import AppConfig, load_config
from log import setup_logging

logger = logging.getLogger("main")

CATEGORY_HELP = "카테고리 (config cleaning.categories 중 하나). 생략 시 전체"


def valid_date(value: str) -> str:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("날짜는 YYYY-MM-DD 형식이어야 합니다.") from exc
    return value


def add_scope_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--date-from", type=valid_date, help="시작일 (YYYY-MM-DD, 발행일 기준)")
    parser.add_argument("--date-to", type=valid_date, help="종료일 (YYYY-MM-DD, 발행일 기준)")
    parser.add_argument("--category", help=CATEGORY_HELP)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="뉴스 수집 → 정제 → AI 요약·분석 → 리포트 CLI (BBC News 코리아)",
    )
    parser.add_argument("--config", default="config.json", help="설정 파일 경로 (기본 config.json)")
    parser.add_argument("--verbose", action="store_true", help="DEBUG 로그 출력")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("fetch", help="뉴스 수집 (RSS + 크롤링) → raw 저장")
    p.add_argument("--source", choices=["rss", "crawl", "all"], default="all", help="수집 방법 (기본 all)")
    p.add_argument("--limit", type=int, default=20, help="RSS 항목 수 / 섹션당 기사 수 (기본 20)")
    p.add_argument("--category", help="크롤링할 섹션 하나만 지정")
    p.add_argument("--no-body", action="store_true", help="RSS 본문 보강(크롤링) 생략")

    p = sub.add_parser("clean", help="raw → 정제·중복 처리 → clean 저장")
    p.add_argument("--duplicate-policy", choices=["skip", "upsert"], help="중복 정책 (기본 config)")
    p.add_argument("--all", action="store_true", help="처리된 raw까지 전건 재정제")
    p.add_argument("--limit", type=int, help="처리할 raw 최대 건수")

    p = sub.add_parser("summarize", help="AI 요약 → news.summary 저장")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--all", action="store_true", help="전체 뉴스 대상 (이미 요약된 건은 스킵)")
    g.add_argument("--unsummarized", action="store_true", help="미요약 뉴스만 (기본)")
    g.add_argument("--id", type=int, nargs="+", dest="news_ids", help="특정 뉴스 ID")
    p.add_argument("--limit", type=int, help="최대 처리 건수 (기본 config summary.default_limit)")
    p.add_argument("--force", action="store_true", help="이미 요약된 뉴스도 다시 요약")

    p = sub.add_parser("analyze", help="기간·카테고리 뉴스 종합 AI 인사이트 분석")
    add_scope_options(p)
    p.add_argument("--limit", type=int, help="분석 대상 최대 기사 수 (기본 config analysis.default_limit)")
    p.add_argument("--sort", choices=["latest", "oldest"], default="latest")
    p.add_argument("--show", type=int, metavar="ID", help="저장된 분석 결과 조회")
    p.add_argument("--list", action="store_true", help="저장된 분석 결과 목록")

    p = sub.add_parser("sentiment", help="[보너스] 뉴스 감성 분석 (긍정/중립/부정)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--id", type=int, dest="article_id", help="특정 뉴스 1건 분석/재분석")
    g.add_argument("--all", action="store_true", help="이미 분석된 기사도 재분석")
    g.add_argument("--unsentimented", action="store_true", help="미분석 기사만 (기본)")
    add_scope_options(p)
    p.add_argument("--limit", type=int)
    p.add_argument("--sort", choices=["latest", "oldest"], default="latest")

    p = sub.add_parser("report", help="품질 지표·TOP N·AI 인사이트 리포트 + 차트")
    add_scope_options(p)
    p.add_argument("--top", type=int, help="TOP N (기본 config report.top_n)")
    p.add_argument("--format", choices=["md", "txt"], default="md")
    p.add_argument("--out", help="저장 경로 (기본 output/report.<format>)")
    p.add_argument("--no-charts", action="store_true", help="차트 생성 생략")

    p = sub.add_parser("export", help="CSV / JSONL / Excel 내보내기")
    p.add_argument("--format", choices=["csv", "jsonl", "xlsx"], default="csv")
    p.add_argument("--status", choices=["all", "clean", "summarized"], default="all", help="요약 상태 필터")
    add_scope_options(p)
    p.add_argument("--out", help="저장 경로 (기본 output/exports/…)")

    p = sub.add_parser("list", help="[보너스] 뉴스 목록 조회 (필터·페이지네이션)")
    add_scope_options(p)
    p.add_argument("--keyword", help="제목·본문·요약 키워드")
    p.add_argument("--status", choices=["all", "clean", "summarized"], default="all")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--page-size", type=int, default=10)
    p.add_argument("--sort", choices=["latest", "oldest"], default="latest")

    p = sub.add_parser("show", help="[보너스] 뉴스 상세 조회")
    p.add_argument("id", type=int)
    return parser


# ---------------------------------------------------------------------------
# 핸들러
# ---------------------------------------------------------------------------

def _db_config(config: AppConfig) -> dict:
    db = dict(config.database)
    db["path"] = str(config.db_path)
    return db


def _validate_category(config: AppConfig, category: str | None) -> None:
    if category and config.categories and category not in config.categories + ["기타"]:
        raise ValueError(f"알 수 없는 카테고리 '{category}'. 가능한 값: {', '.join(config.categories)}, 기타")


def _validate_range(args: argparse.Namespace) -> None:
    if getattr(args, "date_from", None) and getattr(args, "date_to", None) and args.date_from > args.date_to:
        raise ValueError("--date-from은 --date-to보다 늦을 수 없습니다.")


def cmd_fetch(config: AppConfig, args: argparse.Namespace) -> int:
    from collector import run_fetch

    _validate_category(config, args.category)
    success, failed = run_fetch(
        config, source=args.source, limit=args.limit, category=args.category, with_body=not args.no_body
    )
    return 0 if failed == 0 or success > 0 else 1


def cmd_clean(config: AppConfig, args: argparse.Namespace) -> int:
    from clean_service import clean_saved_articles

    clean_saved_articles(config, args.duplicate_policy, all_raw=args.all, limit=args.limit)
    return 0  # 필수 필드 미충족 건은 정상적인 정제 탈락이므로 실패로 보지 않는다


def _ai_client(config: AppConfig):
    from ai_client import build_ai_client

    return build_ai_client(config.ai)


def cmd_summarize(config: AppConfig, args: argparse.Namespace) -> int:
    from summarizer import run_summarize

    mode = "id" if args.news_ids else "all" if args.all else "unsummarized"
    counts = run_summarize(
        config, _ai_client(config), mode=mode, news_ids=args.news_ids, limit=args.limit, force=args.force
    )
    return 0 if counts["failed"] == 0 else 1


def print_insight(insight: dict) -> None:
    result = insight.get("insight_result") or {}
    print("\n=== AI 인사이트 분석 결과 ===")
    print(f"저장 ID: {insight['id']}")
    print(f"조건: {insight.get('date_from') or '처음'} ~ {insight.get('date_to') or '현재'} · 카테고리 {insight.get('category') or '전체'}")
    print(f"선택 뉴스: {insight.get('selected_article_count')}건 · 요약 사용 뉴스: {insight.get('summarized_article_count')}건")
    print("\n[주요 트렌드]")
    for item in result.get("trends", []):
        print(f"- {item}")
    print("\n[핵심 키워드]")
    print(", ".join(result.get("keywords", [])))
    print("\n[주요 이슈]")
    for item in result.get("major_issues", []):
        print(f"- {item}")


def cmd_analyze(config: AppConfig, args: argparse.Namespace) -> int:
    from insight_analyzer import InsightAnalyzer
    from models import AnalysisScope
    from repository import NewsRepository

    repository = NewsRepository(_db_config(config))

    if args.list:
        rows = repository.list_insights()
        if not rows:
            print("저장된 분석 결과가 없습니다.")
        for row in rows:
            print(f"ID={row['id']} | {row['created_at']} | {row.get('date_from') or '처음'}~{row.get('date_to') or '현재'} | "
                  f"{row.get('category') or '전체'} | {row['selected_article_count']}건")
        return 0

    if args.show:
        insight = repository.get_insight(args.show)
        if not insight:
            logger.error("ID=%s 분석 결과를 찾을 수 없습니다.", args.show)
            return 1
        print_insight(insight)
        return 0

    _validate_range(args)
    _validate_category(config, args.category)
    analysis_cfg = config.analysis
    limit = args.limit or int(analysis_cfg.get("default_limit", 50))
    max_limit = int(analysis_cfg.get("max_limit", 200))
    if limit <= 0 or limit > max_limit:
        raise ValueError(f"--limit은 1~{max_limit} 사이여야 합니다.")

    scope = AnalysisScope(
        date_from=args.date_from, date_to=args.date_to, category=args.category, limit=limit, sort=args.sort
    )
    analyzer = InsightAnalyzer(
        repository=repository,
        ai_client=_ai_client(config),
        batch_size=int(analysis_cfg.get("batch_size", 20)),
        max_ai_attempts=int(analysis_cfg.get("max_ai_attempts", 2)),
    )
    logger.info("AI 분석 요청 중...")
    result = analyzer.analyze(scope)
    logger.info("분석 완료")
    insight = repository.get_insight(result["insight_id"])
    print_insight(insight)
    return 0


def cmd_sentiment(config: AppConfig, args: argparse.Namespace) -> int:
    from models import SentimentScope
    from repository import NewsRepository
    from sentiment_analyzer import SentimentAnalyzer

    _validate_range(args)
    _validate_category(config, args.category)
    cfg = config.sentiment
    mode = "id" if args.article_id else "all" if args.all else "unsentimented"
    limit = 1 if args.article_id else (args.limit or int(cfg.get("default_limit", 20)))
    scope = SentimentScope(
        date_from=args.date_from, date_to=args.date_to, category=args.category,
        limit=limit, sort=args.sort, article_id=args.article_id, mode=mode,
    )
    analyzer = SentimentAnalyzer(
        repository=NewsRepository(_db_config(config)),
        ai_client=_ai_client(config),
        max_ai_attempts=int(cfg.get("max_ai_attempts", 2)),
    )
    result = analyzer.analyze(scope)
    print("\n=== AI 감성 분석 결과 ===")
    print(f"선택 뉴스: {result['selected_article_count']}건 · 분석 완료: {result['analyzed_article_count']}건 · "
          f"실패: {result['failed_count']}건 · 본문 없음 스킵: {result['skipped_no_content_count']}건")
    for item in result["results"]:
        sr = item["sentiment_result"]
        print(f"- ID={item['news_id']} | {sr['sentiment']} | score={sr['score']:.2f} | {sr['reason']}")
    return 0 if result["failed_count"] == 0 else 1


def cmd_report(config: AppConfig, args: argparse.Namespace) -> int:
    from report.report import run_report

    _validate_range(args)
    _validate_category(config, args.category)
    run_report(
        config, date_from=args.date_from, date_to=args.date_to, category=args.category,
        top_n=args.top, fmt=args.format, out=args.out, with_charts=not args.no_charts,
    )
    return 0


def cmd_export(config: AppConfig, args: argparse.Namespace) -> int:
    from report.exporter import run_export

    _validate_range(args)
    _validate_category(config, args.category)
    path = run_export(
        config, fmt=args.format, status=args.status, category=args.category,
        date_from=args.date_from, date_to=args.date_to, out=args.out,
    )
    print(path)
    return 0


def cmd_list(config: AppConfig, args: argparse.Namespace) -> int:
    _validate_range(args)
    _validate_category(config, args.category)
    rows, total = storage.list_news(
        category=args.category, date_from=args.date_from, date_to=args.date_to,
        status=None if args.status == "all" else args.status, keyword=args.keyword,
        page=args.page, page_size=args.page_size, order=args.sort,
    )
    pages = max((total + args.page_size - 1) // args.page_size, 1)
    print(f"총 {total}건 · 페이지 {args.page}/{pages} (페이지당 {args.page_size}건)")
    print(f"{'ID':>4}  {'발행일':<16}  {'카테고리':<6}  {'상태':<10}  {'감성':<8}  제목")
    for row in rows:
        status = "summarized" if row.get("summary") else "clean"
        sentiment = "-"
        if row.get("sentiment_result_json"):
            try:
                sentiment = json.loads(row["sentiment_result_json"]).get("sentiment", "-")
            except ValueError:
                pass
        print(f"{row['id']:>4}  {(row.get('published_at') or '')[:16]:<16}  {row.get('category') or '':<6}  "
              f"{status:<10}  {sentiment:<8}  {row['title'][:50]}")
    if not rows:
        print("(조건에 맞는 뉴스가 없습니다)")
    return 0


def cmd_show(config: AppConfig, args: argparse.Namespace) -> int:
    from repository import NewsRepository

    row = storage.get_news(args.id)
    if not row:
        logger.error("ID=%s 뉴스를 찾을 수 없습니다.", args.id)
        return 1
    sentiment = None
    with NewsRepository(_db_config(config)).connect() as conn:
        NewsRepository(_db_config(config)).ensure_sentiments_table()
        srow = conn.execute("SELECT sentiment_result_json FROM sentiment_results WHERE news_id = ?", (args.id,)).fetchone()
        if srow:
            sentiment = json.loads(srow[0])
    print(f"=== 뉴스 ID {row['id']} ===")
    print(f"제목    : {row['title']}")
    print(f"URL     : {row['url']}")
    print(f"카테고리: {row.get('category')} · 소스: {row.get('source')} · 수집 방법: raw_id={row.get('raw_id')}")
    print(f"발행    : {row.get('published_at')} · 수집: {row.get('collected_at')}")
    print(f"요약    : {row.get('summary') or '(미요약)'}")
    if sentiment:
        print(f"감성    : {sentiment.get('sentiment')} (score {sentiment.get('score')}) — {sentiment.get('reason')}")
    print("본문    :")
    print(row["content"][:1500] + (" …" if len(row["content"]) > 1500 else ""))
    return 0


HANDLERS = {
    "fetch": cmd_fetch, "clean": cmd_clean, "summarize": cmd_summarize, "analyze": cmd_analyze,
    "sentiment": cmd_sentiment, "report": cmd_report, "export": cmd_export, "list": cmd_list, "show": cmd_show,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        parser.exit(2, f"[ERROR] {exc}\n")

    log_cfg = config.logging
    setup_logging(log_cfg.get("level", "INFO"), config.resolve(log_cfg.get("file", "logs/app.log")), args.verbose)
    storage.configure(config.db_path)
    storage.create_tables()

    try:
        return HANDLERS[args.command](config, args)
    except ValueError as exc:
        logger.error("%s", exc)
        return 2
    except KeyboardInterrupt:
        logger.warning("사용자 중단")
        return 1
    except Exception as exc:  # 예상 밖 오류: 스택은 파일 로그에, 콘솔엔 한 줄
        logger.error("실행 실패: %s", exc)
        logger.debug("상세", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
