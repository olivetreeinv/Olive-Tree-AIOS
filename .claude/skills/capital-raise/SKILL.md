# Capital Raise Skill — Olive Tree Investments
**Trigger:** `/capital-raise`, "raise capital", "investor outreach", "soft commitments", "who do I call for this deal"

> **STATUS: LIVE (2026-06-19).** Scaffolded from Justin Brennan mentorship mining.
> `scripts/capital_raise.py` is built and verified. First raise: 641 Powder Springs (Smyrna).
> Nothing sends without Brian's approval (`--send` flag required).

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

## How to run a raise (641 Powder Springs playbook)

### Step 1 — Size the audience
```bash
python3 scripts/capital_raise.py audience
```
Pages all GHL contacts, buckets by tag, prints reachable counts, writes
`output/capital-raise/641-powder-springs-audience-<date>.csv`.
**Result (2026-06-19):** 633 tagged contacts · 320 email · 557 phone · 0 enrolled.

### Step 2 — Verify copy + self-test
Check `output/capital-raise/641-first-touch.md` against the drip's first email/SMS in GHL.
Then enroll yourself to confirm the drip fires correctly:
```bash
python3 scripts/capital_raise.py enroll --send --contact-id <your-contact-id>
```
Confirm you receive the email + text and the landing page/Loom render at
`https://olivetreeinv.io/641_powder`.

### Step 3 — Dry-run then send
```bash
python3 scripts/capital_raise.py enroll              # dry-run — prints who would enroll
python3 scripts/capital_raise.py enroll --send       # live — enrolls all 633, idempotent
```
Each enrolled contact gets the tag `raise-641-enrolled` so re-runs skip them.
GHL's "Deal Funnel Pitch Deck" workflow handles the email, SMS, Loom, and follow-up drip.

### Step 4 — Track soft commits
As prospects respond and you add them to the Investors pipeline in GHL:
```bash
python3 scripts/capital_raise.py track
```
Shows running total vs. $400K Q3 target. Log each commitment in the "Soft commitment"
stage with `monetaryValue` set to the dollar amount.

### Step 5 — Tax/returns hook (optional, for the right investor)
Cost-seg + bonus depreciation: Year-1 paper loss of ~$0.95–$1.20 per $1 invested.
Order the cost-seg study in the first 30 days post-close (3rd-party, post-reno for
bigger basis); hold 5 years to minimize recapture.

## GHL asset IDs (641 Powder Springs)
- **Funnel:** `O2Op6S7p7DbBEgkEuZLd` — `https://olivetreeinv.io/641_powder`
- **Drip workflow:** `0f93b671-d649-4836-9cd4-39ce0985c4c1` — "Deal Funnel Pitch Deck"
- **Investors pipeline:** `TUzH2bLOw4Iw06LUB625`
- **Soft commitment stage:** `aae3cd8d-aaca-48a6-8638-f19950794d37`
- **Enrolled tag:** `raise-641-enrolled`

## 506(b) compliance checkpoints
- Outreach only to tagged contacts (pre-existing relationships). Never the untagged 270.
- SMS copy carries "Reply STOP" — verify GHL opt-out is enabled on the workflow.
- Never blast the full 915-contact list.

## Script: `scripts/capital_raise.py`
Built 2026-06-19. Uses `subprocess.run(['curl',...])` for GHL calls (Python 3.14 SSL).
All writes are idempotent. `--send` flag required for any live action.
