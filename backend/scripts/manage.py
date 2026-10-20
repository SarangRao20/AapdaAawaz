"""Database and demo management.

Usage (from backend/):
    .venv\\Scripts\\python scripts\\manage.py init-db          create tables (never drops data)
    .venv\\Scripts\\python scripts\\manage.py reset            delete all reports/incidents/audit (keeps settings)
    .venv\\Scripts\\python scripts\\manage.py reset --reseed   ...and load the 40 synthetic reports again
    .venv\\Scripts\\python scripts\\manage.py seed             load synthetic reports that are not loaded yet
    .venv\\Scripts\\python scripts\\manage.py evaluate         print development/hold-out metrics

Stop the API server before running reset against the same database.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal, init_db  # noqa: E402
from app.services import demo, evaluation, stats  # noqa: E402
from app.services.settings_store import get_config  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    r = sub.add_parser("reset")
    r.add_argument("--reseed", action="store_true")
    r.add_argument("--settings", action="store_true", help="also restore default thresholds")
    sub.add_parser("seed")
    sub.add_parser("evaluate")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        if args.cmd == "init-db":
            print("database ready")
        elif args.cmd == "reset":
            print("deleted:", json.dumps(demo.reset(db, reset_settings=args.settings)))
            if args.reseed:
                print("seeded:", demo.seed(db, "all")["created"], "reports")
        elif args.cmd == "seed":
            print("seeded:", demo.seed(db, "remaining")["created"], "reports")
        elif args.cmd == "evaluate":
            res = evaluation.run(get_config(db))
            for name, split in res["splits"].items():
                m = split["metrics"]
                print(f"\n[{name}] n={m['n_reports']}  {split['description']}")
                print(f"  location accuracy     {m['location']['accuracy']:.3f}")
                print(f"  people-count accuracy {m['people_count']['accuracy']:.3f}")
                print(f"  priority accuracy     {m['priority']['accuracy']:.3f}  under-triaged: {m['priority']['under_triaged']}")
                print(f"  vulnerable micro F1   {m['vulnerable']['micro']['f1']}")
                d = m["deduplication"]["pairwise"]
                print(f"  duplicate pairs P/R   {d['precision']} / {d['recall']}")
                print(f"  human-review rate     {m['human_review']['rate']:.3f}")
            print("\n" + "\n".join(f"* {c}" for c in res["caveats"]))
        if args.cmd != "evaluate":
            s = stats.dashboard(db)
            print(f"reports={s['total_reports']} incidents={s['unique_incidents']} duplicates_linked={s['duplicates_linked']}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
