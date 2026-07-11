---
type: site-guide
collection: kenneth-suna-site
content_type: member-guide
title: Covered Calls Explained
instructor: Kenneth Suna
source_url: https://www.kennethsuna.com/coveredcallsexplained
date_added: 2026-07-10
---

## Summary
Kenneth's paid Research Vault guide to his weekly covered-call + cash-secured-put income system — the written companion to the $180/WEEK series. Covers stock selection, premium risk bands, strike selection, rolling, the repair strategy for underwater positions, lot assignment (FIFO/LIFO), the wheel, Greeks, early-assignment traps, and account placement (taxable vs. Roth). This is the core written resource behind the strategy Brian's Premium Desk runs.

## Key Content

### 01. What a covered call is
- Sell a call option on stock you already own. One contract = 100 shares — you must own 100 shares first.
- More volatile stocks pay higher premiums; the catch is most volatile stocks are expensive per share, pricing out smaller accounts.
- Seller keeps the premium in all cases. If stock stays below strike: keep shares + premium. If above: shares sold at strike — premium kept, upside above strike forfeited.

### 02. Finding covered-call stocks
- Volatility intuition: KO (Coca-Cola) premiums are ~1% or less. Kenneth targets weekly income in the **2–4% range**, accepting more risk. HIMS = high volatility = high premium. Risk-averse sellers should use higher-quality, less volatile names.
- Free screen: CNBC homepage lists **most active, market movers (top and bottom), and unusual volume** — including droppers.
- Quality stocks dropping on bad news: distinguish structural bad news ("sales could slow over the next several quarters" = very bad) from transient ("sales dropped last quarter due to something out of their control" = overreaction, stock can recover fast).
- His weekly workflow: write down stocks that are soaring → buy on potential pullback the following week → sell a covered call → earn premium → (hopefully) get assigned → freed capital funds the next week's trades.

### 03. Premium mechanics + risk bands
Worked example: buy 100 HIMS at $56, sell $58-strike weekly call (sell Monday, expires Friday). Stock closes Friday at $62 → shares assigned at $58.
- Share profit: ($58 − $56) × 100 = **$200**
- Premium: ~**$180**/week average
- Total: **$380** (minus taxes). Counterparty bought at $58 with stock at $62 = $400 gain minus the $180 premium paid.
- Yes, trading the stock outright that week would have made $600 — but the weekly move isn't guaranteed; the premium is.

**Premium risk bands (weekly premium as % of stock price):**
| Band | Read |
|---|---|
| 0.3–0.8% | Conservative |
| 0.8–1.5% | Normal range |
| 1.5–2.5% | Aggressive |
| >3% | **Pause.** Stock is ultra-volatile; traders expect big swings. Consider trading the stock itself (upside is capped by the call) or skipping the trade — a 3.5% weekly premium can be wiped out by a 15% drop in the underlying. |

Premium % = (premium / stock price) × 100. Example: $8.10 premium on a $738 stock → 8.10 / 738 = 0.0109 → **1.09%** (normal range).

### 04. Strike price selection
- Strikes closest to the current price pay much higher premium (higher assignment odds); further out = safer from assignment, smaller premium.
- Buy at $56, sell $58 strike = selling "$2 out of the money."
- Live chain example, stock at $58.19: $59 strike premium = $1.51 (**$151**/contract); $65 strike = $0.28 (**$28**/contract).
- A $63 strike on a $56 stock (needs +12.5% in a week) pays much less — unlikely moves price cheap.

### 05. Rolling the option
Scenario: Friday, stock $58.85, strike $59 — assignment likely.
- **If cost basis is recent/near the strike** (bought at $56): don't bother rolling. Take assignment, keep the profit + premium, rebuy Monday (or sell a CSP).
- **If cost basis is old and low** (bought at $10): reasons to keep shares — big tax bill on assignment, and losing an irreplaceable low basis. Options:
  1. **Buy back** (close) the contract before expiration — may cost a lot if at a loss, but you keep the shares.
  2. **Stop selling CCs** on long-term holds if buybacks are too costly/risky.
  3. **Roll**: buy back the call (take the loss) and simultaneously sell a new call at a later date/strike. Keeps shares, but roll cost can exceed the next week's premium (especially if volatility cools), so rolling isn't always profitable.

### 06. Covered-call repair strategy (underwater position)
Scenario: bought at $55, sold $56 strike for $180 premium, stock craters to $40. You're long-term bullish and fine holding at a loss — but $56 strikes now pay nothing.
- Sell a strike a few dollars OTM at the new level, e.g. **$45** — not $41. A $41 strike pays more but risks **early assignment** if the stock rips past it mid-week, locking a big realized loss.
- Outcomes:
  - Stock stays under $45 (hits $44): keep shares + premium; next week sell $49 strike. **Ladder the strike up a few dollars each week as the stock recovers**, earning smaller premiums until it's back at $55 and you can sell $56+ strikes again.
  - Stock hits $47 on Wednesday: rolling mid-week means a bigger buyback loss the new premium may not offset. Early assignment $2 over strike is unlikely while there's still time to fall back below by Friday. Kenneth's play: **wait and roll in the last hour before Friday's close** (unless the stock rockets early in the morning).
- Gate: if you don't believe the stock can recover, don't run the repair — either don't trade it or cut losses.

### 07. Assign by lot (FIFO/LIFO)
Scenario: 100 shares at $10 (long-term core) + 100 shares at $56 (bought expressly for CC selling). To make sure assignment takes the $56 lot, set the brokerage **cost basis method to LIFO** (Last In, First Out); default is FIFO, which would surrender the $10 lot.
- Schwab: Profile tab → Cost Basis Method → LIFO. Schwab does not allow assigning lots per-transaction or retroactively — must be pre-set. Other brokerages vary; ask them.

### 08. Cash-secured puts (the wheel)
Scenario: assigned at $58, stock now $64. Instead of chasing, sell a CSP at the price you'd happily rebuy.
- Sell a **$60-strike CSP** with **$6,000** cash secured. If stock closes ≤ $60: obligated to buy 100 shares at $60 (even if it's $51). If it closes $60.01+: obligation gone, keep premium. Either way the premium is kept — "paid to wait and buy the stock at the price I want to pay."
- Live example: stock $59, sell $58 CSP → on the hook for $5,800 if assigned, earn **$117** premium for agreeing to do what you planned anyway.
- Order entry: options chain → PUT side → hit BID at your strike → quantity 1 → confirm. Ignore "MAX LOSS" (just the 100%-if-stock-goes-to-zero reminder).
- **Escape hatch**: a CSP can always be bought back before expiration. Stock $65, sell $62-strike CSP, stock crashes to $52 — you are not forced to take assignment if you buy back the contract (at a loss, since its price jumped), avoiding the $62 purchase.
- **Skip rule**: earnings next week / fragile economy / competitor just missed → "skip the premium, it's not worth the risk," sit out, rebuy shares when ready.
- **Best CSP timing (his view): right after a dramatic selloff.** Stock falls $50 → $38 on bad news; fear inflates put premiums. Sell a $37-strike CSP — the buyer pays up for crash protection; you collect a fat premium for agreeing to buy at $37. "High premiums don't exist because everyone thinks the stock is safe. High premiums exist because everyone is worried it isn't." His edge read: post-selloff consolidation around $38 = downside largely done, rebound possible.

**The wheel loop:** buy 100 shares → sell covered call → (maybe) assigned: keep profit + premium → sell cash-secured put → keep premium + (maybe) get shares back at your target price → own 100 shares again → sell covered call → repeat.

### 09. Downside of cash-secured puts
- Far-OTM CSPs after a big run-up pay almost nothing: stock ran $10 → $18, you want back in at $14 — a $14-strike CSP might pay **~$10 per contract** while tying up thousands in cash.
- His alternative: use that cash to buy a different stock, sell its call, earn a real premium, possibly get assigned within the same week — then check the first stock later; if it's near $14, just buy it. Capital efficiency over token premiums.

### 10. Greeks (what matters for a call seller)
- **Delta** — rough probability the option finishes in the money and shares get assigned. Stock $50.40, $51 strike, delta .41 → ~41% assignment odds (estimate from price, time, volatility — not a guarantee).
- **Gamma** — how much delta moves per $1 move in the stock. Not heavily used.
- **Theta** — daily time decay. **The seller's friend**: rises as expiration nears; option decaying to worthless = keep shares + premium.
- **Vega / IV** — sensitivity to implied volatility. Higher IV = higher premium. IV dropping after you sell (IV crush) benefits the seller; IV spiking raises assignment odds and buyback cost.
- His priorities: **IV and delta**. Worried about losing shares → pick lower delta. Pure income (his stance) → higher delta is fine; assignment is "no biggie."

### 11. Other rules and traps
- **Early profit lock**: sold a $57 strike, stock at $54, position showing most of the premium as profit → can buy to close any day and bank the smaller, certain gain.
- **Capped upside**: buy at $50, sell $51 strike, stock hits $60 → assigned at $51. Profit = $1/share + premium; rally missed. Accepted cost of the strategy.
- **Below-basis strike trap**: buy at $50, stock falls to $42. A $51 strike now pays almost nothing; a $43 strike pays well but assignment at $43.00+ means selling **below your $50 basis = realized loss**. Know which one you're choosing.
- **Ex-dividend early assignment**: call sold Monday expiring Friday, ex-dividend Wednesday → the buyer may exercise Tuesday to capture the dividend. You lose the shares early and miss the dividend; you keep the premium. Watch for it when the option is already ITM and the dividend is large.
- **Brokerage "loss shown" math** (don't panic): earned $143 premium, buy-to-close costs $400 → screen shows a $257 loss ($400 − $143). That's the net of the round trip, not a surprise extra charge.
- **Dividend stocks**: much smaller premiums (HIMS premium >> KO premium — low-vol names pay dividends instead). Pros: dividend + premium, lower downside risk, premium cushions dips, sideways markets pay you twice. Cons: small premiums and the ex-dividend early-assignment risk above.

### 12. Entry timing risk
- Momentum entries: on a trendy stock that rips, he buys the breakout, sells a call, captures premium, and is happy to be assigned — not a long-term hold.
- **Avoid buying a stock that already surged that week** (e.g., at $18.55 after the run). High premium, but the drop risk is worse. Instead: wait 1–2 weeks for a selloff or sideways consolidation; re-enter on a breakout with increased volume, then sell the call.

### 13. Covered calls in a Roth IRA? No.
- The Roth's edge is decades of tax-free compounding on limited contribution space (currently $7,500/yr if eligible). Spending it on modest CC premiums crowds out its best use.
- Occasional short-term capital gains in a taxable account cost far less than sacrificing 20–30 years of tax-free growth on a quality ETF.
- His rule: **covered calls belong in taxable accounts**; let the Roth compound quietly.

## Relevance to Premium Desk
This is the closest source document to the desk's actual strategy. Where his rules confirm, extend, or contradict a mechanical $50k CC/CSP wheel:

- **Cadence contradiction**: Kenneth runs weekly expirations (sell Monday, expire Friday) for higher annualized premium and fast redeployment; the desk sells 30–45 DTE and manages at 21 DTE. His weekly cadence also explains his roll timing ("last hour Friday") — that rule does not transplant to a 45-DTE book, but his covered-calls-went-weekly logic matches the desk's 2026-07 move to weekly CCs.
- **Premium bands as a screener gate (extend)**: 0.3–0.8% conservative / 0.8–1.5% normal / 1.5–2.5% aggressive / >3% = pause. The >3%-weekly pause is effectively a max-IV circuit breaker — a useful upper gate to pair with the desk's existing minimum-IV-rank gate (the desk screens for enough premium; Kenneth screens for too much).
- **Delta by intent (extend)**: he deliberately sells high delta because assignment is welcome (income-first, no attachment to shares). A mechanical wheel that always sells ~0.30 delta leaves premium on the table on flexible lots. Rule worth adopting: pick delta per lot intent — low delta on core shares, near-the-money on wheel lots.
- **CSP capital-efficiency rule (contradicts CSP-first)**: he rejects far-OTM CSPs with token premiums (~$10 against thousands reserved) and would rather rotate the cash into another CC cycle. A CSP-first desk should add his floor: if the CSP premium at the desired strike is negligible, skip the put and redeploy — don't reserve cash for scraps.
- **Post-selloff CSP timing (extend)**: his best-CSP window is right after a panic drop, when fear inflates put premiums — the inverse of the desk's anomaly circuit breaker, which stands down in turmoil. Tension worth a deliberate decision: his rule sells fear; the desk's breaker avoids it.
- **Confirms desk rules**: skip trades into earnings; never sell a strike below basis unintentionally; ex-dividend early-assignment check on ITM calls; taxable account (the desk's Alpaca account, not a Roth); LIFO/lot hygiene for mixed core + wheel positions in the same ticker.
- **Repair ladder (extend)**: the desk's 21-DTE management doesn't specify what to do deep underwater. His ladder — sell a strike a few dollars OTM (never so close that early assignment locks a loss), step it up weekly as the stock recovers — is a concrete drawdown playbook.
- **Entry-timing filter (extend)**: don't open wheel positions on a stock that already ripped that week; wait for consolidation and a volume breakout. A cheap pre-entry check the desk's screener could encode.

## Source
[Covered Calls Explained](https://www.kennethsuna.com/coveredcallsexplained) — paid Research Vault member guide (Brian has purchased access; notes for personal use).
