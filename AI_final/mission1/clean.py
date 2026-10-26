"""평가 전 정리 — 스크립트가 만든 산출물을 지워, 처음부터 다시 생성되는 것을 확인할 수 있게 한다.

실행: python clean.py            # 지울 대상을 보여 주고 삭제
      python clean.py --dry-run  # 목록만 보기(삭제 안 함)
다시 만들기: python analysis.py && python build_dashboard.py

지우지 않는 것: 수집 원본(data/raw/ · data/metadata.json) · 대시보드 캡처(dashboard/screenshots/) · 코드 · 문서.
원본은 다시 받으면 표본이 달라져 리포트 수치와 어긋날 수 있어 남긴다(새로 받기는 python collect.py --force).
"""

import argparse
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

# analysis.py · build_dashboard.py 가 다시 만드는 것만 지운다
TARGETS = [
    "images",                 # 그림 9장
    "outputs",                # 표 · key_numbers.json
    "data/processed",         # 정제한 주 데이터 + 파생 지표
    "dashboard/index.html",   # 대시보드
    "__pycache__",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="생성 산출물 정리")
    parser.add_argument("--dry-run", action="store_true", help="삭제하지 않고 대상만 출력")
    args = parser.parse_args()

    found = [BASE / t for t in TARGETS if (BASE / t).exists()]
    if not found:
        print("지울 산출물이 없다(이미 정리된 상태).")
        print("다시 만들기: python analysis.py && python build_dashboard.py")
        return 0

    head = "(미리보기) " if args.dry_run else ""
    for path in found:
        files = sum(1 for p in path.rglob("*") if p.is_file()) if path.is_dir() else 1
        name = f"{path.relative_to(BASE)}{'/' if path.is_dir() else ''}"
        print(f"{head}삭제: {name:<24} 파일 {files}개")
        if not args.dry_run:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

    if args.dry_run:
        print("\n실제로 지우려면: python clean.py")
    else:
        print("\n정리 완료. 다시 만들기: python analysis.py && python build_dashboard.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
