#!/usr/bin/env python3
"""
Olive Tree Investments — GHL Account Export + SQLite Import

Usage:
  python3 scripts/ghl_export.py export          # dump raw JSON to archives/ghl-export-<date>/
  python3 scripts/ghl_export.py import           # upsert latest archive into olive.db (idempotent)

Env vars (in .env):
  GHL_API_KEY       — GHL Private Integration token
  GHL_LOCATION_ID   — GHL sub-account location ID

Note: uses subprocess curl (Python 3.14 SSL cert issue on this machine).
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

# ── path setup ──────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

load_dotenv(REPO_ROOT / ".env")

GHL_API_KEY     = os.getenv("GHL_API_KEY", "")
GHL_LOCATION_ID = os.getenv("GHL_LOCATION_ID", "")
GHL_BASE        = "https://services.leadconnectorhq.com"
ARCHIVES_DIR    = REPO_ROOT / "archives"


# ── GHL HTTP helpers (curl; matches capital_raise.py convention) ─────────────

def _curl_config(version: str = "2021-07-28") -> str:
    """Return curl -K config lines with headers — never exposed in argv."""
    return (
        f'header = "Authorization: Bearer {GHL_API_KEY}"\n'
        f'header = "Version: {version}"\n'
        'header = "Content-Type: application/json"\n'
        'header = "Accept: application/json"\n'
    )


def _parse(result: subprocess.CompletedProcess, label: str) -> dict:
    if not result.stdout.strip():
        print(f"  WARNING: empty response ({label}). stderr: {result.stderr.strip()}", file=sys.stderr)
        return {}
    try:
        return json.loads(result.stdout, strict=False)
    except json.JSONDecodeError as e:
        print(f"  WARNING: JSON parse error ({label}): {e}", file=sys.stderr)
        return {}


def ghl_get(path: str, params: dict | None = None, version: str = "2021-07-28") -> dict:
    url = f"{GHL_BASE}{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"
    # ponytail: headers via stdin config — keeps token out of argv/ps
    r = subprocess.run(
        ["curl", "-s", "-K", "-", url],
        input=_curl_config(version), capture_output=True, text=True,
    )
    return _parse(r, f"GET {path}")


def ghl_post(path: str, body: dict) -> dict:
    # ponytail: headers via stdin config — keeps token out of argv/ps
    r = subprocess.run(
        ["curl", "-s", "-K", "-", "-X", "POST", f"{GHL_BASE}{path}", "-d", json.dumps(body)],
        input=_curl_config(), capture_output=True, text=True,
    )
    return _parse(r, f"POST {path}")


# ── paginated contact fetch ──────────────────────────────────────────────────

def fetch_all_contacts() -> list[dict]:
    contacts, after, page = [], None, 0
    MAX_PAGES = 200  # ponytail: runaway guard — 200 pages × 100 = 20k contacts
    while page < MAX_PAGES:
        body: dict = {"locationId": GHL_LOCATION_ID, "pageLimit": 100}
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
    if page == MAX_PAGES:
        print("WARNING: hit 200-page runaway guard (20,000 contacts). Results may be incomplete.", file=sys.stderr)
    return contacts


# ── subcommand: export ───────────────────────────────────────────────────────

def cmd_export(_args):
    out_dir = ARCHIVES_DIR / f"ghl-export-{date.today()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Export directory: {out_dir}")

    # ── contacts ────────────────────────────────────────────────────────────
    print("\nFetching contacts…")
    contacts = fetch_all_contacts()
    (out_dir / "contacts.json").write_text(json.dumps(contacts, indent=2))
    print(f"  contacts: {len(contacts)}")

    # ── notes (per-contact, skip empty, throttle) ────────────────────────────
    print("Fetching notes (one call per contact)…")
    notes_map: dict[str, list] = {}
    for i, c in enumerate(contacts, 1):
        cid = c["id"]
        d = ghl_get(f"/contacts/{cid}/notes")
        note_list = d.get("notes", [])
        if note_list:
            notes_map[cid] = note_list
        if i % 100 == 0:
            print(f"  … {i}/{len(contacts)} contacts checked for notes")
        time.sleep(0.15)
    (out_dir / "notes.json").write_text(json.dumps(notes_map, indent=2))
    total_notes = sum(len(v) for v in notes_map.values())
    print(f"  notes: {total_notes} across {len(notes_map)} contacts")

    # ── conversations (best-effort) ──────────────────────────────────────────
    print("Fetching conversations (best-effort)…")
    conversations = []
    conv_errors = 0
    try:
        offset = 0
        while True:
            d = ghl_get("/conversations/search", {
                "locationId": GHL_LOCATION_ID,
                "limit": "100",
                "startAfterDate": str(offset) if offset else "",
            })
            batch = d.get("conversations", [])
            if not batch:
                break
            for conv in batch:
                try:
                    msgs = ghl_get(f"/conversations/{conv['id']}/messages", {"limit": "100"})
                    conv["messages"] = msgs.get("messages", [])
                    time.sleep(0.15)
                except Exception as e:  # noqa: BLE001
                    conv["messages"] = []
                    conv_errors += 1
            conversations.extend(batch)
            if len(batch) < 100:
                break
            offset = batch[-1].get("dateUpdated", offset + 100)
            time.sleep(0.2)
    except Exception as e:  # noqa: BLE001
        print(f"  WARNING: conversation export failed: {e}", file=sys.stderr)
    (out_dir / "conversations.json").write_text(json.dumps(conversations, indent=2))
    print(f"  conversations: {len(conversations)} (errors: {conv_errors})")

    # ── simple endpoint snapshots ────────────────────────────────────────────
    simple: list[tuple[str, str, dict | None, str]] = [
        ("tags",          f"/locations/{GHL_LOCATION_ID}/tags",                    None,                                      "2021-07-28"),
        ("custom_fields", f"/locations/{GHL_LOCATION_ID}/customFields",            None,                                      "2021-07-28"),
        ("workflows",     "/workflows/",                                            {"locationId": GHL_LOCATION_ID},           "2021-07-28"),
        ("pipelines",     "/opportunities/pipelines",                               {"locationId": GHL_LOCATION_ID},           "2021-07-28"),
        ("funnels",       "/funnels/funnel/list",                                  {"locationId": GHL_LOCATION_ID},           "2021-07-28"),
        ("forms",         "/forms/",                                                {"locationId": GHL_LOCATION_ID},           "2021-07-28"),
        ("calendars",     "/calendars/",                                            {"locationId": GHL_LOCATION_ID},           "2021-04-15"),
        ("campaigns",     "/emails/schedule",                                       {"locationId": GHL_LOCATION_ID, "limit": "100"}, "2021-07-28"),
    ]
    counts: dict[str, int] = {"contacts": len(contacts), "notes": total_notes, "conversations": len(conversations)}

    for name, path, params, version in simple:
        d = ghl_get(path, params, version=version)
        (out_dir / f"{name}.json").write_text(json.dumps(d, indent=2))
        # best-effort count: look for any list value
        ct = next((len(v) for v in d.values() if isinstance(v, list)), len(d) if d else 0)
        counts[name] = ct
        print(f"  {name}: {ct}")

    # ── summary table ────────────────────────────────────────────────────────
    print(f"\n{'─'*40}")
    print(f"{'Resource':<20} {'Count':>8}")
    print(f"{'─'*40}")
    for k, v in counts.items():
        print(f"  {k:<18} {v:>8}")
    print(f"{'─'*40}")
    print(f"Done. Archive: {out_dir}")


# ── subcommand: import ───────────────────────────────────────────────────────

def cmd_import(_args):
    # find latest archive
    archives = sorted(ARCHIVES_DIR.glob("ghl-export-*"), reverse=True)
    if not archives:
        print("No archives found. Run `export` first.", file=sys.stderr)
        sys.exit(1)
    src = archives[0]
    print(f"Importing from: {src}")

    from db.connection import get_session, init_db
    from db.schema import Campaign, Contact, ContactNote, ContactTag

    init_db()
    session = get_session()

    # ── contacts + tags ──────────────────────────────────────────────────────
    contacts_raw: list[dict] = json.loads((src / "contacts.json").read_text())
    print(f"Upserting {len(contacts_raw)} contacts…")

    contact_pk: dict[str, int] = {}  # ghl_id → db id

    for i, raw in enumerate(contacts_raw, 1):
        ghl_id = raw.get("id", "")
        try:
            row = session.query(Contact).filter_by(ghl_id=ghl_id).first()
            if not row:
                row = Contact(ghl_id=ghl_id)
                session.add(row)

            row.first_name    = raw.get("firstName")
            row.last_name     = raw.get("lastName")
            row.email         = raw.get("email")
            row.phone         = raw.get("phone")
            row.company       = raw.get("companyName")
            row.address       = raw.get("address1")
            row.city          = raw.get("city")
            row.state         = raw.get("state")
            row.postal_code   = raw.get("postalCode")
            row.custom_fields = json.dumps(raw.get("customFields") or [])
            row.source        = raw.get("source")
            row.dnd           = bool(raw.get("dnd"))
            row.unsubscribed  = bool(raw.get("unsubscribed") or False)
            row.date_added    = str(raw.get("dateAdded") or "")
            row.created_at    = str(raw.get("dateAdded") or "")

            session.flush()
            contact_pk[ghl_id] = row.id

            # tags: delete-and-replace per contact, committed immediately
            # so a mid-run kill never leaves earlier contacts tag-less
            session.query(ContactTag).filter_by(contact_id=row.id).delete()
            for tag in (raw.get("tags") or []):
                session.add(ContactTag(contact_id=row.id, tag=tag))

            session.commit()
        except Exception as e:
            session.rollback()
            print(f"  WARNING: skipped contact {ghl_id}: {e}", file=sys.stderr)
            continue

        if i % 100 == 0:
            print(f"  … {i}/{len(contacts_raw)} contacts imported")

    print(f"  contacts: {session.query(Contact).count()} in DB")

    # ── notes ────────────────────────────────────────────────────────────────
    notes_raw: dict = json.loads((src / "notes.json").read_text())
    note_count = 0
    for ghl_id, note_list in notes_raw.items():
        contact_id = contact_pk.get(ghl_id)
        if not contact_id:
            continue
        for n in note_list:
            nid = n.get("id")
            row = session.query(ContactNote).filter_by(ghl_note_id=nid).first() if nid else None
            if not row:
                row = ContactNote(contact_id=contact_id)
                session.add(row)
            row.body       = n.get("body", "")
            row.ghl_note_id = nid
            row.created_at = str(n.get("dateAdded") or "")
            note_count += 1
    session.commit()
    print(f"  notes: {note_count} upserted")

    # ── campaigns ────────────────────────────────────────────────────────────
    campaigns_raw = json.loads((src / "campaigns.json").read_text())
    camp_list = next((v for v in campaigns_raw.values() if isinstance(v, list)), [])
    for c in camp_list:
        cid_str = str(c.get("id", ""))
        row = session.query(Campaign).filter_by(name=c.get("name"), subject=c.get("subject")).first()
        if not row:
            row = Campaign()
            session.add(row)
        row.name       = c.get("name")
        row.subject    = c.get("subject")
        row.status     = c.get("status")
        row.sent_count = c.get("sentCount")
        row.created_at = str(c.get("createdAt") or "")
    session.commit()
    print(f"  campaigns: {session.query(Campaign).count()} in DB")

    session.close()
    print("Import complete (idempotent — safe to re-run).")


# ── entry point ──────────────────────────────────────────────────────────────

def main():
    if not GHL_API_KEY or not GHL_LOCATION_ID:
        print("ERROR: GHL_API_KEY and GHL_LOCATION_ID must be set in .env", file=sys.stderr)
        sys.exit(1)

    p = argparse.ArgumentParser(description="Olive Tree — GHL account export + SQLite import")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("export", help="Dump raw JSON to archives/ghl-export-<date>/")
    sub.add_parser("import", help="Upsert latest archive into olive.db (idempotent)")

    args = p.parse_args()
    {"export": cmd_export, "import": cmd_import}[args.cmd](args)


if __name__ == "__main__":
    main()
