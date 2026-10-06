"""국내 여행 추천 CLI — LLM(Gemini) + 지도(Kakao Local) API 조합.

    python3 travel_planner.py -date "YYYY-MM-DD" [--cities N] [--count N] [--no-cache]

흐름: [1/3] LLM 1차 추천(JSON) → [2/3] 지역별 맛집 검색 → [3/3] LLM 최종 리포트(Markdown)
결과: results/<날짜>_raw.json · results/<날짜>_travel_plan.md
"""

import argparse
import sys
from datetime import datetime

import config
import pipeline
import place_api


def valid_date(text):
    """argparse 타입 검사 — YYYY-MM-DD 가 아니면 사용법과 함께 종료된다."""
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        parsed = None
    # strptime 은 '2026-1-5' 도 받아 주므로, 파일명·캐시 키가 갈리지 않게 0 채움 형식인지도 본다
    if parsed is None or parsed.strftime("%Y-%m-%d") != text:
        raise argparse.ArgumentTypeError(f"날짜 형식이 올바르지 않습니다: '{text}' (예: 2026-10-03)")
    return text


def valid_count(text):
    """argparse 타입 검사 — 지역당 맛집 수는 1~15 (Kakao 검색 size 상한)."""
    try:
        value = int(text)
    except ValueError:
        value = 0
    if not 1 <= value <= place_api.MAX_SIZE:
        raise argparse.ArgumentTypeError(f"맛집 수는 1~{place_api.MAX_SIZE} 사이 정수여야 합니다: '{text}'")
    return value


def build_parser():
    parser = argparse.ArgumentParser(
        prog="travel_planner.py",
        description="여행 날짜를 입력하면 LLM 이 지역을 추천하고, 지도 API 로 맛집을 찾아 여행 리포트를 만든다.",
    )
    parser.add_argument("-date", "--date", required=True, type=valid_date, metavar='"YYYY-MM-DD"',
                        help="여행 날짜 (필수)")
    parser.add_argument("--cities", type=int, default=3, choices=[1, 2, 3],
                        help="추천 지역 수 (기본 3, 보너스: 복수 지역)")
    parser.add_argument("--count", type=valid_count, default=5,
                        help=f"지역당 맛집 검색 수 1~{place_api.MAX_SIZE} (기본 5)")
    parser.add_argument("--no-cache", action="store_true",
                        help="같은 날짜의 저장된 원본 JSON 이 있어도 API 를 다시 호출한다")
    return parser


def run(args):
    """CLI 실행 — 파이프라인을 돌리고 결과 경로를 안내한다. 종료 코드를 돌려준다."""
    result = pipeline.run(args.date, args.cities, args.count, use_cache=not args.no_cache)
    if not result["ok"]:
        return 1
    errors = result["raw"]["errors"]
    print(f"\n완료! {pipeline.display_path(result['report_path'])} 를 확인하세요.")
    print(f"      원본 데이터: {pipeline.display_path(result['raw_path'])}")
    if errors:
        print(f"      오류 {len(errors)}건 — 리포트 끝 '오류 요약(errors)' 참고")
    return 0


def main():
    args = build_parser().parse_args()   # 날짜 형식 오류 → 사용법 출력 후 종료(exit 2)
    config.require_keys()                # 키 미설정 → 설정 안내 후 종료(exit 1)
    sys.exit(run(args))


if __name__ == "__main__":
    main()
