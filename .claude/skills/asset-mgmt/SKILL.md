# Asset Management Skill — Olive Tree Investments
**Trigger:** `/asset-mgmt`, "manage the property", "ops dashboard", "PM check-in", "investor update on [property]"

> **STATUS: DRAFT / SCOPED 2026-06-09.** Scaffolded from Justin Brennan mentorship mining
> (videos: GDkVIivKJ10, GC31FAVq0R4 + the 10-stage roadmap in wiki/mfs-docs). Needs Brian's
> review + connections before it's a live skill. Kicks in after a deal closes.

---

## What this skill does

Runs post-close asset management on owned properties: tracks the weekly operating KPIs,
holds the property manager accountable, and produces investor updates. Turns ownership
into a managed system instead of ad-hoc firefighting.

## Why it exists (the mentorship lesson)

- **"Manage the manager, not the property."** Ownership leverage comes from PM
  accountability, not operator involvement in day-to-day tasks.
- **Four weekly reports define the operation.** Track these every week from day one of
  ownership:
  1. **Unit availability** (vacancy + upcoming move-outs)
  2. **Work orders** (open / closed / aging)
  3. **Delinquencies** (who's behind, how much, collection status)
  4. **Lease expirations / renewals** (rolling 60–90 day window)
- **Retention-weighted PM comp.** Tie part of PM compensation to renewals/retention, not
  just occupancy — reduces turn cost, the biggest hidden NOI leak.
- **Quarterly investor updates.** Short Loom/video + written update: what happened, why it
  matters, what's next — in Olive Tree voice.

## Execution (proposed)

### Step 1: Pull the weekly ops dashboard
For each owned property, collect the 4 reports from the PM (email/portal). Surface
exceptions only: aging work orders, delinquency spikes, vacancy above proforma,
renewals at risk.

### Step 2: PM accountability check
Compare actuals vs. the business plan (proforma rents, occupancy, expense lines from
the deal-analysis underwriting). Flag drift. Draft the PM follow-up on any miss.

### Step 3: Renewal / retention watch
Rolling 60–90 day lease-expiration list → prompt renewal outreach early. Track renewal
rate; flag if trending below target (turn cost kills value-add returns).

### Step 4: Quarterly investor update
Draft in Brian's voice: occupancy, NOI vs. proforma, CapEx progress, distributions,
what's next. Capture happened → matters → next. Pair with a short Loom script.
Never sends without Brian's approval.

## KPIs tracked
NOI vs. proforma · economic occupancy · delinquency % · work-order aging ·
renewal rate · CapEx % complete · DSCR (current debt)

## Connections needed
- PM reporting (email/portal) — varies by property
- QuickBooks / Bluevine (financials) — not yet connected
- Email (investor updates, drafts only) — connected

## To build before this goes live
- [ ] `scripts/ops_dashboard.py` — ingest the 4 weekly PM reports, surface exceptions
- [ ] Per-property business-plan baseline (from deal-analysis underwriting at close)
- [ ] Investor-update template in Olive Tree voice
- [ ] First owned property to manage (none yet — this activates post-close)
