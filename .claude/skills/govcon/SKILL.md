---
name: govcon
description: Government contracting pipeline coach for Brian Norton. Checks bid status, surfaces next actions, helps find and contact subcontractors, and guides each bid from discovery to submission. Trigger on "govcon", "check my bids", "where am I on govcon", "next steps on bids", "help me contact subs", "govcon pipeline", or "what do I do next on govcon".
---

## What this skill does

Pulls the live bid pipeline from the Olive Tree GovCon app, figures out where each bid is stuck, and tells Brian exactly what to do next — including drafting subcontractor outreach on the spot.

**One run = one clear action list + any outreach drafted and ready to send.**

---

## App connection

The GovCon app runs locally at `http://localhost:8000`. All data lives there.

**Check if it's running before anything else:**
```bash
curl -s http://localhost:8000/api/bids > /dev/null 2>&1 && echo "up" || echo "down"
```

If down: tell Brian to run this in the govcon project directory:
```bash
cd "/Users/olivetree/Documents/Olive AIOS/olive-tree-govcon" && .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## API calls

```bash
# Full pipeline + summary
curl -s "http://localhost:8000/api/bids"

# Filter by status
curl -s "http://localhost:8000/api/bids?status=researching"
curl -s "http://localhost:8000/api/bids?status=sub_contacted"
curl -s "http://localhost:8000/api/bids?status=quoted"

# Update a bid's status
curl -s -X PATCH "http://localhost:8000/api/bids/{notice_id}" \
  -H "Content-Type: application/json" \
  -d '{"status": "sub_contacted", "notes": "Called Smith Landscaping 2026-06-01"}'

# Get top opportunities (for new bid discovery)
curl -s "http://localhost:8000/api/opportunities?state=SOUTHEAST&days_back=30&limit=50&analyze=false"
```

---

## Execution

### Step 1 — Check if app is running
If down, prompt Brian to start it and wait.

### Step 2 — Pull the full pipeline
```bash
curl -s "http://localhost:8000/api/bids"
```

Parse: `bids[]`, `summary.total`, `summary.hit_rate`.

### Step 3 — Triage by status

For each bid, apply this decision tree:

#### `researching`
**Next action:** Analyze the docs + research pricing, then find a sub.
- Check `deadline` — if under 7 days, flag as **URGENT**
- Check `resourceLinks` — if docs exist, remind to click Analyze in the app
- Ask: *"Have you found any subs for this one yet?"*
- If no → go to **Sub Outreach Flow** below

#### `sub_contacted`
**Next action:** Follow up for a quote or enter it if received.
- Ask: *"Did you get a quote back from the sub?"*
- If yes → prompt Brian to open the app, click Proposal, enter the quote
- If no → draft a follow-up message (call or email)

#### `quoted`
**Next action:** Review the proposal and submit on SAM.gov.
- Surface: our_bid, sub_quote, gross_profit, deadline
- Remind: *"Your proposal is generated. Go to SAM.gov and submit before [deadline]."*
- Provide the SAM.gov link from `sam_link`
- Ask: *"Do you want me to review the proposal text before you submit?"*
- After confirmed submitted → prompt to update status to `submitted`

#### `submitted`
**Next action:** Wait. Monitor SAM.gov for award notice.
- Show days since submission
- Remind: *"Check SAM.gov for an award notice. They typically notify within 2–4 weeks on RFQs."*
- If deadline passed with no notice → may have lost; suggest updating to `lost`

#### `won`
**Next action:** Sign subcontractor agreement, schedule kickoff.
- Congratulate
- Remind: subcontractor agreement must be signed before work begins
- Remind: submit first invoice after work milestone is hit; government pays net 30

#### `lost` / `skipped`
Surface briefly. Ask if there's a lesson to note.

---

## Sub Outreach Flow

Triggered when a bid is in `researching` status and no sub has been contacted yet.

### What you need:
- Bid title and scope (from the pipeline data)
- Place of performance state + city if available
- Deadline (to set a quote-by date = deadline minus 5 days)

### Step A — Find subcontractors

Search for businesses that do this work in the contract's location:

```
[service type] contractors [city, state]
[NAICS description] companies near [city]
```

Use WebSearch. Look for:
- Small businesses (3–15 employees)
- 4+ star Google reviews
- Active website
- Phone number listed

Surface 3–5 candidates with name, phone, and website.

### Step B — Draft the phone script

Pull `sub_outreach_script` from the proposal if it exists (from `proposal_text` field or by calling `/api/opportunity/{notice_id}/proposal`). If not yet generated, write one:

```
Hey [Name], my name's Brian Norton with Olive Tree Investments.

I've got a federal government contract opportunity in [city] for [service — plain English description].
The government pays net 30 after the work is completed.

I need a quote by [deadline minus 5 days] to submit the bid.

Are you interested and could you get me a price for [scope in one sentence]?

Best number to send it to is brian@olivetreeinv.io.
```

Short. Natural. Not robotic.

### Step C — Draft the follow-up email

```
Subject: Federal Contract Opportunity — [Service] in [City]

Hey [Name],

I tried calling — leaving a note here too.

I have a federal contract opportunity in [city] for [service]. Government pays net 30 after completion.

I need a quote by [deadline minus 5 days] to submit. Scope: [1 sentence].

Reply here or call me: [Brian's number if known, otherwise email]

-Brian
brian@olivetreeinv.io
```

### Step D — Update the pipeline

After Brian confirms he contacted a sub:
```bash
curl -s -X PATCH "http://localhost:8000/api/bids/{notice_id}" \
  -H "Content-Type: application/json" \
  -d '{"status": "sub_contacted", "sub_name": "[name]", "notes": "Contacted [date]"}'
```

---

## Output format

```
# GovCon Pipeline — {date}

## Summary
{X} active bids · {X} need action · Hit rate: {X}%

## Action Items  (ranked by urgency)

### 🔴 URGENT — [Bid Title] · {X} days left
Status: researching
Next: [specific action]
[drafted outreach or prompt if needed]

### 🟡 THIS WEEK — [Bid Title] · {X} days left
Status: sub_contacted
Next: Follow up with [sub name] for quote

### 🟢 ON TRACK — [Bid Title]
Status: submitted
Next: Monitor SAM.gov for award notice

---
## No Active Bids?
If pipeline is empty, prompt:
"Want me to pull the Top 20 scored opportunities from the app so you can pick your first bid to track?"
Then call the opportunities API and score + surface the top 5.
```

---

## Critical rules

1. **Never fabricate bid data.** If the app is down or returns nothing, say so.
2. **Always show deadlines.** The #1 reason bids are lost is missing the deadline.
3. **One action per bid.** Don't overwhelm — one clear next step, then ask if Brian wants to act on it now.
4. **Draft on request.** If Brian says "help me contact subs" — draft the script and email immediately, don't just describe what to do.
5. **Update the pipeline.** After any action is taken, offer to update the bid status via the API.
6. **Flag urgency clearly.** Under 7 days = 🔴. 7–14 days = 🟡. 14+ days = 🟢.
