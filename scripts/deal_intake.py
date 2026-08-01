#!/usr/bin/env python3
"""
deal_intake.py — scan ~/Downloads for new deal-doc drops (OM / T-12 / Rent Roll)
and print the ready-to-paste workup command for each. Removes the manual
"here's the folder path" step at the start of every workup.

Usage:
  python3 scripts/deal_intake.py            # show new (unseen) candidates
  python3 scripts/deal_intake.py --all      # include already-seen ones
  python3 scripts/deal_intake.py --ack      # mark current candidates as seen
  python3 scripts/deal_intake.py --count    # just print the number (for heartbeat)
"""

import argparse
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

DOWNLOADS = Path.home() / "Downloads"
SEEN_FILE = Path(__file__).parent.parent / "data" / "deal_intake_seen.json"
DAYS_BACK = 21

DOC_PAT = re.compile(
    r"\bom\b|offering|t[\s\-_]?12|trailing|rent[\s\-_]?roll|proforma|pro[\s\-_]forma|financial",
    re.IGNORECASE,
)
DOC_EXT = {".pdf", ".xlsx", ".xls", ".csv"}


def _seen() -> set[str]:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def find_candidates() -> list[dict]:
    """Folders in ~/Downloads (recent, containing deal-looking docs)."""
    cutoff = datetime.now() - timedelta(days=DAYS_BACK)
    out = []
    if not DOWNLOADS.exists():
        return out
    for d in DOWNLOADS.iterdir():
        if not d.is_dir() or d.name.startswith("."):
            continue
        if datetime.fromtimestamp(d.stat().st_mtime) < cutoff:
            continue
        docs = []
        # ponytail: 2000-file cap guards against a giant unzipped repo in Downloads
        for i, f in enumerate(d.rglob("*")):
            if i > 2000:
                break
            if f.is_file() and f.suffix.lower() in DOC_EXT and DOC_PAT.search(f.name):
                docs.append(f.name)
        if docs:
            out.append({"path": str(d), "name": d.name, "docs": sorted(docs)[:8]})
    return sorted(out, key=lambda c: c["name"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="include already-seen folders")
    ap.add_argument("--ack", action="store_true", help="mark current candidates as seen")
    ap.add_argument("--count", action="store_true", help="print only the count of new candidates")
    args = ap.parse_args()

    cands = find_candidates()
    seen = _seen()
    new = [c for c in cands if c["path"] not in seen]

    if args.count:
        print(len(new))
        return

    if args.ack:
        SEEN_FILE.parent.mkdir(exist_ok=True)
        SEEN_FILE.write_text(json.dumps(sorted(seen | {c["path"] for c in cands}), indent=1))
        print(f"Acknowledged {len(new)} new candidate(s); {len(cands)} total marked seen.")
        return

    show = cands if args.all else new
    if not show:
        print("No new deal-doc folders in ~/Downloads.")
        return

    print(f"DEAL INTAKE — {len(show)} candidate(s) in ~/Downloads:\n")
    for c in show:
        tag = "" if c["path"] not in seen else "  (seen)"
        print(f"  {c['name']}{tag}")
        for doc in c["docs"]:
            print(f"      - {doc}")
        print(f"    → Lets workup {c['name']} — docs: '{c['path']}'\n")
    print("After starting a workup: python3 scripts/deal_intake.py --ack")


if __name__ == "__main__":
    main()
