---
name: bpo
description: Generate a single-family BPO (Broker Price Opinion). Pulls 3 active and 3 sold comps from FMLS by build type, age, beds, and baths. Creates a Google Doc + PDF in Drive under 'Olive Tree Investments - BPOs / [address]'. Trigger on "/bpo", "bpo on [address]", "run a BPO", "broker price opinion", "pull comps on", "what's this house worth".
---

# BPO Skill — Olive Tree Investments

## What this does

Generates a professional Broker Price Opinion (BPO) for a single-family property:
- **3 active comps** — current competition (same zip, ±1 bed, ±25% sqft, ±15 yr age)
- **3 sold comps** — last 3–12 months, same criteria, sorted most recent first
- **Google Doc** — formatted BPO with all sections (subject, comps, value, marketability, neighborhood trend)
- **PDF** — exported alongside the Doc
- **Drive folder** — `Olive Tree Investments - BPOs / [address]`

All data pulled from FMLS via Bridge Interactive API.

---

## Trigger

Any of:
- `/bpo`
- "bpo on [address]"
- "run a BPO for..."
- "broker price opinion on..."
- "pull comps on [address]"

---

## Execution

### Step 1 — Collect address

If not already provided, ask:

> **What's the full property address?** (include city, state, zip)
> Anything else to add — as-is value estimate, ARV, or repair notes to pre-fill?

### Step 2 — Check if listed on FMLS

The script auto-searches FMLS for the address. Two paths:

**Path A — Listed on FMLS (most common):**
The script pulls subject details (beds, baths, sqft, year, style, price, agent) directly. Run:
```bash
python3 scripts/bpo.py --address "[address]" [--as-is "$X"] [--repaired "$X"]
```

**Path B — Not listed (off-market or withdrawn):**
Ask Brian for:
- Zip code
- Beds / baths / sqft / year built / style (Traditional, Ranch, etc.)

Then run:
```bash
python3 scripts/bpo.py \
  --address "[address]" \
  --zip [zip] --beds [n] --baths [n] --sqft [n] --year [n] --style [style] \
  [--as-is "$X"] [--repaired "$X"]
```

### Step 3 — Report results

After the script completes, report:

```
BPO complete for [address]

Sold comps (X found):
  #1 — [address], [beds]bd/[ba]ba, [sqft]sqft — sold $[price] on [date] ([prox])
  #2 — ...
  #3 — ...

Active comps (X found):
  #1 — [address], [beds]bd/[ba]ba, [sqft]sqft — listed at $[price] ([prox])
  ...

Google Doc: [link]
PDF: [link]
Folder: [link]
```

If fewer than 3 sold comps are found, note it explicitly: "Only X sold comps in the last 12 months at this zip — BPO shows what's available."

---

## Value fields

`--as-is` and `--repaired` are optional pre-fills for the Value section. If Brian gives estimates upfront, include them. Otherwise leave blank — he fills them in the Doc.

---

## BPO best practices applied

- **Sold comps**: prioritized over active (actuals beat asking prices)
- **Recency**: most recent closings weighted first (3 months preferred, 12 max)
- **Proximity**: haversine distance shown when lat/lon available; otherwise "same zip"
- **$/sqft**: sold comp average computed and surfaced in the doc
- **Comp criteria**: ±1 bed, ±25% sqft, ±15 yr age — widest match that's still comparable

---

## Drive location

All BPOs saved under:
`Olive Tree Investments - BPOs / [full address] / BPO - [address].gdoc + .pdf`

Folder is created on first run and reused on re-runs (same address).
