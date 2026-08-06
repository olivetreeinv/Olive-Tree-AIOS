#!/usr/bin/env python3
"""
Olive Tree — Land Call (/land-call cockpit)

Daily cold-call cockpit for phone-enriched sellers in the Land Sellers tab.
Shows today's call list (new + callbacks due) with a pre-filled script and
each owner's offer. Logs outcomes back to the sheet.

Requires skip-traced phone numbers in the Owner Phone column (col 12).
Manual free lookup: True People Search. Paid: BatchData / Kind (~$0.10/record).
Add phones directly to the Land Sellers tab — no separate step needed.

Usage:
  # Today's call list for Cartersville
  python3 scripts/land_call.py --zip 30120

  # Log a call outcome
  python3 scripts/land_call.py --log <parcel_id> --outcome interested
  python3 scripts/land_call.py --log <parcel_id> --outcome no
  python3 scripts/land_call.py --log <parcel_id> --outcome callback --callback 2026-06-24
  python3 scripts/land_call.py --log <parcel_id> --outcome contracted

  # Show callbacks due today or earlier
  python3 scripts/land_call.py --zip 30120 --callbacks

  # Add a phone number to an existing row
  python3 scripts/land_call.py --add-phone <parcel_id> --phone 770-555-0100

  # All sellers with no phone yet (for skip-trace prioritization)
  python3 scripts/land_call.py --zip 30120 --no-phone
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from land_sheets import get_token, read_rows, upsert_row  # noqa: E402

load_dotenv()

TAB = "Land Sellers"

# Column indices (land_setup.TABS["Land Sellers"])
C_PARCEL   =  0   # Parcel ID
C_SITUS    =  1   # Situs Address
C_ZIP      =  2   # Situs Zip
C_ACRES    =  4   # Acres
C_OWNER    =  5   # Owner Name
C_OFFER    = 11   # Offer Price
C_PHONE    = 12   # Owner Phone (skip-traced)
C_CHANNEL  = 14   # Channel
C_STATUS   = 15   # Call Status
C_LASTCALL = 16   # Last Call (ISO date)
C_CALLBACK = 17   # Callback Date (ISO date)
C_OUTCOME  = 18   # Outcome
C_NOTES    = 19   # Notes

OUTCOMES = {"interested", "no", "callback", "contracted", "voicemail", "wrong-number"}

SCRIPT = """
  ─────────────────────────────────────────────────────────────
  SELLER SCRIPT
  ─────────────────────────────────────────────────────────────
  OPEN:
  "Hey {owner} — is this the owner of {situs}?
   I'll be quick — would you be open to selling that lot
   if the price was right?"

  OFFER:
  "I can do {offer} cash — you pay zero realtor fees and
   zero closing costs, so it's net to you. Close in 2–3
   weeks through a title company. You sign remotely."

  IF THEY PUSH BACK ON PRICE:
  "Got it — let me check with my partner real quick…"
  [pause 60s]
  "…yeah, we can make {offer} work. And we can move fast."

  IF NO:
  "No worries — save my number as 'Brian Land Guy'. If you
   ever decide to sell, that's me. Have a good one."
  ─────────────────────────────────────────────────────────────
"""


def _col(row, idx, default=""):
    return (row[idx].strip() if len(row) > idx and row[idx] else default)


def _offer_fmt(raw):
    try:
        return f"${float(raw):,.0f}"
    except (ValueError, TypeError):
        return raw or "[OFFER]"


def _is_callable(row, mode, today_str):
    phone  = _col(row, C_PHONE)
    status = _col(row, C_STATUS)
    cb     = _col(row, C_CALLBACK)
    if not phone:
        return False
    if mode == "callbacks":
        return status == "callback" and cb and cb <= today_str
    # Normal list: new + voicemail + callback due today
    if status in ("new", "voicemail"):
        return True
    if status == "callback" and cb and cb <= today_str:
        return True
    return False


def cmd_list(args):
    token = get_token()
    rows  = read_rows(token, TAB)
    if len(rows) <= 1:
        sys.exit("Land Sellers tab is empty — run /land-sellers first.")

    today_str = date.today().isoformat()
    data = rows[1:]

    calls = []
    for i, r in enumerate(data, 2):   # row index 2+ in sheet (row 1 = header)
        if args.zip_code and _col(r, C_ZIP) != args.zip_code:
            continue
        if _is_callable(r, "callbacks" if args.callbacks else "all", today_str):
            calls.append((i, r))

    if args.no_phone:
        calls = [(i, r) for i, r in enumerate(data, 2)
                 if (not args.zip_code or _col(r, C_ZIP) == args.zip_code)
                 and not _col(r, C_PHONE)]
        print(f"\n  Sellers without a phone — zip {args.zip_code or 'all'}:\n")
        for _, r in calls:
            print(f"  {_col(r, C_PARCEL):18} {_col(r, C_OWNER):32} {_col(r, C_SITUS)}")
        print(f"\n  {len(calls)} row(s). Add phones with --add-phone <parcel_id> --phone <num>.")
        return

    label = "Callbacks due" if args.callbacks else "Today's call list"
    print(f"\n  {label} — zip {args.zip_code or 'all'} — {today_str}")
    print(f"  {len(calls)} seller(s) to call\n")

    if not calls:
        if not args.callbacks:
            print("  No callable rows. Possible reasons:")
            print("  • Owner Phone column is empty — skip-trace phones first (--no-phone shows list).")
            print("  • All new rows already called today.")
        return

    for idx, (_, r) in enumerate(calls, 1):
        parcel = _col(r, C_PARCEL)
        owner  = _col(r, C_OWNER)
        situs  = _col(r, C_SITUS)
        offer  = _offer_fmt(_col(r, C_OFFER))
        phone  = _col(r, C_PHONE)
        status = _col(r, C_STATUS)
        cb     = _col(r, C_CALLBACK)

        print(f"  {'='*60}")
        print(f"  CALL {idx}: {owner}")
        print(f"  Parcel: {parcel}   Situs: {situs}")
        print(f"  Phone:  {phone}   Status: {status}"
              + (f"   Callback was: {cb}" if cb else ""))
        print(SCRIPT.format(owner=owner, situs=situs, offer=offer))
        print(f"  Log result:")
        print(f"    python3 scripts/land_call.py --log {parcel} --outcome interested")
        print(f"    python3 scripts/land_call.py --log {parcel} --outcome no")
        print(f"    python3 scripts/land_call.py --log {parcel} --outcome callback "
              f"--callback YYYY-MM-DD")
        print()


def cmd_log(args):
    if args.outcome not in OUTCOMES:
        sys.exit(f"--outcome must be one of: {', '.join(sorted(OUTCOMES))}")

    token = get_token()
    rows  = read_rows(token, TAB)
    today = date.today().isoformat()

    # Find the matching row
    target = None
    for r in rows[1:]:
        if _col(r, C_PARCEL) == args.log:
            target = list(r)
            break
    if target is None:
        sys.exit(f"Parcel '{args.log}' not found in Land Sellers tab.")

    # Pad row to at least 20 cols
    while len(target) < 20:
        target.append("")

    target[C_STATUS]   = args.outcome
    target[C_LASTCALL] = today
    target[C_OUTCOME]  = args.outcome
    if args.callback:
        target[C_CALLBACK] = args.callback
    if args.notes:
        existing = target[C_NOTES] or ""
        target[C_NOTES] = (existing + " | " + args.notes).strip(" |")

    upsert_row(token, TAB, C_PARCEL, args.log, target)

    msg = f"Logged: {args.log} → {args.outcome}"
    if args.callback:
        msg += f" (callback {args.callback})"
    print(f"  {msg}")

    if args.outcome == "interested":
        print("\n  Next: qualify the seller (title clear? sole owner? back taxes?).")
        print("  Then /land-contract to draft the PSA.")
    elif args.outcome == "no":
        print("\n  Tagged 'no'. Ask them to save your number — many deals close months later.")
    elif args.outcome == "callback":
        print(f"\n  Callback scheduled for {args.callback}. "
              f"It'll surface in --callbacks on that date.")
    elif args.outcome == "contracted":
        print("\n  Contracted! Run /land-deal to track the spread and deal-killer checks.")


def cmd_add_phone(args):
    if not args.phone:
        sys.exit("--phone is required with --add-phone")

    token = get_token()
    rows  = read_rows(token, TAB)

    target = None
    for r in rows[1:]:
        if _col(r, C_PARCEL) == args.add_phone:
            target = list(r)
            break
    if target is None:
        sys.exit(f"Parcel '{args.add_phone}' not found in Land Sellers tab.")

    while len(target) < 20:
        target.append("")

    target[C_PHONE]   = args.phone
    target[C_CHANNEL] = "call"   # promote from mail to call now that we have a number

    upsert_row(token, TAB, C_PARCEL, args.add_phone, target)
    print(f"  Phone {args.phone} added for {args.add_phone}; channel → call.")
    print(f"  Run `python3 scripts/land_call.py --zip <zip>` to see today's call list.")


def main():
    ap = argparse.ArgumentParser(description="Land seller cold-call cockpit.")
    ap.add_argument("--zip", dest="zip_code", help="Filter to this situs zip")
    ap.add_argument("--callbacks", action="store_true",
                    help="Show only callbacks due today or earlier")
    ap.add_argument("--no-phone", action="store_true",
                    help="List sellers without a phone number (skip-trace queue)")

    # Logging
    ap.add_argument("--log", metavar="PARCEL_ID", help="Parcel to log a call for")
    ap.add_argument("--outcome", choices=sorted(OUTCOMES),
                    help="Call outcome to record")
    ap.add_argument("--callback", metavar="YYYY-MM-DD",
                    help="Callback date (use with --outcome callback)")
    ap.add_argument("--notes", help="Free-text call notes appended to Notes column")

    # Phone enrichment
    ap.add_argument("--add-phone", metavar="PARCEL_ID",
                    help="Add a skip-traced phone to a seller row")
    ap.add_argument("--phone", help="Phone number to add (use with --add-phone)")

    args = ap.parse_args()

    if args.log:
        cmd_log(args)
    elif args.add_phone:
        cmd_add_phone(args)
    else:
        cmd_list(args)


if __name__ == "__main__":
    main()
