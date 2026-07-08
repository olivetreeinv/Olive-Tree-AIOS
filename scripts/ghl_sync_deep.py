#!/usr/bin/env python3
"""
ghl_sync_deep.py — One-time sync of olive.db from a "deep export" archive
(archives/ghl-export-deep-<date>/), which uses different filenames/shapes
than the plain ghl_export.py archives (contacts_full.json instead of
contacts.json, no notes.json, plus tags.json / form_submissions.json /
newsletter_audience.json).

Reuses the contact upsert logic from scripts/ghl_export.py::cmd_import
(same field mapping, same delete-and-replace tag strategy) — only the
loader and the three new reconcile steps are new.

Usage:
    python3 scripts/ghl_sync_deep.py archives/ghl-export-deep-2026-07-07
"""

import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.connection import get_session, init_db
from db.schema import Contact, ContactNote, ContactTag

REPO = Path(__file__).parent.parent


def upsert_contacts(session, contacts_raw: list[dict]) -> tuple[int, int, dict]:
    """Same field mapping as ghl_export.py::cmd_import. Returns (created, updated, ghl_id->pk)."""
    contact_pk: dict[str, int] = {}
    created = updated = 0

    for i, raw in enumerate(contacts_raw, 1):
        ghl_id = raw.get("id", "")
        try:
            row = session.query(Contact).filter_by(ghl_id=ghl_id).first()
            is_new = row is None
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
            row.date_added    = str(raw.get("dateAdded") or "")
            if is_new:
                row.created_at = str(raw.get("dateAdded") or "")
            # unsubscribed is local-only state (not in GHL export) — never touch it here.

            session.flush()
            contact_pk[ghl_id] = row.id

            # GHL tags: delete-and-replace GHL-sourced tags only would require
            # knowing which tags came from GHL vs local. ghl_export.py's original
            # routine replaces ALL tags wholesale; that would nuke local-only tags
            # like raise-641-enrolled. Instead: union in any new GHL tag, keep everything
            # already present. ponytail: no diffing of GHL-removed tags; add if missing.
            existing_tags = {t.tag.lower() for t in row.tags}
            for tag in (raw.get("tags") or []):
                if tag.lower() not in existing_tags:
                    session.add(ContactTag(contact_id=row.id, tag=tag))
                    existing_tags.add(tag.lower())

            session.commit()
            created += is_new
            updated += (not is_new)
        except Exception as e:
            session.rollback()
            print(f"  WARNING: skipped contact {ghl_id}: {e}", file=sys.stderr)
            continue

        if i % 200 == 0:
            print(f"  … {i}/{len(contacts_raw)} contacts processed")

    return created, updated, contact_pk


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: python3 scripts/ghl_sync_deep.py <archive-dir>")
    src = REPO / sys.argv[1]
    if not src.exists():
        sys.exit(f"Archive not found: {src}")

    db_path = REPO / "data" / "olive.db"
    backup_path = REPO / "data" / f"olive.db.bak-{date.today().isoformat()}"
    if not backup_path.exists():
        backup_path.write_bytes(db_path.read_bytes())
        print(f"Backup written: {backup_path}")
    else:
        print(f"Backup already exists, leaving as-is: {backup_path}")

    init_db()
    session = get_session()

    # ── 1. contacts upsert ───────────────────────────────────────────────────
    contacts_raw = json.loads((src / "contacts_full.json").read_text())["contacts"]
    print(f"\nUpserting {len(contacts_raw)} contacts…")
    created, updated, contact_pk = upsert_contacts(session, contacts_raw)
    print(f"  created: {created}  updated: {updated}  unchanged: {len(contacts_raw) - created - updated}")

    josh = session.query(Contact).filter_by(ghl_id="PQPb8HTgpLiDh0AMkP2G").first()
    print(f"  CHECK Josh Germon: email={josh.email!r} phone={josh.phone!r}")

    # ── 2. tags reconcile ────────────────────────────────────────────────────
    ghl_tags = json.loads((src / "tags.json").read_text())["tags"]
    local_tag_counts: dict[str, int] = {}
    for (tag,) in session.query(ContactTag.tag).all():
        local_tag_counts[tag.lower()] = local_tag_counts.get(tag.lower(), 0) + 1

    print(f"\nTags reconcile ({len(ghl_tags)} GHL tags):")
    zero_count = []
    for t in ghl_tags:
        name = t["name"]
        n = local_tag_counts.get(name.lower(), 0)
        print(f"  {name:<30} {n} contacts")
        if n == 0:
            zero_count.append(name)
    print(f"  Zero-contact tags: {zero_count if zero_count else 'none'}")

    # ── 3. form submissions ──────────────────────────────────────────────────
    submissions = json.loads((src / "form_submissions.json").read_text())["submissions"]
    print(f"\nForm submissions ({len(submissions)}):")
    for sub in submissions:
        ghl_id = sub.get("contactId")
        row = session.query(Contact).filter_by(ghl_id=ghl_id).first()
        if not row:
            # fall back to email match
            email = sub.get("email")
            row = session.query(Contact).filter_by(email=email).first() if email else None
        if not row:
            print(f"  WARNING: no local contact for submission {sub.get('id')} ({sub.get('name')})")
            continue

        ts_ms = sub.get("others", {}).get("eventData", {}).get("timestamp")
        sub_date = (
            datetime.fromtimestamp(ts_ms / 1000).date().isoformat()
            if ts_ms else str(sub.get("createdAt") or "")[:10]
        )
        page = sub.get("others", {}).get("eventData", {}).get("page", {}).get("url", "unknown page")
        note_body = f"GHL form submission ({page}) on {sub_date}"

        already = any(n.body == note_body for n in row.notes)
        if already:
            print(f"  {row.email or row.ghl_id}: note already present, skipped")
            continue
        session.add(ContactNote(
            contact_id=row.id,
            body=note_body,
            created_at=datetime.now().isoformat(timespec="seconds"),
        ))
        print(f"  {row.email or row.ghl_id}: note added — {note_body}")
    session.commit()

    # ── 4. newsletter audience tagging ──────────────────────────────────────
    audience = json.loads((src / "newsletter_audience.json").read_text())
    recipient_ids = audience["all_recipient_contactIds"]
    print(f"\nNewsletter audience ({len(recipient_ids)} recipient ids):")

    raw_by_id = {c["id"]: c for c in contacts_raw}
    tagged = skipped_dnd = skipped_no_email = not_found = 0
    for ghl_id in recipient_ids:
        row = session.query(Contact).filter_by(ghl_id=ghl_id).first()
        if not row:
            not_found += 1
            continue
        raw = raw_by_id.get(ghl_id, {})
        email_dnd = (raw.get("dndSettings") or {}).get("Email", {}).get("status") == "active"
        if not row.email:
            skipped_no_email += 1
            continue
        if email_dnd or row.dnd:
            skipped_dnd += 1
            continue
        if not any(t.tag.lower() == "newsletter" for t in row.tags):
            session.add(ContactTag(contact_id=row.id, tag="newsletter"))
        tagged += 1
    session.commit()
    print(f"  tagged: {tagged}  skipped-DND: {skipped_dnd}  skipped-no-email: {skipped_no_email}  not-found-in-db: {not_found}")

    # ── 5. final sanity report ───────────────────────────────────────────────
    total = session.query(Contact).count()
    with_email = session.query(Contact).filter(Contact.email.isnot(None), Contact.email != "").count()
    newsletter_count = (
        session.query(ContactTag)
        .filter(ContactTag.tag == "newsletter")
        .join(Contact, Contact.id == ContactTag.contact_id)
        .count()
    )
    dup_ghl_ids = (
        session.query(Contact.ghl_id)
        .group_by(Contact.ghl_id)
        .having(__import__("sqlalchemy").func.count(Contact.id) > 1)
        .all()
    )

    print(f"\nFinal sanity:")
    print(f"  total contacts:        {total}")
    print(f"  with email:            {with_email}")
    print(f"  newsletter tag count:  {newsletter_count}")
    print(f"  duplicate ghl_ids:     {len(dup_ghl_ids)} {dup_ghl_ids if dup_ghl_ids else ''}")

    session.close()


if __name__ == "__main__":
    main()
