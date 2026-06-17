# Olive Tree — Land Wholesaling Buy Box

**Buy box is law.** Check this before any land work — scouting, seller outreach, offers, contracts. If a parcel or market isn't in here, flag it before proceeding.

This is the **land-wholesaling** buy box — a separate vertical from the multifamily buy box (`references/buy-box.md`). Different markets, buyers, and criteria.

---

## The model (one line)

Builder-first: lock an out-of-state owner's vacant lot under an **assignable contract** ~10–20% below what a local builder/developer will pay, then assign to the builder for the spread. No money down. (`references/land-wholesale-playbook.md` for the full method.)

---

## Two requirements for a market (Carson & Jackson)

A zip/market qualifies only if **both** are true:
1. **Active building demand** — builders/developers are buying lots here (new construction present).
2. **Uniform, mass-offerable inventory** — enough similar vacant lots that one blanket offer fits many owners. Measured by the **cookie-cutter uniformity score** in `/land-scout` (acreage CV → uniformity in [0,1]).

Plus the seller-side test we added from live data:
3. **Absentee inventory at a workable basis** — a real pool of **vacant + out-of-state-owned** lots (the motivated seller) that are also reasonably uniform and cheaply based. A hot metro can have hundreds of absentee lots yet still fail if they're non-uniform and high-basis (e.g. Forsyth/30040) — spreads are too thin to wholesale.

---

## Active markets

| Market | County | Zips | Flavor | Seller band | Status |
|---|---|---|---|---|---|
| **Cartersville** | Bartow, GA | 30120, 30121 | Rural/exurban absentee acreage | **1–10 ac** | **LAUNCH** |
| White | Bartow, GA | 30184 | Same, thinner | 1–10 ac | Watch |
| Emerson | Bartow, GA | 30137 | Same, thinner | 1–10 ac | Watch |

**Cassville (30123):** mail routes through 30120 — don't filter on it as a situs zip.

**Forsyth/30040 — REJECTED for wholesaling.** Hot new-construction county with a real absentee pool (~367 vacant out-of-state lots), but lot sizes are non-uniform (uniformity 0.0) and the basis is high (~$256K avg land) — a built-out, expensive metro where wholesale spreads are thin. Fails the cookie-cutter + economics tests despite having sellers. Kept only as a GIS test county.

---

## Cartersville (Bartow) — the launch market

Validated against live Bartow County parcel data (`bartow-ga` in `scripts/land_parcels.py`):

- **~400 vacant, out-of-state-owned lots** across 30120 + 30121 (vs. 1 in Forsyth).
- This is a **rural/exurban absentee-acreage** market — the meaty inventory is **1–10 acre** vacant tracts held by out-of-state owners (TX, MD, MI, FL), **not** FL-style quarter-acre cookie-cutter lots.
- **Package deals exist** — e.g. one FL owner holds 3 adjacent Timber Trail lots (4.96 + 5.45 + 6.67 ac). Always check for same-owner multi-lots (`/land-sellers` flags them).

### Seller filter (what `/land-sellers` pulls)
- Vacant (no structure: `BuildingValue = 0`)
- Out-of-state owner (`Mailing_State ≠ GA`)
- **1–10 acres** (drop sub-0.5 ac — mostly HOA common areas; handle 10+ ac as one-off larger plays)
- Exclude owners that are HOAs / `ASSOC` / `C/O` management cos.

### Offer math
`offer = builder/developer price per acre × acres × (1 − spread)`, spread **10–20%**.
Anchor sanity-check against the parcel's appraised **LandValue** (don't offer above it without a builder confirmed higher).

---

## Universal rules

- **No phones from the county** — mailing addresses are free; phone numbers require manual skip-trace (free) or a paid API. **Direct mail is the free auto-scale channel** (`/land-mail`); cold calls (`/land-call`) need the phone step first.
- **Every contract** carries an assignability clause + a feasibility contingency to closing; EMD due at closing, not signing. (`templates/land-psa-template.md` — attorney review required.)
- **Buyer-first**: confirm a builder/developer's price before mass-offering a zip. A seller list with no buyer is just a mailing list.

---

## Adding a market

Run `/land-scout [zip]`. It screens the 3 requirements from county parcel data and writes a Go/No-Go to the **Land Markets** tab. To wire a new county, add a config block to `scripts/land_parcels.py` (`COUNTIES`) — only ArcGIS-Online-hosted county orgs are reachable.
