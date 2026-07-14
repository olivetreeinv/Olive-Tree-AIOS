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
| `templates/loi-fields.json` | LOI fields, defaults, formulas, Doc token map (source of truth) |
| `templates/loi-template.md` | LOI in-chat preview body |

---

## Execution

### Phase 0: Session Kickoff

**Deal-doc intake scan (silent):**
```bash
python3 scripts/deal_intake.py
```
If it lists new doc-drop folders in ~/Downloads, surface them as workup
candidates alongside the pipeline results. After a workup starts, run
`python3 scripts/deal_intake.py --ack`.

**Sync Fathom meetings first (silent):**
```bash
cd "/Users/olivetree/Documents/Olive AIOS" && source .env && python3 scripts/fathom_sync.py --days 7
```
Run before anything else. Logs the last 7 days of meetings to the Meetings sheet and `wiki/meetings/` so call notes are current before pipeline review. If it errors, skip silently.

**First-run check (2026-05-29 build — remove after first confirmed run):**
Three new automations shipped. Before running the pipeline, surface this prompt:

```
⚙️ 3 new automations are live — first run since build on 2026-05-29.

Validate each during this session:
  1. Availability checks — deal_search.py should filter unavailable listings automatically
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

**Scope prompt — map calendar to phases first:**

If the daily brief was run (or calendar was already pulled), map today's scheduled blocks to pipeline phases and lead with a suggestion:

| Calendar block | Suggested phase |
|---|---|
| "Deal Sourcing" | Phases 1–3 (new listings + broker discovery + follow-ups) |
| "Underwrite / Deep Work" | Phases 4–5 (inbound emails + deal analysis) |
| "Shortlist + Strategy" | Phases 5–6 (deal analysis + LOI) |
| All three blocks (full deal day) | Full pipeline |
| No relevant blocks | Show generic menu |

Format:
```
Based on your calendar today — [block name] at [time] — I'd suggest:

  → [Phase X: description]

Run that, or pick something else?

  1. Full pipeline — all phases (~20 min)
  2. New listings + broker discovery + follow-ups (Phases 1–3)
  3. Inbound emails + deal analysis only (Phases 4–5)
  4. Draft an LOI — tell me the deal name
```

Proceed to selected phases only.

---

### Parallel Data Gather (Phases 1, 2, 4)

After Brian selects a scope that includes any of Phases 1, 2, or 4, launch them as concurrent sub-agents before presenting any results. Do not run them sequentially.

**Spawn simultaneously:**
- **Agent A** — `python3 scripts/deal_search.py --days 7` + `python3 scripts/crexi_live.py --state GA --deals` + `python3 scripts/broker_sites.py` then extract/screen the fetched pages (Phase 1: new listings — email alerts + full live Crexi buy-box screen + off-market broker-site sweep per /deal-search SKILL.md)
- **Agent B** — `python3 scripts/crexi_live.py --state GA` (Phase 2: broker discovery — live Crexi, add states as polygons are captured; `scripts/broker_search.py` for email-alert fallback). New brokers land with blank contact fields — enrich via background agents per /broker-search Step 6 before outreach.
- **Agent C** — `python3 scripts/deal_inbox.py --days 7` + `python3 scripts/broker_replies.py --days 7` (Phase 4: inbound deal emails + replies from known brokers — deal emails to run, contact updates, replies needing Brian)

Wait for all three to complete. Then run Phase 3 (broker follow-ups) using Agent B's new-broker output. If broker_replies reported contact updates, apply with `broker_replies.py --apply`; if it flagged DEAL emails, offer `/deal-analysis` on each.

Merge all results and present in the Phase 1 → 2 → 3 → 4 order below. Brian sees one unified view, not three separate outputs.

If Brian's scope excludes a phase (e.g., "inbound emails only"), skip that agent — don't spawn what won't be used.

---

### Phase 1: Scan for New Listings

*(Results from Agent A — already run in parallel above)*

After the scan, present a summary:

```
📋 New Listings — Week of [date]

✅ IN BUY BOX ([n] found):
1. [Property Name] — [n] units | [zip], [market] | $[price/unit]/unit
   [Platform] | Broker: [name] <[email]>
2. ...

🔶 NEAR BUY BOX ([n] found — unit count 10–65, off the 15–50 target):
1. [Property Name] — [n] units | [zip], [market] | $[price/unit]/unit
   [Platform] | Broker: [name] <[email]>
2. ...

⚠️ OUTSIDE BUY BOX ([n] flagged):
- [Property Name] — [zip] not in active markets

All logged to Deal Sourcing tab (Near matches as `Near — Review`, not `Pass`).

Any of these worth a closer look? (list numbers, or 'none')
```

Near-buy-box listings are worth underwriting even when Brian won't pursue them — the point is the broker relationship (they may bring the next listing that's a real fit) and the practice of pricing outside a clean 15–50 unit deal. Offer to run `/deal-analysis` on any Near pick same as an in-box one.

If Brian identifies a deal → jump to Phase 5 for that deal.
If none → continue to Phase 2.

---

### Phase 2: Discover New Brokers

*(Results from Agent B — already run in parallel above)*

No buy-box filter — any broker with 2+ MF listings on any platform qualifies. The goal is network width, not deal fit.

Present a summary:

```
🔍 New Brokers — [date]

NEW BROKERS ADDED ([n]):
1. [Name] — [Brokerage] | [n] listings on [Platform(s)] | [markets]
2. ...

ALREADY IN LIST ([n] matched, skipped)

SINGLE-LISTING BROKERS ([n] — not yet qualifying):
- [Name] — 1 listing on [Platform] in [zip/market]

New brokers added to Brokers List as Tier B. Ready to queue outreach? (y/n)
```

If yes → draft outreach using the broker call script from `/broker-search` SKILL.md.
Then continue to Phase 3.

---

### Phase 3: Broker Follow-Ups

Pull the Brokers List from the Deal Sourcing spreadsheet (`1VxOlof56s8GosrWkSctL-FMm7AoJKJ6YtM3GllMKVH4`, Brokers List tab). New brokers added in Phase 2 will appear here — prioritize outreach to them first.

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

On approval — always sandbox first, then production:
1. **Dry run:** `python3 scripts/broker_followup.py --send-all --dry-run [--exclude ROWS]` — shows every draft, no emails sent, no sheet updates. Present output to Brian.
2. **Production:** `python3 scripts/broker_followup.py --send-all [--exclude ROWS]` — only after Brian confirms dry run looks clean.
3. Script updates Brokers List automatically: `Last Contact` → today, `Next Follow-Up` → +7 days, `# Deals Sent` += 1.
4. Brokers with no email address are skipped automatically with a warning.

**No auto-dormant.** Attempt count is tracked but brokers are never moved to Dormant automatically — Brian sets that manually by editing Status in the sheet.

**Pre-market access push.** For Tier-B / new brokers, prioritize a **3-property tour ask per target metro** over generic check-ins — the tour earns pre-market flow. Draft:

```
[First name], planning a trip to [metro] [month] — could we walk a few of your
listings? We're 10–30 units, $50–150K/door. Mostly I want to learn your inventory
and get on your pre-market/pocket-listing list so we can move fast when the right
one comes up.

-Brian
```
Track **"Pre-market list: Y/N"** as a broker field; brokers who share pre-market move to **Tier A**.

---

### Phase 4: Scan Inbound Deal Emails

*(Results from Agent C — already run in parallel above)*

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

For each deal Brian says to analyze → proceed to Phase 5.

---

### Phase 5: Deal Analysis

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

On `PURSUE LOI` → move directly to Phase 6.
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

### Phase 6: LOI Drafting

Triggered by:
- `/deal-analysis` returning `PURSUE LOI`, OR
- Brian saying "draft LOI for [property name]"

> Fields, defaults, and formulas: `templates/loi-fields.json`. Preview body: `templates/loi-template.md`. Generation: `python3 scripts/loi.py`.

**Before finalizing the LOI, prompt Brian to call the broker first:**
> "Call broker before sending? Confirm: how many offers are in, where is pricing
> trending, are we in range?" Capture the answer and adjust price/terms before drafting.
> Submitting blind on price loses winnable deals — a 2-minute call calibrates the offer.

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

### Phase 7: Session Summary

After all phases are complete:

```
✅ Session Complete — [date]

LISTINGS:    [n] new found | [n] in buy box
NEW BROKERS: [n] added to Brokers List
FOLLOW-UPS:  [n] drafted | [n] sent
INBOUND:     [n] reviewed | [n] analyzed | [n] doc requests sent
ANALYSIS:    [n] PURSUE | [n] MORE INFO | [n] PASS
LOIs:        [n] drafted | [n] sent

---
Outstanding:
- [Any pending approvals or doc requests not yet actioned]

Next run: Monday [date] — `python3 scripts/deal_search.py --days 7` then `python3 scripts/broker_search.py`

Log any decisions from this session? (y/n)
```

---

## Sub-skills and scripts called

| Phase | Script / Skill |
|---|---|
| Phase 1 | `/deal-search` → `scripts/deal_search.py` + `scripts/crexi_live.py --deals` |
| Phase 2 | `/broker-search` → `scripts/crexi_live.py` (live) / `scripts/broker_search.py` (email alerts) |
| Phase 3 | `scripts/broker_followup.py` |
| Phase 4 | `scripts/deal_inbox.py` + `scripts/broker_replies.py` |
| Phase 5 | `/deal-analysis` → `scripts/deal_analysis.py` |
| Phase 6 | LOI draft using `/loi` → `scripts/loi.py` |

All scripts are built and operational.

---

## Rules

- **Draft only.** Every email shown to Brian before sending. No exceptions.
- **Buy box first.** Check zip against `references/buy-box.md` before spending time on any deal.
- **Link formatting.** Never include bare URLs in email drafts. Always use markdown hyperlinks with the property address as the label: `[123 Main St, Smyrna GA](url)`. This renders cleanly in chat and converts to an HTML anchor in the sent email.
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
