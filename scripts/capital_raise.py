#!/usr/bin/env python3
"""
Olive Tree Investments — Capital Raise (GHL)

Segments the GHL contact list, enrolls tagged contacts into a deal drip workflow,
and tracks soft-commit totals against the raise target.

Usage:
  python3 scripts/capital_raise.py audience                    # Size audience, write CSV
  python3 scripts/capital_raise.py enroll                      # Dry-run (print only)
  python3 scripts/capital_raise.py enroll --send               # Live enroll (idempotent)
  python3 scripts/capital_raise.py enroll --send --contact-id <id>  # Single contact (self-test)
  python3 scripts/capital_raise.py send-sms                    # Dry-run SMS to friend tag
  python3 scripts/capital_raise.py send-sms --send             # Live SMS send (idempotent)
  python3 scripts/capital_raise.py send-sms --tag family       # Different tag (default: friend)
  python3 scripts/capital_raise.py track                       # Soft-commit total vs target

Env vars (in .env):
  GHL_API_KEY       — GHL Private Integration token
  GHL_LOCATION_ID   — GHL sub-account location ID

Note: uses subprocess curl for all HTTP calls (Python 3.14 SSL cert issue in this env).
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# Config — 641 Powder Springs defaults
# ─────────────────────────────────────────────

GHL_API_KEY      = os.getenv("GHL_API_KEY", "")
GHL_LOCATION_ID  = os.getenv("GHL_LOCATION_ID", "")
GHL_BASE         = "https://services.leadconnectorhq.com"

DEAL_SLUG        = "641-powder-springs"
WORKFLOW_ID      = "0f93b671-d649-4836-9cd4-39ce0985c4c1"   # "Deal Funnel Pitch Deck"
PIPELINE_ID      = "TUzH2bLOw4Iw06LUB625"                   # Investors
SOFT_COMMIT_STAGE= "aae3cd8d-aaca-48a6-8638-f19950794d37"   # "Soft commitment" stage
ENROLLED_TAG     = "raise-641-enrolled"
RAISE_TARGET     = 400_000   # Q3 goal

OUTPUT_DIR       = Path("output/capital-raise")

ENROLL_BATCH     = 20          # contacts per batch before sleeping
ENROLL_SLEEP     = 2.0         # seconds between batches (rate-limit guard)
ENROLL_CALL_SLEEP= 0.25        # seconds between individual enrollment calls

SMS_TAG          = "friend"    # default tag for send-sms
SMS_SENT_TAG     = "raise-641-sms-sent"
SMS_BODY         = (
    "Hey {first_name}, it's Brian Norton. Got a new multifamily deal in Smyrna, GA — "
    "641 Powder Springs, 14 units. 6% pref, ~18% target ROI, $25K min. "
    "2-min walkthrough + deck: https://olivetreeinv.io/641_powder — "
    "let me know if you want in. Reply STOP to opt out."
)


# ─────────────────────────────────────────────
# GHL API helpers
# ─────────────────────────────────────────────

def _headers_v1():
    return [
        "-H", f"Authorization: Bearer {GHL_API_KEY}",
        "-H", "Version: 2021-07-28",
        "-H", "Content-Type: application/json",
        "-H", "Accept: application/json",
    ]


def _parse(result: subprocess.CompletedProcess, label: str) -> dict:
    if not result.stdout.strip():
        print(f"WARNING: empty response from GHL ({label}). stderr: {result.stderr.strip()}", file=sys.stderr)
        return {}
    try:
        return json.loads(result.stdout, strict=False)
    except json.JSONDecodeError as e:
        print(f"WARNING: JSON parse error from GHL ({label}): {e}", file=sys.stderr)
        return {}


def ghl_get(path: str, params: dict | None = None) -> dict:
    url = f"{GHL_BASE}{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"
    result = subprocess.run(["curl", "-s", url] + _headers_v1(), capture_output=True, text=True)
    return _parse(result, f"GET {path}")


def ghl_post(path: str, body: dict) -> dict:
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", f"{GHL_BASE}{path}"] + _headers_v1() + ["-d", json.dumps(body)],
        capture_output=True, text=True
    )
    return _parse(result, f"POST {path}")


def ghl_post_empty(path: str) -> dict:
    """POST with no body (workflow enrollment)."""
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", f"{GHL_BASE}{path}"] + _headers_v1(),
        capture_output=True, text=True
    )
    return _parse(result, f"POST {path}")


def ghl_post_tags(contact_id: str, tags: list[str]) -> dict:
    return ghl_post(f"/contacts/{contact_id}/tags", {"tags": tags})


# ─────────────────────────────────────────────
# Contact pagination
# ─────────────────────────────────────────────

def fetch_all_contacts() -> list[dict]:
    contacts = []
    after = None
    page = 0
    while page < 20:
        body = {"locationId": GHL_LOCATION_ID, "pageLimit": 100}
        if after:
            body["searchAfter"] = after
        d = ghl_post("/contacts/search", body)
        batch = d.get("contacts", [])
        if not batch:
            break
        contacts.extend(batch)
        after = batch[-1].get("searchAfter")
        page += 1
        if len(batch) < 100:
            break
    if page == 20:
        print("WARNING: hit 20-page cap (2,000 contacts). Results may be incomplete.", file=sys.stderr)
    return contacts


# ─────────────────────────────────────────────
# Audience subcommand
# ─────────────────────────────────────────────

def cmd_audience(args):
    print("Scanning GHL contacts…")
    all_contacts = fetch_all_contacts()
    print(f"Total fetched: {len(all_contacts)}")

    tagged, untagged, by_tag = [], [], {}
    for c in all_contacts:
        tags = c.get("tags") or []
        if tags:
            tagged.append(c)
            for t in tags:
                by_tag[t] = by_tag.get(t, 0) + 1
        else:
            untagged.append(c)

    with_email = sum(1 for c in tagged if c.get("email"))
    with_phone = sum(1 for c in tagged if c.get("phone"))
    already_enrolled = sum(1 for c in tagged if ENROLLED_TAG in (c.get("tags") or []))

    print(f"\n{'='*50}")
    print(f"AUDIENCE — {DEAL_SLUG}")
    print(f"{'='*50}")
    print(f"  Total contacts:       {len(all_contacts)}")
    print(f"  Tagged (audience):    {len(tagged)}")
    print(f"  Untagged (excluded):  {len(untagged)}")
    print(f"  Have email:           {with_email}")
    print(f"  Have phone:           {with_phone}")
    print(f"  Already enrolled:     {already_enrolled}")
    print(f"  Net to enroll:        {len(tagged) - already_enrolled}")
    print(f"\nTag breakdown:")
    for t, n in sorted(by_tag.items(), key=lambda x: -x[1]):
        print(f"  {t}: {n}")

    # Write CSV
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / f"{DEAL_SLUG}-audience-{date.today()}.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "first_name", "last_name", "email", "phone", "tags", "enrolled"])
        for c in tagged:
            tags = c.get("tags") or []
            w.writerow([
                c.get("id", ""),
                c.get("firstName", ""),
                c.get("lastName", ""),
                c.get("email", ""),
                c.get("phone", ""),
                "|".join(tags),
                "yes" if ENROLLED_TAG in tags else "no",
            ])
    print(f"\nCSV written: {csv_path}")


# ─────────────────────────────────────────────
# Enroll subcommand
# ─────────────────────────────────────────────

def cmd_enroll(args):
    single_id = getattr(args, "contact_id", None)
    live = getattr(args, "send", False)

    mode = "LIVE" if live else "DRY-RUN"
    print(f"[{mode}] Enrolling into workflow: Deal Funnel Pitch Deck")
    print(f"         Workflow ID: {WORKFLOW_ID}")
    if single_id:
        print(f"         Single contact: {single_id}")
    print()

    # 506(b) reminder
    print("506(b) REMINDER: This outreach is to pre-existing relationships only (tagged contacts).")
    print()

    if single_id:
        contacts = [ghl_get(f"/contacts/{single_id}").get("contact") or {"id": single_id}]
    else:
        print("Fetching contacts…")
        all_contacts = fetch_all_contacts()
        contacts = [c for c in all_contacts if (c.get("tags") or []) and ENROLLED_TAG not in (c.get("tags") or [])]
        print(f"Target: {len(contacts)} untagged-enrolled contacts with ≥1 tag")

    enrolled_count = 0
    skipped_count = 0
    error_count = 0

    for i, c in enumerate(contacts, 1):
        name = f"{c.get('firstName', '')} {c.get('lastName', '')}".strip() or c.get("email") or c["id"]
        tags = c.get("tags") or []

        if ENROLLED_TAG in tags and not single_id:
            skipped_count += 1
            continue

        if not live:
            print(f"  [{i}/{len(contacts)}] WOULD enroll: {name}  |  {c.get('email','')}  |  {c.get('phone','')}")
            enrolled_count += 1
            continue

        # Enroll in workflow — GHL returns {} or a success body on 200; errors always include "message"
        resp = ghl_post_empty(f"/contacts/{c['id']}/workflow/{WORKFLOW_ID}")

        if "message" not in resp:
            # Tag as enrolled (idempotency)
            ghl_post_tags(c["id"], [ENROLLED_TAG])
            enrolled_count += 1
            print(f"  [{i}] enrolled: {name}")
        else:
            error_count += 1
            print(f"  [{i}] ERROR ({name}): {resp.get('message', resp)}")

        time.sleep(ENROLL_CALL_SLEEP)
        if i % ENROLL_BATCH == 0:
            print(f"  … batch {i // ENROLL_BATCH} done, sleeping {ENROLL_SLEEP}s …")
            time.sleep(ENROLL_SLEEP)

    print(f"\n{'='*50}")
    if live:
        print(f"Enrolled: {enrolled_count} | Skipped (already enrolled): {skipped_count} | Errors: {error_count}")
    else:
        print(f"DRY-RUN complete. Would enroll {enrolled_count} contacts. Run with --send to execute.")


# ─────────────────────────────────────────────
# Send-SMS subcommand
# ─────────────────────────────────────────────

def cmd_send_sms(args):
    tag = getattr(args, "tag", SMS_TAG) or SMS_TAG
    live = getattr(args, "send", False)

    mode = "LIVE" if live else "DRY-RUN"
    print(f"[{mode}] SMS first-touch — tag: '{tag}'")
    print(f"506(b) REMINDER: Outreach to pre-existing relationships only.")
    print()

    print("Fetching contacts…")
    all_contacts = fetch_all_contacts()

    targets = [
        c for c in all_contacts
        if tag in (c.get("tags") or [])
        and c.get("phone")
        and SMS_SENT_TAG not in (c.get("tags") or [])
    ]
    skipped_no_phone = sum(
        1 for c in all_contacts
        if tag in (c.get("tags") or []) and not c.get("phone")
    )
    already_sent = sum(
        1 for c in all_contacts
        if tag in (c.get("tags") or []) and SMS_SENT_TAG in (c.get("tags") or [])
    )

    print(f"Tag '{tag}' contacts:  {sum(1 for c in all_contacts if tag in (c.get('tags') or []))}")
    print(f"  Have phone:          {len(targets) + already_sent}")
    print(f"  Already sent:        {already_sent}  (skipping)")
    print(f"  No phone:            {skipped_no_phone}  (skipping)")
    print(f"  Will text:           {len(targets)}")
    print()

    if not targets:
        print("Nothing to send.")
        return

    sent_count = error_count = 0

    for i, c in enumerate(targets, 1):
        first = c.get("firstName") or c.get("first_name") or "there"
        name  = f"{first} {c.get('lastName', '')}".strip()
        phone = c.get("phone", "")
        body  = SMS_BODY.format(first_name=first)

        if not live:
            print(f"  [{i}/{len(targets)}] WOULD text: {name}  |  {phone}")
            sent_count += 1
            continue

        # Get or create conversation — if one already exists, fetch it
        conv_resp = ghl_post("/conversations/", {
            "locationId": GHL_LOCATION_ID,
            "contactId": c["id"],
        })
        conv_id = conv_resp.get("conversation", {}).get("id") or conv_resp.get("id")

        if not conv_id:
            # Conversation already exists — search for it
            search = ghl_get("/conversations/search", {
                "locationId": GHL_LOCATION_ID,
                "contactId": c["id"],
                "limit": "1",
            })
            existing = search.get("conversations", [])
            conv_id = existing[0].get("id") if existing else None

        if not conv_id:
            print(f"  [{i}] ERROR: could not get conversation for {name}")
            error_count += 1
            time.sleep(ENROLL_CALL_SLEEP)
            continue

        msg_resp = ghl_post("/conversations/messages", {
            "type": "SMS",
            "conversationId": conv_id,
            "contactId": c["id"],
            "message": body,
        })

        if "message" in msg_resp and msg_resp.get("message") != "success":
            print(f"  [{i}] ERROR ({name}): {msg_resp.get('message', msg_resp)}")
            error_count += 1
        else:
            ghl_post_tags(c["id"], [SMS_SENT_TAG])
            sent_count += 1
            print(f"  [{i}] sent: {name}  |  {phone}")

        time.sleep(ENROLL_CALL_SLEEP)
        if i % ENROLL_BATCH == 0:
            print(f"  … batch {i // ENROLL_BATCH} done, sleeping {ENROLL_SLEEP}s …")
            time.sleep(ENROLL_SLEEP)

    print(f"\n{'='*50}")
    if live:
        print(f"Sent: {sent_count} | Errors: {error_count} | Already sent (skipped): {already_sent}")
    else:
        print(f"DRY-RUN complete. Would text {sent_count} contacts. Run with --send to execute.")


# ─────────────────────────────────────────────
# Track subcommand
# ─────────────────────────────────────────────

def cmd_track(args):
    print("Fetching Investors pipeline…")
    d = ghl_get("/opportunities/search", {
        "location_id": GHL_LOCATION_ID,
        "pipeline_id": PIPELINE_ID,
        "limit": "100",
    })
    opps = d.get("opportunities", [])

    total_committed = 0
    soft_commits = []
    all_opps = []

    for o in opps:
        stage_id = (o.get("pipelineStage") or {}).get("id", "")
        val = o.get("monetaryValue") or 0
        name = o.get("name", "?")
        stage_name = (o.get("pipelineStage") or {}).get("name", "?")
        all_opps.append((name, stage_name, val))
        if stage_id == SOFT_COMMIT_STAGE:
            total_committed += val
            soft_commits.append((name, val))

    pct = (total_committed / RAISE_TARGET * 100) if RAISE_TARGET else 0
    remaining = max(0, RAISE_TARGET - total_committed)

    print(f"\n{'='*50}")
    print(f"SOFT-COMMIT TRACKER — {DEAL_SLUG}")
    print(f"{'='*50}")
    print(f"  Q3 Raise Target:  ${RAISE_TARGET:,.0f}")
    print(f"  Committed so far: ${total_committed:,.0f}  ({pct:.1f}%)")
    print(f"  Still needed:     ${remaining:,.0f}")
    print(f"\nSoft commitments ({len(soft_commits)}):")
    if soft_commits:
        for name, val in sorted(soft_commits, key=lambda x: -x[1]):
            print(f"  {name}: ${val:,.0f}")
    else:
        print("  (none yet)")

    print(f"\nAll pipeline opportunities ({len(all_opps)}):")
    if all_opps:
        for name, stage, val in all_opps:
            print(f"  [{stage}] {name}: ${val:,.0f}")
    else:
        print("  (pipeline is empty)")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def main():
    if not GHL_API_KEY or not GHL_LOCATION_ID:
        print("ERROR: GHL_API_KEY and GHL_LOCATION_ID must be set in .env", file=sys.stderr)
        sys.exit(1)

    p = argparse.ArgumentParser(description="Olive Tree Capital Raise — GHL")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("audience", help="Size and export the tagged audience to CSV")

    enroll_p = sub.add_parser("enroll", help="Enroll tagged contacts into the deal drip")
    enroll_p.add_argument("--send", action="store_true", help="Execute live (default: dry-run)")
    enroll_p.add_argument("--contact-id", help="Enroll a single contact ID only (for self-test)")

    sms_p = sub.add_parser("send-sms", help="SMS first-touch to a tag (default: friend)")
    sms_p.add_argument("--send", action="store_true", help="Execute live (default: dry-run)")
    sms_p.add_argument("--tag", default=SMS_TAG, help=f"Tag to target (default: {SMS_TAG})")

    sub.add_parser("track", help="Show soft-commit total vs raise target")

    args = p.parse_args()
    {
        "audience": cmd_audience,
        "enroll": cmd_enroll,
        "send-sms": cmd_send_sms,
        "track": cmd_track,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
