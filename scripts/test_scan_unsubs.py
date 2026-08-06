"""Self-check for newsletter._own_words + BODY_OPTOUT_RE — the quote-stripping that
decides whether a body-pass opt-out is the sender's own words or quoted/forwarded
text. Run: python3 scripts/test_scan_unsubs.py"""
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.newsletter import BODY_OPTOUT_RE, _own_words


def payload(text):
    data = base64.urlsafe_b64encode(text.encode()).decode()
    return {"body": {"data": data}}


def hits(text):
    return bool(BODY_OPTOUT_RE.search(_own_words(payload(text))))


# Real opt-out reply (the Trey shape): own words above the quote. Must flag.
REPLY = """Unsubscribe.

On 8/3/26 09:01, brian@olivetreeinv.io wrote:
Hi Trey, Following up on 641 Powder Springs."""
assert hits(REPLY), "own-words unsubscribe above quote must flag"

# Our own footer quoted back in a harmless reply. Must NOT flag.
QUOTED_FOOTER = """Sounds good, send it over.

On 8/1/26 10:00, brian@olivetreeinv.io wrote:
> Great deal here.
> To stop receiving these, reply UNSUBSCRIBE."""
assert not hits(QUOTED_FOOTER), "quoted footer must not flag"

# Forwarded newsletter with an unsubscribe footer. Must NOT flag.
FORWARD = """Brian, thoughts on this deal?

---------- Forwarded message ---------
From: deals@othersponsor.com
Click here to unsubscribe from this list."""
assert not hits(FORWARD), "forwarded footer must not flag"

# HTML reply: own-words opt-out, our footer inside the gmail_quote. Must flag.
HTML_REPLY = """<div dir="ltr">Please remove me from your list.</div>
<div class="gmail_quote">On Mon, brian@olivetreeinv.io wrote:<br>
reply UNSUBSCRIBE to stop</div>"""
assert hits(HTML_REPLY), "own-words opt-out in HTML must flag"

# Interested reply quoting our footer. Must NOT flag.
INTERESTED = """Very interested -- send the deck.

> To stop receiving these, reply UNSUBSCRIBE."""
assert not hits(INTERESTED), "interested reply must not flag"

print("all scan-unsubs checks pass")
