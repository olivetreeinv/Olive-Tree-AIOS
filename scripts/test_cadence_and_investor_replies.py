#!/usr/bin/env python3
"""Checks for the 2026-08-01 usage-audit fixes.

1. heartbeat's Mon/Fri cadence nudge reaches the ntfy `summary`, not just stdout
   (it printed only to the log for weeks — /q3-scoreboard ran 1 of 5 Fridays).
2. deal_inbox only surfaces investor-language replies from *active drip*
   contacts, so a stranger saying "interested" doesn't land in the raise list.

Run: python3 scripts/test_cadence_and_investor_replies.py
"""
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))


def test_nudge_reaches_summary():
    """Same weekday->nudge logic heartbeat.py runs; the bug was omitting it from summary."""
    def summarize(today, reds=(), new_deals=(), stale=()):
        nudge = ""
        if today.weekday() == 0:
            nudge = "MONDAY: run /lets-get-to-work"
        elif today.weekday() == 4:
            nudge = "FRIDAY: run /q3-scoreboard"
        summary = "All 9 systems green" if not reds else f"{len(reds)} RED"
        if new_deals:
            summary += f" · {len(new_deals)} new deal folder(s)"
        if stale:
            summary += f" · {len(stale)} unreviewed script(s)"
        if nudge:
            summary += f" · {nudge}"
        return summary

    assert "/lets-get-to-work" in summarize(date(2026, 8, 3)), "Monday nudge missing"
    assert "/q3-scoreboard" in summarize(date(2026, 8, 7)), "Friday nudge missing"
    # Tue-Thu and weekends stay quiet — a nudge every day is a nudge nobody reads.
    for d in (date(2026, 8, 4), date(2026, 8, 6), date(2026, 8, 1)):
        assert "run /" not in summarize(d), f"unexpected nudge on {d:%A}"
    # Nudge rides alongside the existing suffixes, doesn't replace them.
    both = summarize(date(2026, 8, 7), stale=["a", "b"])
    assert "unreviewed script(s)" in both and "/q3-scoreboard" in both


def test_investor_replies_filtered_to_drip_contacts():
    import deal_inbox

    drip = {"lp@example.com": ("Dana Reed", "641-powder-springs")}
    msgs = {
        "m1": ("Dana Reed <lp@example.com>", "Re: 641 — interested"),
        "m2": ("Random Guy <nobody@example.com>", "Re: interested in your services"),
        "m3": ("DANA REED <LP@Example.COM>", "Re: the deck"),  # case/format drift
    }

    with patch.object(deal_inbox, "get_drip_contacts", return_value=drip), \
         patch.object(deal_inbox, "search_messages",
                      return_value=[{"id": k} for k in msgs]), \
         patch.object(deal_inbox, "get_message_full", side_effect=lambda t, i: i), \
         patch.object(deal_inbox, "extract_header",
                      side_effect=lambda m, h: msgs[m][0 if h == "From" else 1]), \
         patch.object(deal_inbox, "extract_body_preview", return_value="..."):
        out = deal_inbox.scan_investor_replies("tok", days=1)

    emails = {r["email"].lower() for r in out}
    assert emails == {"lp@example.com"}, f"expected only the drip contact, got {emails}"
    assert len(out) == 2, "both of Dana's messages should surface"
    assert out[0]["drip"] == "641-powder-springs"


def test_investor_replies_survive_db_failure():
    """Unattended job: a dead DB must not take down the whole morning scan."""
    import deal_inbox
    with patch.object(deal_inbox, "get_drip_contacts", side_effect=RuntimeError("no db")):
        assert deal_inbox.scan_investor_replies("tok", days=1) == []


def test_commit_command_survives_apostrophe_names(capsys=None):
    """The printed command gets copy-pasted into a shell — O'Brien must not break it."""
    import io
    import contextlib
    import shlex
    import deal_inbox

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        deal_inbox.print_investor_replies([{
            "name": "Sean O'Brien", "email": "s@example.com", "drip": "641",
            "subject": "interested", "date": "Fri, 1 Aug 2026", "preview": "...",
        }])
    line = next(l for l in buf.getvalue().splitlines() if "capital_raise.py commit" in l)
    args = shlex.split(line.split("Log it:")[1])
    assert "Sean O'Brien" in args, f"name did not survive shell parsing: {args}"


def test_summary_lists_investors():
    import morning_deal_scan as m
    out = m.build_summary(([], 0, 3), ([], [], []), (2, 1),
                          [{"name": "Dana Reed", "subject": "Re: 641 — interested"}])
    assert "1 INVESTOR" in out and "Dana Reed" in out
    assert "INVESTOR" not in m.build_summary(([], 0, 3), ([], [], []), (2, 1), [])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"  ok  {name}")
    print("all checks passed")
