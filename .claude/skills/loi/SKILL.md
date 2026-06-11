---
name: loi
description: Draft a Letter of Intent for a deal that underwriting returned PURSUE LOI (Green GO). Gathers terms, prompts the broker price-check call, drafts from the Olive Tree LOI template, saves the LOI as a Google Doc in the property's deal folder, and preps the broker email. Nothing sends without Brian's approval. Trigger on "/loi", "draft LOI", "draft an LOI for", "send an offer on", "let's make an offer".
---

# LOI Skill — Olive Tree Investments

## What this skill does

Turns a Green GO into a submitted offer. Runs after `/underwriting` or `/deal-analysis` returns **PURSUE LOI** — drafts the Letter of Intent from the Olive Tree template, saves it to the property's deal folder in Drive, and stages the broker email for Brian's approval.

**Position in the pipeline:** Underwriting (Green GO) → **LOI** → Pitch Deck (`/pitch-deck`) → PSA / DD. The LOI and pitch deck both live in the deal folder: `Olive Tree Investments - Deals / [property address] /`.

---

## References (read before drafting)

| File | Why |
|---|---|
| `references/loi-template.md` | Defaults + field guide (earnest money, DD period, closing) |
| `templates/loi-template.md` | Full LOI legal text — the actual document to draft from |
| `references/knowledge-base-process.md` | Stage 7 (Offers & Negotiation) checklist |
| Deal analysis output / Deal Sourcing sheet | Offer price, units, broker contact |

---

## Execution

### Step 1 — Confirm the Green GO

Pull the deal's analysis (this session, Deal Sourcing sheet, or `wiki/deals/`). If the latest verdict isn't PURSUE LOI, say so and ask Brian to confirm he wants to offer anyway. Pull the **max defensible offer** (DSCR rate-sweep ceiling) — that number anchors the offer, not the seller's ask.

### Step 2 — The broker call (don't skip)

> "Call the broker before we finalize: how many offers are in, where is pricing
> trending, are we in range? 2 minutes on the phone calibrates the price."

Capture the answer and adjust price/terms. Submitting blind on price loses winnable deals.

### Step 3 — Gather terms

| Input | Source | Default |
|---|---|---|
| Property name + address | Deal Sourcing log | — |
| Offer price | Underwriting output + broker call | ≤ max defensible offer |
| Earnest money | Brian confirms | 1–2% of offer |
| DD period | Brian confirms | 30–45 days |
| Closing timeline | Brian confirms | 45–60 days from execution |
| Financing | Value-add standard | Bridge, non-recourse, I/O |
| Special terms | Brian confirms | Make-ready credit if ≥10 vacant units |

Ask for anything missing in one batch — then draft.

### Step 4 — Draft the LOI

Use the full legal text in `templates/loi-template.md`, filled with the terms above. Show Brian the complete draft in-chat for review. Iterate until approved.

### Step 5 — Save to the deal folder

On approval, upload the LOI as a Google Doc into the property's deal folder:

```bash
python3 - <<'EOF'
import json, sys, requests
sys.path.insert(0, "scripts")
from types import SimpleNamespace
from gws_auth import get_token
from deal_analysis import ensure_deal_folder, UPLOAD_BASE

token  = get_token()
folder = ensure_deal_folder(token, SimpleNamespace(address="[ADDRESS]", property="[PROPERTY]"))

html = open("/tmp/loi.html").read().encode()   # write the approved LOI as HTML first
meta = {"name": "[PROPERTY] — LOI — [YYYY-MM-DD]",
        "mimeType": "application/vnd.google-apps.document"}
if folder: meta["parents"] = [folder]

boundary = "loi_upload"
body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(meta)}\r\n--{boundary}\r\nContent-Type: text/html\r\n\r\n"
        ).encode() + html + f"\r\n--{boundary}--".encode()
r = requests.post(f"{UPLOAD_BASE}?uploadType=multipart",
    headers={"Authorization": f"Bearer {token}",
             "Content-Type": f"multipart/related; boundary={boundary}"},
    data=body, timeout=120)
r.raise_for_status()
print("LOI saved:", f"https://docs.google.com/document/d/{r.json()['id']}/edit")
EOF
```

### Step 6 — Stage the broker email

Draft the cover email (Brian's voice — short, direct, numbers up front, signs **-Brian**) with the LOI attached/linked. Show it. **Never send without explicit approval.**

### Step 7 — Log it

On send approval:
- Deal Sourcing sheet: Stage → "LOI Submitted", Last Updated → today
- `decisions/log.md`: deal name, offer price, rationale, date
- `wiki/deals/[slug].md`: status → `loi-sent`
- Set a follow-up: per the KB, follow up with the broker within 24 hours of sending

---

## Notes

- **The ceiling is law.** Never draft above the DSCR max defensible offer without Brian explicitly overriding — and log the override in `decisions/log.md`.
- **Non-binding, always.** The LOI must state it's non-binding and subject to PSA.
- **Collections verification is a DD ask** — bank statements come after an accepted LOI, never in the LOI itself.
- **Losing LOIs still build brokers.** If the offer loses, draft a gracious note that keeps the relationship warm.
