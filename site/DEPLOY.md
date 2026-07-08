# Deploy: Olive Tree Investments Static Site

## Before You Deploy

1. **Web3Forms access key** — go to https://web3forms.com, create a free account tied to `brian+lead@olivetreeinv.io`, copy the access key, and replace `WEB3FORMS_ACCESS_KEY_TODO` in `site/index.html` (the contact form).

2. **Google Calendar booking link** — create an appointment schedule at https://calendar.google.com/calendar/r/appointmentscheduling, copy the link (or embed code), and replace every `href="#booking"` placeholder in `partner-with-us/index.html`, `641_powder.html`, and `index.html`.

---

## Option A: Cloudflare Pages Dashboard (drag-and-drop, no CLI)

1. Go to https://dash.cloudflare.com → **Pages** → **Create a project** → **Direct Upload**.
2. Name the project `olive-tree-investments`.
3. Drag the entire `site/` folder into the upload zone (or zip it and upload).
4. Click **Deploy site**. Cloudflare assigns a `*.pages.dev` preview URL — verify all pages load.

### Wire the custom domain

5. In the project → **Custom domains** → **Set up a custom domain**.
6. Add `olivetreeinv.io` (apex) and `www.olivetreeinv.io`.
7. Cloudflare will show the DNS records to add. In your Cloudflare DNS dashboard:
   - **Apex** (`olivetreeinv.io`): set as a Cloudflare **Pages** record (Cloudflare handles it automatically when the domain is on Cloudflare).
   - **www**: add a CNAME `www` → `olive-tree-investments.pages.dev` (or Cloudflare will configure it for you).
   - Remove the old CNAME pointing `www` to `sites.ludicrous.cloud`.

> **Note:** Both the apex (`olivetreeinv.io`) and `www` sub-domain will serve identical content from Pages. Existing per-page paths (`/641_powder`, `/partner-with-us`, `/terms-and-conditions`, `/privacy-policy`) all resolve to their respective HTML files. The `/641_powder` path works because `641_powder.html` is at site root — Cloudflare Pages serves it at `/641_powder` when you add a `_redirects` rule (see below).

### Preserve `/641_powder` path (printed on mail pieces)

Create `site/_redirects` with:

```
/641_powder   /641_powder.html   200
/partner-with-us  /partner-with-us/index.html  200
```

This tells Cloudflare Pages to serve the file without redirecting, keeping the URL clean.

---

## Option B: Wrangler CLI

```bash
npm install -g wrangler          # install once
wrangler login                   # authenticate
npx wrangler pages deploy site/ --project-name olive-tree-investments
```

Then follow the custom domain steps in Option A (dashboard).

---

## Apex Redirect

If traffic hits the bare apex (`olivetreeinv.io`) and you want it to canonicalize to `www`, add to `site/_redirects`:

```
https://olivetreeinv.io/*   https://www.olivetreeinv.io/:splat   301
```

Or leave both apex and www serving identical content (simpler, both already point to Pages).

---

## Rollback

Cloudflare Pages keeps every deployment. To roll back:
1. Dashboard → **Pages** → `olive-tree-investments` → **Deployments**.
2. Find the previous deployment → **Manage** → **Rollback to this deployment**.

To repoint away from Pages entirely (emergency):
- Change the `www` CNAME back to `sites.ludicrous.cloud`.
- Remove the apex Pages record and re-add your previous apex A/CNAME.

---

## After Deploy Checklist

- [ ] Replace `WEB3FORMS_ACCESS_KEY_TODO` in `index.html`
- [ ] Replace `href="#booking"` placeholders with real Google Calendar link
- [ ] Test contact form submission (check `brian+lead@olivetreeinv.io`)
- [ ] Verify `/641_powder` loads without redirect (mail piece URL)
- [ ] Verify `/terms-and-conditions/` and `/privacy-policy/` load
- [ ] Test mobile nav on iPhone
