---
name: land-mail
description: Generate mass direct-mail offer letters for all Land Sellers rows with channel=mail — one per parcel, merged from templates/land-mail-offer.md. Output to output/land-mail/<date>-<zip>/. Nothing sends automatically. Trigger on "/land-mail", "generate offer letters", "mail merge for [zip]", "print land offers".
---

# Land Mail Skill — Olive Tree Investments

## What this skill does

Takes every row in the **Land Sellers** tab with `channel=mail` and generates a
personalized cash-offer letter for each parcel owner — merged from
`templates/land-mail-offer.md`. Writes individual `.txt` files + a single
`_all_letters.txt` printable to `output/land-mail/<date>-<zip>/`.

Brian reviews, prints, stuffs, and mails. Nothing leaves the machine automatically.

**Free channel.** Direct mail requires only a stamp. The county gives you mailing
addresses for free; no skip trace needed.

## Prerequisites

1. `/land-scout [zip]` → **GO**
2. `/land-builders` — at least one builder's $/acre on file
3. `/land-sellers --zip [zip]` — seller list populated (channel=mail rows)

## Running it

```bash
# Generate letters for all new mail-channel sellers in Cartersville
python3 scripts/land_mail.py --zip 30120

# Preview 3 letters first — no files written
python3 scripts/land_mail.py --zip 30120 --dry-run --limit 3

# Reprint / include rows already run once
python3 scripts/land_mail.py --zip 30120 --status all

# Subset — just the top 20 by offer size (sellers script already ranks them)
python3 scripts/land_mail.py --zip 30120 --limit 20

# Source-of-truth method: enclose a pre-filled SIGNABLE PSA with each letter
python3 scripts/land_mail.py --zip 30120 --with-contract --dry-run --limit 1
```

Set `BRIAN_PHONE` in `.env` so the letter footer uses your real number instead of
the placeholder. `BRIAN_EMAIL` defaults to `brian@olivetreeinv.io`.

### `--with-contract` (letter + signable mail-back contract)

Merges the assignable PSA (`templates/land-psa-template.md`) per parcel and writes
a `NNN-<parcel>-CONTRACT.txt` beside each letter, plus a `_all_contracts.txt` batch.
Stuff one letter + one matching contract (same `NNN-` prefix) per envelope; the
seller signs and mails it back. The §4 feasibility contingency lets you terminate
anytime before closing, so their signature binds them, not you.

⚠️ **GA attorney review of the PSA template is required before mailing any of
these** — a signed return is a binding contract. PSA constants are env-overridable:
`BUYER_LEGAL_NAME` (default `Olive Tree Investments, LLC`), `LAND_EMD` (default `$10`),
`LAND_CLOSE_DAYS` (default `30`).

## Output

| File | Contents |
|---|---|
| `output/land-mail/<date>-<zip>/001-<parcel>.txt` | Individual letter per parcel |
| `output/land-mail/<date>-<zip>/_all_letters.txt` | Full batch, page-break separated (print this) |

## Mail workflow after output

1. Print `_all_letters.txt` — one letter per page.
2. Print/copy the `templates/land-psa-template.md` as the enclosed contract
   (attorney-reviewed first — don't mail without it).
3. Stuff + stamp + mail each to the owner's mailing address printed at the top.
4. When responses come in, update the **Outcome** column in Land Sellers.
   Phone calls that come in → log in **Call Status** and move to `/land-call`.

## How the offer is filled

`Offer = builder $/acre × acres × (1 − spread)` — same math as `/land-sellers`.
The letter uses the Offer Price already computed and stored in the sheet (col 11),
so no recalculation occurs here. If you re-run `/land-sellers` with a different
spread or builder price, re-run `/land-mail` to refresh the letters.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Land Sellers tab is empty` | Run `/land-sellers --zip [zip]` first. |
| `0 letters to generate` | Check that rows have `channel=mail` and `status=new`; try `--status all`. |
| Owner Zip column blank | Those 45 rows predate the Owner Zip column. Re-run `/land-sellers` to refresh. |
| Offer shows as `[OFFER]` | The row's Offer Price cell is empty — check `/land-sellers` ran with a builder price. |
| `[PHONE]` in letter footer | Add `BRIAN_PHONE=770-555-0100` to `.env`. |
