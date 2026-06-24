# Broker Search Skill — Olive Tree Investments
**Trigger:** `/broker-search`, "find new brokers", "scan for brokers", "broker discovery", "who has listings on crexi", "run broker search"

---

## What this skill does

Scans Crexi, LoopNet, and FMLS for commercial brokers who have **2 or more active multifamily listings**, then cross-references against the existing Brokers List in Google Drive. Qualifying brokers not already in the sheet are added automatically.

This skill is **not buy-box filtered.** Any broker with 2+ MF listings on any of the three platforms qualifies — regardless of zip code or unit count. The goal is to build the broadest possible broker network, especially for markets where active listings are thin.

**Pipeline:**
Crexi API + LoopNet platform + FMLS API → aggregate listings by broker → filter 2+ listings → cross-ref Google Drive Brokers List → add qualifying new brokers

---

## Why broker count — not buy box

~60–80% of multifamily trades pre-market and never hits a portal. The on-market listing is the entry point to the **broker** who controls that pocket of inventory. A broker with 3 listings in Charlotte today may have pocket deals in Huntsville next month. Cast wide — qualify the broker, not the listing.

Every new broker added = potential access to pre-market flow that never shows up in a deal search.

---

## Broker add rules

A broker is added **only if both conditions are true:**

1. **2 or more active MF listings** found across Crexi, LoopNet, or FMLS in the current scan
2. **Not already in the Brokers List** — checked by email address first, then by full name

Brokers with only 1 listing are tracked in the scan output but not added. They'll qualify if they accumulate a second listing.

New brokers are added with:
- **Tier = B** (relationship not yet established)
- **Buy Box Sent = No**
- **Status = "New — Found via Platform Scan"**
- **Pre-market list = No** + follow-up flag: "Request pre-market list"

---

## Running the script

```bash
# Standard run — live API calls to all three platforms
python3 scripts/broker_search.py

# Test run — prints qualifying brokers without writing to sheet
python3 scripts/broker_search.py --dry-run

# Specific platform only
python3 scripts/broker_search.py --source crexi
python3 scripts/broker_search.py --source loopnet
python3 scripts/broker_search.py --source fmls
```

---

## Platform sources

### Crexi
Queries the Crexi API for all active multifamily listings (`PropertyType=Multifamily`, `Status=Active`). Groups results by broker email. Requires `CREXI_API_KEY` in `.env`.

### LoopNet
Queries LoopNet's listing search for active multifamily properties. Groups results by agent/broker. Requires `LOOPNET_API_KEY` in `.env` (or uses scraper fallback if key not set — slower, rate-limited).

### FMLS
Queries the FMLS Data API for active multifamily listings in Georgia. Groups results by listing agent. Requires `FMLS_API_KEY` in `.env`. If not set, FMLS source is skipped with a warning.

---

## Google Drive cross-reference

The script reads the Brokers List from the Deal Sourcing spreadsheet in Google Drive:

```
Spreadsheet ID: 1VxOlof56s8GosrWkSctL-FMm7AoJKJ6YtM3GllMKVH4
Tab: Brokers List
```

Deduplication logic:
1. Match by email address (primary)
2. Match by full name (secondary — catches brokers who list with different emails)

Brokers already in the sheet are skipped entirely — no updates, no overwrites.

---

## What gets logged

### Brokers List tab (Google Drive)
Only brokers meeting the 2-listing threshold who aren't already in the sheet.

Columns populated automatically:
`Brokerage` | `Broker Name` | `Email` | `Phone` | `Markets/Zips` | `Specialty` | `Tier` | `Buy Box Sent` | `# Deals Sent` | `Last Contact` | `Status` | `Notes`

### Scan summary (printed, not logged)
```
🔍 Broker Scan — [date]

NEW BROKERS FOUND ([n]):
1. [Name] — [Brokerage] | [n] listings on [Platform(s)] | [markets]
2. ...

ALREADY IN LIST ([n] matched, skipped):
- [Name] — matched by [email/name]

SINGLE-LISTING BROKERS ([n] — not yet qualifying):
- [Name] — 1 listing on [Platform] in [zip/market]
```

---

## Broker call script (paste into outreach — never auto-sends)

```
"Hi [name] — I came across your listing at [address], [n]-unit building.
We're buyers, 10–30 units, $50–150K/door in [metro].
Two quick asks: (1) anything coming pre-market? (2) who do you use locally
for lending, property management, and insurance?"
Close with: "Setting a tour trip [month] — can we walk it?"
```

Rules: state the buy box (units, price, vintage) every call; always ask for
(a) pre-market flow and (b) lender/PM/insurance referrals; the tour is for the
**relationship**, not the listed deal (most are overpriced).

**Qualifying scripts — be ready to answer fast:**
- Property type: value-add multifamily, 15–50 units
- Markets: [current active buy box markets from references/buy-box.md]
- Price range: up to ~$150K/door depending on market; deal-by-deal
- Equity readiness: "We can move 24–48h after receiving the full package"

**Questions to ask the broker:**
- Who are the main employers in the area?
- What's the market cap rate for this asset class and vintage?
- What's the as-is and post-reno price/door?
- Any path-of-progress infrastructure nearby?
- What's the whisper price — seller's real number?
- What terms matter most to the seller (price, close speed, lease-back)?

**Resume rule:** Always attach Brian's resume on 20+ unit approaches. Brokers vet buyers hard above 20 units — a resume signals credibility before a single number is shared.

**Link formatting rule:** When referencing a property listing URL in any email draft, never include a bare URL. Always format as a markdown hyperlink using the property address as the label:
`[123 Main St, Smyrna GA](https://www.crexi.com/properties/...)`
This renders as a clean clickable link in the chat preview and converts to an `<a>` tag in the sent HTML email.

---

## On-to-Off outreach playbook

~60–80% of MF trades never hit a portal. The on-market listing is bait to reach the broker who controls the pocket. Run this after each scan for qualifying new brokers — all outreach is **draft only; Brian approves before anything sends**:

1. Pick 2–3 of the broker's active listings in or near the buy box — even overpriced ones. The deal isn't the point; the broker is.
2. Outreach: ask escrow/offer status, then book an in-person tour. State the buy box (units, price/door, markets) clearly.
3. Tour belly-to-belly. Hand a business card, look and act the part. Log contact in the Brokers List; bump Tier if the broker has real deal flow.
4. Follow-up: "Totally understand the gap on price — we're active buyers in this market. Any deals on or off market coming up that fit [buy box]?" → ask directly for the pre-market list.
5. Set **Pre-market list = "Requested"** in the Brokers List + 2-week ping cadence in notes.

Favor mom-and-pop brokers on sub-20-unit assets — you reach the decision-maker directly.

**Also:** Subscribe directly to local and regional brokerage marketing email lists and websites. Their deal blasts reveal on- and off-market inventory before or without portal posting.

---

## Suggested cadence

Run **every Monday morning** as part of `/lets-get-to-work`, after deal-search. Platform listings update daily — weekly scans catch new brokers before competitors reach out.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Crexi API error" | Check `CREXI_API_KEY` in `.env` |
| "LoopNet scraper rate-limited" | Add `LOOPNET_API_KEY` to `.env` for API access |
| "FMLS source skipped" | Set `FMLS_API_KEY` in `.env` |
| Broker not being added | Check they have 2+ listings in the scan — run `--dry-run` to verify count |
| Duplicate broker getting through | Name format mismatch — check the email column on the existing row |
| Auth error | Run `gws auth login -s sheets` then retry |

---

Reference: `references/google-workspace-api.md` for Sheets API details.
