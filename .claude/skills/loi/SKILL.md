---
name: loi
description: Draft a Letter of Intent for a deal. Works two ways: (1) after /deal-analysis or /underwriting returns a GO — auto-populates from that session's data; (2) manually triggered — runs an intake interview to collect everything needed. Saves the LOI as a Google Doc + PDF in the deal folder and stages the broker email. Nothing sends without Brian's approval. Trigger on "/loi", "draft LOI", "draft an LOI for", "send an offer on", "let's make an offer".
---

# LOI Skill — Olive Tree Investments

## What this skill does

Turns a GO verdict into a submitted offer. Drafts the Letter of Intent using `templates/loi-template.md`, saves it as a **Google Doc + PDF** in the property's deal folder, and stages the broker email for Brian's approval.

**Position in the pipeline:** Underwriting (GO) → **LOI** → Pitch Deck (`/pitch-deck`) → PSA / DD.

---

## Two entry modes

### Mode A — Post-deal-analysis (auto-populated)
Triggered right after `/deal-analysis` or `/underwriting` returns a **GO**. Most data is already in session. Skip to Step 3 — only confirm price and any overrides.

### Mode B — Manual trigger (intake interview)
Triggered standalone with no deal context. Run the intake interview in Step 1 before drafting anything.

---

## Execution

### Step 1 — Intake interview (Mode B only)

Ask all of the following in **one message** — don't fire questions one at a time:

> **Company info — confirm before I proceed:**
> I'm pulling these from your AIOS context. Correct anything that's wrong:
> - Company: [state what you found in context/CLAUDE.md — e.g., "Olive Tree Investments LLC"]
> - Owner: [state what you found — e.g., "Brian Norton"]
> - City: [state what you found — e.g., "Atlanta"]
> - Contact footer: [email | phone | website from context]
> If any of these are wrong, say so. Otherwise just say "confirmed" and I'll move on.
>
> **Deal info — fill in what's missing:**
>
> 1. **Company logo** — optional. The Olive Tree logo hosted on olivetreeinv.io is inserted automatically (1-inch height). To override, paste a **direct public image URL** (ends in `.png`/`.jpg`, shows only the image in a browser). Drive links don't work — Google serves an HTML page, not the image bytes.
> 2. **Property address** (full street, city, state, zip)?
> 3. **Broker name + brokerage**?
> 4. **Offer price** ($)?
> 5. **Number of units**?
> 6. **Financing** — default is 70% LTC Bridge, No Financing Contingency. Changing it?
> 7. **Due diligence period** — default 28 days. Changing it?
> 8. **Closing timeline** — default 60 days. Changing it?
> 9. **Special conditions** — default N/A. Anything to add (make-ready credit, rent roll warranty, etc.)?
> 10. **Date** — default today. Changing it?

**How to auto-fill company info:** Check `context/` files and `CLAUDE.md` for company name, owner name, city, email, phone, and website. State what you found explicitly so Brian can confirm or correct. If nothing is found in context, ask for it directly.

Don't hand-calculate deposits or per-unit — `scripts/loi.py` derives them from the formulas in `templates/loi-fields.json` (the single source of truth for fields, defaults, formulas, and Google-Doc tokens). You only collect the inputs; the script applies defaults and computes the rest.

---

### Step 2 — Confirm go / no-go (Mode A only)

Pull the deal's latest verdict from this session, the Deal Sourcing sheet, or `wiki/deals/`.

- **GO** → proceed. Anchor price to the **DSCR max defensible offer ceiling**.
- **NO-GO** → flag it. Ask Brian to confirm he wants to proceed anyway before drafting.

If Brian overrides a NO-GO, log it in `decisions/log.md` before continuing.

---

### Step 3 — Draft the LOI

Load `templates/loi-template.md`. Fill every placeholder with the collected terms. Auto-calculate all deposit fields. Show the complete draft in-chat for review.

Fields, defaults, and formulas all come from `templates/loi-fields.json` (single source of truth). Don’t recompute deposits here. If Brian did not provide a logo, leave LOGO blank — the script removes the token.

Render the `{{KEY}}` preview from `templates/loi-template.md` and show it to Brian. Iterate until approved.

---

### Step 4 — Generate the Google Doc + PDF

On approval, write the collected terms to `/tmp/loi_values.json` (flat `{KEY: value}` using keys from `loi-fields.json` — only include what Brian provided/changed; defaults and formulas are applied by the script) and run:

```bash
python3 scripts/loi.py --values /tmp/loi_values.json --dry-run   # confirm resolved numbers
python3 scripts/loi.py --values /tmp/loi_values.json              # generate Doc + PDF
# add --folder-id <id> to target a specific deal folder; omit to auto-resolve by property name
```

The script copies the template Doc into the deal folder, replaces all `<...>` tokens (longest-first; both apostrophe variants for DATE), exports the PDF, and uploads it. It prints JSON — relay the links to Brian:

```
doc_url  → Google Doc (edit link)
pdf_link → PDF in Drive
```

---

### Step 5 — Stage the broker email

Draft the cover email. Brian's voice — short, direct, numbers up front, signs **-Brian**. Include the PDF Drive link as the attachment reference.

```
Subject: LOI — [Property Address]

[BROKER_NAME],

Attached is our LOI for [PROPERTY_ADDRESS] at $[OFFER_PRICE] ($[PRICE_PER_UNIT]/unit).

[One sentence on thesis — e.g., "Strong value-add play — we like the upside on rents."]

Let me know if you have questions.

-Brian
```

**Never send without explicit approval from Brian.**

---

### Step 6 — Log it

On send approval:
- Deal Sourcing sheet: Stage → "LOI Submitted", Last Updated → today
- `decisions/log.md`: deal name, offer price, rationale, date
- `wiki/deals/[slug].md`: status → `loi-sent`

---

## Rules

- **The ceiling is law.** Never draft above the DSCR max defensible offer without Brian's explicit override — log any override in `decisions/log.md`.
- **Non-binding, always.** LOI must state it's non-binding and subject to PSA.
- **Logo = optional.** If no logo provided, omit the logo line. Don't leave a broken placeholder.
- **Collections verification is a DD ask.** Bank statements come after LOI acceptance — never in the LOI.
- **If the LOI loses** — draft a gracious broker note before closing the session.
- **One question batch.** Ask for everything in Step 1 at once. Don't drip questions one at a time.

---

## References

| File | Why |
|---|---|
| `templates/loi-fields.json` | **Single source of truth** — fields, defaults, formulas, Google-Doc token map |
| `templates/loi-template.md` | In-chat preview body (`{{KEY}}` tokens) |
| `scripts/loi.py` | Generates the Google Doc + PDF from the values file |
| `references/knowledge-base-process.md` | Stage 7 (Offers & Negotiation) full checklist |
| Deal analysis output / wiki | Offer price, units, broker contact |
