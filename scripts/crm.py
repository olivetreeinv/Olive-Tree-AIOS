#!/usr/bin/env python3
"""
Olive Tree — CRM CLI  (/crm skill engine)

Local contact management on top of data/olive.db.
Source of truth for all contacts (GHL decommissioning in progress).

Usage:
  python3 scripts/crm.py search "Jane"
  python3 scripts/crm.py search "investor" --tag newsletter --tag lp-prospect
  python3 scripts/crm.py show 42
  python3 scripts/crm.py show jane@example.com
  python3 scripts/crm.py add --first Jane --last Doe --email jane@example.com \\
      --phone 770-555-0100 --company "Acme Capital" --tag investor --note "Met at conf"
  python3 scripts/crm.py tag 42 newsletter lp-prospect
  python3 scripts/crm.py untag 42 newsletter
  python3 scripts/crm.py note 42 "Called — interested in next deal"
  python3 scripts/crm.py unsub 42
  python3 scripts/crm.py resub 42
  python3 scripts/crm.py segments
  python3 scripts/crm.py import-csv path/to/contacts.csv
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func, or_
from db.connection import get_session
from db.schema import Contact, ContactTag, ContactNote, EmailLog, DripEnrollment


# ── resolution helper ────────────────────────────────────────────────────────

def _resolve(session, ref: str) -> Contact:
    """Resolve id (int str) or email to a Contact; exit on miss."""
    if ref.lstrip("-").isdigit():
        c = session.get(Contact, int(ref))
    elif "@" in ref:
        c = session.query(Contact).filter(
            func.lower(Contact.email) == ref.lower()
        ).first()
    else:
        sys.exit(f"Error: '{ref}' is not an id (integer) or email (contains @)")
    if not c:
        sys.exit(f"Contact not found: {ref}")
    return c


def _tag_str(contact: Contact) -> str:
    return ", ".join(t.tag for t in contact.tags) if contact.tags else "—"


# ── subcommands ──────────────────────────────────────────────────────────────

def cmd_search(args):
    session = get_session()
    q = args.query.lower()

    base = session.query(Contact).filter(
        or_(
            func.lower(Contact.first_name).contains(q),
            func.lower(Contact.last_name).contains(q),
            func.lower(Contact.email).contains(q),
            func.lower(Contact.phone).contains(q),
            func.lower(Contact.company).contains(q),
        )
    )

    # AND-filter each --tag
    for tag in (args.tag or []):
        tag_l = tag.lower()
        base = base.filter(
            Contact.id.in_(
                session.query(ContactTag.contact_id).filter(
                    func.lower(ContactTag.tag) == tag_l
                )
            )
        )

    total = base.count()
    rows = base.limit(50).all()

    print(f"{'ID':<6} {'Name':<30} {'Email':<35} {'Phone':<16} Tags")
    print("─" * 100)
    for c in rows:
        name = f"{c.first_name or ''} {c.last_name or ''}".strip() or "—"
        print(f"{c.id:<6} {name:<30} {(c.email or '—'):<35} {(c.phone or '—'):<16} {_tag_str(c)}")
    if total > 50:
        print(f"\n… {total - 50} more. Narrow your query.")
    else:
        print(f"\n{total} result(s)")
    session.close()


def cmd_show(args):
    session = get_session()
    c = _resolve(session, args.ref)

    name = f"{c.first_name or ''} {c.last_name or ''}".strip() or "—"
    print(f"\n{'─'*60}")
    print(f"  {name}  (id={c.id})")
    print(f"{'─'*60}")
    print(f"  Email:       {c.email or '—'}")
    print(f"  Phone:       {c.phone or '—'}")
    print(f"  Company:     {c.company or '—'}")
    print(f"  Address:     {', '.join(filter(None, [c.address, c.city, c.state, c.postal_code])) or '—'}")
    print(f"  Source:      {c.source or '—'}")
    print(f"  Unsubscribed:{' YES' if c.unsubscribed else ' no'}")
    print(f"  DND:         {' YES' if c.dnd else ' no'}")
    print(f"  Date added:  {c.date_added or '—'}")
    print(f"  GHL id:      {c.ghl_id}")
    print(f"\n  Tags: {_tag_str(c)}")

    notes = sorted(c.notes, key=lambda n: n.created_at or "", reverse=True)
    if notes:
        print(f"\n  Notes ({len(notes)}):")
        for n in notes:
            print(f"    [{n.created_at or '—'}] {n.body}")
    else:
        print("\n  Notes: none")

    if c.email_logs:
        print(f"\n  Email log ({len(c.email_logs)}):")
        for e in sorted(c.email_logs, key=lambda x: x.sent_at or "", reverse=True)[:5]:
            print(f"    [{e.sent_at or '—'}] {e.subject or '—'}  ({e.status or '—'})")
    else:
        print("\n  Email log: none")

    if c.drip_enrollments:
        print(f"\n  Drip sequences:")
        for d in c.drip_enrollments:
            print(f"    {d.drip_name}  step={d.step}  status={d.status}  next={d.next_due or '—'}")
    print()
    session.close()


def cmd_add(args):
    session = get_session()

    # Duplicate check
    existing = None
    if args.email:
        existing = session.query(Contact).filter(
            func.lower(Contact.email) == args.email.lower()
        ).first()
    if existing and not args.force:
        sys.exit(
            f"Duplicate email: {args.email} → id={existing.id}. Use --force to overwrite."
        )

    import uuid
    from datetime import date

    if existing and args.force:
        c = existing
        c.first_name = args.first or c.first_name
        c.last_name  = args.last  or c.last_name
        c.phone      = args.phone or c.phone
        c.company    = args.company or c.company
    else:
        c = Contact(
            ghl_id     = f"local-{uuid.uuid4().hex[:12]}",
            first_name = args.first,
            last_name  = args.last,
            email      = args.email,
            phone      = args.phone,
            company    = args.company,
            date_added = date.today().isoformat(),
            created_at = date.today().isoformat(),
        )
        session.add(c)
        session.flush()

    for tag in (args.tag or []):
        _ensure_tag(session, c, tag)

    if args.note:
        from datetime import datetime
        session.add(ContactNote(
            contact_id = c.id,
            body       = args.note,
            created_at = datetime.now().isoformat(timespec="seconds"),
        ))

    session.commit()
    action = "Updated" if (existing and args.force) else "Added"
    print(f"{action} contact id={c.id}  {args.first} {args.last}  <{args.email}>")
    session.close()


def _ensure_tag(session, contact: Contact, tag: str):
    exists = any(t.tag.lower() == tag.lower() for t in contact.tags)
    if not exists:
        session.add(ContactTag(contact_id=contact.id, tag=tag))


def cmd_tag(args):
    session = get_session()
    c = _resolve(session, args.ref)
    added = []
    for tag in args.tags:
        if not any(t.tag.lower() == tag.lower() for t in c.tags):
            session.add(ContactTag(contact_id=c.id, tag=tag))
            added.append(tag)
    session.commit()
    if added:
        print(f"Tagged id={c.id} with: {', '.join(added)}")
    else:
        print("No new tags (all already present).")
    session.close()


def cmd_untag(args):
    session = get_session()
    c = _resolve(session, args.ref)
    removed = []
    for tag in args.tags:
        for t in list(c.tags):
            if t.tag.lower() == tag.lower():
                session.delete(t)
                removed.append(tag)
    session.commit()
    print(f"Removed tags from id={c.id}: {', '.join(removed) if removed else 'none matched'}")
    session.close()


def cmd_note(args):
    session = get_session()
    c = _resolve(session, args.ref)
    from datetime import datetime
    session.add(ContactNote(
        contact_id = c.id,
        body       = args.text,
        created_at = datetime.now().isoformat(timespec="seconds"),
    ))
    session.commit()
    print(f"Note added to id={c.id}")
    session.close()


def cmd_unsub(args):
    session = get_session()
    c = _resolve(session, args.ref)
    c.unsubscribed = True
    session.commit()
    print(f"Unsubscribed id={c.id}  {c.email}")
    session.close()


def cmd_resub(args):
    session = get_session()
    c = _resolve(session, args.ref)
    c.unsubscribed = False
    session.commit()
    print(f"Re-subscribed id={c.id}  {c.email}")
    session.close()


def cmd_segments(args):
    session = get_session()

    # Tag counts (active = not unsubscribed)
    tag_rows = (
        session.query(ContactTag.tag, func.count(ContactTag.contact_id))
        .join(Contact, Contact.id == ContactTag.contact_id)
        .filter(Contact.unsubscribed == False)  # noqa: E712
        .group_by(ContactTag.tag)
        .order_by(func.count(ContactTag.contact_id).desc())
        .all()
    )
    tag_rows_all = (
        session.query(ContactTag.tag, func.count(ContactTag.contact_id))
        .group_by(ContactTag.tag)
        .all()
    )
    all_map = {t: n for t, n in tag_rows_all}

    print(f"\n{'Tag':<35} {'Active':>8}  {'Total':>7}")
    print("─" * 55)
    for tag, count_active in tag_rows:
        print(f"{tag:<35} {count_active:>8}  {all_map.get(tag, count_active):>7}")

    # Totals
    total     = session.query(func.count(Contact.id)).scalar()
    unsub     = session.query(func.count(Contact.id)).filter(Contact.unsubscribed == True).scalar()   # noqa: E712
    with_email = session.query(func.count(Contact.id)).filter(Contact.email != None, Contact.email != "").scalar()  # noqa: E711
    with_phone = session.query(func.count(Contact.id)).filter(Contact.phone != None, Contact.phone != "").scalar()  # noqa: E711

    print(f"\n{'─'*55}")
    print(f"  Total contacts:    {total}")
    print(f"  With email:        {with_email}")
    print(f"  With phone:        {with_phone}")
    print(f"  Unsubscribed:      {unsub}")
    print()
    session.close()


def cmd_import_csv(args):
    path = Path(args.path)
    if not path.exists():
        sys.exit(f"File not found: {path}")

    session = get_session()
    import uuid
    from datetime import date

    added = updated = skipped = 0
    today = date.today().isoformat()

    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            email = (row.get("email") or "").strip()
            first = (row.get("first_name") or "").strip()
            last  = (row.get("last_name")  or "").strip()

            if not email:
                skipped += 1
                continue

            c = session.query(Contact).filter(
                func.lower(Contact.email) == email.lower()
            ).first()

            if c:
                # update non-blank fields
                if first: c.first_name = first
                if last:  c.last_name  = last
                if row.get("phone"):   c.phone   = row["phone"].strip()
                if row.get("company"): c.company = row["company"].strip()
                updated += 1
            else:
                c = Contact(
                    ghl_id     = f"csv-{uuid.uuid4().hex[:12]}",
                    first_name = first,
                    last_name  = last,
                    email      = email,
                    phone      = (row.get("phone")   or "").strip() or None,
                    company    = (row.get("company") or "").strip() or None,
                    date_added = today,
                    created_at = today,
                )
                session.add(c)
                session.flush()
                added += 1

            for tag in (row.get("tags") or "").split(";"):
                tag = tag.strip()
                if tag:
                    _ensure_tag(session, c, tag)

    session.commit()
    print(f"Import complete — added: {added}  updated: {updated}  skipped: {skipped}")
    session.close()


# ── CLI wiring ───────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        prog="crm.py",
        description="Olive Tree local CRM — contacts in data/olive.db",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # search
    s = sub.add_parser("search", help="Search contacts by name/email/phone/company")
    s.add_argument("query")
    s.add_argument("--tag", action="append", metavar="TAG", help="Filter by tag (repeatable = AND)")

    # show
    s = sub.add_parser("show", help="Full contact detail")
    s.add_argument("ref", help="Contact id or email")

    # add
    s = sub.add_parser("add", help="Add a new contact")
    s.add_argument("--first",   required=True)
    s.add_argument("--last",    required=True)
    s.add_argument("--email",   required=True)
    s.add_argument("--phone",   default=None)
    s.add_argument("--company", default=None)
    s.add_argument("--tag",     action="append", metavar="TAG")
    s.add_argument("--note",    default=None)
    s.add_argument("--force",   action="store_true", help="Overwrite on duplicate email")

    # tag / untag
    s = sub.add_parser("tag",   help="Add tags to a contact")
    s.add_argument("ref")
    s.add_argument("tags", nargs="+")

    s = sub.add_parser("untag", help="Remove tags from a contact")
    s.add_argument("ref")
    s.add_argument("tags", nargs="+")

    # note
    s = sub.add_parser("note", help="Add a note to a contact")
    s.add_argument("ref")
    s.add_argument("text")

    # unsub / resub
    s = sub.add_parser("unsub", help="Mark contact unsubscribed")
    s.add_argument("ref")

    s = sub.add_parser("resub", help="Re-subscribe a contact")
    s.add_argument("ref")

    # segments
    sub.add_parser("segments", help="Tag segments + database totals")

    # import-csv
    s = sub.add_parser("import-csv", help="Upsert contacts from a CSV file")
    s.add_argument("path", help="Path to CSV (columns: first_name,last_name,email,phone,company,tags)")

    args = p.parse_args()
    dispatch = {
        "search":     cmd_search,
        "show":       cmd_show,
        "add":        cmd_add,
        "tag":        cmd_tag,
        "untag":      cmd_untag,
        "note":       cmd_note,
        "unsub":      cmd_unsub,
        "resub":      cmd_resub,
        "segments":   cmd_segments,
        "import-csv": cmd_import_csv,
    }
    dispatch[args.cmd](args)


if __name__ == "__main__":
    main()
