# Let's Get to Work — Olive Tree Investments
**Trigger:** `/lets-get-to-work`, "lets get to work", "run the pipeline", "deal sourcing session", "monday run"

---

## What this skill does

Runs Brian's full multifamily acquisition pipeline in one guided session. Acts as the orchestrator — calling sub-skills at each phase and pausing for Brian's approval before any outbound action.

**Nothing sends without approval. Every email, follow-up, and LOI is a draft shown first.**

**Pipeline:**
New listings → Broker follow-ups → Inbound deal emails → Document requests → Deal analysis → LOI draft

**Cadence:** Run every morning. Standard scan covers the prior 7 days. Includes optional `/daily-brief` integration at kickoff.

---

## References (read before every run)

| File | Why |
|---|---|
| `references/buy-box.md` | Active markets — filter every deal before spending time on it |
| `references/knowledge-base-metrics.md` | Deal thresholds, Stage 4 weekly cadence |
| `references/knowledge-base-process.md` | 10-stage pipeline (on-demand for stage-specific work) |
| `references/voice.md` | Brian's tone — all drafted emails must match this |
| `references/google-workspace-api.md` | Gmail + Sheets API |
| `references/loi-template.md` | LOI defaults + field guide (quick reference) |
| `templates/loi-template.md` | Full LOI legal text — read this when drafting |

---

## Execution

### Phase 0: Session Kickoff

**First-run check (2026-05-29 build — remove after first confirmed run):**
Three new automations shipped. Before running the pipeline, surface this prompt:

```
⚙️ 3 new automations are live — first run since build on 2026-05-29.

Validate each during this session:
  1. Availability checks — broker_search.py should filter unavailable listings automatically
  2. Email personalization — broker_followup.py drafts should match Tier (A/B/C) without manual edits
  3. Doc requests — deal_inbox.py --doc-request [n] should generate a ready-to-send draft

Confirm each worked at the end of this session. If any fail, report back and I'll fix.
```

Then open the session:

```
🚀 Let's Get to Work — [Day, Date]

Run daily brief first? (y/n)
```

**If yes:** Execute the daily brief inline — pull today's calendar, scan Gmail (last 24h), show Q3 pulse, surface the #1 action. Follow the output format from `/daily-brief` SKILL.md. Then flow directly into the scope prompt below without asking again.

**If no (or any pipeline selection):** Skip straight to scope.

```
What's the focus today?

  1. Full pipeline — all phases (~15 min)
  2. New listings + follow-ups only (Phases 1–2)
  3. Inbound emails + deal analysis only (Phases 3–4)
  4. Draft an LOI — tell me the deal name

Reply with a number, or describe what you need.
```

Proceed to selected phases only.

---

### Phase 1: Scan for New Listings

Run the broker-search script to pull new listings from Gmail alerts (Crexi + LoopNet):

```bash
python3 scripts/broker_search.py --days 7
```

After the scan, present a summary:

```
📋 New Listings — Week of [date]

✅ IN BUY BOX ([n] found):
1. [Property Name] — [n] units | [zip], [market] | $[price/unit]/unit
   [Platform] | Broker: [name] <[email]>
2. ...

⚠️ OUTSIDE BUY BOX ([n] flagged):
- [Property Name] — [zip] not in active markets

All logged to Deal Sourcing tab.

Any of these worth a closer look? (list numbers, or 'none')
```

If Brian identifies a deal → jump to Phase 4 for that deal.
If none → continue to Phase 2.

---

### Phase 2: Broker Follow-Ups

Pull the Brokers List from the Deal Sourcing spreadsheet (`1VxOlof56s8GosrWkSctL-FMm7AoJKJ6YtM3GllMKVH4`, Brokers List tab).

Flag brokers where:
- `Next Follow-Up` ≤ today's date, AND
- `Status` ≠ "Dormant"

```bash
python3 scripts/broker_followup.py --check
```

For each overdue broker, draft a follow-up in Brian's voice:

```
📬 Follow-Up Drafts — [n] brokers overdue

---
1. To: [Broker Name] <[email]>
   Brokerage: [brokerage] | Last contact: [date] | Markets: [zips]

   Subject: Following up — [market] multifamily

   [First name],

   Circling back — we're still actively looking in [zip/market] for
   15–50 unit value-add deals. Any new inventory coming to market or
   off-market opportunities you know of?

   We can move fast with the right deal.

   -Brian

---
2. ...

Approve all / review one-by-one / skip?
(type 'all' / '1' / '2' / 'skip')
```

On approval:
1. Run `python3 scripts/broker_followup.py --send-all` to send all overdue brokers with valid emails in one pass.
2. Script updates Brokers List automatically: `Last Contact` → today, `Next Follow-Up` → +7 days, `# Deals Sent` += 1.
3. Brokers with no email address are skipped automatically with a warning.

**No auto-dormant.** Attempt count is tracked but brokers are never moved to Dormant automatically — Brian sets that manually by editing Status in the sheet.

---

### Phase 3: Scan Inbound Deal Emails

Search Gmail for broker emails that look like deal submissions (last 7 days):

```bash
python3 scripts/deal_inbox.py --days 7
```

Search uses these Gmail queries (run in sequence, deduplicate):
```
newer_than:7d (subject:"offering memorandum" OR subject:"OM" OR subject:"multifamily" OR subject:"for sale" OR subject:"apartment") -from:me
newer_than:7d ("rent roll" OR "T-12" OR "T12" OR "asking price" OR "cap rate") -from:me
```

Cross-reference sender email against Brokers List. Flag:
- Known broker → show broker name + tier
- Unknown sender → flag as "new contact"

Present:

```
📥 Inbound Deal Emails — [n] found

1. From: [Name] <[email]> — [Brokerage or "Unknown"]
   Subject: [subject]
   Date: [date]
   Preview: [first 140 chars]
   Buy box: ✅ [zip] ([market]) / ❌ [zip] not in buy box / ❓ Zip unclear

   → a) Analyze this deal  b) Skip  c) Mark irrelevant
```

For each deal Brian says to analyze → proceed to Phase 4.

---

### Phase 4: Deal Analysis

For each deal flagged from Phase 1 or Phase 3:

**Check what documents are available:**
- OM attached? T-12 attached? Rent Roll attached?
- Any doc linked in the email body (Drive link, Crexi link)?

**Market Rent Check — ask before running analysis:**

```
To pull Rentometer market comps, I need:
  1. Full property address (include zip)
  2. OM asking rent per unit ($/mo)
  3. Bedrooms — dominant unit type (1, 2, 3, or 4)
  4. Baths — optional (1 or 1.5+)
```

Pass these as `--beds`, `--baths`, and `--om-rent` in the call below.
Rentometer runs automatically and sets market GPR from the median comp.

**If documents are available:**

Call `/deal-analysis`:

```bash
python3 scripts/deal_analysis.py --analyze \
  --property "[name]" --asking [price] --units [n] --zip [zip] \
  --beds [n] --om-rent [om_rent_per_unit] [--baths "1|1.5+"] \
  [--drive-id [id]] [--gmail-id [message_id]]
```

Wait for the output. Present the full analysis and recommendation to Brian.

On `PURSUE LOI` → move directly to Phase 5.
On `MORE INFO NEEDED` → show doc-request draft (from deal_analysis output). Brian approves → send via Gmail API.
On `PASS` → log Stage as "Pass" in Deal Sourcing. Offer brief pass note to broker (optional, show draft).

**If documents are missing:**

Run the doc-request script with the deal's index from Phase 3:

```bash
python3 scripts/deal_inbox.py --doc-request [INDEX] --days 7
```

Script generates the draft and prints it. On Brian's approval:

```bash
python3 scripts/deal_inbox.py --doc-request [INDEX] --days 7 --send
```

---

### Phase 5: LOI Drafting

Triggered by:
- `/deal-analysis` returning `PURSUE LOI`, OR
- Brian saying "draft LOI for [property name]"

> Defaults + field guide: `references/loi-template.md`. Full legal text for drafting: `templates/loi-template.md`. Read both — references for defaults, templates for the actual document.

**Gather LOI inputs:**

| Input | Source | Default |
|---|---|---|
| Property name + address | Deal Sourcing log | — |
| Offer price | Deal analysis output | Negotiated from asking |
| Earnest money | Brian confirms | Recommend: 1–2% of offer |
| DD period | Brian confirms | Recommend: 30–45 days |
| Closing timeline | Brian confirms | Recommend: 45–60 days from LOI execution |
| Financing type | Value-add standard | Bridge loan, non-recourse, 3-yr I/O |
| Special terms | Brian confirms | — |

If any are missing, ask before drafting.

**Draft structure (until template is provided):**

```
LETTER OF INTENT — [Property Name]
[Date]

To: [Broker Name], [Brokerage]
Re: [Property Address]

Dear [Broker Name],

Olive Tree Investments ("Buyer") is pleased to submit this non-binding
Letter of Intent for the acquisition of [Property Name], located at
[Address], consisting of [n] units.

PURCHASE PRICE: $[offer price] ($[price/unit]/unit)

EARNEST MONEY: $[amount], deposited within [n] business days of LOI
execution. [Hard/Soft] after [n]-day feasibility period.

DUE DILIGENCE PERIOD: [n] days from execution.

CLOSING: [n] days from LOI execution, subject to financing.

FINANCING: Bridge loan, non-recourse, [LTV]% LTV, interest-only.
Financing contingency: [yes/no].

This LOI is non-binding and subject to execution of a formal Purchase
and Sale Agreement acceptable to both parties.

Brian Norton
CEO, Olive Tree Investments
brian@olivetreeinv.io

---
Review this draft. Options:
  1. Approve — send to [broker name] via Gmail
  2. Edit before sending
  3. Save draft only
```

On approval:
- Send via Gmail API
- Update Deal Sourcing: Stage → "LOI Submitted", Last Updated → today
- Log to `decisions/log.md`: deal name, offer price, rationale, date

---

### Phase 6: Session Summary

After all phases are complete:

```
✅ Session Complete — [date]

LISTINGS:    [n] new found | [n] in buy box
FOLLOW-UPS:  [n] drafted | [n] sent
INBOUND:     [n] reviewed | [n] analyzed | [n] doc requests sent
ANALYSIS:    [n] PURSUE | [n] MORE INFO | [n] PASS
LOIs:        [n] drafted | [n] sent

---
Outstanding:
- [Any pending approvals or doc requests not yet actioned]

Next run: Monday [date] — `python3 scripts/broker_search.py --days 7`

Log any decisions from this session? (y/n)
```

---

## Sub-skills and scripts called

| Phase | Script / Skill |
|---|---|
| Phase 1 | `scripts/broker_search.py` |
| Phase 2 | `scripts/broker_followup.py` |
| Phase 3 | `scripts/deal_inbox.py` |
| Phase 4 | `/deal-analysis` → `scripts/deal_analysis.py` |
| Phase 5 | LOI draft using `references/loi-template.md` |

All scripts are built and operational.

---

## Rules

- **Draft only.** Every email shown to Brian before sending. No exceptions.
- **Buy box first.** Check zip against `references/buy-box.md` before spending time on any deal.
- **Availability check.** Before presenting any listing from a broker email, verify it's still active by fetching the listing URL or searching the broker's platform (marcusmillichap.com, crexi.com, loopnet.com). Flag as "availability unverified" only if site is inaccessible.
- **No auto-dormant.** Track attempts but never move a broker to Dormant automatically — Brian sets that manually.
- **Log everything.** Every deal touched gets logged in Deal Sourcing. Every LOI goes in `decisions/log.md`.
- **Daily cadence.** Run every morning. `--days 7` is standard for listings scan.
- **Scope match.** Only run the phases Brian selects. Don't run the full pipeline when he asks for one thing.

---

## Suggested schedule

```
Every Monday at 8:00 AM:
  /lets-get-to-work → Full pipeline (Phase 1–3 auto, Phases 4–5 on deal-by-deal approval)
```

To configure: run `/schedule` and set the above.
