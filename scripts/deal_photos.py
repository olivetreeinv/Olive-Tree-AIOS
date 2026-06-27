#!/usr/bin/env python3
"""
Olive Tree Investments — Deal Photo Resolver

Three representative, license-clean photos per deal — all FREE, no API key:
  • property  — clickable Google Maps link to the exact address (see the building)
  • area      — the city/submarket's lead photo from Wikipedia
  • community — the market's signature draw (e.g. The Battery) from Wikipedia

Why Wikipedia: it serves embeddable, public/CC images via a free, keyless REST
endpoint. Listing portals (apartments.com, Crexi, LoopNet) 403 our sandbox, and
Google image search has no free API — so we use Wikipedia for the embedded shots
and a plain Google Maps link for the building itself. No billing, no Street View.

Usage:
    from deal_photos import resolve_photos, render_markdown
    photos = resolve_photos("641 Powder Springs St SE, Smyrna, GA 30080", "30080")
    print(render_markdown(photos))
"""

import re
from functools import lru_cache
from urllib.parse import quote, quote_plus

import requests

# Per buy-box zip → Wikipedia article titles for the area + community photos.
# Add markets as they go live. Unknown zips fall back to parsing the address for
# the area shot; a wrong/missing title degrades to a Google image-search link.
MARKET_PHOTOS = {
    "30080": {"area": "Smyrna, Georgia",        "community": "The Battery Atlanta"},
    "30341": {"area": "Chamblee, Georgia",      "community": "Assembly Atlanta"},
    "30005": {"area": "Alpharetta, Georgia",    "community": "Avalon (development)"},
    "37207": {"area": "Nashville, Tennessee",   "community": "Germantown, Nashville"},
    "37115": {"area": "Madison, Tennessee",     "community": None},
    "37408": {"area": "Chattanooga, Tennessee", "community": "Chattanooga"},
    "35801": {"area": "Huntsville, Alabama",    "community": "Redstone Arsenal"},
    "35205": {"area": "Birmingham, Alabama",    "community": "Five Points South"},
    "35806": {"area": "Huntsville, Alabama",    "community": "Cummings Research Park"},
    "37087": {"area": "Lebanon, Tennessee",     "community": None},
    "37918": {"area": "Knoxville, Tennessee",   "community": None},
    "37804": {"area": "Maryville, Tennessee",   "community": None},
    "37615": {"area": "Johnson City, Tennessee", "community": None},
}

_STATE_NAMES = {"GA": "Georgia", "TN": "Tennessee", "AL": "Alabama",
                "FL": "Florida", "SC": "South Carolina", "NC": "North Carolina"}

_WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
_UA = "OliveTreeAIOS/1.0 (deal photo resolver)"


@lru_cache(maxsize=128)
def fetch_wikipedia_image(title, timeout=8):
    """Return the lead image URL for a Wikipedia article title, or None.

    Cached: a batch run (e.g. lets-get-to-work) over many deals in the same
    market resolves each area/community title once, not once per deal.
    """
    if not title:
        return None
    try:
        r = requests.get(_WIKI_SUMMARY.format(quote(title.replace(" ", "_"))),
                         headers={"User-Agent": _UA}, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError):
        return None
    # Prefer the full-res original; fall back to the thumbnail.
    for key in ("originalimage", "thumbnail"):
        src = (data.get(key) or {}).get("source")
        if src:
            return src
    return None


def _city_from_address(address):
    """Best-effort 'City, State' Wikipedia title from a street address."""
    # "641 Powder Springs St SE, Smyrna, GA 30080" → "Smyrna, Georgia"
    parts = [p.strip() for p in address.split(",") if p.strip()]
    if len(parts) < 2:
        return None
    city = parts[-2]
    m = re.search(r"\b([A-Z]{2})\b", parts[-1])
    state = _STATE_NAMES.get(m.group(1)) if m else None
    return f"{city}, {state}" if state else city


def property_link(address):
    """Free Google Maps link to the exact address — click to see the building."""
    return {"kind": "link", "name": "View on Google Maps",
            "url": f"https://www.google.com/maps/search/{quote_plus(address)}"}


def _wiki_cell(title):
    """Embedded Wikipedia image if found, else a Google image-search link."""
    if not title:
        return None
    url = fetch_wikipedia_image(title)
    if url:
        return {"kind": "image", "url": url, "name": title}
    return {"kind": "link", "name": title,
            "url": f"https://www.google.com/search?q={quote_plus(title)}&tbm=isch"}


def resolve_photos(address, zip_code=None):
    """Resolve property (link) + area & community (embedded Wikipedia photos)."""
    cfg = MARKET_PHOTOS.get(str(zip_code or ""), {})
    area_title = cfg.get("area") or _city_from_address(address or "")
    return {
        "property": property_link(address or ""),
        "area": _wiki_cell(area_title),
        "community": _wiki_cell(cfg.get("community")),
    }


def render_markdown(photos):
    """Render the three photos as markdown — images embed, links are clickable."""
    def cell(label, p):
        if not p:
            return f"**{label}:** _(none for this market yet)_"
        if p["kind"] == "image":
            return f"**{label}** — {p.get('name', '')}\n\n![{label}]({p['url']})"
        return f"**{label}:** [{p.get('name', 'View')} ↗]({p['url']})"

    return "\n\n".join([
        "### Photos",
        cell("📸 Property", photos["property"]),
        cell("🗺️ Area", photos["area"]),
        cell("🏙️ Community", photos["community"]),
    ])


if __name__ == "__main__":
    import argparse
    import json
    import re

    p = argparse.ArgumentParser(description="Resolve the 3-photo block for a deal.")
    p.add_argument("--address", help="Full property address (include zip)")
    p.add_argument("--zip", dest="zip_code", help="5-digit zip; auto-extracted from --address if omitted")
    p.add_argument("--market", help="Market name (accepted for compatibility; resolution keys off zip)")
    # Positional fallback: address [zip] — keeps older callers working.
    p.add_argument("pos", nargs="*", help=argparse.SUPPRESS)
    args = p.parse_args()

    addr = args.address or (args.pos[0] if len(args.pos) > 0 else
                            "641 Powder Springs St SE, Smyrna, GA 30080")
    zc = args.zip_code or (args.pos[1] if len(args.pos) > 1 else None)
    if not zc:
        m = re.search(r"\b(\d{5})\b", addr)
        zc = m.group(1) if m else "30080"

    result = resolve_photos(addr, zc)
    print(json.dumps(result, indent=2))
    print("\n" + "=" * 50)
    print(render_markdown(result))
