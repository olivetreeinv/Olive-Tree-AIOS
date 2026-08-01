---
type: research-note
title: Covered-Call Method Comparison — Suna vs the Field (Aug 2026)
generated: 2026-08-01
status: DECIDED — moderate tier applied 2026-08-01, aggressive tier in shadow
---

# Is Suna's method the best? Can the desk make more per week on $50k?

**Verdict: keep the Suna weekly share-first core. It's the right method class for an automated desk.** The realistic path to more income is not a different guru — it's turning on the leg that has never earned a cent (the wheel-back cash-secured puts), cutting the thin-premium tail, and letting the shadow counters prove or kill the aggressive levers with live data.

**Realism first.** The old target of $1,000/week on $50,000 is ~104% annualized. Nothing documented sustains that — not Kenneth Suna (best stretch ~3%/week on a $33k book, with real losing weeks and a self-titled "huge covered call mistake" video), not the CBOE's 30-year index studies (~9–11% annualized), not practitioner wheel data ($400–800/month on $50k). The desk's own measured ceiling is **~$640/week at normal 1.3% fills**, $980–1,225 only in fear-priced weeks. July's true pace: **~31% annualized gross, +2.6% equity ($51,323), Sharpe 1.56, max drawdown 1.87%** — already above the honest practitioner band. Target restated to **$500/week**.

## The field, compared

| Method | Mechanics | Documented yield | Take for this desk |
|---|---|---|---|
| **Suna (live desk)** | Weekly expiries, ~0.45 delta (near-the-money), share-first, assignment welcome, Friday-afternoon net-credit rolls, repair ladder | ~31% ann. (July actual); Suna himself ~3%/wk best stretch | Keep. Weekly near-ATM is the highest-yield class of covered-call writing |
| **tastytrade** | 45 days to expiration (DTE), 0.30 delta, close at 50% profit, roll at 21 DTE to dodge gamma risk | ~10–15% ann. | Their whole case for monthlies is management burden — automation removes it. Weekly gross runs 18–35% vs 10–15% for monthlies |
| **Alan Ellman (Blue Collar Investor)** | Monthlies, 2–4% initial return targets, 20%/10% buyback-exit ladder | ~20–40% ann. claimed | His 20%/10% exit discipline rhymes with our 60% profit-close; monthly cadence again the only real difference |
| **CBOE index research (BXM/PUT)** | Systematic 30-day writing on the S&P 500 | BXM ~9%, PUT ~10% ann. over 30 yrs; **put-write beats buy-write ~1%/yr, wins 68% of years** | The one structural challenge to share-first. Parked, not adopted — see below |
| **Practitioner wheel consensus** | 0.20–0.30 delta cash-secured puts, 21–30 DTE, wheel on assignment | 15–25% ann. realistic | Confirms the desk is already above the honest band; be suspicious of anything promising 60%+ |

**Why not flip to put-first (the CBOE "PUT conundrum")?** The research edge is real, but Suna's objection is specifically about small accounts: weekly cash-secured-put collateral strangles the income cadence (four separate videos). And our own wheel leg went **0-for-8 lifetime** — not because puts don't work, but because it sized collateral against the wrong buying-power number (fixed 7/31, unverified). Decision: prove the fixed wheel-back leg first (earliest possible fill: week of Aug 7). If it fills cleanly for a few weeks, revisit put-first entries with actual desk data instead of index-fund research.

## What was applied today (moderate tier)

1. **Premium floor 0.8% → 1.2%/week** (`PREM_MIN`, `scripts/trading_suna.py`). Grounded in the ledger: across July's 15 real call fills ($1,992 premium), a 1.2% floor forgoes only $117 (XLE, BAC — thin fills that tied up ~$6–8k each for <$100/wk). 1.5% would forgo $390; the pending proposal's 2.0% hard gate would forgo $828 — 42% of everything the desk earned.
2. **Earnings-window guard fixed at the root.** The old check only skipped names with earnings <3 days out — a 7-DTE pick could still straddle a day-5 earnings date. Entry expiry is now capped *before* earnings (`dte_cap` → `pick_weekly_call`), and the wheel got the same guard — it previously had **none** (a cash-secured put across an earnings gap-down is the exact tail risk Suna warns about).
3. **Shadow counters for the aggressive levers** — logged on every entry, rejecting nothing: A2 (2.0% hard gate), A4 (stable vs high-IV tier mix), A5 (what the 0.30-delta strike would have earned vs the chosen 0.45). Review alongside the `trend`/`quality`/`highs` shadow gates after the first live week (Aug 3–7).
4. **Target restated $1k/wk → $500/wk** in `CC_WEEKLY_TARGET_USD`, the goal registry, and the skill doc — so `/goal-watch` judges against a target that can actually be met.
5. **The five 7/10 upgrade-proposal files finally ruled** (they'd sat "awaiting approval" for three weeks): the 12-item covered-call set resolved item-by-item (adopted / shadow / already-live / declined), the three 1-of-N-coverage ETF/dividend files declined as off-mandate.

## Where next week's income actually comes from

| Lever | Expected effect | Status |
|---|---|---|
| Wheel-back CSPs finally filling | July's v2-era puts yielded 0.95–2.17%/wk on collateral — call it $50–150/wk when names are assigned | Fixed 7/31; first possible fill week of Aug 7 — **watch for the 🎡 line** |
| 1.2% premium floor | Frees ~$6–8k per skipped thin name for a better one | Live Monday |
| Full deployment | Already done — idle cash fell 76% → 10% across July | Holding |
| 2.0% gate / delta tiers / vol blend | Unknown — that's what the shadow counters measure | Data by ~Aug 7 review |

**Not doing:** monthly cadence (drops the desk into the 10–15% yield class to solve a management problem it doesn't have), intraweek rotation on rallies (medium-confidence, complex), ETF income sleeves (fee + NAV-decay drag; off-mandate).

## Sources

- Desk data: `decisions/log.md` 2026-07-26 → 2026-08-01, `archives/trading-eval-2026-08/*.json`, `data/olive.db`
- Suna corpus: `wiki/trading-desk/kenneth-suna-site/covered-calls-explained.md` + 52 transcript files; fidelity ~85% (7/31 pass)
- [tastytrade covered-call mechanics](https://tastytrade.com/learn/trading-products/options/covered-call/) · [weekly vs monthly comparison](https://www.borntosell.com/covered-call-blog/weekly-vs-monthly) · [CBOE BXM/PUT studies](https://ir.cboe.com/news/news-details/2016/Study-Analyzes-Performance-of-CBOE-SP-500-SPX-Options-Selling-Indexes-02-23-2016/default.aspx) · [put-write vs buy-write analysis](https://www.optionstocksmachines.com/post/writing-conundrums/) · [realistic wheel returns on $50k](https://wheelstrategy.substack.com/p/wheel-strategy-returns-monthly-income-examples) · [Ellman 20%/10% guidelines](https://www.thebluecollarinvestor.com/20-10-guidelines-for-covered-call-writing-and-put-selling-same-name-different-circumstances/) · [strike-delta yield tradeoffs](https://quantwheel.com/learn/covered-call-strike-selection/)
