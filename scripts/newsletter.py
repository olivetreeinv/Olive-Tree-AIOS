#!/usr/bin/env python3
"""
newsletter.py — local Gmail-API newsletter engine.

Commands
--------
build       merge content into template, save HTML, create campaigns row
test-send   send to brian@olivetreeinv.io with [TEST] subject prefix
send        send to newsletter-tagged audience (resume-safe, 2–4s delay)
scan-unsubs search Gmail for UNSUBSCRIBE replies, flag contacts
"""

import argparse
import base64
import html
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests
from dotenv import load_dotenv

# ── paths ────────────────────────────────────────────────────────────────────
REPO = Path(__file__).parent.parent
load_dotenv(REPO / ".env")

sys.path.insert(0, str(REPO))
from scripts.gws_auth import get_token
from db.connection import get_session
from db.schema import Campaign, Contact, ContactTag, EmailLog

TEMPLATE = REPO / "templates" / "newsletter.html"
OUTPUT_DIR = REPO / "output" / "newsletters"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
FROM_ADDR  = "brian@olivetreeinv.io"
TEST_ADDR  = "brian@olivetreeinv.io"

UNSUB_NOTE = (
    'To stop receiving these emails, '
    '<a href="mailto:brian@olivetreeinv.io?subject=UNSUBSCRIBE">reply UNSUBSCRIBE</a>.'
)


# ── markdown → HTML ──────────────────────────────────────────────────────────
def _md_to_html(text: str) -> str:
    """Minimal markdown → HTML. Paragraphs, bold, italic, links, h2/h3."""
    # escape first, then we'll re-insert safe HTML tags
    lines = text.split("\n")
    out, para = [], []

    def flush_para():
        if para:
            line = " ".join(para).strip()
            if line:
                out.append(f"<p style='margin:0 0 16px;'>{line}</p>")
            para.clear()

    for raw in lines:
        line = raw.rstrip()

        if not line:
            flush_para()
            continue

        # headings (before escaping so we can detect #)
        if line.startswith("### "):
            flush_para()
            content = _inline(line[4:])
            out.append(f"<h3 style='font-size:18px;color:#1C2110;margin:24px 0 8px;border-bottom:1px solid #D7D9C5;padding-bottom:6px;'>{content}</h3>")
        elif line.startswith("## "):
            flush_para()
            content = _inline(line[3:])
            out.append(f"<h2 style='font-size:22px;color:#1C2110;border-bottom:2px solid #5A6A1E;padding-bottom:10px;margin:32px 0 12px;'>{content}</h2>")
        elif line.startswith("---"):
            flush_para()
            out.append("<hr style='border:none;border-top:2px solid #D7D9C5;margin:32px 0;'>")
        else:
            para.append(_inline(line))

    flush_para()
    return "\n".join(out)


def _inline(text: str) -> str:
    """Inline markdown: escape HTML, then apply bold/italic/links."""
    text = html.escape(text)
    # bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # italic
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    # links  [label](url)
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^\)]+)\)",
        r'<a href="\2" style="color:#5A6A1E;">\1</a>',
        text,
    )
    return text


# ── template render ──────────────────────────────────────────────────────────
def render_template(subject: str, body_html: str, first_name: str = "there") -> str:
    tmpl = TEMPLATE.read_text()
    tmpl = tmpl.replace("{{subject}}", html.escape(subject))
    tmpl = tmpl.replace("{{first_name}}", html.escape(first_name))
    tmpl = tmpl.replace("{{body_html}}", body_html)
    tmpl = tmpl.replace("{{unsubscribe_note}}", UNSUB_NOTE)
    return tmpl


# ── slug ─────────────────────────────────────────────────────────────────────
def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ── Gmail send ───────────────────────────────────────────────────────────────
def _send_raw(token: str, to: str, subject: str, html_body: str) -> dict:
    msg = MIMEMultipart("alternative")
    msg["to"]      = to
    msg["from"]    = FROM_ADDR
    msg["subject"] = str(Header(subject, "utf-8"))
    msg["List-Unsubscribe"] = f"<mailto:{FROM_ADDR}?subject=UNSUBSCRIBE>"
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    r = requests.post(
        f"{GMAIL_BASE}/messages/send",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"raw": raw},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


# ── db helpers ───────────────────────────────────────────────────────────────
def _get_campaign(session, id_or_name: str) -> Campaign:
    try:
        cid = int(id_or_name)
        row = session.get(Campaign, cid)
    except ValueError:
        row = session.query(Campaign).filter_by(name=id_or_name).first()
    if not row:
        sys.exit(f"Campaign not found: {id_or_name!r}")
    return row


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── commands ─────────────────────────────────────────────────────────────────

def cmd_build(args):
    subject = args.subject or args.name

    # load content
    if args.html:
        body_html = Path(args.html).read_text()
    elif args.markdown:
        body_html = _md_to_html(Path(args.markdown).read_text())
    else:
        sys.exit("Provide --html or --markdown")

    # render with generic first_name for the saved file
    full_html = render_template(subject, body_html)
    slug = slugify(args.name)
    out_path = OUTPUT_DIR / f"{slug}.html"
    out_path.write_text(full_html)

    # db row — upsert by name so rebuilding after edits doesn't create duplicates
    session = get_session()
    camp = session.query(Campaign).filter_by(name=args.name).first()
    if camp:
        camp.subject   = subject
        camp.html_path = str(out_path)
        camp.status    = "draft"
    else:
        camp = Campaign(
            name=args.name,
            subject=subject,
            html_path=str(out_path),
            status="draft",
            sent_count=0,
            created_at=_now(),
        )
        session.add(camp)
    session.commit()
    print(f"Built: {out_path}")
    print(f"Campaign row id={camp.id}  status=draft")


def cmd_test_send(args):
    session = get_session()
    camp = _get_campaign(session, args.campaign)
    html_body = Path(camp.html_path).read_text()
    # personalize for test recipient
    html_body = html_body.replace("Hey there,", "Hey Brian,")

    token = get_token()
    result = _send_raw(token, TEST_ADDR, f"[TEST] {camp.subject}", html_body)
    print(f"Sent to {TEST_ADDR}  message_id={result.get('id')}")


def cmd_send(args):
    session = get_session()
    camp = _get_campaign(session, args.campaign)

    audience_tag = args.tag or "newsletter"

    # contacts tagged audience_tag, with email, not unsubscribed
    tagged_ids = {
        r.contact_id
        for r in session.query(ContactTag).filter(ContactTag.tag == audience_tag)
    }
    contacts = (
        session.query(Contact)
        .filter(
            Contact.id.in_(tagged_ids),
            Contact.email.isnot(None),
            Contact.email != "",
            Contact.unsubscribed == False,  # noqa: E712
        )
        .all()
    )

    # already sent for this campaign (resume-safe)
    already_sent = {
        r.contact_id
        for r in session.query(EmailLog).filter_by(
            campaign_id=camp.id, status="sent"
        )
    }
    to_send = [c for c in contacts if c.id not in already_sent]

    if args.limit:
        to_send = to_send[: args.limit]

    print(f"Audience tag={audience_tag!r}: {len(contacts)} total, {len(already_sent)} already sent, {len(to_send)} queued")

    if args.dry_run:
        print("[dry-run] No emails sent.")
        return

    template_html = Path(camp.html_path).read_text()
    token = get_token()
    sent = failed = 0

    for c in to_send:
        # Re-fetch unsubscribe flag fresh — could have changed since we built the list
        session.expire(c)
        if c.unsubscribed:
            print(f"  SKIP (now unsubscribed): {c.email}")
            continue

        first = c.first_name or "there"
        body = template_html.replace("Hey there,", f"Hey {html.escape(first)},")

        try:
            _send_raw(token, c.email, camp.subject, body)
            # Residual race: if killed after send but before commit, one contact
            # gets a duplicate on resume — acceptable (worst case: one extra email).
            session.add(EmailLog(
                contact_id=c.id,
                campaign_id=camp.id,
                subject=camp.subject,
                sent_at=_now(),
                status="sent",
            ))
            session.commit()
            sent += 1
        except Exception as e:
            session.rollback()
            print(f"  FAIL {c.email}: {e}")
            try:
                session.add(EmailLog(
                    contact_id=c.id,
                    campaign_id=camp.id,
                    subject=camp.subject,
                    sent_at=_now(),
                    status="failed",
                ))
                session.commit()
            except Exception:
                session.rollback()
            failed += 1

        time.sleep(random.uniform(2, 4))

    # update campaign
    camp.status = "sent"
    camp.sent_count = (camp.sent_count or 0) + sent
    session.commit()
    print(f"Done. sent={sent} failed={failed}")


def cmd_scan_unsubs(args):
    token = get_token()
    days = args.days

    # Inbound-only: our own sends carry UNSUBSCRIBE in the footer, so a bare
    # match flags every outbound newsletter (and Brian himself).
    queries = [
        f"in:inbox to:brian@olivetreeinv.io subject:UNSUBSCRIBE "
        f"-from:brian@olivetreeinv.io newer_than:{days}d",
    ]
    found_emails = set()
    for q in queries:
        r = requests.get(
            f"{GMAIL_BASE}/messages",
            headers={"Authorization": f"Bearer {token}"},
            params={"q": q, "maxResults": 100},
            timeout=30,
        )
        r.raise_for_status()
        for msg in r.json().get("messages", []):
            detail = requests.get(
                f"{GMAIL_BASE}/messages/{msg['id']}",
                headers={"Authorization": f"Bearer {token}"},
                params={"format": "metadata", "metadataHeaders": ["From"]},
                timeout=30,
            )
            detail.raise_for_status()
            for h in detail.json().get("payload", {}).get("headers", []):
                if h["name"] == "From":
                    m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", h["value"])
                    if m and m.group(0).lower() != "brian@olivetreeinv.io":
                        found_emails.add(m.group(0).lower())

    if not found_emails:
        print(f"No UNSUBSCRIBE requests found in last {days} days.")
        return

    session = get_session()
    flagged = []
    for email in found_emails:
        c = session.query(Contact).filter(
            Contact.email.ilike(email)
        ).first()
        if c:
            flagged.append((c.id, c.email, c.first_name))
            if not args.dry_run:
                c.unsubscribed = True
    if not args.dry_run:
        session.commit()

    tag = "[dry-run] would flag" if args.dry_run else "Flagged as unsubscribed"
    for cid, email, name in flagged:
        print(f"  {tag}: id={cid} {email} ({name})")
    if not flagged:
        print(f"Emails found in Gmail ({list(found_emails)}) — no matching contacts.")
    else:
        print(f"\nTotal: {len(flagged)} contact(s) {'(dry-run, nothing written)' if args.dry_run else 'marked unsubscribed'}.")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Olive Tree newsletter engine")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="Merge content → template, save HTML, create campaign row")
    p_build.add_argument("--name",     required=True, help="Campaign name, e.g. 'July 2026 Newsletter'")
    p_build.add_argument("--subject",  help="Email subject (defaults to --name)")
    p_build.add_argument("--html",     help="Path to HTML body file")
    p_build.add_argument("--markdown", help="Path to Markdown body file")

    p_test = sub.add_parser("test-send", help="Send [TEST] copy to brian@olivetreeinv.io")
    p_test.add_argument("--campaign", required=True, help="Campaign id or name")

    p_send = sub.add_parser("send", help="Send to newsletter-tagged audience")
    p_send.add_argument("--campaign", required=True)
    p_send.add_argument("--limit",    type=int, help="Cap audience size")
    p_send.add_argument("--dry-run",  action="store_true")
    p_send.add_argument("--tag",      help="Override audience tag (default: newsletter)")

    p_scan = sub.add_parser("scan-unsubs", help="Scan Gmail for UNSUBSCRIBE replies")
    p_scan.add_argument("--days",    type=int, default=30)
    p_scan.add_argument("--dry-run", action="store_true", help="Print matches, don't write")

    args = parser.parse_args()
    {"build": cmd_build, "test-send": cmd_test_send,
     "send": cmd_send, "scan-unsubs": cmd_scan_unsubs}[args.cmd](args)


if __name__ == "__main__":
    main()
