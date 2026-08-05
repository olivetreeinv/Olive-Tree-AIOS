#!/usr/bin/env python3
"""drip_dupe_check.py — did today's 9am drip double-send?

Written for the MacBook→mini cutover (2026-08-05). Both machines had
com.olivetree.drip scheduled for 9am; if the MacBook's jobs weren't fully
retired, every contact gets two emails. This checks the receipts rather than
trusting that the bootout worked.

A double-send is the same contact receiving the same drip step twice in one day.

  .venv/bin/python scripts/drip_dupe_check.py            # print the report
  .venv/bin/python scripts/drip_dupe_check.py --notify   # + macOS banner / ntfy push
  .venv/bin/python scripts/drip_dupe_check.py --date 2026-08-06

Exit 0 = clean, 1 = duplicates found.
"""
import argparse
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DB = REPO / "data" / "olive.db"


def check(day: str):
    """Returns (total_sent, real_dupes, explained_dupes).

    A contact enrolled N times in the same drip legitimately receives N copies —
    that's a data problem, not a double-send. Only duplicates in EXCESS of the
    enrollment count indicate two machines both running the drip job.
    """
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    total = c.execute(
        "select count(*) from email_log where sent_at like ?", (f"{day}%",)
    ).fetchone()[0]
    rows = c.execute(
        """select contact_id, drip_step, count(*) n
             from email_log
            where sent_at like ?
         group by contact_id, drip_step
           having n > 1
         order by n desc""",
        (f"{day}%",),
    ).fetchall()

    # How many times is each contact enrolled in each drip?
    enrol = {
        (cid, name): n
        for cid, name, n in c.execute(
            "select contact_id, drip_name, count(*) from drip_enrollments group by contact_id, drip_name"
        )
    }
    c.close()

    real, explained = [], []
    for cid, step, n in rows:
        # drip_step looks like "drip:641-powder-springs:02" -> drip name is the middle
        parts = (step or "").split(":")
        name = parts[1] if len(parts) > 2 else None
        expected = enrol.get((cid, name), 1)
        (explained if n <= expected else real).append((cid, step, n, expected))
    return total, real, explained


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--notify", action="store_true")
    a = ap.parse_args()

    total, real, explained = check(a.date)

    if not total:
        title, body = "Drip check: no sends", f"No emails logged for {a.date}."
    elif real:
        worst = max(n for _, _, n, _ in real)
        title = f"DRIP DOUBLE-SEND — {len(real)} contact(s)"
        body = (
            f"{total} emails logged {a.date}. {len(real)} contact/step pairs got MORE "
            f"copies than their enrollment count (worst: {worst}x). Two machines are "
            f"likely both running the drip job — check launchctl list on the MacBook "
            f"and that its plists are in ~/aios-retired/."
        )
    else:
        title = "Drip check: clean"
        body = f"{total} emails logged {a.date}, no unexplained duplicates."
        if explained:
            body += f" ({len(explained)} contact(s) got multiple copies from duplicate ENROLLMENTS — a data issue, not a double-send.)"

    print(f"{title}\n{body}")
    for cid, step, n, exp in real[:10]:
        print(f"  UNEXPLAINED  contact {cid}  {step}  sent {n}x, enrolled {exp}x")
    for cid, step, n, exp in explained[:10]:
        print(f"  explained    contact {cid}  {step}  sent {n}x, enrolled {exp}x")

    if a.notify:
        subprocess.run([str(REPO / "scripts" / "notify.sh"), title, body], check=False)

    return 1 if real else 0


if __name__ == "__main__":
    sys.exit(main())
