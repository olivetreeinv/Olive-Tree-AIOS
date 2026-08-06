# Olive Tree LLM Wiki — Schema

This file defines the structure of the wiki. The ingest script reads it before generating any pages.
Do not delete it. Edit it to adjust page templates, required fields, or ingest rules.

---

## Wiki Rules

1. Every page belongs to exactly one category: `deals/`, `markets/`, `brokers/`, `mfs-docs/`, `mfs-videos/`, `govcon-bids/`, `govcon-subs/`, `govcon-agencies/`, or `skills/`.
2. Every page must have YAML frontmatter with the required fields for its type.
3. Use `[[category/page-name]]` WikiLink syntax for all cross-references.
4. Unknown values are written as `—`, never guessed.
5. Pages are created once per entity. Updates append to existing pages — they don't overwrite.
6. The ingest log at `_log.md` is append-only. Never edit it manually.

---

## Page Types

### Deal Page — `deals/slug.md`

**Required frontmatter fields:** `type`, `name`, `address`, `market`, `broker`, `units`, `asking_price`, `status`, `last_updated`

**Status values:** `prospect` | `analyzing` | `loi-sent` | `under-contract` | `closed` | `dead`

```markdown
---
type: deal
name: The Peachtree Arms
address: 123 Main St, Chattanooga TN 37408
market: "[[markets/chattanooga-southside]]"
broker: "[[brokers/john-smith]]"
units: 24
asking_price: $2,100,000
basis_per_unit: $87,500
status: analyzing
last_updated: 2026-06-09
---

## Quick Verdict
PURSUE LOI / MORE INFO NEEDED / PASS — one sentence reason.

## Key Numbers
| Metric | Current | Pro Forma |
|---|---|---|
| NOI | | |
| Cap Rate | | |
| IRR | | |
| Cash-on-Cash | | |
| DSCR | | |
| Equity Multiple | | |

## Assumptions
- Rent upside: 
- CapEx budget: 
- Exit cap: 
- Hold period: 

## Risks
1. 
2. 
3. 

## Sources
- `raw/filename.pdf` — ingested YYYY-MM-DD

## Notes

```

---

### Market Page — `markets/slug.md`

**Required frontmatter fields:** `type`, `name`, `zip`, `state`, `in_buy_box`, `last_updated`

```markdown
---
type: market
name: Chattanooga Southside
zip: "37408"
state: TN
in_buy_box: true
composite_score: —
last_updated: 2026-06-09
---

## Scorecard
| Criteria | Score (1-10) | Notes |
|---|---|---|
| Population growth | | |
| Job growth | | |
| Rent growth (YoY) | | |
| Vacancy rate | | |
| Cap rate trend | | |
| Supply pipeline | | |
| Investor demand | | |

**Composite: — / 10 — GO / NO-GO**

## Key Numbers
- Avg asking cap rate: 
- Avg rent/unit: 
- Vacancy rate: 
- YoY rent growth: 

## Active Deals
- [[deals/example-deal]]

## Active Brokers
- [[brokers/example-broker]]

## Notes

```

---

### Broker Page — `brokers/slug.md`

**Required frontmatter fields:** `type`, `name`, `company`, `email`, `phone`, `markets`, `last_contact`

```markdown
---
type: broker
name: John Smith
company: Marcus & Millichap
email: jsmith@marcusmillichap.com
phone: "404-555-0100"
markets:
  - "[[markets/chattanooga-southside]]"
  - "[[markets/north-nashville]]"
last_contact: 2026-06-09
---

## Deal Flow
| Deal | Units | Price | Status | Date |
|---|---|---|---|---|
| [[deals/example]] | 24 | $2.1M | analyzing | 2026-06-01 |

## Contact History
- **2026-06-09** — Sent OM for Peachtree Arms

## Notes

```

---

### Multifamily Schooled Document — `mfs-docs/slug.md`

**Required frontmatter fields:** `type`, `title`, `topic`, `source_file`, `date_added`

```markdown
---
type: mfs-doc
title: Underwriting 101 — Analyzing a Value-Add Deal
topic: underwriting
instructor: —
source_file: underwriting-101.pdf
date_added: 2026-06-09
---

## Summary
One-paragraph overview of what this document covers.

## Key Takeaways
1. 
2. 
3. 

## Action Items
Things to apply directly to Olive Tree deals or process:
- 

## Key Terms
| Term | Definition |
|---|---|
| | |

## Related
- [[deals/example-deal]]
- [[mfs-videos/related-video]]

```

---

### Multifamily Schooled Video — `mfs-videos/slug.md`

**Required frontmatter fields:** `type`, `title`, `topic`, `youtube_url`, `date_watched`

```markdown
---
type: mfs-video
title: How to Analyze Your First Apartment Deal
topic: deal-analysis
youtube_url: https://youtube.com/watch?v=XXXX
duration: —
date_watched: 2026-06-09
---

## Summary
One-paragraph overview of what the video covers.

## Key Concepts
1. 
2. 
3. 

## Timestamps
| Time | Topic |
|---|---|
| 0:00 | |
| 5:30 | |

## Action Items
- 

## Related
- [[mfs-docs/related-doc]]
- [[deals/example-deal]]

```

---

### GovCon Bid Page — `govcon-bids/slug.md`

**Required frontmatter fields:** `type`, `title`, `notice_id`, `agency`, `naics_code`, `state`, `deadline`, `status`

**Status values:** `researching` | `sub_contacted` | `quoted` | `submitted` | `won` | `lost` | `skipped`

```markdown
---
type: govcon-bid
title: Laurel River Lake Janitorial and Cleaning Services
notice_id: 6f9747d487e1454aa47621b930ca3b67
agency: "[[govcon-agencies/usda-forest-service]]"
naics_code: "561720"
naics_label: Janitorial & Cleaning
state: KY
deadline: 2026-06-04
sam_link: https://sam.gov/...
status: researching
sub_name: —
sub_contact: —
sub_quote: —
our_bid: —
past_price_ceiling: —
gross_profit: —
last_updated: 2026-06-09
---

## Status
Current stage and next action.

## Subcontractor
- **Name:** [[govcon-subs/sub-name]]
- **Quote:** —
- **Contact:** —

## Pricing
| Item | Amount |
|---|---|
| Sub quote | |
| Our bid | |
| Past price ceiling | |
| Gross profit | |
| Margin % | |

## Proposal
Paste or summarize the submitted proposal text.

## Notes

```

---

### GovCon Subcontractor — `govcon-subs/slug.md`

**Required frontmatter fields:** `type`, `name`, `contact`, `naics_codes`, `states`, `last_contact`

```markdown
---
type: govcon-sub
name: ABC Cleaning Services
contact: John Doe — john@abccleaning.com — 404-555-0100
naics_codes:
  - "561720"
  - "561730"
states:
  - GA
  - KY
  - TN
last_contact: 2026-06-09
reliability: —
---

## Quote History
| Bid | NAICS | State | Quote | Outcome | Date |
|---|---|---|---|---|---|
| [[govcon-bids/example-bid]] | 561720 | GA | $12,000 | won | 2026-06-01 |

## Notes

```

---

### GovCon Agency — `govcon-agencies/slug.md`

**Required frontmatter fields:** `type`, `name`, `abbreviation`

```markdown
---
type: govcon-agency
name: USDA Forest Service
abbreviation: USDA-FS
typical_naics:
  - "561720"
  - "561730"
  - "561710"
---

## Overview
What this agency typically buys. Avg contract size, frequency, regions.

## Past Awards (from USASpending)
| Title | Amount | State | Year |
|---|---|---|---|
| | | | |

## Active Bids
- [[govcon-bids/example-bid]]

## Notes

```

---

## Ingest Rules

| Source type | Pages created |
|---|---|
| `deal_om` | `deals/` + (new) `markets/` + (new) `brokers/` |
| `t12` | Updates existing `deals/` page |
| `rent_roll` | Updates existing `deals/` page |
| `broker_email` | `brokers/` + (new) `deals/` if deal mentioned |
| `broker_profile` | `brokers/` |
| `market_report` | `markets/` |
| `mfs_document` | `mfs-docs/` |
| `mfs_video` | `mfs-videos/` |
| `govcon_bid` | `govcon-bids/` + (new) `govcon-agencies/` |
| `govcon_sub` | `govcon-subs/` |
| `other` | Skipped — logged |

---

## Buy Box (authoritative source: `references/buy-box.md`)

10 active markets: Chamblee (30341), Smyrna (30080), Alpharetta (30005), North Nashville (37207),
Madison TN (37115), Chattanooga Southside (37408), Huntsville Core (35801), Birmingham Urban (35205),
Huntsville Growth (35806), Lebanon TN (37087).

Universal filter: 15–50 units, multifamily only, value-add required.
