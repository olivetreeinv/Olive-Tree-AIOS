#!/usr/bin/env python3
"""
Rank & Rent — Site Factory (/rr_sitegen)

Builds a static, mobile-first lead-gen site from a single site.json config.
Stdlib only — no Jinja, no npm, no external CSS/JS files. One inline <style>
block per page, optional tiny nav-toggle <script>.

Usage:
    python3 scripts/rr_sitegen.py <slug>            # rank-rent/sites/<slug>/site.json
    python3 scripts/rr_sitegen.py path/to/site.json
    python3 scripts/rr_sitegen.py <slug> --check     # build then validate dist/

site.json schema:
{
  "business_name": "Cartersville Tree Pros",
  "niche": "Tree Service",
  "phone": "PHONE_TBD",                 // tracking number; "PHONE_TBD" renders as a placeholder
  "email": "brian@olivetreeinv.io",     // contact form posts to formsubmit.co/{email}
  "city": "Cartersville",
  "state": "GA",
  "address": "123 Main St, Cartersville, GA 30120",   // optional, omit if no verifiable address
  "color_primary": "#1f4d2c",
  "color_accent": "#c1502e",
  "hero_headline": "...",
  "hero_subhead": "...",
  "about": "1-3 paragraphs, plain text (blank lines = new paragraph)",
  "hours": "Mon-Sat 7am-7pm, 24/7 Emergency Service",
  "testimonials": [ {"quote": "...", "name": "...", "placeholder": true} ],
  "services": [
    {
      "slug": "tree-removal",
      "name": "Tree Removal",
      "headline": "...",
      "body": "paragraph one\\n\\nparagraph two ...",   // \\n\\n separates paragraphs
      "faqs": [ {"q": "...", "a": "..."} ]
    }
  ],
  "service_areas": [
    {"slug": "acworth", "name": "Acworth", "body": "paragraph one\\n\\nparagraph two"}
  ]
}

Pages generated (clean folder URLs):
  /index.html
  /services/<slug>/index.html          (one per service)
  /areas/<slug>/index.html             (one per service area)
  /contact/index.html
  /404.html
  /sitemap.xml
  /robots.txt

Every page: unique <title> + meta description (service + city where relevant), exactly one
<h1>, LocalBusiness JSON-LD on the homepage, Service + FAQPage JSON-LD on service pages,
sticky mobile click-to-call bar, tel: links as the primary CTA, nav + footer + in-content
internal links, contact form posting to formsubmit.co.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SITES_DIR = ROOT / "rank-rent" / "sites"


# ---------------------------------------------------------------- helpers --

def esc(s):
    """Minimal HTML-escape for text nodes/attributes."""
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def paragraphs(text):
    """'\\n\\n'-split body text -> <p> tags."""
    if not text:
        return ""
    parts = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    return "\n".join(f"<p>{esc(p)}</p>" for p in parts)


def tel_href(phone):
    digits = re.sub(r"\D", "", phone or "")
    return f"tel:{digits}" if digits else "tel:0000000000"


def phone_display(phone):
    if not phone or phone == "PHONE_TBD":
        return "(Call Us)"
    return phone


# ---------------------------------------------------------------- layout ---

def base_style(primary, accent):
    return f"""
:root{{--primary:{primary};--accent:{accent};--ink:#1a1a1a;--muted:#5a5a5a;--bg:#fff;--line:#e6e6e2;}}
*{{box-sizing:border-box;}}
html{{scroll-behavior:smooth;}}
body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  color:var(--ink);background:var(--bg);line-height:1.6;}}
img{{max-width:100%;display:block;}}
a{{color:var(--primary);}}
.wrap{{max-width:1080px;margin:0 auto;padding:0 20px;}}
header.site{{background:var(--primary);color:#fff;position:sticky;top:0;z-index:50;}}
header.site .wrap{{display:flex;align-items:center;justify-content:space-between;padding:14px 20px;}}
.brand{{color:#fff;font-weight:700;font-size:1.15rem;text-decoration:none;}}
nav.main{{display:flex;gap:18px;}}
nav.main a{{color:#fff;text-decoration:none;font-size:.95rem;opacity:.92;}}
nav.main a:hover{{opacity:1;text-decoration:underline;}}
.nav-toggle{{display:none;background:none;border:1px solid #fff;color:#fff;padding:6px 10px;border-radius:6px;font-size:1rem;}}
.call-btn{{background:var(--accent);color:#fff;padding:9px 16px;border-radius:6px;text-decoration:none;
  font-weight:700;white-space:nowrap;}}
.call-btn:hover{{opacity:.92;}}
.hero{{background:linear-gradient(180deg,var(--primary) 0%,#123 130%);color:#fff;padding:56px 0 48px;}}
.hero h1{{font-size:2.1rem;margin:0 0 14px;line-height:1.2;}}
.hero p.sub{{font-size:1.15rem;opacity:.95;max-width:640px;margin:0 0 26px;}}
.hero .cta-row{{display:flex;gap:14px;flex-wrap:wrap;}}
.btn{{display:inline-block;padding:14px 26px;border-radius:8px;font-weight:700;text-decoration:none;font-size:1.05rem;}}
.btn.primary{{background:var(--accent);color:#fff;}}
.btn.secondary{{background:#fff;color:var(--primary);}}
.trust-strip{{background:#f4f3ee;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:16px 0;}}
.trust-strip .wrap{{display:flex;gap:28px;flex-wrap:wrap;justify-content:center;font-size:.92rem;color:var(--muted);
  font-weight:600;text-align:center;}}
section{{padding:44px 0;}}
section h2{{font-size:1.6rem;margin:0 0 18px;}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:20px;}}
.card{{border:1px solid var(--line);border-radius:10px;padding:20px;background:#fff;}}
.card h3{{margin:0 0 8px;font-size:1.15rem;}}
.card a.more{{font-weight:600;text-decoration:none;}}
.faq{{border-top:1px solid var(--line);padding:16px 0;}}
.faq h3{{margin:0 0 8px;font-size:1.05rem;}}
.testimonials{{background:#f4f3ee;}}
.t-card{{background:#fff;border:1px solid var(--line);border-radius:10px;padding:20px;}}
.t-card .q{{font-style:italic;margin:0 0 10px;}}
.t-card .who{{font-weight:700;font-size:.9rem;color:var(--muted);}}
.t-card .flag{{font-size:.78rem;color:var(--muted);}}
.areas-list{{display:flex;flex-wrap:wrap;gap:10px;}}
.areas-list a{{background:#f4f3ee;border:1px solid var(--line);padding:8px 14px;border-radius:20px;
  text-decoration:none;font-size:.92rem;color:var(--ink);}}
form.contact{{display:grid;gap:12px;max-width:520px;}}
form.contact input,form.contact textarea{{padding:12px;border:1px solid var(--line);border-radius:6px;font-size:1rem;
  font-family:inherit;width:100%;}}
form.contact button{{background:var(--accent);color:#fff;border:none;padding:14px;border-radius:6px;font-size:1.05rem;
  font-weight:700;cursor:pointer;}}
footer.site{{background:#1a1a1a;color:#ccc;padding:36px 0 90px;font-size:.9rem;}}
footer.site a{{color:#ccc;}}
footer.site .cols{{display:flex;flex-wrap:wrap;gap:36px;}}
footer.site h4{{color:#fff;font-size:.95rem;margin:0 0 10px;}}
footer.site ul{{list-style:none;margin:0;padding:0;}}
footer.site li{{margin-bottom:6px;}}
.call-bar{{position:fixed;bottom:0;left:0;right:0;background:var(--accent);color:#fff;text-align:center;
  padding:14px;font-weight:700;font-size:1.05rem;text-decoration:none;display:none;z-index:60;}}
@media (max-width:760px){{
  nav.main{{display:none;position:absolute;top:100%;left:0;right:0;background:var(--primary);flex-direction:column;
    padding:12px 20px;}}
  nav.main.open{{display:flex;}}
  .nav-toggle{{display:inline-block;}}
  .call-bar{{display:block;}}
  body{{padding-bottom:56px;}}
  .hero h1{{font-size:1.6rem;}}
}}
"""


def head(title, description, canonical_path, primary, accent, extra_jsonld=""):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{canonical_path}">
<style>{base_style(primary, accent)}</style>
{extra_jsonld}</head>
"""


def nav_links(cfg):
    links = [("/", "Home")]
    for s in cfg["services"]:
        links.append((f"/services/{s['slug']}/", s["name"]))
    links.append(("/contact/", "Contact"))
    return links


def header_html(cfg):
    phone = cfg.get("phone", "PHONE_TBD")
    items = "".join(f'<a href="{href}">{esc(label)}</a>' for href, label in nav_links(cfg))
    return f"""<header class="site">
  <div class="wrap">
    <a class="brand" href="/">{esc(cfg['business_name'])}</a>
    <button class="nav-toggle" onclick="document.querySelector('nav.main').classList.toggle('open')">Menu</button>
    <nav class="main">{items}</nav>
    <a class="call-btn" href="{tel_href(phone)}">Call {esc(phone_display(phone))}</a>
  </div>
</header>
"""


def footer_html(cfg):
    svc_items = "".join(
        f'<li><a href="/services/{s["slug"]}/">{esc(s["name"])}</a></li>' for s in cfg["services"]
    )
    area_items = "".join(
        f'<li><a href="/areas/{a["slug"]}/">{esc(a["name"])}</a></li>' for a in cfg["service_areas"]
    )
    addr = cfg.get("address")
    addr_html = f"<li>{esc(addr)}</li>" if addr else ""
    return f"""<footer class="site">
  <div class="wrap cols">
    <div>
      <h4>{esc(cfg['business_name'])}</h4>
      <ul>
        <li>{esc(cfg.get('city',''))}, {esc(cfg.get('state',''))}</li>
        {addr_html}
        <li><a href="{tel_href(cfg.get('phone'))}">{esc(phone_display(cfg.get('phone')))}</a></li>
        <li><a href="mailto:{esc(cfg.get('email',''))}">{esc(cfg.get('email',''))}</a></li>
        <li>{esc(cfg.get('hours',''))}</li>
      </ul>
    </div>
    <div>
      <h4>Services</h4>
      <ul>{svc_items}</ul>
    </div>
    <div>
      <h4>Service Areas</h4>
      <ul>{area_items}</ul>
    </div>
  </div>
  <div class="wrap" style="margin-top:20px;opacity:.7;">
    &copy; {esc(cfg.get('business_name'))}. All rights reserved.
  </div>
</footer>
<a class="call-bar" href="{tel_href(cfg.get('phone'))}">Call Now: {esc(phone_display(cfg.get('phone')))}</a>
"""


def page(cfg, title, description, canonical_path, h1, body_html, extra_jsonld=""):
    primary = cfg.get("color_primary", "#1f4d2c")
    accent = cfg.get("color_accent", "#c1502e")
    return (
        head(title, description, canonical_path, primary, accent, extra_jsonld)
        + "<body>\n"
        + header_html(cfg)
        + body_html.replace("{{H1}}", f'<h1>{esc(h1)}</h1>', 1)
        + footer_html(cfg)
        + "</body></html>\n"
    )


# ------------------------------------------------------------- JSON-LD -----

def jsonld_script(data):
    return f'<script type="application/ld+json">{json.dumps(data)}</script>\n'


def local_business_jsonld(cfg, site_url):
    d = {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "name": cfg["business_name"],
        "telephone": cfg.get("phone", ""),
        "email": cfg.get("email", ""),
        "url": site_url,
        "areaServed": [a["name"] for a in cfg["service_areas"]],
        "address": {
            "@type": "PostalAddress",
            "addressLocality": cfg.get("city", ""),
            "addressRegion": cfg.get("state", ""),
        },
    }
    if cfg.get("address"):
        d["address"]["streetAddress"] = cfg["address"]
    return jsonld_script(d)


def service_jsonld(cfg, svc, site_url):
    return jsonld_script({
        "@context": "https://schema.org",
        "@type": "Service",
        "serviceType": svc["name"],
        "name": f"{svc['name']} — {cfg['business_name']}",
        "provider": {"@type": "LocalBusiness", "name": cfg["business_name"], "telephone": cfg.get("phone", "")},
        "areaServed": cfg.get("city", ""),
        "url": f"{site_url}/services/{svc['slug']}/",
    })


def faq_jsonld(faqs):
    if not faqs:
        return ""
    return jsonld_script({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": f["q"],
                "acceptedAnswer": {"@type": "Answer", "text": f["a"]},
            }
            for f in faqs
        ],
    })


# ---------------------------------------------------------------- pages ----

def build_index(cfg, site_url):
    services_cards = "\n".join(
        f'''<div class="card"><h3>{esc(s["name"])}</h3><p>{esc(s["headline"])}</p>
        <a class="more" href="/services/{s["slug"]}/">Learn more &rarr;</a></div>'''
        for s in cfg["services"]
    )
    areas_links = "\n".join(
        f'<a href="/areas/{a["slug"]}/">{esc(a["name"])}</a>' for a in cfg["service_areas"]
    )
    testimonials = "\n".join(
        f'''<div class="t-card"><p class="q">&ldquo;{esc(t["quote"])}&rdquo;</p>
        <p class="who">{esc(t["name"])}</p>
        {"<p class='flag'>Placeholder review — replace with a real customer quote.</p>" if t.get("placeholder") else ""}
        </div>'''
        for t in cfg.get("testimonials", [])
    )
    phone = cfg.get("phone")
    body = f"""
<section class="hero">
  <div class="wrap">
    {{{{H1}}}}
    <p class="sub">{esc(cfg.get('hero_subhead',''))}</p>
    <div class="cta-row">
      <a class="btn primary" href="{tel_href(phone)}">Call {esc(phone_display(phone))}</a>
      <a class="btn secondary" href="/contact/">Get a Free Estimate</a>
    </div>
  </div>
</section>
<div class="trust-strip"><div class="wrap">
  <span>Licensed &amp; Insured</span><span>24/7 Emergency Service</span>
  <span>Free Estimates</span><span>Serving {esc(cfg.get('city',''))} &amp; {esc(cfg.get('state',''))}</span>
</div></div>
<section><div class="wrap">
  <h2>Our Services</h2>
  <div class="grid">{services_cards}</div>
</div></section>
<section><div class="wrap">
  <h2>About {esc(cfg['business_name'])}</h2>
  {paragraphs(cfg.get('about',''))}
</div></section>
<section class="testimonials"><div class="wrap">
  <h2>What Neighbors Say</h2>
  <div class="grid">{testimonials}</div>
</div></section>
<section><div class="wrap">
  <h2>Areas We Serve</h2>
  <div class="areas-list">{areas_links}</div>
</div></section>
"""
    title = f"{cfg['business_name']} | {cfg['niche']} in {cfg['city']}, {cfg['state']}"
    desc = f"{cfg['niche']} serving {cfg['city']}, {cfg['state']} and nearby areas. Licensed, insured, free estimates. Call {phone_display(phone)}."
    ld = local_business_jsonld(cfg, site_url)
    return page(cfg, title, desc, site_url + "/", cfg.get("hero_headline", cfg["business_name"]), body, ld)


def build_service_page(cfg, svc, site_url):
    faqs_html = "\n".join(
        f'<div class="faq"><h3>{esc(f["q"])}</h3><p>{esc(f["a"])}</p></div>' for f in svc.get("faqs", [])
    )
    other_services = "\n".join(
        f'<div class="card"><h3>{esc(s["name"])}</h3><a class="more" href="/services/{s["slug"]}/">View service &rarr;</a></div>'
        for s in cfg["services"] if s["slug"] != svc["slug"]
    )
    areas_links = "\n".join(
        f'<a href="/areas/{a["slug"]}/">{esc(a["name"])}</a>' for a in cfg["service_areas"]
    )
    phone = cfg.get("phone")
    body = f"""
<section class="hero">
  <div class="wrap">
    {{{{H1}}}}
    <p class="sub">Serving {esc(cfg.get('city',''))}, {esc(cfg.get('state',''))} and the surrounding area.</p>
    <div class="cta-row">
      <a class="btn primary" href="{tel_href(phone)}">Call {esc(phone_display(phone))}</a>
      <a class="btn secondary" href="/contact/">Get a Free Estimate</a>
    </div>
  </div>
</section>
<section><div class="wrap">
  {paragraphs(svc.get('body',''))}
</div></section>
{f'<section><div class="wrap"><h2>Common Questions</h2>{faqs_html}</div></section>' if faqs_html else ''}
<section><div class="wrap">
  <h2>Other Services</h2>
  <div class="grid">{other_services}</div>
</div></section>
<section><div class="wrap">
  <h2>Areas We Serve</h2>
  <div class="areas-list">{areas_links}</div>
</div></section>
"""
    title = f"{svc['name']} in {cfg['city']}, {cfg['state']} | {cfg['business_name']}"
    desc = f"{svc['name']} in {cfg['city']}, {cfg['state']}. {svc['headline']} Call {phone_display(phone)} for a free estimate."
    canonical = f"{site_url}/services/{svc['slug']}/"
    ld = service_jsonld(cfg, svc, site_url) + faq_jsonld(svc.get("faqs"))
    return page(cfg, title, desc, canonical, svc["headline"], body, ld)


def build_area_page(cfg, area, site_url):
    services_links = "\n".join(
        f'<a href="/services/{s["slug"]}/">{esc(s["name"])}</a>' for s in cfg["services"]
    )
    phone = cfg.get("phone")
    h1 = f"{cfg['niche']} in {area['name']}, {cfg.get('state','')}"
    body = f"""
<section class="hero">
  <div class="wrap">
    {{{{H1}}}}
    <p class="sub">{esc(cfg['business_name'])} serves {esc(area['name'])} and the surrounding area.</p>
    <div class="cta-row">
      <a class="btn primary" href="{tel_href(phone)}">Call {esc(phone_display(phone))}</a>
      <a class="btn secondary" href="/contact/">Get a Free Estimate</a>
    </div>
  </div>
</section>
<section><div class="wrap">
  {paragraphs(area.get('body',''))}
</div></section>
<section><div class="wrap">
  <h2>Services in {esc(area['name'])}</h2>
  <div class="areas-list">{services_links}</div>
</div></section>
"""
    title = f"{cfg['niche']} in {area['name']}, {cfg.get('state','')} | {cfg['business_name']}"
    desc = f"{cfg['niche']} serving {area['name']}, {cfg.get('state','')}. Licensed, insured, free estimates. Call {phone_display(phone)}."
    canonical = f"{site_url}/areas/{area['slug']}/"
    return page(cfg, title, desc, canonical, h1, body)


def build_contact_page(cfg, site_url):
    phone = cfg.get("phone")
    email = cfg.get("email", "")
    body = f"""
<section class="hero">
  <div class="wrap">
    {{{{H1}}}}
    <p class="sub">Call, email, or send the form below — we'll get back to you fast.</p>
    <div class="cta-row">
      <a class="btn primary" href="{tel_href(phone)}">Call {esc(phone_display(phone))}</a>
    </div>
  </div>
</section>
<section><div class="wrap">
  <h2>Send Us a Message</h2>
  <form class="contact" action="https://formsubmit.co/{esc(email)}" method="POST">
    <input type="hidden" name="_subject" value="New lead from {esc(cfg['business_name'])} website">
    <input type="hidden" name="_captcha" value="false">
    <input type="text" name="name" placeholder="Your Name" required>
    <input type="tel" name="phone" placeholder="Your Phone" required>
    <input type="email" name="email" placeholder="Your Email">
    <textarea name="message" rows="5" placeholder="What do you need help with?" required></textarea>
    <button type="submit">Send Message</button>
  </form>
</div></section>
"""
    title = f"Contact {cfg['business_name']} | {cfg['niche']} in {cfg['city']}, {cfg['state']}"
    desc = f"Contact {cfg['business_name']} for {cfg['niche']} in {cfg['city']}, {cfg['state']}. Call {phone_display(phone)} or send a message."
    return page(cfg, title, desc, site_url + "/contact/", f"Contact {cfg['business_name']}", body)


def build_404_page(cfg, site_url):
    body = """
<section><div class="wrap" style="padding:80px 0;text-align:center;">
  {{H1}}
  <p><a href="/">Return to the homepage</a>.</p>
</div></section>
"""
    return page(cfg, "Page Not Found | " + cfg["business_name"], "Page not found.",
                site_url + "/404.html", "Page Not Found", body)


# ---------------------------------------------------------------- build ----

def build(cfg, out_dir, site_url):
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    def write(rel_path, content):
        p = out_dir / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        written.append(rel_path)

    write("index.html", build_index(cfg, site_url))
    for svc in cfg["services"]:
        write(f"services/{svc['slug']}/index.html", build_service_page(cfg, svc, site_url))
    for area in cfg["service_areas"]:
        write(f"areas/{area['slug']}/index.html", build_area_page(cfg, area, site_url))
    write("contact/index.html", build_contact_page(cfg, site_url))
    write("404.html", build_404_page(cfg, site_url))

    # sitemap + robots
    urls = ["/", "/contact/"] + [f"/services/{s['slug']}/" for s in cfg["services"]] \
        + [f"/areas/{a['slug']}/" for a in cfg["service_areas"]]
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        sitemap.append(f"  <url><loc>{site_url}{u}</loc></url>")
    sitemap.append("</urlset>")
    write("sitemap.xml", "\n".join(sitemap) + "\n")
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {site_url}/sitemap.xml\n")

    return written


# ---------------------------------------------------------------- check ----

def check(out_dir):
    """Validate the built dist/: expected pages exist, exactly one <h1> per HTML
    page, and every <script type="application/ld+json"> block parses as JSON."""
    errors = []
    html_files = sorted(out_dir.rglob("*.html"))
    if not html_files:
        return [f"No HTML files found in {out_dir}"]

    for f in html_files:
        text = f.read_text(encoding="utf-8")
        h1_count = len(re.findall(r"<h1[ >]", text))
        if h1_count != 1:
            errors.append(f"{f.relative_to(out_dir)}: expected exactly one <h1>, found {h1_count}")
        for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', text, re.S):
            try:
                json.loads(m.group(1))
            except json.JSONDecodeError as e:
                errors.append(f"{f.relative_to(out_dir)}: invalid JSON-LD ({e})")
        if "<title>" not in text:
            errors.append(f"{f.relative_to(out_dir)}: missing <title>")
        if 'name="description"' not in text:
            errors.append(f"{f.relative_to(out_dir)}: missing meta description")

    for required in ("sitemap.xml", "robots.txt", "index.html", "404.html", "contact/index.html"):
        if not (out_dir / required).exists():
            errors.append(f"missing required file: {required}")

    return errors


# ---------------------------------------------------------------------- main

def resolve_config_path(arg):
    p = Path(arg)
    if p.suffix == ".json" and p.exists():
        return p
    site_json = SITES_DIR / arg / "site.json"
    if site_json.exists():
        return site_json
    sys.exit(f"Could not find site.json for '{arg}' (looked at {site_json})")


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    do_check = "--check" in args
    args = [a for a in args if a != "--check"]
    if not args:
        sys.exit(__doc__)

    cfg_path = resolve_config_path(args[0])
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    slug = cfg_path.parent.name
    out_dir = cfg_path.parent / "dist"

    site_url = cfg.get("site_url", f"https://{slug}.example.com")

    written = build(cfg, out_dir, site_url)
    print(f"Built {len(written)} files to {out_dir}")
    for w in written:
        print(f"  {w}")

    if do_check or True:  # self-check always runs after a build
        errors = check(out_dir)
        if errors:
            print(f"\nCHECK FAILED — {len(errors)} issue(s):")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        else:
            print(f"\nCHECK OK — {len(written)} files, all pages have one <h1>, all JSON-LD valid.")


if __name__ == "__main__":
    main()
