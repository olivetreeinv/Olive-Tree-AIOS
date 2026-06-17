---
name: land-sellers
description: Auto-build a land seller list for a zip from county parcel data — vacant, out-of-state-owned lots in the market's acreage band, with mailing addresses and computed cash offers. Trigger on "/land-sellers", "build seller list for [zip]", "find land sellers in [zip]", "pull absentee owners [zip]".
---

# Land Sellers Skill — Olive Tree Investments

## What this skill does

Auto-builds the **seller list** for a zip straight from county parcel data — no
Zillow, no manual list building. Pulls vacant lots owned by **out-of-state**
owners in the market's acreage band, attaches each owner's **mailing address**,
and computes a cash **offer**. Writes to the **Land Sellers** tab + `olive.db`.

Run after `/land-scout` GO + `/land-builders` (need a builder price first).

## How the offer is computed

`offer = builder $/acre × acres × (1 − spread)`, spread default 15% (range 10–20%).
Builder $/acre comes from the **Land Builders** tab (the zip's highest on file),
or `--builder-price`. Assessed value is shown for reference but is **not** a cap
(raw-land assessments lag far below market).

## Ranking & tags

- **★ Individuals first** — an out-of-state person who bought and forgot is the
  prime motivated seller. Entity/developer owners (LLC/INC/HOMES…) rank lower.
- **PACKAGE** — same owner holds multiple lots (e.g. HOBBA, FL — 3 adjacent
  Timber Trail lots). Pursue as a bundle.
- HOAs, banks, churches, government owners are excluded automatically.

## Running it

```bash
# Build Cartersville list (uses Land Builders price for 30120)
python3 scripts/land_sellers.py --zip 30120

# Preview without writing; override price + spread
python3 scripts/land_sellers.py --zip 30120 --builder-price 8000 --spread 0.15 --dry-run

# Different county / acreage band
python3 scripts/land_sellers.py --county forsyth-ga --zip 30040 --min-acres 0.1 --max-acres 2
```

Re-running is safe — only new parcels are appended (deduped on parcel id).

## Output columns (Land Sellers tab)

Parcel ID · Situs Address · Zip · Subdivision · Acres · Owner Name · **Owner
Mailing Address** · City · State · Out-of-State · Est Land Value · **Offer
Price** · Owner Phone (blank — skip-trace) · Builder Target · Channel · Call
Status · Last Call · Callback · Outcome · Notes (PACKAGE / INDIVIDUAL).

## After building the list

- **`/land-mail`** — free mass-offer mail-merge (mailing addresses are free).
- **`/land-call`** — needs phone numbers first: skip-trace the ★ individuals
  (manual True People Search, free; or a paid API). Brian dials these.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `No builder $/acre for [zip]` | Add a builder via `/land-builders` or pass `--builder-price`. |
| Offers look low/high | Confirm the builder $/acre is for this lot type; adjust `--spread`. |
| A developer slipped in as ★ | Edit the row; the entity heuristic isn't perfect on odd names. |
| Few results | Widen `--min/--max-acres`, or the zip's absentee pool is genuinely thin (check `/land-scout`). |
