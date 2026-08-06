# Code Review Skill — Olive Tree Investments
**Trigger:** `/code-review`, "review this PR", "review my code", "check this before merge", "is this safe to merge"

---

## What this skill does

Reviews staged diffs or PR changes for production-breaking issues. Architecture-first — not syntax, not style. Every finding maps to a severity. Critical findings block the merge.

**Output:** Inline PR comments (with `--comment`) + terminal summary → `APPROVED ✅` or `BLOCKED ❌`

---

## Review mandate

### In scope — always check for:

**Security**
- SQL injection, command injection, XSS, CSRF
- Broken or missing auth checks (missing permission guard, hardcoded credentials, token logged/exposed)
- Secrets or API keys in plaintext (even in comments or logs)
- Insecure deserialization, path traversal, open redirects

**Business logic**
- Calculation errors that would produce wrong financial outputs (NOI, IRR, CoC, DSCR, fees)
- Off-by-one errors in loops or ranges
- Wrong conditionals (e.g., `>=` vs `>` on threshold checks)
- Data integrity gaps (no transaction where multiple writes must be atomic)

**Performance**
- N+1 queries (loop that runs a DB query per iteration)
- Missing indexes on WHERE/JOIN columns
- Unbounded loops or list builds with no size guard
- Synchronous blocking calls where async is available
- Memory leaks (unclosed file handles, uncleaned temp files, growing caches)

**Architecture**
- Race conditions or missing locks around shared state
- Tight coupling that makes failure modes unpredictable
- Missing retry/backoff on flaky external API calls (Crexi, LoopNet, SAM.gov, Google APIs)
- Swallowed exceptions (`except: pass`, bare `except Exception` with no logging)
- Unhandled None/null at system boundaries (user input, API responses, DB reads)

**Edge cases**
- Empty list/dict inputs passed to functions that assume non-empty
- Zero or negative values in financial denominators (cap rate, unit count, price)
- Missing guard on external data shape (API response schema change breaks silently)

### Always flag — regardless of scope:
- Any code touching **auth** (login, session, token validation, role checks, API key verification)
- Any code touching **payments** (charges, refunds, ledger writes, subscription changes, disbursements)
- Any code touching **data deletion** (DELETE queries, file removal, cascade deletes, soft-delete bypass, bulk ops)

### Out of scope — do not flag:
- Naming conventions (snake_case vs camelCase, etc.)
- Formatting and line length
- Import ordering
- Docstring / comment presence or style
- Test coverage percentage
- Framework opinions ("I would use X instead of Y")

---

## Severity system

**CRITICAL** — blocks merge. These break production, expose data, corrupt records, or are exploitable.
> SQL injection vector, auth bypass, payment calculation error, unguarded bulk delete, API key in plaintext, integer overflow in financial calc, missing transaction on multi-write

**WARNING** — informational. Degrades reliability or performance; does not block.
> N+1 query, unhandled None in non-critical path, missing retry on external call, swallowed exception with no log

**INFO** — optional. Low-risk observations worth a glance; no action required.

---

## How to run

```bash
/code-review                      # review staged diff, output to terminal
/code-review --comment            # review + post inline GitHub PR comments
/code-review ultra                # deep multi-agent cloud review (billed)
/code-review ultra --comment      # recommended before any merge to main
```

Effort levels: `low` → `medium` (default) → `high` → `max` → `ultra` (multi-agent cloud)

For security-sensitive PRs (auth, payments, deletions) — always use `ultra --comment`.

---

## Output format

```
## AI Code Review — [branch → main]

### 🔴 CRITICAL (n)
- `file.py:42` — SQL injection: f-string used to build query with user input. Use parameterized queries.
- `scripts/deal_analysis.py:87` — Division by zero: `unit_count` not checked before use as denominator.

### 🟡 WARNINGS (n)
- `scripts/broker_search.py:114` — N+1: listing.get() called inside a for loop over all brokers.
- `app/routes.py:33` — Bare except swallows all errors silently.

### 🚩 Auth / Payment / Delete flags
- `app/auth.py:20` — FLAGGED [auth]: token validated but expiry not checked.
- `scripts/deal_analysis.py:201` — FLAGGED [financial calc]: fee calculation uses seller's stated NOI without normalization.

---
Verdict: APPROVED ✅  |  BLOCKED ❌ (resolve all CRITICALs before merge)
```

---

## Merge gate

- **Any CRITICAL** → verdict is `BLOCKED`. PR cannot merge until all CRITICALs are resolved.
- **Warnings** do not block. Acknowledge them in a PR comment or fix them.
- The GitHub Actions workflow `.github/workflows/ai-code-review.yml` enforces this automatically as a required status check.

---

## Canary (post-production)

Once the govcon app (or any Olive Tree service) is deployed to cloud infra with staged rollout support, add a canary step to the workflow:
1. Deploy to canary slot (10% traffic)
2. Monitor error rate + latency for N minutes via health endpoint
3. Auto-promote or rollback based on thresholds

Not applicable to local-only scripts. Wire this up at deployment time.
