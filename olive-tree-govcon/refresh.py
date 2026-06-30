#!/usr/bin/env python3
"""
refresh.py — CLI tool for updating local SAM.gov bulk-data extracts.

Usage
-----
python refresh.py entities                  # latest monthly Entity Management extract
python refresh.py entities --date 20240601  # specific date
python refresh.py exclusions                # latest daily Exclusions extract
python refresh.py exclusions --date 20240601
python refresh.py all                       # both (entities first, then exclusions)
python refresh.py status                    # show what's currently loaded

Schedule examples (crontab -e)
------------------------------
# Daily exclusions at 06:00
0 6 * * * cd /path/to/olive-tree-govcon && .venv/bin/python refresh.py exclusions

# Monthly entities on the 5th at 02:00 (gives SAM.gov time to publish)
0 2 5 * * cd /path/to/olive-tree-govcon && .venv/bin/python refresh.py entities
"""

import argparse
import asyncio
import os
import sys
import textwrap
from datetime import datetime, timezone

from dotenv import load_dotenv

from entity_db import SAM_DB, db_stats
from extract_manager import refresh_entities, refresh_exclusions

load_dotenv()


def _banner():
    print()
    print("  🌿  Olive Tree GovCon — SAM.gov Bulk Data Refresh")
    print(f"      {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print()


def _print_status():
    stats = db_stats(SAM_DB)
    print("  ─── Database Status ───────────────────────────────────")
    print(f"  Entities    : {stats['entity_count']:>10,}")
    print(f"  Exclusions  : {stats['exclusion_count']:>10,}")
    print()
    if stats["last_entity_import"]:
        e = stats["last_entity_import"]
        print(f"  Last entity import  : {e['filename']}  ({e['finished_at'][:19]})")
    else:
        print("  Last entity import  : (none — run: python refresh.py entities)")
    if stats["last_exclusion_import"]:
        x = stats["last_exclusion_import"]
        print(f"  Last exclusion import: {x['filename']}  ({x['finished_at'][:19]})")
    else:
        print("  Last exclusion import: (none — run: python refresh.py exclusions)")
    print()
    if not stats["ready"]:
        print("  ⚠️  Entity database is empty. Run 'python refresh.py all' to populate.")
    else:
        print("  ✅ Database is populated and ready.")
    print()


async def _run(args):
    api_key = os.getenv("SAM_API_KEY", "").strip()
    if not api_key and args.command != "status":
        print("  ✗  SAM_API_KEY not set in .env")
        sys.exit(1)

    _banner()

    if args.command == "status":
        _print_status()
        return

    if args.command in ("entities", "all"):
        print("  ── Entity Management (monthly) ────────────────────────")
        try:
            n = await refresh_entities(
                api_key=api_key,
                db_path=SAM_DB,
                date_str=getattr(args, "date", None),
                log=print,
            )
            print(f"  → {n:,} entities loaded.\n")
        except Exception as exc:
            print(f"\n  ✗  Entity refresh failed: {exc}\n")
            if args.command == "entities":
                sys.exit(1)

    if args.command in ("exclusions", "all"):
        print("  ── Exclusions (daily) ─────────────────────────────────")
        try:
            n = await refresh_exclusions(
                api_key=api_key,
                db_path=SAM_DB,
                date_str=getattr(args, "date", None),
                log=print,
            )
            print(f"  → {n:,} exclusion records loaded.\n")
        except Exception as exc:
            print(f"\n  ✗  Exclusion refresh failed: {exc}\n")
            sys.exit(1)

    _print_status()


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent("""\
            Refresh local SAM.gov bulk-data extracts.

            commands:
              entities    Download + import the monthly Entity Management extract
              exclusions  Download + import the daily Exclusions extract
              all         Both of the above
              status      Show what is currently loaded
        """),
    )
    parser.add_argument(
        "command",
        choices=["entities", "exclusions", "all", "status"],
    )
    parser.add_argument(
        "--date",
        metavar="YYYYMMDD",
        help="Force a specific extract date instead of auto-discovering the latest",
    )
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
