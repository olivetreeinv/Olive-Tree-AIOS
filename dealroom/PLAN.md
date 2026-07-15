# Deal Room — Standalone Web App Plan

*Drafted 2026-07-14. Status: PLAN — not yet started.*

Invite-only web app exposing 5 AIOS skills (broker search, deal analysis, market research, LOI, pitch deck) through a polished UI. Internals black-boxed. Paywall-ready. Polish + speed are the priorities.

## Product definition

- **One screen, Google-style.** A single command bar with a curated dropdown of actions (not free-form chat). Each action opens a short structured form (city, address, price, etc.) and an upload zone where relevant.
- **Doc ingestion.** Drag-drop OM / T-12 / Rent Roll (PDF/XLSX). Stored in app storage, parsed by the agent job.
- **Jobs, not chat.** Every action runs as a background agent job with a live progress timeline (streamed steps: "Extracting T-12… Solving DSCR ceiling… Building scorecard"). Feels like a product, hides the agent.
- **Deliverables library.** Results render in-app (verdict cards, scorecards) with downloadable PDFs. Users never see Brian's Drive, Canva, scripts, or prompts.

### The 5 actions

| Action | User inputs | Deliverable |
|---|---|---|
| Market Research | city/zip | 7-criteria scorecard + verdict (in-app + PDF) |
| Deal Analysis | address, price, docs (OM/T-12/RR) | Quick Verdict → financials → letter-grade scorecard → GO price; populated Deal Analyzer (XLSX download) |
| Broker Search | state/market | broker list with listings count + contacts (CSV/table) |
| LOI | deal terms (or "from analysis #N") | LOI PDF |
| Pitch Deck | deal (from analysis) | LP deck PDF |

Curated prompt dropdown = these 5, each with 2–3 preset variants (e.g. "Quick screen" vs "Full underwrite"). No open-ended prompt box in v1.

## Architecture

**Frontend + API: Next.js (App Router, TS) on Vercel.** Auth, invite gating, upload signing, job CRUD, SSE relay of progress. Perplexity concurs this is the standard path (sources: Claude Agent SDK hosting docs, SaaS starter ecosystem).

**Agent worker: Python FastAPI + Claude Agent SDK, running on the Mac mini** (the planned migration target), exposed via Cloudflare Tunnel. This is the load-bearing choice:

- `crexi_live.py` **requires a residential IP** (cloud 403s) — broker search's best mode only works from home.
- `gws_auth.py` shells out to the interactive `gws` CLI — works as-is on the mini, blocked headless in cloud.
- `data/olive.db` (aios_recall), `references/*.md`, Playwright/Rentometer, all local — work unchanged.

So the mini worker reuses the entire existing stack with ~zero refactors. Ceiling: single point of failure, home uptime. Upgrade path when scale/paywall demands: move worker to Fly.io, standardize Google auth on the `.env` refresh-token path (`loi.py` already does this — it's the template), accept losing crexi live mode in cloud (broker search stays a mini-only job or runs on a schedule and serves cached results).

**Data: Supabase** (Postgres + file storage). Tables: `users`, `invites`, `jobs`, `artifacts`, `deals`. Uploads and output PDFs live here — outputs are *copied out* of Drive/Canva into app storage so users never touch Brian's accounts.

**Auth + paywall: Clerk.** Invite-only via allowlist/invitations now; Clerk Billing (Stripe under the hood) flips on later without re-architecting. Plan gates = middleware checks on job creation.

**Job flow:** Next.js `POST /jobs` → worker queue (single FastAPI process + asyncio queue is enough at invite scale; Redis/Celery only if concurrency demands) → Agent SDK session runs the skill prompt with the repo's scripts as tools → progress events → SSE to browser → artifacts uploaded to Supabase → job complete.

## Per-skill wiring (from dependency research)

| Skill | Headless-ready today | Needs |
|---|---|---|
| LOI | ✅ `loi.py` is already cloud-ready (.env token path) | LLM only for intake → replaced by the form |
| Deal Analysis | Math/analyzer/GO-solve = deterministic Python | LLM required for OM/T-12/RR extraction; Drive template IDs stay (Brian's Drive is the "factory", output PDF/XLSX copied to app storage) |
| Market Research | ❌ ~95% LLM + WebSearch | Runs fine as an Agent SDK job; no refactor |
| Broker Search | `crexi_live.py` deterministic | Residential IP (mini ✅); contact enrichment stays agent WebSearch |
| Pitch Deck | Copy/export deterministic | Slide population is LLM via Canva MCP; Canva token refresh rewrites `.env` → move tokens to DB store (small refactor, `canva_token_store.py` already exists) |

**Identity decision:** all pipelines keep running as Brian's Google/Canva accounts (single-tenant factory). Users only ever receive app-hosted artifacts. Per-user Google OAuth is explicitly out of scope — YAGNI until there's a reason users need output in *their* Drive.

## Black-box + paywall framework

- Skill prompts, scripts, buy-box, and KB live server-side only. The API surface is `POST /jobs {action, params, files}` — nothing else leaks.
- Every job records token cost + runtime in `jobs` → this is the metering foundation for pricing later (per-analysis credits is the natural model; deal analysis ≈ $0.50–$3 in Claude tokens per run).
- Feature flags per plan tier from day 1 (a `plan` column + one middleware check), so the paywall is a config change, not a build.

## UI (polish priority)

- Brand: Brand Kit 2026 (Forest/Olive/Brass/Bone, Cormorant Garamond + Archivo) — reuse `site/brand/index.html` tokens.
- Home: centered command bar, action dropdown, recent jobs below. Zero dashboard clutter.
- Job page: streaming step timeline → result reveal (verdict card animates in). This is the "slick" moment; invest here.
- Build with taste-skill / redesign-skill standards; no template look.

## Phases

1. **Skeleton (week 1):** Next.js + Clerk invites + Supabase + FastAPI worker on the mini behind Cloudflare Tunnel. One action end-to-end: **Market Research** (pure LLM, no doc parsing, no Google writes — lowest-risk slice). Verify: invited user runs a city, sees streamed progress, gets scorecard PDF.
2. **Deal Analysis + ingestion (week 2):** upload pipeline, agent extraction → `deal_analysis.py` → analyzer XLSX + summary PDF copied to app storage. Verify: OM+T-12 upload → verdict + GO price + downloads, no Drive links exposed.
3. **LOI + Broker Search (week 3):** LOI form → PDF; broker search job (mini-only) with cached results table. Verify: LOI PDF renders correct terms; broker scan returns GA rows.
4. **Pitch Deck + polish pass (week 4):** Canva token store refactor, deck job; then a full taste-skill/redesign pass + speed budget (LCP < 1.5s, job start < 2s).
5. **Paywall (later):** flip Clerk Billing on, price from measured per-job costs.

## Costs (monthly, invite scale)

- Vercel free–$20 · Supabase free–$25 · Clerk free (<10k MAU) · Cloudflare Tunnel free · Claude API usage-billed per job (the real variable — metered from day 1). Mac mini: already planned.
- Free-alternative note: Auth.js instead of Clerk saves $0 now anyway (both free at this scale); Clerk wins on invitations + billing built-in.

## Open decisions for Brian

1. **Name/domain** (dealroom.olivetreeinv.io? standalone brand?)
2. **Mac mini worker OK as v1 backbone?** (recommended; cloud worker = Fly.io later, loses crexi live)
3. **Who are the first invited users** — LPs? mentees? This shapes which action gets the polish budget first.
