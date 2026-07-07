# Olive Tree AIOS — Agent & Review Guidelines

Personal automation repo for Olive Tree Investments (multifamily syndication + land wholesaling). Mostly standalone Python scripts in `scripts/` run locally or via launchd; no web service in this repo. Full project context lives in `CLAUDE.md`.

## Review guidelines

Review for issues that break production or produce wrong financial output. Skip style, formatting, naming, import order, and docstring nitpicks.

**Priorities, in order:**

1. **Financial correctness** — this repo computes NOI, cap rate, IRR, cash-on-cash, DSCR, offer prices, and fee splits. Any calculation error is P1. Watch for: zero/negative denominators (unit count, price, cap rate), `>=` vs `>` on threshold gates, unnormalized seller-stated numbers used directly, missing rounding on money.
2. **Speed & efficiency** — sequential API/network calls that could be batched or parallelized, repeated work inside loops, re-reads of the same file/sheet, N+1 patterns against Google Sheets/Drive or SQLite.
3. **Robustness at boundaries** — unhandled None/empty on external data (API responses, sheet rows, parsed docs), missing retry/backoff on flaky external APIs (Google, Crexi, LoopNet, SAM.gov, KIE), swallowed exceptions (`except: pass`), unclosed resources (prefer context managers).
4. **Security** — secrets or API keys in code or logs (everything belongs in `.env`), unsafe subprocess use, SQL built by string formatting.

**Always flag regardless of scope:** anything that sends email/SMS or enrolls contacts in drips (nothing may send without explicit approval or a `--send` flag), bulk deletes or destructive sheet/DB writes, and auth/token handling.

**Domain rules reviewers must respect:**
- Never scale proforma property tax to purchase price — TN/GA/AL reassess on county cycles, not on sale.
- OM actuals go in current-expense columns; knowledge-base adjustments go in proforma columns. Template defaults are never used when OM data exists.

**Output:** per finding give file:line, severity (HIGH/MED/LOW), one-line issue, concrete fix. Group by file. If a file is clean, one line says so.
