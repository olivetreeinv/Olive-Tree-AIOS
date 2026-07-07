#!/usr/bin/env python3
"""
Olive Tree Investments — GHL Workflow Content Export

Pulls full workflow step content (emails/SMS/delays) from GHL's INTERNAL
backend — the public API only lists workflow names, not step bodies.
Auth = the `token-id` header GHL's own SPA sends to
services.leadconnectorhq.com / backend.leadconnectorhq.com. We capture it
the same way scripts/wiki_clientclub.py does: launch Chromium via Playwright
with Brian's Chrome cookies, load the GHL app, and sniff the header off the
first backend request. Requires Brian logged into GHL in Chrome.

Usage:
  python3 scripts/ghl_workflow_export.py                 # Playwright capture + export
  python3 scripts/ghl_workflow_export.py --token-id XXX  # skip Playwright
  python3 scripts/ghl_workflow_export.py --workflow-id <id>  # just one

Output:
  archives/ghl-export-2026-07-06/workflows/<name>.json  — raw API response
  archives/ghl-export-2026-07-06/workflows/<name>.md    — human-readable steps

NOTE: the internal endpoints below are educated guesses (the backend is
undocumented). If they all 404, run once with Brian watching DevTools on the
workflow editor page and update ENDPOINT_TEMPLATES with the real URL.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
EXPORT_DIR = ROOT / "archives" / "ghl-export-2026-07-06"
OUT_DIR = EXPORT_DIR / "workflows"
WORKFLOWS_JSON = EXPORT_DIR / "workflows.json"

GHL_APP = "https://app.gohighlevel.com"
LOCATION_ID = "SLq7B2pldVzfQLKjGpvw"

# ponytail: endpoint guesses — internal backend is undocumented; adjust at runtime
ENDPOINT_TEMPLATES = [
    "https://backend.leadconnectorhq.com/workflow/{wid}",
    "https://backend.leadconnectorhq.com/workflows/{wid}",
    "https://backend.leadconnectorhq.com/workflow/{wid}?locationId={loc}",
    "https://backend.leadconnectorhq.com/workflows/{wid}/actions?locationId={loc}",
    "https://services.leadconnectorhq.com/workflows/{wid}",
    "https://services.leadconnectorhq.com/workflows/{wid}?locationId={loc}",
]


# ─────────────────────────────────────────────
# Token capture (pattern from wiki_clientclub.py::_get_token_via_playwright)
# ─────────────────────────────────────────────

def _get_token_via_playwright() -> tuple[str, dict]:
    """Load the GHL app with Brian's Chrome cookies, sniff token-id header."""
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    print("[auth] Extracting Chrome cookies via yt-dlp …")
    import tempfile as _tf
    _cookie_file = Path(_tf.mktemp(suffix=".txt"))
    try:
        subprocess.run(
            ["yt-dlp", "--cookies-from-browser", "chrome",
             "--cookies", str(_cookie_file),
             "--skip-download", GHL_APP],
            capture_output=True, text=True, timeout=60,
        )
        raw = _cookie_file.read_text() if _cookie_file.exists() else ""
    finally:
        _cookie_file.unlink(missing_ok=True)

    cookies = []
    for line in raw.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.strip().split("\t")
        if len(parts) < 7:
            continue
        domain, _, path, secure, _exp, name, value = parts[:7]
        cookies.append({"name": name, "value": value,
                        "domain": domain.lstrip("."), "path": path,
                        "secure": secure.upper() == "TRUE"})
    if not cookies:
        raise RuntimeError(
            "No cookies exported from Chrome. Log into GHL in Chrome first. "
            "If Chrome is open, close it and retry — yt-dlp needs exclusive DB access."
        )

    captured: dict = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)  # visible: Brian may need to finish login/2FA
        ctx = browser.new_context()
        ctx.add_cookies(cookies)
        page = ctx.new_page()

        def on_request(req):
            if (("leadconnectorhq.com" in req.url)
                    and not captured and "token-id" in req.headers):
                captured.update(req.headers)

        page.on("request", on_request)

        urls = [
            f"{GHL_APP}/v2/location/{LOCATION_ID}/automation/workflows",
            f"{GHL_APP}/v2/location/{LOCATION_ID}/dashboard",
            GHL_APP,
        ]
        print("[auth] Loading GHL app to capture token-id (log in if prompted) …")
        for url in urls:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except PWTimeout:
                pass
            deadline = time.time() + 60  # generous: allows manual login
            while time.time() < deadline and not captured:
                page.wait_for_timeout(500)
            if captured:
                break
        browser.close()

    if not captured or "token-id" not in captured:
        raise RuntimeError(
            "Could not capture token-id from the GHL app.\n"
            "Workaround: pass it manually with --token-id <value>.\n"
            "Get it from Chrome DevTools → Network → any request to "
            "backend.leadconnectorhq.com → Request Headers → token-id."
        )
    token_id = captured["token-id"]
    print(f"[auth] token-id captured (first 20 chars: {token_id[:20]}…)")
    return token_id, captured


def _headers(token_id: str, extra: dict) -> dict:
    base = {
        "token-id": token_id,
        "channel": "APP",
        "source": "WEB_USER",
        "version": "2021-07-28",
        "content-type": "application/json",
    }
    for k in ("x-cp-build-version", "x-middleware", "x-platform-details", "x-request-source"):
        if k in extra:
            base[k] = extra[k]
    return base


# ─────────────────────────────────────────────
# Fetch + render
# ─────────────────────────────────────────────

def fetch_workflow(wid: str, hdrs: dict) -> dict:
    tried = []
    for tmpl in ENDPOINT_TEMPLATES:
        url = tmpl.format(wid=wid, loc=LOCATION_ID)
        try:
            r = requests.get(url, headers=hdrs, timeout=30)
        except requests.RequestException as ex:
            tried.append(f"{url} → {ex}")
            continue
        if r.ok:
            try:
                data = r.json()
            except ValueError:
                tried.append(f"{url} → 200 but non-JSON")
                continue
            print(f"  hit: {url}")
            return data
        tried.append(f"{url} → HTTP {r.status_code}")
    raise RuntimeError(
        f"All endpoint guesses failed for workflow {wid}:\n  " + "\n  ".join(tried) +
        "\nOpen the workflow editor in Chrome with DevTools → Network, find the "
        "request that returns the step list, and add its URL to ENDPOINT_TEMPLATES."
    )


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def render_md(name: str, data: dict) -> str:
    """Best-effort human-readable dump — walks any list of step/action dicts."""
    lines = [f"# GHL Workflow — {name}", ""]
    # Find the actions/steps list wherever it lives
    steps = None
    for key in ("actions", "steps", "nodes"):
        found = _find_key(data, key)
        if isinstance(found, list) and found:
            steps = found
            break
    if not steps:
        lines.append("_Could not locate a steps/actions list — see raw JSON._")
        return "\n".join(lines)
    for i, s in enumerate(steps, 1):
        if not isinstance(s, dict):
            continue
        stype = s.get("type") or s.get("actionType") or s.get("name") or "?"
        lines.append(f"## Step {i} — {stype}")
        for field in ("delay", "wait", "waitTime", "interval"):
            if s.get(field):
                lines.append(f"- **Delay:** {s[field]}")
        meta = s.get("meta") or s.get("data") or s.get("config") or s
        for field in ("subject", "title"):
            if isinstance(meta, dict) and meta.get(field):
                lines.append(f"- **Subject:** {meta[field]}")
        for field in ("body", "html", "message", "templateBody"):
            if isinstance(meta, dict) and meta.get(field):
                lines.append(f"\n```\n{meta[field]}\n```")
                break
        lines.append("")
    return "\n".join(lines)


def _find_key(obj, key):
    """Depth-first search for a key anywhere in nested dicts/lists."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = _find_key(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_key(v, key)
            if r is not None:
                return r
    return None


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Export GHL workflow step content")
    p.add_argument("--token-id", default="", help="Skip Playwright; supply token-id from DevTools")
    p.add_argument("--workflow-id", default="", help="Export a single workflow id")
    args = p.parse_args()

    workflows = json.loads(WORKFLOWS_JSON.read_text())["workflows"]
    if args.workflow_id:
        workflows = [w for w in workflows if w["id"] == args.workflow_id]
        if not workflows:
            raise SystemExit(f"ERROR: workflow id {args.workflow_id} not in {WORKFLOWS_JSON}")

    if args.token_id:
        token_id, extra = args.token_id, {}
        print(f"[auth] Using supplied token-id (first 20 chars: {token_id[:20]}…)")
    else:
        token_id, extra = _get_token_via_playwright()
    hdrs = _headers(token_id, extra)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = err = 0
    for w in workflows:
        print(f"\n[{w['name']}]")
        try:
            data = fetch_workflow(w["id"], hdrs)
        except RuntimeError as ex:
            print(f"  ERROR: {ex}", file=sys.stderr)
            err += 1
            continue
        slug = _slug(w["name"])
        (OUT_DIR / f"{slug}.json").write_text(json.dumps(data, indent=2))
        (OUT_DIR / f"{slug}.md").write_text(render_md(w["name"], data))
        print(f"  wrote {OUT_DIR / slug}.json + .md")
        ok += 1

    print(f"\nDone: {ok} exported, {err} failed.")
    if err:
        sys.exit(1)


if __name__ == "__main__":
    main()
