# Capital Raise Skill — Olive Tree Investments
**Trigger:** `/capital-raise`, "raise capital", "investor outreach", "soft commitments", "who do I call for this deal"

> **STATUS: DRAFT / SCOPED 2026-06-09.** Scaffolded from Justin Brennan mentorship mining
> (videos: u_tBhtH5JhM, Qr3f3NDdPF4, YlPdtLkshAg, GC31FAVq0R4, Fb4en-eg04w). Needs Brian's
> review + scripts before it's a live skill. Nothing here sends without approval.

---

## What this skill does

Runs Olive Tree's LP capital raise for a specific deal — from soft-commit pipeline to
funded equity. Drafts investor outreach in Brian's voice, tracks commitments against the
raise target, and surfaces who to call next. Built around the Q3 goal: **$400K+ in soft LP
commitments**.

## Why it exists (the mentorship lesson)

- **Build the investor base BEFORE the deal.** Have 25–30 soft-committed investors lined up
  *before* you're under LOI — capital readiness is what lets you move fast and win deals.
- **Raise is deal-first.** Investors commit to a specific opportunity with real numbers, not
  to a blind fund. The pitch deck and the deal drive the conversation.
- **506(b) = pre-existing relationships, no general solicitation.** Outreach goes to people
  Brian already knows. Relationship-building (dinners, calls, 1:1s) is the engine — not ads.

## Fund terms (from CLAUDE.md — confirm per deal)

- Minimum: **$25K** · accredited + non-accredited (506(b))
- Structure: **6% pref, then 70/30 LP/GP** split
- Targets: **18.21% annual ROI, 2.09x equity multiple, 4–6 yr hold**
- Investor types: Individuals, HNW, Family Offices, Institutions (pref equity)

## Execution (proposed)

### Step 1: Set the raise target
From the deal's equity requirement (deal-analysis output) → total LP equity needed,
min check size, # of investors to fill it. Output the gap vs. current soft commitments.

### Step 2: Pull the investor pipeline
Source of truth = **GoHighLevel CRM** (not yet connected — see connections.md). Until
connected, maintain a soft-commit list. Segment by: committed / verbal / warm / cold,
and by check-size band.

### Step 3: Draft deal-first outreach (never auto-sends)
Per investor segment, draft in Brian's voice: 1-line hook + the 3 headline numbers
(pref, target IRR, equity multiple) + the ask (soft commit + amount). Attach the deal
pitch deck (`/pitch-deck`).

### Step 4: Track commitments to target
Log each response as soft-commit $ amount. Show running total vs. raise target and vs.
the Q3 $400K goal. Flag when the deal is oversubscribed or short.

### Step 5: Tax/returns hook (optional, for the right investor)
Cost-seg + bonus depreciation as the close: a Year-1 paper loss of ~$0.95–$1.20 per $1
invested. Order the cost-seg study in the first 30 days post-close (3rd-party, after reno
on value-add for a bigger basis); hold 5 years to minimize recapture.

## Connections needed
- **GoHighLevel** (CRM / investor pipeline) — not yet connected
- `/pitch-deck` (Canva) — connected
- Email (drafts only, Brian approves) — connected

## To build before this goes live
- [ ] `scripts/capital_pipeline.py` — read/segment investor CRM, track soft commits vs target
- [ ] Soft-commit tracking sheet or GHL pipeline fields
- [ ] Confirm fund terms + 506(b) compliance language with Brian
