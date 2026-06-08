---
name: govcon
description: Government contracting pipeline coach for Brian Norton. Checks bid status, surfaces next actions, helps find and contact subcontractors, and guides each bid from discovery to submission. Trigger on "govcon", "check my bids", "where am I on govcon", "next steps on bids", "help me contact subs", "govcon pipeline", or "what do I do next on govcon".
---

## What this skill does

Full government contracting workflow — no local app required. Everything runs via direct API calls:
- **Pipeline:** Google Sheets (read/write)
- **Bid cache:** Google Drive (read first — only hits SAM.gov for new bids)
- **Opportunity discovery:** SAM.gov API (direct — daily quota, check cache first)
- **Document analysis:** SAM.gov resource links → PDF → Claude (saved to Drive cache)
- **Pricing research:** USASpending.gov API (direct)
- **Proposal generation:** Claude Sonnet (inline)

**One run = one clear action list + any outreach or proposals drafted and ready.**

---

## Keys & IDs

```
SAM_API_KEY=SAM-eb4fe7b1-74cb-4ecc-9675-14d4fb27d97b    # SAM.gov — daily quota, resets midnight UTC
GOVCON_SHEET_ID=1y7eQTpmY6V5O22f_bgZUjFNgkWuOcoZbGPGWMz5ECGw
ANTHROPIC_API_KEY=<your-key-from-console.anthropic.com>
DRIVE_GOVCON_CACHE_FOLDER=1fLmZ0CSpugi5j-wb3eQqOAdHPtQM3pRB   # GovCon Bid Cache (root)
DRIVE_BIDS_FOLDER=1nBGkN44a0i39RxNq9s9pYCzBEPRsoVwg            # GovCon Bid Cache/bids/
```

All in `.env`. GWS credentials via `gws auth export --unmasked`.

---

## Target NAICS codes

| Code | Trade |
|------|-------|
| 561730 | Landscaping |
| 561720 | Janitorial & Cleaning |
| 238320 | Painting & Wall Covering |
| 484210 | Household & Office Moving |
| 531311 | Residential Property Management |
| 812990 | All Other Personal Services |
| 562910 | Remediation Services |
| 562112 | Hazardous Waste Collection |

Also valid (construction trades): 238110, 238130, 238140, 238160, 238210, 238220, 238310, 238330, 238910

---

## Auth helpers

### GWS token (use this pattern — saves to /tmp for reuse across commands)
```python
import subprocess, json, ssl, urllib.request, urllib.parse

gws = json.loads(subprocess.run(['gws','auth','export','--unmasked'], capture_output=True, text=True).stdout)
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE

token_data = urllib.parse.urlencode({
    'client_id': gws['client_id'], 'client_secret': gws['client_secret'],
    'refresh_token': gws['refresh_token'], 'grant_type': 'refresh_token'
}).encode()
req = urllib.request.Request('https://oauth2.googleapis.com/token', data=token_data, method='POST')
with urllib.request.urlopen(req, context=ctx) as r:
    TOKEN = json.loads(r.read())['access_token']
open('/tmp/gws_token.txt','w').write(TOKEN)
```
Then in Bash: `TOKEN=$(cat /tmp/gws_token.txt)`

---

## Feature 0 — Drive Cache (check BEFORE SAM.gov on every run)

**Drive folder:** `GovCon Bid Cache/bids/` — one JSON file per bid, named `{notice_id}.json`
**Cache folder ID:** `1nBGkN44a0i39RxNq9s9pYCzBEPRsoVwg`

### Read all cached bids
```python
import ssl, urllib.request, json

ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
TOKEN = open('/tmp/gws_token.txt').read().strip()
BIDS_FOLDER = "1nBGkN44a0i39RxNq9s9pYCzBEPRsoVwg"

# List all cached bid files
req = urllib.request.Request(
    f"https://www.googleapis.com/drive/v3/files?q=%27{BIDS_FOLDER}%27+in+parents+and+trashed%3Dfalse&fields=files(id,name)&pageSize=100",
    headers={"Authorization": f"Bearer {TOKEN}"}
)
with urllib.request.urlopen(req, context=ctx) as r:
    files = json.loads(r.read()).get('files', [])

# Download and parse each bid JSON
cached_bids = {}
for f in files:
    notice_id = f['name'].replace('.json','')
    req2 = urllib.request.Request(
        f"https://www.googleapis.com/drive/v3/files/{f['id']}?alt=media",
        headers={"Authorization": f"Bearer {TOKEN}"}
    )
    with urllib.request.urlopen(req2, context=ctx) as r:
        cached_bids[notice_id] = json.loads(r.read())

print(f"Loaded {len(cached_bids)} cached bids from Drive")
```

### Write/update a bid cache entry
```python
def cache_bid(notice_id, data, token, folder_id, existing_file_id=None):
    ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
    content = json.dumps(data, indent=2).encode('utf-8')
    boundary = 'govcon_boundary'
    metadata = json.dumps({"name": f"{notice_id}.json", "parents": [folder_id]}).encode()
    body = (
        f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'.encode() +
        metadata + b'\r\n' +
        f'--{boundary}\r\nContent-Type: application/json\r\n\r\n'.encode() +
        content + b'\r\n' + f'--{boundary}--'.encode()
    )
    url = f'https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart'
    if existing_file_id:
        url = f'https://www.googleapis.com/upload/drive/v3/files/{existing_file_id}?uploadType=multipart'
    req = urllib.request.Request(url, data=body, method='POST' if not existing_file_id else 'PATCH',
        headers={'Authorization': f'Bearer {token}', 'Content-Type': f'multipart/related; boundary={boundary}'})
    with urllib.request.urlopen(req, context=ctx) as r:
        return json.loads(r.read()).get('id')
```

### Cache JSON schema (per bid)
```json
{
  "notice_id": "...",
  "title": "...",
  "solicitation_number": "...",
  "trade": "...", "naics": "...", "state": "...",
  "deadline": "ISO datetime",
  "set_aside": "Total Small Business",
  "contract_type": "RFP|RFQ|IFB",
  "agency": "...",
  "place_of_performance": "...",
  "period_of_performance": {"phase_in": "...", "base": "...", "options": "..."},
  "poc": [{"role": "...", "name": "...", "email": "..."}],
  "submission_instructions": "...",
  "scope_summary": "2-3 sentence plain English",
  "key_requirements": ["...", "..."],
  "submission_checklist": ["...", "..."],
  "go_no_go": "GO|NO-GO|NEEDS-REVIEW",
  "go_no_go_reason": "...",
  "sam_link": "https://sam.gov/...",
  "resource_links": ["..."],
  "pws_text": "Full extracted PWS text or 'Pending'",
  "cached_date": "YYYY-MM-DD",
  "cache_version": 1
}
```

### When to use cache vs SAM.gov
- **Cached bid** (file exists in Drive): read from cache. Don't call SAM.gov.
- **New bid** (file not in Drive): fetch from SAM.gov, write to cache immediately.
- **PWS pending** (`pws_text` contains "Pending"): try to fetch PDFs from `resource_links`, update cache.
- **SAM.gov quota exceeded**: use cache only. Surface clearly which bids have pending PWS.

---

## Feature 1 — Pipeline (Google Sheets)

**Sheet:** `1y7eQTpmY6V5O22f_bgZUjFNgkWuOcoZbGPGWMz5ECGw`
**Tabs:** `Bids` (pipeline) · `Sub Outreach` (candidates + scripts per bid) · `Bid Documents` (all attachments with download links)

### Column map — Bids tab
`A=Notice ID | B=Title | C=Trade | D=NAICS | E=State | F=Deadline | G=Days Left | H=Status | I=Sub Name | J=Sub Contact | K=Sub Quote | L=Our Bid | M=Gross Profit | N=Set-Aside | O=Notes | P=SAM.gov Link`

### Column map — Bid Documents tab
`A=Bid Title | B=Notice ID | C=Document Name | D=Size (KB) | E=Posted Date | F=Access | G=Download Link (HYPERLINK formula) | H=Resource ID`

### Fetch resource links for a bid (v3 API — use this, not v2 search)
```bash
curl -s "https://sam.gov/api/prod/opps/v3/opportunities/{NOTICE_ID}/resources?api_key=$SAM_API_KEY"
# Returns: _embedded.opportunityAttachmentList[].attachments[]
# Key fields: name, resourceId, size, accessLevel, deletedFlag
# Download URL: https://sam.gov/api/prod/opps/v3/opportunities/resources/files/{resourceId}/download?api_key=$SAM_API_KEY
```

### Download and analyze a specific document
```python
import urllib.request, ssl
ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
# Get resource_links from Drive cache or Bid Documents tab (column H = resourceId)
resource_id = "fbf2cb094cc44a8d91670b810644eddd"  # example: Fort Stewart SF30
url = f"https://sam.gov/api/prod/opps/v3/opportunities/resources/files/{resource_id}/download?api_key={SAM_KEY}"
req = urllib.request.Request(url)
with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
    pdf_bytes = r.read()
# Then extract text with pypdf or send bytes to Claude for analysis
```

### Read pipeline
```bash
curl -s "https://sheets.googleapis.com/v4/spreadsheets/$SHEET_ID/values/Bids!A1:P100" \
  -H "Authorization: Bearer $TOKEN"
```

### Update a bid row (replace ROW_NUM with actual row, e.g. 3)
```bash
curl -s -X PUT "https://sheets.googleapis.com/v4/spreadsheets/$SHEET_ID/values/Bids!H{ROW_NUM}?valueInputOption=USER_ENTERED" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"values": [["sub_contacted"]]}'
```

### Append a new bid
```bash
curl -s -X POST "https://sheets.googleapis.com/v4/spreadsheets/$SHEET_ID/values/Bids!A1:append?valueInputOption=USER_ENTERED" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"values": [["notice_id","title","trade","naics","state","deadline","days_left","researching","","","","","","Total Small Business","","https://sam.gov/..."]]}'
```

### Sub Outreach tab — column map
`A=Bid | B=Sub Name | C=Phone | D=Website | E=Date Contacted | F=Method | G=Response | H=Quote Amount | I=Notes`

Scripts (phone + email) are saved below the candidate rows for each bid, clearly labeled.

---

## Feature 2 — SAM.gov opportunity discovery

**Direct API — no local app.**

```bash
SAM_KEY="SAM-eb4fe7b1-74cb-4ecc-9675-14d4fb27d97b"
FROM_DATE=$(date -v-60d +%m/%d/%Y)   # macOS
TO_DATE=$(date +%m/%d/%Y)

# Query one NAICS at a time (repeat for each target code)
curl -s "https://api.sam.gov/prod/opportunities/v2/search?api_key=$SAM_KEY&limit=50&ptype=k&naicsCode=561730&postedFrom=$FROM_DATE&postedTo=$TO_DATE"
```

**Response field:** `opportunitiesData[]`

**Key fields per opportunity:**
- `noticeId` — unique ID
- `title`
- `naicsCode`
- `responseDeadLine` — ISO datetime (e.g. `2026-06-05T14:00:00-04:00`)
- `typeOfSetAside` — `SBA`=Total Small Biz, `8A`=8(a), `HUBZ`=HUBZone
- `typeOfSetAsideDescription` — human readable
- `placeOfPerformance.state.code` / `.city.name`
- `pointOfContact[0].email` — contracting officer
- `uiLink` — SAM.gov URL
- `resourceLinks[]` — attached PDFs (SOW, PWS, etc.)
- `solicitationNumber`
- `fullParentPathName` — agency chain

**Filter:** Keep `typeOfSetAside == "SBA"` only. Skip `8A` and `HUBZ` unless Brian has a certified sub.

**Quota error:** `{"code":"900804","message":"Message throttled out"}` — surface clearly, do not retry. Resets midnight UTC.

---

## Feature 3 — Document analysis (PDFs → Claude)

Downloads attached PDFs from `resourceLinks`, extracts text, analyzes with Claude Haiku.

```bash
# Download and analyze PDF docs for a notice
python3 << 'PYEOF'
import urllib.request, json, sys, os, re, ssl

notice_id = "8ae3e9d2e3d14a269cbd8249584d5c0e"  # replace per bid
resource_links = [...]  # from SAM.gov opportunity data

# Download PDFs (skip SSL verify issues with ctx)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

combined_text = ""
for url in resource_links[:3]:  # first 3 docs max
    try:
        with urllib.request.urlopen(url, context=ctx, timeout=30) as r:
            content = r.read()
        # Try pypdf if available
        try:
            from pypdf import PdfReader
            from io import BytesIO
            reader = PdfReader(BytesIO(content))
            text = "\n".join(p.extract_text() or "" for p in reader.pages[:50])
            combined_text += text + "\n"
        except Exception:
            combined_text += content.decode("utf-8", errors="ignore")[:5000]
    except Exception as e:
        print(f"Could not fetch {url}: {e}")

print(combined_text[:2000])  # preview before sending to Claude
PYEOF
```

**Then analyze with Claude inline** (no API call needed — you ARE Claude):

Read the extracted text and produce:
- `scope_summary` — 2–3 sentence plain English summary
- `subcontractors_allowed` — yes / no / unclear (look for FAR 52.244-2, "may subcontract", "self-performance required")
- `go_no_go` — GO / NO-GO / NEEDS-REVIEW
- `go_no_go_reason` — one sentence
- `key_requirements` — top 3–5 performance standards
- `submission_checklist` — what Brian needs to submit
- `contract_type` — RFQ / RFP / IFB

**GO criteria:** Services contract, subcontracting allowed or unclear, no security clearance required.
**NO-GO criteria:** Self-performance required, clearance needed, or products/manufacturing.

---

## Feature 4 — Pricing research (USASpending.gov)

Pulls past federal contract awards for a NAICS to establish pricing ceiling.

```bash
python3 << 'PYEOF'
import urllib.request, json, ssl

naics = "561730"
state = "GA"  # optional

payload = json.dumps({
    "filters": {
        "award_type_codes": ["A","B","C","D"],
        "naics_codes": [naics],
        "place_of_performance_locations": [{"country": "USA", "state": state}]
    },
    "fields": ["Award ID","Recipient Name","Award Amount","Description","Awarding Agency","Start Date","End Date"],
    "page": 1, "limit": 10,
    "sort": "Award Amount", "order": "desc",
    "subawards": False
}).encode()

ctx = ssl.create_default_context()
req = urllib.request.Request(
    "https://api.usaspending.gov/api/v2/search/spending_by_award/",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST"
)
with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
    data = json.loads(r.read())

awards = data.get("results", [])
amounts = sorted(a.get("Award Amount",0) for a in awards if a.get("Award Amount",0) > 0)
if amounts:
    ceiling = amounts[-1]
    median = amounts[len(amounts)//2]
    rec_low, rec_high = ceiling * 0.75, ceiling * 0.85
    print(f"Ceiling: ${ceiling:,.0f} | Median: ${median:,.0f}")
    print(f"Recommended bid: ${rec_low:,.0f} – ${rec_high:,.0f}")
    for a in awards[:5]:
        print(f"  {a.get('Recipient Name','?')[:40]} — ${a.get('Award Amount',0):,.0f}")
PYEOF
```

**Use this to:** Set `past_price_ceiling`, validate sub quote + our bid are competitive, confirm margin.

---

## Feature 5 — Proposal generation (Claude inline)

When Brian has a sub quote and is ready to submit, generate the full proposal package.

**Inputs needed:**
- Opportunity data (title, agency, NAICS, state, deadline, notice ID, SAM link, description)
- `sub_quote` — what the sub quoted
- `our_bid` — sub_quote × 1.15–1.20 (15–20% margin is standard)
- `past_price_ceiling` — from USASpending (if available)
- `sub_name` — confirmed subcontractor

**Generate four sections inline:**

### PROPOSAL
Executive summary (2–3 sentences), technical approach, price table, subcontractor info, capability statement (generic), POC: Brian Norton brian@olivetreeinv.io.

### SUB OUTREACH SCRIPT
60-second phone script: contract name, location, what the work is, net-30 payment, quote deadline (bid deadline minus 5 days). Natural tone, not robotic.

### SUB EMAIL TEMPLATE
Under 150 words. Subject + body. Sign off: -Brian, brian@olivetreeinv.io

### PRICING RATIONALE
3–4 bullets: why this bid price is right given sub quote, past ceiling, and margin target.

**After generating**, update the Bids sheet row: status → `quoted`, columns K/L/M with quote/bid/profit.

---

## Execution flow

### Step 1 — Auth + read pipeline + load cache (all at once)
1. Get GWS token (Python SSL-bypass method → save to `/tmp/gws_token.txt`)
2. Read `Bids!A1:P100` from Google Sheets → parse rows 2+, compute days left
3. Load Drive cache (Feature 0) → read all `bids/*.json` files
4. For each bid in Sheets: if notice_id is in Drive cache, use cached data for scope/POC/requirements. If not in cache, fetch from SAM.gov and write to cache.
5. Flag any bids where `pws_text` is "Pending" — SAM.gov quota may be needed to fill them.

### Step 2 — Triage each bid by status (column H)

#### `researching`
- Under 7 days → 🔴 URGENT
- No sub in column I → trigger **Sub Outreach Flow** (see below)
- Has sub → remind to get quote

#### `sub_contacted`
- Ask: *"Did you get a quote back?"*
- Yes → record in col K, calculate our_bid (×1.15–1.20), update cols L+M, run **pricing research**, update status to `quoted`
- No → draft follow-up call/email

#### `quoted`
- Surface: our_bid, sub_quote, gross_profit, deadline
- Offer to generate full proposal (Feature 5)
- After confirmed → update status to `submitted`

#### `submitted`
- Show days since submission
- Remind: *"Check SAM.gov for award notice — typically 2–4 weeks on RFQs."*
- Deadline passed with no notice → suggest updating to `lost`

#### `won`
- Sub agreement must be signed before work begins
- Invoice after work milestone — government pays net 30

#### `lost` / `skipped`
- Surface briefly. Ask if there's a lesson to note in column O.

---

## Sub Outreach Flow

Triggered when status = `researching` and Sub Name (col I) is empty.

### Step A — Find subcontractors
WebSearch: `[trade] contractors [city, state]`

Look for: small business (3–15 employees), 4+ star reviews, active website, phone number listed.
Surface 3–5 candidates with name, phone, website.

Add candidates to the `Sub Outreach` tab in the sheet.

### Step B — Draft phone script
```
Hey [Name], my name's Brian Norton with Olive Tree Investments.

I've got a federal government contract opportunity in [city] for [service — plain English].
The government pays net 30 after the work is completed.

I need a quote by [deadline minus 5 days] to submit the bid.

Are you interested and could you get me a price for [scope in one sentence]?

Best email is brian@olivetreeinv.io.
```

### Step C — Draft follow-up email
```
Subject: Federal Contract Opportunity — [Service] in [City]

Hey [Name],

Tried calling — leaving a note here too.

I have a federal contract opportunity in [city] for [service]. Government pays net 30 after completion.

Need a quote by [deadline minus 5 days]. Scope: [1 sentence].

Reply here or call me — brian@olivetreeinv.io

-Brian
```

### Step D — Save scripts to sheet
Append to `Sub Outreach` tab below the candidate rows, labeled clearly (bid name, phone script, email subject, email body, quote due date, SAM link).

### Step E — Update pipeline
After Brian confirms contact, update Bids row: status → `sub_contacted`, col I → sub name, col J → contact, col O → `Called/Emailed [date]`.

---

## New bid discovery flow

When Brian wants fresh opportunities:

1. Query SAM.gov directly (Feature 2) for each target NAICS
2. Filter: Total Small Business set-aside only, deadline ≥ 5 days out
3. Score and surface top 5 (ranked by: days left ascending, Southeast location preferred)
4. For each candidate: show title, trade, location, deadline, set-aside, SAM link
5. Ask Brian which to add → append to Bids sheet

---

## Output format

```
# GovCon Pipeline — {date}

## Summary
{X} active bids · {X} need action today

## Action Items (ranked by urgency)

### 🔴 URGENT — [Title] · {X} days left · [City, State]
Status: researching | Set-aside: Total Small Business
Next: [specific action]
[drafted outreach if applicable]

### 🟡 THIS WEEK — [Title] · {X} days left · [State]
Status: sub_contacted · Sub: [name]
Next: Follow up with [name] for quote

### 🟢 TRACKING — [Title]
Status: submitted
Next: Monitor SAM.gov for award notice

---
Sheet: https://docs.google.com/spreadsheets/d/1y7eQTpmY6V5O22f_bgZUjFNgkWuOcoZbGPGWMz5ECGw
```

Always print the sheet link at the bottom.

---

## Critical rules

1. **Never fabricate bid data.** Read from the sheet. If unreachable, say so.
2. **Always show deadlines.** The #1 reason bids are lost is missing the deadline.
3. **One action per bid.** One clear next step, then ask if Brian wants to act on it now.
4. **Draft on request.** "Help me contact subs" → draft script and email immediately.
5. **Write everything back to the sheet.** Every action taken gets recorded.
6. **Flag urgency clearly.** Under 7 days = 🔴. 7–14 days = 🟡. 14+ days = 🟢.
7. **SAM.gov link on every bid.** Always visible in output.
8. **No localhost.** Never start or call the local govcon app. All features are replicated here.
