---
type: skill
name: broker-search
trigger: /broker-search
status: active
---

## What it does
Scans Gmail for Crexi and LoopNet listing alert emails, parses each property, filters against the buy box, and logs results to the Deal Sourcing spreadsheet. Adds brokers to the Brokers List only if they have 2+ active listings in the scan.

## Trigger phrases
- `/broker-search`
- "scan for new deals"
- "check listing alerts"
- "find new listings"
- "run broker search"

## What it reads
- Gmail (Crexi + LoopNet alert emails)
- `references/buy-box.md` — active markets and filters
- Google Sheets — Deal Sourcing spreadsheet

## Output
- Filtered deal list (buy-box matches only)
- New brokers logged if they have 2+ active listings
- Deduped from prior scans

## Notes
- Requires Crexi and LoopNet saved searches set up first (one-time setup per the SKILL.md).
- Saved search naming convention: `OTI - [zip]` (e.g. `OTI - 30341`).
- 9 active zip codes: 30341, 30080, 30005, 37207, 37115, 37408, 35801, 35205, 35806.
- Gmail MCP must be connected.
- Called by [[skills/lets-get-to-work]] Phase 1.
