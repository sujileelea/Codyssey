"""시드 CSV(date, value, memo)를 Firestore data 컬렉션에 올린다.

    python scripts/seed_firestore.py --dry-run          # 올릴 내용만 확인
    python scripts/seed_firestore.py                    # data 가 비어 있을 때만 올린다
    python scripts/seed_firestore.py --reset            # 기존 data 를 backups/ 에 JSON 으로 저장한 뒤 지우고 다시 올린다

자격 증명은 서버와 같은 환경 변수(.env)를 쓴다 — FIREBASE_SERVICE_ACCOUNT_PATH 또는 _JSON,
로컬 에뮬레이터면 FIRESTORE_EMULATOR_HOST.
"""
import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.firebase import get_db          # noqa: E402
from app.repositories import now          # noqa: E402
from app.schemas import DataIn            # noqa: E402

DEFAULT_CSV = BACKEND / "data" / "ai_shopping_weekly.csv"
BATCH = 400                               # Firestore 배치 한도 500 이하


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        rows = [DataIn(**r) for r in csv.DictReader(f)]          # 서버와 같은 검증을 통과한 행만
    days = [r.date for r in rows]
    if len(days) != len(set(days)):
        raise SystemExit("같은 날짜가 두 번 이상 있습니다.")
    return [{"date": r.date.isoformat(), "value": r.value, "memo": r.memo} for r in rows]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--reset", action="store_true", help="기존 data 를 백업한 뒤 지우고 다시 올린다")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    rows = load(a.csv)
    print(f"{a.csv.name}: {len(rows)}행 ({rows[0]['date']} ~ {rows[-1]['date']})")
    if a.dry_run:
        return

    col = get_db().collection("data")
    existing = list(col.stream())
    if existing and not a.reset:
        raise SystemExit(f"data 컬렉션에 이미 {len(existing)}개가 있습니다. 바꾸려면 --reset 을 붙이세요.")
    if existing:
        backup = BACKEND / "backups" / f"data-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
        backup.parent.mkdir(exist_ok=True)
        backup.write_text(json.dumps([{"id": s.id, **s.to_dict()} for s in existing], ensure_ascii=False, default=str, indent=1),
                          encoding="utf-8")
        print(f"백업: {backup.relative_to(BACKEND)} ({len(existing)}개)")
        for i in range(0, len(existing), BATCH):
            batch = get_db().batch()
            for s in existing[i:i + BATCH]:
                batch.delete(s.reference)
            batch.commit()

    for i in range(0, len(rows), BATCH):
        batch = get_db().batch()
        for r in rows[i:i + BATCH]:
            batch.set(col.document(), {**r, "created_at": now(), "updated_at": now()})
        batch.commit()
    print(f"업로드: {len(rows)}개 → data 컬렉션")


if __name__ == "__main__":
    main()
