---
name: land-call
description: Daily cold-call cockpit for phone-enriched land sellers — shows today's call list with the seller script and pre-computed offer, then logs outcomes (interested/no/callback/contracted) back to the Land Sellers tab. Trigger on "/land-call", "today's call list", "log call outcome", "who do I call today".
---

# Land Call Skill — Olive Tree Investments

## What this skill does

Pulls phone-enriched rows from **Land Sellers** (status = new, voicemail, or
callback due today), shows the pre-filled seller script with the parcel's offer
and situs address, and logs call outcomes back to the sheet.

**Phones are the missing piece.** The county gives mailing addresses free;
phones require a skip-trace step. Two paths:
- **Free/manual:** True People Search (truepeoplesearch.com) — look up a name +
  address, copy the phone into the Land Sellers tab with `--add-phone`.
- **Paid/automated:** BatchData or Kind API (~$0.10–0.20/record) — use
  `scripts/land_skiptrace.py` (deferred — not yet built).

Prioritize ★ individual owners first (they're already sorted to the top in the
Land Sellers tab).

## Running it

```bash
# Today's call list for Cartersville (phone-enriched rows only)
python3 scripts/land_call.py --zip 30120

# Callbacks due today or earlier
python3 scripts/land_call.py --zip 30120 --callbacks

# Who needs a phone number (skip-trace queue)
python3 scripts/land_call.py --zip 30120 --no-phone

# Add a skip-traced phone (channel auto-promoted from mail → call)
python3 scripts/land_call.py --add-phone 0051-0574-005 --phone 772-555-0100

# Log outcomes
python3 scripts/land_call.py --log 0051-0574-005 --outcome interested
python3 scripts/land_call.py --log 0051-0574-005 --outcome no
python3 scripts/land_call.py --log 0051-0574-005 --outcome callback --callback 2026-06-24 --notes "wants 60K, will reconsider in July"
python3 scripts/land_call.py --log 0051-0574-005 --outcome contracted
```

## Outcome values

| Outcome | What it means | Next |
|---|---|---|
| `interested` | They want to talk price | Qualify → `/land-contract` |
| `no` | Hard no right now | Ask for referral, tag callback in 90 days |
| `callback` | Call back on a date | Use `--callback YYYY-MM-DD`; resurfaces automatically |
| `voicemail` | Left a message | Auto-resurfaces on next call list |
| `contracted` | Signed PSA | Run `/land-deal` |
| `wrong-number` | Bad number | Clear phone, try skip-trace again |

## Script outline (shown in the cockpit)

"Hey [name] — is this the owner of [situs]? I'll be quick — would you be open
to selling that lot if the price was right?"

Offer → if they push back → counter-offer move ("let me check with my partner")
→ if no → "save my number as Brian Land Guy."

Full scripts in `references/land-cold-call-scripts.md`.

## Workflow

1. Run `--no-phone` to see who needs a skip-trace.
2. Look up phones on True People Search → `--add-phone` to record.
3. Run the call list → work through each seller → log outcomes.
4. Callbacks resurface automatically on the due date.
5. `interested` leads → `/land-contract` to draft the PSA.

## Notes

- Setting a phone number via `--add-phone` promotes the row's channel from
  `mail` to `call` (both outreach channels can overlap — mail still goes).
- Sellers with no phone stay on the mail channel; `/land-mail` covers them.
- The call list re-orders by call_status, not offer size — work callbacks
  first, then new rows.
