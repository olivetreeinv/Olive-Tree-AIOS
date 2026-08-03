#!/usr/bin/env python3
"""
newsletter.py — local Gmail-API newsletter engine.

Commands
--------
build       merge content into template, save HTML, create campaigns row
test-send   send to brian@olivetreeinv.io with [TEST] subject prefix
send        send to newsletter-tagged audience (resume-safe, 2–4s delay)
scan-unsubs search Gmail for UNSUBSCRIBE replies, flag contacts
scan-bounces search Gmail for hard bounces + 'Delivery incomplete' notices,
             remove dead contacts, trash the delivery-incomplete notifications
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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.header import Header
from email.mime.image import MIMEImage
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
ASSETS_DIR = REPO / "templates" / "newsletter-assets"
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
# Card contract (matches templates/newsletter.html): the template opens the
# greeting card before {{body_html}} and closes the last card after it.
# "## " section titles close the current card, emit a centered blue title
# card, and open a fresh content card — the GHL card-per-section look.
CARD_OPEN = (
    '<table width="100%" cellpadding="0" cellspacing="0" border="0" '
    'style="background:#FFFFFF;border-radius:16px;"><tr>'
    '<td style="padding:26px 28px;font-family:arial,helvetica,sans-serif;'
    'font-size:14px;line-height:1.6;color:#26281C;">'
)
CARD_CLOSE = (
    '</td></tr></table>'
    '<div style="height:16px;line-height:16px;font-size:16px;">&nbsp;</div>'
)


def _md_to_html(text: str) -> str:
    """Minimal markdown → card-based HTML. Paragraphs, bold, italic, links,
    images, h2 (new section card) / h3 (bold subhead)."""
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

        # {{rates}} → live residential + commercial rate table (newsletter_rates.py).
        # Rendered outside the card so it spans the full newsletter width.
        if line.strip() == "{{rates}}":
            flush_para()
            from scripts.newsletter_rates import rates_html
            out.append(CARD_CLOSE + rates_html() + CARD_OPEN)
            continue

        # headings (before escaping so we can detect #)
        if line.startswith("### "):
            flush_para()
            content = _inline(line[4:])
            out.append(f"<p style='margin:20px 0 8px;color:#505A19;'><strong>{content}</strong></p>")
        elif line.startswith("## "):
            flush_para()
            content = _inline(line[3:])
            out.append(
                CARD_CLOSE + CARD_OPEN
                + "<h2 style='margin:0;text-align:center;color:#505A19;font-size:24px;"
                  "font-weight:normal;font-family:Georgia,\"Times New Roman\",serif;'>"
                + content + "</h2>"
                + "<div style='width:48px;height:2px;background:#B7965A;margin:14px auto 0;font-size:0;line-height:0;'>&nbsp;</div>"
                + CARD_CLOSE + CARD_OPEN
            )
        elif line.startswith("---"):
            flush_para()
            out.append("<hr style='border:none;border-top:1px solid #E4DFCF;margin:24px 0;'>")
        else:
            para.append(_inline(line))

    flush_para()
    # drop empty cards left when a full-width block ({{rates}}) borders a section break
    return "\n".join(out).replace(CARD_OPEN + "\n" + CARD_CLOSE, "")


def _inline(text: str) -> str:
    """Inline markdown: escape HTML, then apply bold/italic/links."""
    text = html.escape(text)
    # bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # italic
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    # images  ![alt](cid:file.png) or ![alt](https://...) — before links
    text = re.sub(
        r"!\[([^\]]*)\]\(((?:cid:|https?://)[^\)]+)\)",
        r'<img src="\2" alt="\1" style="display:block;max-width:100%;margin:12px auto;border-radius:8px;">',
        text,
    )
    # links  [label](url)
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^\)]+)\)",
        r'<a href="\2" style="color:#505A19;">\1</a>',
        text,
    )
    return text


# ── template render ──────────────────────────────────────────────────────────
def render_template(subject: str, body_html: str, first_name: str = "there",
                    edition: str = None) -> str:
    # edition defaults to build month, but editions are drafted in the prior
    # month (August built July 31), so allow an explicit override.
    tmpl = TEMPLATE.read_text()
    tmpl = tmpl.replace("{{subject}}", html.escape(subject))
    tmpl = tmpl.replace("{{preheader}}", html.escape(subject))
    tmpl = tmpl.replace("{{first_name}}", html.escape(first_name))
    tmpl = tmpl.replace("{{body_html}}", body_html)
    tmpl = tmpl.replace("{{unsubscribe_note}}", UNSUB_NOTE)
    tmpl = tmpl.replace("{{year}}", str(datetime.now().year))
    tmpl = tmpl.replace("{{edition}}", edition or datetime.now().strftime("%B"))
    return tmpl


# ── slug ─────────────────────────────────────────────────────────────────────
def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ── Gmail send ───────────────────────────────────────────────────────────────
def _send_raw(token: str, to: str, subject: str, html_body: str) -> dict:
    msg = MIMEMultipart("related")
    msg["to"]      = to
    msg["from"]    = FROM_ADDR
    msg["subject"] = str(Header(subject, "utf-8"))
    msg["List-Unsubscribe"] = f"<mailto:{FROM_ADDR}?subject=UNSUBSCRIBE>"
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # inline images: attach any newsletter asset referenced as cid:<filename>
    for f in sorted(ASSETS_DIR.glob("*.*")):
        if f"cid:{f.name}" in html_body:
            img = MIMEImage(f.read_bytes())
            img.add_header("Content-ID", f"<{f.name}>")
            img.add_header("Content-Disposition", "inline", filename=f.name)
            msg.attach(img)

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
    full_html = render_template(subject, body_html, edition=getattr(args, "edition", None))
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
    html_body = html_body.replace("Hi there,", "Hi Brian,")

    token = get_token()
    result = _send_raw(token, TEST_ADDR, f"[TEST] {camp.subject}", html_body)
    print(f"Sent to {TEST_ADDR}  message_id={result.get('id')}")


def cmd_send(args):
    # pre-send hygiene: flag UNSUBSCRIBE replies before building the audience
    print("Scanning for UNSUBSCRIBE replies...")
    cmd_scan_unsubs(argparse.Namespace(days=30, dry_run=args.dry_run))

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
        body = template_html.replace("Hi there,", f"Hi {html.escape(first)},")

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


# Opt-out language for the body pass. Deliberately narrow — soft phrases like
# "not interested" go to human review via the morning scan, never auto-flag.
BODY_OPTOUT_RE = re.compile(
    r"unsubscribe|remove me|take me off|stop (?:sending|emailing)", re.I)

# Everything after the first of these markers is quoted/forwarded content,
# not the sender's own words.
_QUOTE_CUT_RE = re.compile(
    r"-+\s*(?:Original Message|Forwarded message)\s*-+"
    r"|<blockquote|gmail_quote"
    r"|\bOn [^\n]{0,120}wrote:"
    r"|\n\s*>",
    re.I,
)


def _own_words(payload) -> str:
    """Message text with quoted/forwarded content stripped — only what the sender typed."""
    text = _decode_part(payload)
    m = _QUOTE_CUT_RE.search(text)
    if m:
        text = text[: m.start()]
    return html.unescape(re.sub(r"<[^>]+>", " ", text))


def cmd_scan_unsubs(args):
    token = get_token()
    days = args.days

    # Two passes, both inbound-only (our own sends carry UNSUBSCRIBE in the footer).
    # Subject pass: explicit UNSUBSCRIBE subject (footer mailto / Apple Mail one-click)
    # — sender match alone counts. Body pass: opt-out language in the message text —
    # flags only replies (In-Reply-To or "Re:") where the phrase survives
    # quote-stripping, so a forwarded newsletter footer or our own quoted footer
    # can't unsubscribe anyone.
    base = f"in:inbox to:brian@olivetreeinv.io -from:brian@olivetreeinv.io newer_than:{days}d"
    queries = [
        (f"{base} subject:UNSUBSCRIBE", False),
        (f'{base} ("unsubscribe" OR "remove me" OR "take me off"'
         f' OR "stop emailing" OR "stop sending")', True),
    ]
    found_emails = set()
    for q, check_body in queries:
        messages, page_token = [], None
        while True:  # paginate — a missed unsubscribe keeps getting mail
            params = {"q": q, "maxResults": 100}
            if page_token:
                params["pageToken"] = page_token
            r = requests.get(
                f"{GMAIL_BASE}/messages",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            messages.extend(data.get("messages", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        def _fetch_detail(msg):
            params = ({"format": "full"} if check_body
                      else {"format": "metadata", "metadataHeaders": ["From"]})
            # Skip-not-crash on transient Gmail errors: the body pass fans out to
            # every inbox match, and daily windows overlap — a miss is retried
            # tomorrow, but an unhandled 429 would abort the whole unattended scan.
            try:
                detail = requests.get(
                    f"{GMAIL_BASE}/messages/{msg['id']}",
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                    timeout=30,
                )
                detail.raise_for_status()
                return detail.json()
            except requests.RequestException as e:
                print(f"  fetch failed ({type(e).__name__}) msg={msg['id']} — skipped")
                return None

        with ThreadPoolExecutor(max_workers=8) as pool:
            for detail_json in pool.map(_fetch_detail, messages):
                if not detail_json:
                    continue
                payload = detail_json.get("payload", {})
                hdrs = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
                if check_body:
                    is_reply = ("in-reply-to" in hdrs
                                or hdrs.get("subject", "").lower().startswith("re:"))
                    if not is_reply or not BODY_OPTOUT_RE.search(_own_words(payload)):
                        continue
                m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", hdrs.get("from", ""))
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


# ── bounce hygiene ───────────────────────────────────────────────────────────

_HARD_BOUNCE_SIGNALS = (
    "does not exist", "couldn't be found", "could not be found",
    "address not found", "no such user", "user unknown",
    "recipient address rejected", "550 5.1.1",
    # non-Google MTAs (Outlook/Exchange, Postfix, qmail)
    "recipnotfound", "recipient not found", "unknown recipient",
    # EarthLink/Vade (mindspring.com, pipeline.com) — "550 5.5.1 Recipient rejected".
    # Keep the code in the phrase: a bare "recipient rejected" also appears in 5.7.x
    # policy/reputation blocks, which are OUR problem to fix, not a dead address.
    "5.5.1 recipient rejected",
)


def _decode_part(payload) -> str:
    """Recursively base64url-decode every text part of a Gmail message payload."""
    out = []
    data = (payload.get("body") or {}).get("data")
    if data:
        out.append(base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace"))
    for p in payload.get("parts") or []:
        out.append(_decode_part(p))
    return "\n".join(out)


def parse_bounce(text: str):
    """From a Gmail bounce (DSN) blob → (failed_recipient_emails:set, is_hard:bool).

    is_hard = permanent failure (5.x.x status / "address doesn't exist"). We remove ONLY on
    hard bounces so a temporary 4.x.x (over-quota, greylisting) never nukes a good contact.
    ponytail: classifies the whole message; a DSN bundling mixed pass/fail recipients would
    need per-recipient Action parsing — our 1:1 drip/newsletter sends don't produce those.
    """
    low = text.lower()
    # 5.1.x = permanent *recipient-address* failure (no such mailbox) — the real dead address.
    # Deliberately NOT all 5.x.x: 5.2.2 (mailbox full) / 5.2.3 (too large) are valid people we
    # must not delete. Text phrases below still catch the same wording, incl. EarthLink's
    # "550 5.5.1 Recipient rejected" (gated on the phrase, not the bare 5.5.1 code, which also
    # means auth errors that aren't recipient failures).
    is_hard = bool(re.search(r"status:\s*5\.1\.\d+", low)) or any(s in low for s in _HARD_BOUNCE_SIGNALS)
    emails = set(re.findall(r"final-recipient:\s*rfc822;\s*<?([\w.+-]+@[\w.-]+\.\w+)", low))
    if not emails:  # fallback to the human-readable line if the DSN part is missing
        m = re.search(r"wasn'?t delivered to\s*<?([\w.+-]+@[\w.-]+\.\w+)", low)
        if m:
            emails.add(m.group(1))
    return emails, is_hard


def cmd_scan_bounces(args):
    """Scan Gmail for bounces → remove dead contacts from future sends.

    Hard bounces ('address not found') → unsubscribed + tagged `bounced`.
    'Delivery incomplete' notices (Gmail gave up after temporary failures) →
    unsubscribed + tagged `bounced-soft`, and the notification email is trashed.
    Other soft NDRs (mailbox full etc. — valid people) stay untouched.
    The next drip run auto-stops their sequence (it already skips unsubscribed)."""
    token = get_token()
    days = args.days
    # Bounces come from Google's mailer-daemon AND recipient-side postmasters (Outlook/Exchange,
    # corporate MTAs). Match both by sender and by the standard NDR subjects; parse_bounce still
    # gates on a hard 5.1.x / "no such user" status, so a soft or non-bounce match is discarded.
    bounce_terms = (
        "from:mailer-daemon OR from:postmaster OR "
        'subject:undeliverable OR subject:"delivery status notification" OR '
        'subject:"delivery has failed" OR subject:"mail delivery failed" OR '
        'subject:"failure notice" OR subject:"returned mail" OR subject:"undelivered mail"'
    )
    q = f"in:inbox newer_than:{days}d ({bounce_terms})"

    messages, page_token = [], None
    while True:  # paginate — a missed bounce keeps costing sends
        params = {"q": q, "maxResults": 100}
        if page_token:
            params["pageToken"] = page_token
        r = requests.get(f"{GMAIL_BASE}/messages",
                         headers={"Authorization": f"Bearer {token}"},
                         params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        messages.extend(data.get("messages", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    def _fetch_full(msg):
        # Skip-not-crash on transient Gmail errors (mirrors _fetch_detail in
        # cmd_scan_unsubs above): one bad fetch shouldn't crash the whole
        # unattended bounce-hygiene run.
        try:
            d = requests.get(f"{GMAIL_BASE}/messages/{msg['id']}",
                             headers={"Authorization": f"Bearer {token}"},
                             params={"format": "full"}, timeout=30)
            d.raise_for_status()
            return d.json()
        except requests.RequestException as e:
            print(f"  fetch failed ({type(e).__name__}) msg={msg['id']} — skipped")
            return None

    hard, soft, dinc, dinc_ids = set(), set(), set(), []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for dj in pool.map(_fetch_full, messages):
            if not dj:
                continue
            blob = dj.get("snippet", "") + "\n" + _decode_part(dj.get("payload", {}))
            emails, is_hard = parse_bounce(blob)
            emails = {e for e in emails if e != FROM_ADDR.lower() and "mailer-daemon" not in e}
            subj = next((h["value"] for h in dj.get("payload", {}).get("headers", [])
                         if h["name"].lower() == "subject"), "").lower()
            # Gmail's "Delivery incomplete" banner rides on subject "Delivery Status
            # Notification (Delay)"; mailbox-full etc. use "(Failure)" and stay protected.
            is_dinc = "delivery incomplete" in subj or "notification (delay)" in subj
            if is_dinc:
                dinc_ids.append(dj["id"])  # trash the notification either way
            if is_hard:
                hard.update(emails)
            elif is_dinc:
                dinc.update(emails)
            else:
                soft.update(emails)
    dinc -= hard  # a hard failure elsewhere wins
    soft -= hard | dinc

    # dinc_ids too: a delay notice with an unparseable recipient still needs trashing.
    if not hard and not dinc and not dinc_ids:
        extra = f" ({len(soft)} soft/transient skipped)" if soft else ""
        print(f"No hard or delivery-incomplete bounces in last {days} days.{extra}")
        return

    session = get_session()
    flagged, no_match = [], []
    for email, tag in [*((e, "bounced") for e in sorted(hard)),
                       *((e, "bounced-soft") for e in sorted(dinc))]:
        c = session.query(Contact).filter(Contact.email.ilike(email)).first()
        if not c:
            no_match.append(email)
            continue
        already = session.query(ContactTag).filter(
            ContactTag.contact_id == c.id,
            ContactTag.tag.in_(("bounced", "bounced-soft"))).first()
        flagged.append((c.id, c.email, c.first_name, tag, bool(already)))
        if not args.dry_run and not already:
            c.unsubscribed = True
            session.add(ContactTag(contact_id=c.id, tag=tag))
    if not args.dry_run:
        session.commit()
    session.close()

    verb = "[dry-run] would remove" if args.dry_run else "Removed (unsubscribed + tagged"
    for cid, email, name, tag, already in flagged:
        suffix = ")" if not args.dry_run else ""
        print(f"  {verb} {tag}{suffix}: id={cid} {email} ({name})"
              f"{' (already bounced)' if already else ''}")

    if dinc_ids:
        if args.dry_run:
            print(f"  [dry-run] would trash {len(dinc_ids)} 'Delivery incomplete' notification(s)")
        else:
            trashed = 0
            for mid in dinc_ids:
                try:
                    requests.post(f"{GMAIL_BASE}/messages/{mid}/trash",
                                  headers={"Authorization": f"Bearer {token}"},
                                  timeout=30).raise_for_status()
                    trashed += 1
                except requests.RequestException as e:
                    print(f"  trash failed ({type(e).__name__}) msg={mid}")
            print(f"  Trashed {trashed}/{len(dinc_ids)} 'Delivery incomplete' notification(s)")
    if no_match:
        print(f"  bounced but not in CRM ({len(no_match)}): {', '.join(no_match)}")
    if soft:
        print(f"  soft/transient bounces skipped ({len(soft)}): {', '.join(sorted(soft))}")
    new = sum(1 for *_, already in flagged if not already)
    print(f"\nTotal: {new} contact(s) {'would be' if args.dry_run else ''} removed from future sends.")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Olive Tree newsletter engine")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="Merge content → template, save HTML, create campaign row")
    p_build.add_argument("--name",     required=True, help="Campaign name, e.g. 'July 2026 Newsletter'")
    p_build.add_argument("--subject",  help="Email subject (defaults to --name)")
    p_build.add_argument("--html",     help="Path to HTML body file")
    p_build.add_argument("--markdown", help="Path to Markdown body file")
    p_build.add_argument("--edition",  help="Edition label in the hero (default: build month, e.g. 'August')")

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

    p_bounce = sub.add_parser("scan-bounces", help="Scan Gmail for hard bounces, remove dead contacts")
    p_bounce.add_argument("--days",    type=int, default=30)
    p_bounce.add_argument("--dry-run", action="store_true", help="Print matches, don't write")

    args = parser.parse_args()
    {"build": cmd_build, "test-send": cmd_test_send,
     "send": cmd_send, "scan-unsubs": cmd_scan_unsubs,
     "scan-bounces": cmd_scan_bounces}[args.cmd](args)


if __name__ == "__main__":
    main()
