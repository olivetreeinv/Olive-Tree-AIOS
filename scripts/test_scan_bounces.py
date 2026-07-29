"""Self-check for newsletter.parse_bounce — the hard/soft classification + failed-recipient
extraction that decides whether a contact gets removed. Run: python3 scripts/test_scan_bounces.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.newsletter import parse_bounce

HARD = """Delivery Status Notification (Failure)
Your message wasn't delivered to DeadBox@Example.com because the address couldn't be found.
Final-Recipient: rfc822; DeadBox@Example.com
Action: failed
Status: 5.1.1
Remote-MTA: dns; example.com
The response was: 550 5.1.1 The email account that you tried to reach does not exist."""

SOFT = """Delivery Status Notification (Delay)
Final-Recipient: rfc822; busy@example.com
Action: delayed
Status: 4.2.2
Diagnostic-Code: smtp; 452 4.2.2 The recipient's mailbox is over quota; will retry."""

# Permanent class-5 but a VALID recipient (full mailbox). Must NOT be removed.
FULL = """Delivery Status Notification (Failure)
Final-Recipient: rfc822; realperson@example.com
Action: failed
Status: 5.2.2
Diagnostic-Code: smtp; 552 5.2.2 The email account that you tried to reach is over quota."""

# Non-Google hard bounce (Outlook/Exchange NDR from postmaster@). Must be caught.
EXCHANGE = """Delivery has failed to these recipients or groups:
gone@corp.example
Final-Recipient: rfc822; gone@corp.example
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 RESOLVER.ADR.RecipNotFound; not found"""


def test_hard_bounce_extracts_and_flags():
    emails, is_hard = parse_bounce(HARD)
    assert emails == {"deadbox@example.com"}, emails      # lowercased for ilike match
    assert is_hard is True


def test_soft_bounce_is_kept():
    emails, is_hard = parse_bounce(SOFT)
    assert emails == {"busy@example.com"}, emails
    assert is_hard is False                                # 4.x.x → never removed


def test_full_mailbox_is_kept():
    emails, is_hard = parse_bounce(FULL)
    assert emails == {"realperson@example.com"}, emails
    assert is_hard is False                                # 5.2.2 mailbox-full ≠ dead address


def test_non_google_hard_bounce_is_caught():
    emails, is_hard = parse_bounce(EXCHANGE)
    assert emails == {"gone@corp.example"}, emails
    assert is_hard is True                                 # postmaster@ NDRs must count too


if __name__ == "__main__":
    test_hard_bounce_extracts_and_flags()
    test_soft_bounce_is_kept()
    test_full_mailbox_is_kept()
    test_non_google_hard_bounce_is_caught()
    print("ok")
