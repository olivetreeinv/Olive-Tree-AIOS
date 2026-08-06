# Polygon vs Alpaca data-feed comparison — archived 2026-07-07

Ran through 2026-07-08 to decide whether Alpaca (Algo Trader Plus, SIP feed)
could replace Polygon as the trading desk's market-data source.

**Verdict: Alpaca wins.** 0.4bps average price diff, 100% gate agreement
across 55 symbol-days. Polygon was removed from `scripts/trading_data.py` and
all other trading scripts; Alpaca (SIP equities, OPRA options) is now the
sole data source.

`data_compare.py` + `data_compare_report.sh` are kept here for reference only
— not wired into any launchd job or live script.
