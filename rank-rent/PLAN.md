# Rank & Rent — Local Lead-Gen Site Rental (Koerner Office Ep. 315 / Luke Van Der Veer)

**Model:** Build simple SEO websites for boring, high-ticket local services. The site generates
phone calls. Rent the site to one local operator for a flat monthly fee, or sell the calls
pay-per-lead / revenue share. Luke runs 100+ sites at ~$192K/mo. Assets are cheap to build,
compound over time, and are nearly hands-off once ranked and rented.

**Why this fits Brian:** NW Georgia local knowledge (Bartow/Rome/Dalton from the land vertical),
existing cold-call muscle (`/land-call`), Places API + Twilio + olive.db already wired,
and Claude Code turns the expensive part (building + writing 15-page niche sites) into minutes.

---

## Unit economics (per site)

| Item | Cost |
|---|---|
| Domain | ~$10/yr |
| Hosting (Cloudflare Pages) | $0 |
| Twilio tracking number | ~$1.15/mo + ~$0.02/min forwarding |
| Content + build (Claude Code) | $0 |
| **Total to launch a site** | **< $15** |

Revenue once producing: **$500–$1,500/mo flat rent** or **$40–$75 per qualified call**
(tree service leads close into $1,500–$4,000 jobs; operators happily pay). One site = a
30–100x annual return on build cost. The business is a portfolio of these.

## The honest 30-day constraint

Pure SEO takes 60–180 days to rank. Nobody pays rent for a site with no calls. The 30-day
cash lever is a **paid-ads bridge**: run Google Ads on the same site, sell the calls
pay-per-lead at a margin, convert the operator to flat rent as organic rankings replace
ad spend (margin expands to ~100%). SEO compounds in the background from day 1.

## 30-day schedule

**Days 1–3 — Pick markets, deploy sites.**
Validate 3 niche×market combos with a 10-minute SERP check each (see criteria below).
Buy 3 domains (~$30). Generate + deploy 3 sites with `rr_sitegen.py`. Provision 3 Twilio
tracking numbers. Submit to Search Console.

Shortlist to validate first:
1. **Tree service — Cartersville / Bartow County** (storm urgency, $1,500+ tickets)
2. **Towing — Rome GA** (24/7 urgency, high call volume)
3. **Concrete / driveways — Dalton GA** ($3–8K tickets)

SERP check = search "[niche] [city]": PASS if page 1 has directories (Yelp/Angi/Thumbtack),
sites with no SSL, or DIY builder sites in the top 5. FAIL if 5+ polished operator sites
with 100+ reviews.

**Days 3–7 — Foundations + prospect list.**
Top ~30 free citations per site. GBP where verifiable (needs an in-market address — see risks).
Pull operator prospect lists: `rr_prospects.py --pull "tree service" Cartersville,GA`.

**Days 7–14 — Sign the first renter.**
Cold-call operators from the call sheet (script built into `--list`). Offer, in order:
(a) first 10 calls free, then $500/mo; (b) founding rate $299/mo locked 6 months;
(c) pay-per-call $40–75 for calls ≥60s. Recordings via Twilio prove lead quality.
Target: 1 signed operator per niche.

**Days 14–30 — Turn on the bridge, collect first revenue.**
Google Ads on the ONE niche with a signed operator, $30–50/day. Calls route through the
Twilio number → operator's phone; `rr_leads.py --sync` pulls the call log for billing.
Day-30 realistic revenue: **$500–$1,500** (one flat rent + per-call margin). Not $192K —
that's 100 sites and 5 years in. This is month one of a compounding portfolio.

**Days 30–90 — Replicate.**
Factory is built; each new site is ~2 hours + $15. 10 sites by day 90. Kill ads per site
as organic takes over. $5–10K/mo run rate is the 6–12 month target at 10–15 rented sites.

## Risks

- **GBP verification** needs a real address in-market. Mitigation: organic + ads carry the
  model without it; once an operator signs, optimizing THEIR GBP becomes part of the package.
- **Google algo updates** — portfolio across niches/cities diversifies.
- **Renter churn** — call recordings + monthly lead reports (`rr_leads.py --report`) prove value.
- **Ad-bridge spend** ($500–1,000 in month 1) is the only real cash at risk; capped daily.

## Tooling (this repo)

- `scripts/rr_sitegen.py` — site factory: `site.json` → deployable static site in `dist/`
- `scripts/rr_prospects.py` — Places pull → `rr_prospects` table in olive.db → call sheet
- `scripts/rr_leads.py` — Twilio call-log sync → `rr_leads` table → monthly billing report
- `rank-rent/sites/<slug>/` — one folder per site (config + built output)
