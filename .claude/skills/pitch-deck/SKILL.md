---
name: pitch-deck
description: Build a deal-specific LP pitch deck in Canva from the deal's underwriting data and OM. Copies the Olive Tree master template, writes the deal's content into the slides via the Canva editing API (no manual paste-in), exports PDF, and saves it to the property's deal folder in Drive. Runs after a deal is a go (PURSUE LOI).
triggers:
  - /pitch-deck
  - pitch deck
  - create a pitch deck
  - build a pitch deck
  - investor deck
  - LP deck
outputs:
  - Canva design (new design named for the deal, slides populated with deal content)
  - PDF export saved to the deal folder in Drive
dependencies:
  - templates/pitch-deck-fields.json
  - references/canva-api.md
  - references/buy-box.md
  - references/knowledge-base-metrics.md
  - scripts/canva_api.py
  - Canva MCP (editing tools)
  - .env (CANVA_ACCESS_TOKEN)
---

# /pitch-deck Skill

Builds a deal-specific LP pitch deck in Canva — **content written into the slides by the AIOS**, not pasted by Brian. Pulls deal data from the underwriting output and OM, copies the master template, rewrites every populated slide for the new deal via the Canva editing API, exports a PDF, and files it in the property's deal folder.

**When to run:** After the deal is a **go** — `/underwriting` or `/deal-analysis` returned PURSUE LOI. Pipeline: go → `/loi` → `/pitch-deck` → LP outreach (`/capital-raise`).

---

## Template

**641 Powder Springs St Pitch Deck** (completed deal deck — the model to clone)
- Design ID and all field defaults/formulas live in **`templates/pitch-deck-fields.json`** (single source of truth). Read it before building — `master_design_id` is the authoritative ID.
- Pages: 26 · 16:9
- It's a finished LP deck for a real deal (641 Powder Springs St, Smyrna — 14 units). Populating = systematically replacing 641's content with the new deal's using the `find_text` → new value map in the JSON.
- Old 60-slide master (`DAHHfpHE2Es`) is deprecated — don't use it.

---

## Inputs

| Source | What |
|---|---|
| Underwriting output / Deal Analyzer | Returns (IRR, EM, CoC, pref, splits), price, units, debt terms, capital stack |
| OM (in the deal folder) | Property story, photos, unit mix, renovation scope |
| Market research scorecard | Market narrative — population, jobs, rent growth, path of progress |
| `references/knowledge-base-metrics.md` | Standard structure: 6% pref, 70/30 split, fee schedule, $25K min |
| `references/voice.md` | Slide narrative tone — direct, numbers-first |

If invoked without an underwriting run on record, ask for: deal name, address, units, price, vintage/class, strategy, returns (IRR/EM/CoC), raise amount + minimum. **Never fabricate returns** — anything Brian hasn't provided or underwriting hasn't computed stays bracketed for his input.

**Buy box check:** confirm the market is in `references/buy-box.md`; flag if not before building investor materials.

---

## Execution

### Step 1 — Assemble the content model

Load `templates/pitch-deck-fields.json`. It defines the 6 sections (cover, offering_summary, the_property, the_market, the_financials, how_to_invest) with every field's key, default, optional formula, and `find_text` (the literal 641-deal text in the master slides to replace).

Fill each field from the deal data sources below. Apply defaults for anything not provided. Compute formula fields (e.g. `RETURN_PER_100K = EQUITY_MULTIPLE × 100,000`). Build a final `{KEY: value}` map — this is what drives the Canva MCP replacements in Step 3.

**Never fabricate returns.** Any number Brian hasn't provided or underwriting hasn't computed stays bracketed → add to the needs-Brian list at the end.

### Step 2 — Copy the master template

```bash
source .env && python3 scripts/canva_api.py verify   # refresh first if expired
# master_design_id comes from templates/pitch-deck-fields.json
python3 scripts/canva_api.py copy <master_design_id> "Olive Tree - [Deal Name] - [Market]"
```

(If token expired: `python3 scripts/canva_api.py refresh && source .env`)

### Step 3 — Populate the slides (Canva MCP)

Work on the **copy**, never the master:

1. `start-editing-transaction` on the new design ID — returns the page list and element IDs.
2. Walk the deck **section by section** (don't attempt all slides in one pass), using the `sections` order from `pitch-deck-fields.json`. For each field with a `find_text` value, use `replace_text` / `find_and_replace_text` to swap `find_text` → the resolved value from the Step 1 content map.
3. `commit-editing-transaction` after each section. Never leave a transaction uncommitted.
4. Slides needing Brian's input (team photos, deal-specific images, bracketed numbers) — leave template content and add to the needs-Brian list.

Property/area photos: pull candidates via `scripts/deal_photos.py` conventions or ask Brian for OM photo files; images can be uploaded with `upload-asset-from-url` and placed with `update_fill`.

### Step 4 — Review with Brian

Send the edit link + flag what needs his eyes:

```
✓ Deck populated: Olive Tree - [Deal Name]
  Edit: https://www.canva.com/design/[NEW_ID]/edit
  Needs you: [list — photos, team slide, any bracketed numbers]
```

This is external-facing investor content — **Brian reviews before anything exports or sends.** Iterate on his edits via the same transaction flow.

### Step 5 — Export PDF → deal folder

On Brian's approval, one command handles export + upload:

```bash
# --dry-run first to confirm filename + folder target
python3 scripts/canva_api.py archive [DESIGN_ID] --address "[FULL_PROPERTY_ADDRESS]" --dry-run

# Live run: exports PDF, downloads, uploads to Deals / [property short name] /
python3 scripts/canva_api.py archive [DESIGN_ID] --address "[FULL_PROPERTY_ADDRESS]"
```

The deck lands in `Olive Tree Investments - Deals / [address]/` beside the OM, T-12, Deal Analyzer, and LOI. The command prints `pdf_link` and `folder_id` — relay both to Brian.

**Optional:** offer a Gmail draft to the LP list with the PDF — draft only, Brian approves the send.

---

## Output contract

1. **Buy box confirmation**
2. **Populated Canva design** — deal content written into the slides
3. **Needs-Brian list** — photos, team content, any bracketed numbers
4. **PDF in the deal folder** — after Brian approves

---

## Token management

Access tokens expire every 4 hours. `scripts/canva_api.py` auto-refreshes on 401 within a run; for interactive sessions: `python3 scripts/canva_api.py refresh && source .env`. Manual rotation: `scripts/canva_oauth_setup.py`.

---

## Critical rules

1. **Check buy box first.** No investor materials for a market outside `references/buy-box.md` without flagging.
2. **Never fabricate returns.** Every number traces to the Deal Analyzer or Brian. Missing → bracket it and put it on the needs-Brian list.
3. **Numbers must reconcile.** Deck metrics = Deal Analyzer metrics. If the model changes after the deck is built, update the deck.
4. **Brian reviews before export.** This is external LP content — nothing exports or sends without his approval.
5. **Match voice.** Direct, numbers-first, no corporate filler (`references/voice.md`).
6. **One deck per deal.** "Redo it" = edit the existing design, not a new copy.
7. **Commit every transaction.** An uncommitted Canva editing transaction silently loses all changes.
