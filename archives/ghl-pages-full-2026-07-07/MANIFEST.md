# GHL Funnel-Page Snapshot Archive — Full Pass, 2026-07-07

Attempted every page across all 5 GHL funnels / 25 total pages listed in
`archives/ghl-export-deep-2026-07-07/funnels.json` + `funnel_pages.json`.
Captured raw server HTML via `curl -sL` with a browser User-Agent. This
archive supersedes `archives/ghl-pages-2026-07-06/` as the record of what's
publicly reachable — that archive's `content.md`/PDFs/assets are still the
richer artifacts to keep for the rebuild, this pass is the reachability
audit + confirmation capture.

## Routing fact (unchanged from 07-06 finding, re-verified today)

`olivetreeinv.io` (apex) serves the funnel steps that are actually mapped
under the two funnels + blog attached to domainId `KFQMBgNfQZuYv9RVdnvh`.
Any path apex doesn't recognize, and every path on `www.olivetreeinv.io`,
301s to `https://www.olivetreeinv.io/` (home). Confirmed with a fresh probe
against **all 18** unmapped-funnel paths on both hosts today — 100% redirect
to home, 0% served distinct content.

## Page inventory — all 25 pages

### Funnel: 641 Powder Springs St (domainId attached) — 1/1 captured

| Page | URL tried | Status | File |
|---|---|---|---|
| Landing Page | https://olivetreeinv.io/641_powder | **captured** (200, real content) | `641-powder-springs-st/landing-page.html` |

### Funnel: Olive Tree Website (domainId attached) — 4/4 captured

| Page | URL tried | Status | File |
|---|---|---|---|
| Home | https://olivetreeinv.io/home | **captured** (200) | `olive-tree-website/home.html` |
| Terms & Conditions | https://olivetreeinv.io/terms-and-conditions | **captured** (200) | `olive-tree-website/terms-and-conditions.html` |
| Privacy Policy | https://olivetreeinv.io/privacy-policy | **captured** (200) | `olive-tree-website/privacy-policy.html` |
| Partner with us | https://olivetreeinv.io/partner-with-us | **captured** (200 — bare GHL calendar widget, no text content in raw HTML, see gap note below) | `olive-tree-website/partner-with-us.html` |

Also captured: root `/` → `root.html` (identical to Home; apex root serves the same page as `/home`).

### Funnel: Find My House blog (domainId attached) — 4/4 reachable pages captured

| Page | URL tried | Status | File |
|---|---|---|---|
| Blog Home | https://olivetreeinv.io/findmyhouse | **captured** (200) | `find-my-house-blog/blog-home.html` |
| Blog Post (slug template) | https://olivetreeinv.io/post | not publicly reachable — 404 by design, bare `/post` isn't a real route, only slugged posts are | — |
| — post: BENEFITS OF INVESTING IN REAL ESTATE | https://olivetreeinv.io/post/new-blog-post | **captured** (200) | `find-my-house-blog/post-new-blog-post.html` |
| — post: Buying a home versus renting | https://olivetreeinv.io/post/new-blog-post-3301 | **captured** (200) | `find-my-house-blog/post-new-blog-post-3301.html` |
| — post: 5 Essential Tips for First-Time Homebuyers | https://olivetreeinv.io/post/new-blog-post-6430 | **captured** (200) | `find-my-house-blog/post-new-blog-post-6430.html` |

Checked the captured blog home HTML for additional `/post/...` links — only
the same 3 slugs above are linked. No new posts published since the 07-06
capture.

### Funnel: Find My House - Website (domainId = "" — no domain attached) — 0/15 reachable

All 15 steps probed on both `olivetreeinv.io` and `www.olivetreeinv.io`,
plus a hyphenated/URL-encoded funnel-slug guess — every single one 301s to
`https://www.olivetreeinv.io/` (home), meaning zero distinct content served.
This funnel was never published to a domain; its pages only exist inside the
GHL page-builder / preview, which requires an authenticated GHL session
(not exportable via public HTTP). Per task scope, not guessing further
beyond the documented URL/host/slug patterns.

| Page | URL(s) tried | Status |
|---|---|---|
| Home Page | `/home-page` (apex + www) | not publicly reachable |
| Selling Process | `/seller` | not publicly reachable |
| What's your Home Worth? | `/whats-your-home-worth` | not publicly reachable |
| About | `/about` | not publicly reachable |
| Blog | `/blog` | not publicly reachable |
| The Buying Process | `/The-Buying-Process` | not publicly reachable |
| Client Reviews | `/reviews` | not publicly reachable |
| Benefits Of Owning | `/benefits-of-owning` | not publicly reachable |
| Home Loan Options | `/home-loan-options` | not publicly reachable |
| Listing Agent Services | `/listing-agent-services` | not publicly reachable |
| Find A Home | `/find-a-home` | not publicly reachable |
| Real Estate | `/real-estate` | not publicly reachable |
| The Benefits of Investing in Real Estate | `/the-benefits-of-investing-in-real-estate` | not publicly reachable |
| 5 Essential Tips for First-Time Homebuyers | `/5-essential-tips-for-first-time-homebuyers` | not publicly reachable |
| Buying a Home versus Renting | `/buying-a-home-versus-renting` | not publicly reachable |

### Funnel: Investment (domainId = "" — no domain attached) — 0/3 reachable

| Page | URL(s) tried | Status |
|---|---|---|
| Home | `/home-5531` (apex + www) | not publicly reachable |
| Contact Us | `/contact-us-5164` | not publicly reachable |
| About Us | `/About%20Us`, `/investment` (funnel base) | not publicly reachable |

## Totals

- **Reachable + captured: 8 distinct funnel-step pages** (641 Powder, Home,
  Terms, Privacy, Partner-with-us, Blog Home, + 2 additional blog posts —
  9 counting all 3 blog posts) **+ root `/`** = **9 files** in this archive
  (`root.html` duplicates Home content, so 8 unique pages).
- **Not publicly reachable: 18 pages** (15 in "Find My House - Website" + 3
  in "Investment") — both funnels have no domain attached and are GHL-editor-only.
- Same 8 unique pages the 07-06 archive already had (`home`, `terms`,
  `privacy`, `partner-with-us`, `641_powder`, `findmyhouse`, 3 blog posts,
  root). **Newly captured today: 0 pages** — this pass is a re-verification
  + reachability audit of everything, not new content. The reachability
  finding for the 18 unattached-domain pages is unchanged from 07-06 and
  is now confirmed against a second, independent probe.

## site/ fidelity gaps

Compared live-captured text (raw HTML, tags stripped) against the rebuilt
static site (`site/index.html`, `site/641_powder.html`,
`site/partner-with-us/index.html`, `site/privacy-policy/index.html`,
`site/terms-and-conditions/index.html`). Terms & Privacy match content
1:1 (differences are only casing/line-wrap artifacts of the diff, not real
content loss). Two real gaps found:

1. **Home — "Our Story" has invented copy.** `site/index.html` appends a
   sentence not present anywhere in the live GHL Home page or 641 page:
   *"We believe the best deals are built on discipline, and the best
   partnerships are built on integrity. Every member of the Olive Tree team
   is here because they believe that real estate, done right, can create
   lasting value — for investors, for residents, and for the communities we
   serve."* — this sentence **does** exist on the live **641 Powder Springs**
   page's team-bio paragraph, but not on the live Home page. The rebuild
   pulled it into Home from the wrong source page. Not harmful (it's Brian's
   own voice/message) but it's not what GHL actually rendered on Home —
   flag if 1:1 fidelity to the old Home copy matters.

2. **Partner With Us — page purpose changed, not just re-styled.** The live
   GHL page (per `partner-with-us.html` here + the 07-06 archive's PDF/
   content.md notes) is a **bare GoHighLevel calendar-booking widget**
   (widget id `fd8cOUzYtG`, "Brian's Personal Calendar", 30 min slots,
   America/New_York, red accent `#e93d3d`) with **no body copy at all** — just
   a "Back to Home" link and the footer. `site/partner-with-us/index.html`
   adds a descriptive paragraph — *"Schedule a 30-minute call with Brian
   Norton to discuss your investment goals and learn how Olive Tree
   Investments creates returns through value-add multifamily."* — that does
   not exist on the live page. This is a reasonable rebuild choice (a bare
   calendar embed needs some explanatory text), but it's new copy, not
   recovered copy — Brian should sign off on the wording since it wasn't his
   original. Confirm the actual embed points at a live scheduling tool
   (Calendly/Google Calendar) since the GHL widget won't survive
   cancellation.

3. **641 Powder — live page has a genuine content bug the rebuild silently
   resolved.** The live GHL 641 page renders **two conflicting "Return
   Structure" blocks** (a desktop/mobile duplicate pair, per the established
   pattern) with different numbers: one says *"ROI 140% with annual rate of
   return projected at 18%"*, the other says *"ROI 60% with annual rate of
   return projected at 30%."* `site/641_powder.html` keeps only the 18%
   figure and drops the 30%/60% variant entirely — correct call for a clean
   rebuild, but worth a beat with Brian to confirm 18%/140% (not 30%/60%)
   is the number he actually wants published, since the live source itself
   was inconsistent.

No other content, section, form field, or CTA differences found between the
live captures and `site/`.
