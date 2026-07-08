#!/usr/bin/env python3
"""
Olive Tree Investments — Local Drip Engine

File-driven email drip sequences replacing GHL workflows (2026-07-06).
Templates live in templates/drips/<drip>/step-NN.md — frontmatter
(delay_days, subject) + markdown body in Brian's voice. State lives in
data/olive.db (drip_enrollments + email_log).

Usage:
  python3 scripts/drip.py list
  python3 scripts/drip.py enroll --contact brian@olivetreeinv.io --drip welcome
  python3 scripts/drip.py enroll --tag pitchdeck --drip pitch-deck --dry-run
  python3 scripts/drip.py run [--dry-run]        # send everything due
  python3 scripts/drip.py stop --contact 42 [--drip welcome]
  python3 scripts/drip.py status
"""

import argparse
import base64
import random
import re
import sys
import time
from datetime import datetime, timedelta
from email.header import Header
from email.mime.text import MIMEText
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from db.connection import get_session          # noqa: E402
from db.schema import Contact, ContactTag, DripEnrollment, EmailLog  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from gws_auth import get_token                  # noqa: E402

DRIPS_DIR = ROOT / "templates" / "drips"
GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
FROM_ADDR = "brian@olivetreeinv.io"


# ─────────────────────────────────────────────
# Template loading
# ─────────────────────────────────────────────

def load_steps(drip_name: str) -> list[dict]:
    """Return ordered [{n, delay_days, subject, body}] for a drip."""
    drip_dir = DRIPS_DIR / drip_name
    if not drip_dir.is_dir():
        raise SystemExit(f"ERROR: no such drip '{drip_name}' in {DRIPS_DIR}")
    steps = []
    for f in sorted(drip_dir.glob("step-*.md")):
        text = f.read_text()
        # Strip leading HTML comments (placeholder markers)
        text = re.sub(r"^\s*(<!--.*?-->\s*)+", "", text, flags=re.DOTALL)
        m = re.match(r"---\n(.*?)\n---\n(.*)", text, flags=re.DOTALL)
        if not m:
            raise SystemExit(f"ERROR: bad frontmatter in {f}")
        fm = dict(
            line.split(":", 1)
            for line in m.group(1).splitlines() if ":" in line
        )
        steps.append({
            "n": int(f.stem.split("-")[1]),
            "delay_days": int(fm["delay_days"].strip()),
            "subject": fm["subject"].strip(),
            "body": m.group(2).strip(),
        })
    if not steps:
        raise SystemExit(f"ERROR: drip '{drip_name}' has no step files")
    return steps


def all_drips() -> dict[str, int]:
    return {
        d.name: len(list(d.glob("step-*.md")))
        for d in sorted(DRIPS_DIR.iterdir()) if d.is_dir()
    }


# ─────────────────────────────────────────────
# Email send (pattern from broker_followup.py)
# ─────────────────────────────────────────────

def _to_html(text):
    """Convert plain text + markdown links to HTML for Gmail rendering."""
    import html
    body = html.escape(text)
    body = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)',
                  r'<a href="\2">\1</a>', body)
    # bare URLs → links
    body = re.sub(r'(?<!href=")(https?://[^\s<]+)', r'<a href="\1">\1</a>', body)
    body = body.replace("\n", "<br>\n")
    return f"<html><body style='font-family:sans-serif;font-size:14px'>{body}</body></html>"


def send_email(token, to_email, subject, body):
    msg = MIMEText(_to_html(body), "html", "utf-8")
    msg["to"] = to_email
    msg["from"] = FROM_ADDR
    msg["subject"] = str(Header(subject, "utf-8"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    r = requests.post(
        f"{GMAIL_BASE}/messages/send",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"raw": raw},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def resolve_contact(session, ref: str) -> Contact | None:
    if "@" in ref:
        return session.query(Contact).filter(Contact.email.ilike(ref)).first()
    return session.get(Contact, int(ref))


def render(text: str, contact: Contact) -> str:
    return text.replace("{{first_name}}", (contact.first_name or "there").strip() or "there")


# ─────────────────────────────────────────────
# Subcommands
# ─────────────────────────────────────────────

def cmd_list(args):
    print(f"{'DRIP':<20} STEPS")
    for name, n in all_drips().items():
        print(f"{name:<20} {n}")


def cmd_enroll(args):
    steps = load_steps(args.drip)
    session = get_session()

    if args.contact:
        c = resolve_contact(session, args.contact)
        if not c:
            raise SystemExit(f"ERROR: contact '{args.contact}' not found")
        targets = [c]
    else:
        targets = (
            session.query(Contact)
            .join(ContactTag, ContactTag.contact_id == Contact.id)
            .filter(ContactTag.tag == args.tag)
            .all()
        )
        print(f"Tag '{args.tag}': {len(targets)} contacts")

    first_due = datetime.now() + timedelta(days=steps[0]["delay_days"])
    enrolled = skipped = 0
    for c in targets:
        reason = None
        if not (c.email or "").strip():
            reason = "no email"
        elif c.unsubscribed:
            reason = "unsubscribed"
        else:
            existing = (
                session.query(DripEnrollment)
                .filter(DripEnrollment.contact_id == c.id,
                        DripEnrollment.drip_name == args.drip,
                        DripEnrollment.status.in_(["active", "done"]))
                .first()
            )
            if existing:
                reason = f"already enrolled ({existing.status})"
        name = f"{c.first_name or ''} {c.last_name or ''}".strip() or c.email or c.id
        if reason:
            skipped += 1
            print(f"  skip: {name} — {reason}")
            continue
        enrolled += 1
        if args.dry_run:
            print(f"  WOULD enroll: {name} <{c.email}> → {args.drip} step 1 due {first_due:%Y-%m-%d %H:%M}")
            continue
        session.add(DripEnrollment(
            contact_id=c.id, drip_name=args.drip, step=1,
            next_due=first_due.isoformat(timespec="seconds"), status="active",
        ))
        print(f"  enrolled: {name} <{c.email}> → {args.drip} step 1 due {first_due:%Y-%m-%d %H:%M}")

    if not args.dry_run:
        session.commit()
    session.close()
    print(f"\n{'DRY-RUN: would enroll' if args.dry_run else 'Enrolled'} {enrolled} | skipped {skipped}")


def cmd_run(args):
    session = get_session()
    now = now_iso()
    due = (
        session.query(DripEnrollment)
        .filter(DripEnrollment.status == "active", DripEnrollment.next_due <= now)
        .all()
    )
    if not due:
        print("Nothing due.")
        session.close()
        return

    token = None if args.dry_run else get_token()
    sent = failed = stopped = 0

    for e in due:
        c = session.get(Contact, e.contact_id)
        steps = load_steps(e.drip_name)
        step = next((s for s in steps if s["n"] == e.step), None)
        label = f"drip:{e.drip_name}:{e.step:02d}"
        name = f"{c.first_name or ''} {c.last_name or ''}".strip() or c.email

        if step is None:
            # step file removed since enrollment — close out
            e.status = "done"
            print(f"  done (no step {e.step}): {name} / {e.drip_name}")
            continue

        if c.unsubscribed or not (c.email or "").strip():
            e.status = "stopped"
            stopped += 1
            print(f"  stopped (unsubscribed/no email): {name} / {e.drip_name}")
            continue

        subject = render(step["subject"], c)
        body = render(step["body"], c)

        if args.dry_run:
            print(f"  WOULD send {label} → {c.email}  [{subject}]")
            sent += 1
            continue

        try:
            resp = send_email(token, c.email, subject, body)
            status = "sent"
            sent += 1
            print(f"  sent {label} → {c.email}  (msg {resp.get('id')})")
        except Exception as ex:
            status = "failed"
            failed += 1
            print(f"  FAILED {label} → {c.email}: {ex}", file=sys.stderr)

        session.add(EmailLog(
            contact_id=c.id, drip_step=label, subject=subject,
            sent_at=now_iso(), status=status,
        ))

        if status == "sent":
            nxt = next((s for s in steps if s["n"] == e.step + 1), None)
            if nxt:
                e.step += 1
                e.next_due = (datetime.now() + timedelta(days=nxt["delay_days"])).isoformat(timespec="seconds")
            else:
                e.status = "done"

        if not args.dry_run:
            # Per-contact commit: the send is irreversible, so the step advance +
            # log must land immediately — a crash mid-batch must not re-send
            # already-emailed contacts on the next nightly run.
            session.commit()
            time.sleep(random.uniform(2, 4))

    if not args.dry_run:
        session.commit()
    session.close()
    print(f"\n{'DRY-RUN — would send' if args.dry_run else 'Sent'} {sent} | failed {failed} | stopped {stopped}")


def cmd_stop(args):
    session = get_session()
    c = resolve_contact(session, args.contact)
    if not c:
        raise SystemExit(f"ERROR: contact '{args.contact}' not found")
    q = session.query(DripEnrollment).filter(
        DripEnrollment.contact_id == c.id, DripEnrollment.status == "active")
    if args.drip:
        q = q.filter(DripEnrollment.drip_name == args.drip)
    n = 0
    for e in q.all():
        e.status = "stopped"
        n += 1
        print(f"  stopped: {e.drip_name} (was step {e.step})")
    session.commit()
    session.close()
    print(f"Stopped {n} enrollment(s) for {c.email or c.id}")


def cmd_status(args):
    session = get_session()
    rows = session.query(DripEnrollment).all()
    by_drip: dict[str, dict] = {}
    for e in rows:
        d = by_drip.setdefault(e.drip_name, {"active": 0, "done": 0, "stopped": 0, "next": None})
        d[e.status] = d.get(e.status, 0) + 1
        if e.status == "active" and e.next_due and (d["next"] is None or e.next_due < d["next"]):
            d["next"] = e.next_due
    session.close()
    if not by_drip:
        print("No enrollments.")
        return
    print(f"{'DRIP':<20} {'ACTIVE':>6} {'DONE':>6} {'STOPPED':>8}  NEXT DUE")
    for name, d in sorted(by_drip.items()):
        print(f"{name:<20} {d['active']:>6} {d['done']:>6} {d['stopped']:>8}  {d['next'] or '-'}")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Olive Tree local drip engine")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="Available drips + step counts")

    ep = sub.add_parser("enroll", help="Enroll contact(s) into a drip")
    g = ep.add_mutually_exclusive_group(required=True)
    g.add_argument("--contact", help="Contact id or email")
    g.add_argument("--tag", help="Enroll all contacts with this tag")
    ep.add_argument("--drip", required=True, help="Drip name (see list)")
    ep.add_argument("--dry-run", action="store_true")

    rp = sub.add_parser("run", help="Send all due steps")
    rp.add_argument("--dry-run", action="store_true")

    stp = sub.add_parser("stop", help="Stop active enrollment(s)")
    stp.add_argument("--contact", required=True, help="Contact id or email")
    stp.add_argument("--drip", help="Only this drip (default: all active)")

    sub.add_parser("status", help="Enrollment counts per drip")

    args = p.parse_args()
    {"list": cmd_list, "enroll": cmd_enroll, "run": cmd_run,
     "stop": cmd_stop, "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    main()
