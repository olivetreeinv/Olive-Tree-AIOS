#!/usr/bin/env python3
"""
Olive Tree Investments — Capital Raise (local CRM)

GHL replaced by local CRM 2026-07-06: contacts/tags live in data/olive.db,
drips run through scripts/drip.py, soft commits live in investors /
investor_commitments tables. (send-sms removed with GHL — no local SMS
channel yet.)

Usage:
  python3 scripts/capital_raise.py audience                    # Size audience, write CSV
  python3 scripts/capital_raise.py enroll                      # Dry-run (print only)
  python3 scripts/capital_raise.py enroll --send               # Live enroll (idempotent)
  python3 scripts/capital_raise.py enroll --send --contact <id-or-email>  # Single contact
  python3 scripts/capital_raise.py track                       # Soft-commit total vs target
"""

import argparse
import csv
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from db.connection import get_session                                   # noqa: E402
from db.schema import (Contact, ContactTag, DripEnrollment,             # noqa: E402
                       Investor, InvestorCommitment)
from drip import load_steps, resolve_contact                            # noqa: E402

# ─────────────────────────────────────────────
# Config — 641 Powder Springs defaults
# ─────────────────────────────────────────────

DEAL_SLUG    = "641-powder-springs"
DRIP_NAME    = "pitch-deck"          # replaces GHL "Deal Funnel Pitch Deck" workflow
ENROLLED_TAG = "raise-641-enrolled"
RAISE_TARGET = 400_000               # Q3 goal

OUTPUT_DIR = ROOT / "output" / "capital-raise"


# ─────────────────────────────────────────────
# Audience subcommand
# ─────────────────────────────────────────────

def cmd_audience(args):
    session = get_session()
    contacts = session.query(Contact).all()
    tags_by_contact: dict[int, list[str]] = {}
    by_tag: dict[str, int] = {}
    for t in session.query(ContactTag).all():
        tags_by_contact.setdefault(t.contact_id, []).append(t.tag)

    tagged = [c for c in contacts if tags_by_contact.get(c.id)]
    untagged = len(contacts) - len(tagged)
    for c in tagged:
        for t in tags_by_contact[c.id]:
            by_tag[t] = by_tag.get(t, 0) + 1

    with_email = sum(1 for c in tagged if (c.email or "").strip())
    with_phone = sum(1 for c in tagged if (c.phone or "").strip())
    already = sum(1 for c in tagged if ENROLLED_TAG in tags_by_contact[c.id])

    print(f"\n{'='*50}")
    print(f"AUDIENCE — {DEAL_SLUG}")
    print(f"{'='*50}")
    print(f"  Total contacts:       {len(contacts)}")
    print(f"  Tagged (audience):    {len(tagged)}")
    print(f"  Untagged (excluded):  {untagged}")
    print(f"  Have email:           {with_email}")
    print(f"  Have phone:           {with_phone}")
    print(f"  Already enrolled:     {already}")
    print(f"  Net to enroll:        {len(tagged) - already}")
    print(f"\nTag breakdown:")
    for t, n in sorted(by_tag.items(), key=lambda x: -x[1]):
        print(f"  {t}: {n}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / f"{DEAL_SLUG}-audience-{date.today()}.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "first_name", "last_name", "email", "phone", "tags", "enrolled"])
        for c in tagged:
            tags = tags_by_contact[c.id]
            w.writerow([c.id, c.first_name or "", c.last_name or "",
                        c.email or "", c.phone or "", "|".join(tags),
                        "yes" if ENROLLED_TAG in tags else "no"])
    session.close()
    print(f"\nCSV written: {csv_path}")


# ─────────────────────────────────────────────
# Enroll subcommand
# ─────────────────────────────────────────────

def cmd_enroll(args):
    live = args.send
    mode = "LIVE" if live else "DRY-RUN"
    print(f"[{mode}] Enrolling into local drip: {DRIP_NAME}")
    print("506(b) REMINDER: This outreach is to pre-existing relationships only (tagged contacts).\n")

    steps = load_steps(DRIP_NAME)
    first_due = (datetime.now() + timedelta(days=steps[0]["delay_days"])).isoformat(timespec="seconds")

    session = get_session()
    if args.contact:
        c = resolve_contact(session, args.contact)
        if not c:
            raise SystemExit(f"ERROR: contact '{args.contact}' not found")
        targets = [c]
    else:
        # audience = contacts with ≥1 tag, minus the already-enrolled tag
        tagged_ids = {t.contact_id for t in session.query(ContactTag).all()}
        enrolled_ids = {t.contact_id for t in session.query(ContactTag)
                        .filter(ContactTag.tag == ENROLLED_TAG).all()}
        targets = (session.query(Contact)
                   .filter(Contact.id.in_(tagged_ids - enrolled_ids)).all())
        print(f"Target: {len(targets)} tagged, not-yet-enrolled contacts")

    enrolled = skipped = 0
    for i, c in enumerate(targets, 1):
        name = f"{c.first_name or ''} {c.last_name or ''}".strip() or c.email or c.id
        reason = None
        if not (c.email or "").strip():
            reason = "no email"
        elif c.unsubscribed:
            reason = "unsubscribed"
        elif session.query(DripEnrollment).filter(
                DripEnrollment.contact_id == c.id,
                DripEnrollment.drip_name == DRIP_NAME,
                DripEnrollment.status.in_(["active", "done"])).first():
            reason = "already in drip"
        if reason:
            skipped += 1
            print(f"  [{i}] skip: {name} — {reason}")
            continue
        if not live:
            print(f"  [{i}] WOULD enroll: {name}  |  {c.email or ''}")
            enrolled += 1
            continue
        session.add(DripEnrollment(contact_id=c.id, drip_name=DRIP_NAME,
                                   step=1, next_due=first_due, status="active"))
        if not session.query(ContactTag).filter(
                ContactTag.contact_id == c.id, ContactTag.tag == ENROLLED_TAG).first():
            session.add(ContactTag(contact_id=c.id, tag=ENROLLED_TAG))
        enrolled += 1
        print(f"  [{i}] enrolled: {name}")

    if live:
        session.commit()
    session.close()
    print(f"\n{'='*50}")
    if live:
        print(f"Enrolled: {enrolled} | Skipped: {skipped}")
        print("Emails go out on the next `drip.py run` (daily 9:00 via launchd).")
    else:
        print(f"DRY-RUN complete. Would enroll {enrolled} contacts. Run with --send to execute.")


# ─────────────────────────────────────────────
# Track subcommand
# ─────────────────────────────────────────────

def cmd_track(args):
    session = get_session()
    commits = session.query(InvestorCommitment).all()

    soft, all_rows = [], []
    total_committed = 0
    for cm in commits:
        inv = session.get(Investor, cm.investor_id)
        name = inv.name if inv else f"investor #{cm.investor_id}"
        val = cm.amount or 0
        all_rows.append((name, cm.status or "?", val))
        if (cm.status or "").lower() in ("soft", "funded"):
            total_committed += val
            soft.append((name, val))
    session.close()

    pct = (total_committed / RAISE_TARGET * 100) if RAISE_TARGET else 0
    remaining = max(0, RAISE_TARGET - total_committed)

    print(f"\n{'='*50}")
    print(f"SOFT-COMMIT TRACKER — {DEAL_SLUG}")
    print(f"{'='*50}")
    print(f"  Q3 Raise Target:  ${RAISE_TARGET:,.0f}")
    print(f"  Committed so far: ${total_committed:,.0f}  ({pct:.1f}%)")
    print(f"  Still needed:     ${remaining:,.0f}")
    print(f"\nSoft/funded commitments ({len(soft)}):")
    if soft:
        for name, val in sorted(soft, key=lambda x: -x[1]):
            print(f"  {name}: ${val:,.0f}")
    else:
        print("  (none yet)")
    print(f"\nAll commitments ({len(all_rows)}):")
    if all_rows:
        for name, status, val in all_rows:
            print(f"  [{status}] {name}: ${val:,.0f}")
    else:
        print("  (pipeline is empty)")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Olive Tree Capital Raise — local CRM")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("audience", help="Size and export the tagged audience to CSV")

    ep = sub.add_parser("enroll", help="Enroll tagged contacts into the pitch-deck drip")
    ep.add_argument("--send", action="store_true", help="Execute live (default: dry-run)")
    ep.add_argument("--contact", help="Enroll a single contact (id or email) for self-test")

    sub.add_parser("track", help="Show soft-commit total vs raise target")

    args = p.parse_args()
    {"audience": cmd_audience, "enroll": cmd_enroll, "track": cmd_track}[args.cmd](args)


if __name__ == "__main__":
    main()
