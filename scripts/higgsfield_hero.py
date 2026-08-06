#!/usr/bin/env python3
"""
higgsfield_hero.py — generate a light-&-airy carousel hero via Higgsfield
nano_banana_2, with a safe credit check. Returns a local image path, or None so
the caller falls back to Pexels.

Guards against the 2026-06-30 incident (a 502 that billed credits with no output):
checks the balance BEFORE spending, and verifies a real result_url came back.

Binary is `higgsfield` (NOT `hf` — that's the HuggingFace CLI on this machine).
nano_banana_2 = 2 credits/image.

CLI:
    python3 scripts/higgsfield_hero.py --prompt "..." --out output/hero.png
    python3 scripts/higgsfield_hero.py --check          # print credit balance only
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import requests

MODEL = "nano_banana_2"
COST = 2
LIGHT_AIRY = ("Bright, light and airy editorial real estate photograph. {subject}. "
              "Soft natural daylight, airy whites, gentle depth of field, clean negative "
              "space, premium magazine quality, vertical 4:5 composition.")


def credits() -> int | None:
    """Return available credits, or None if not authenticated / unreadable."""
    r = subprocess.run(["higgsfield", "account", "status"], capture_output=True, text=True, timeout=30)
    m = re.search(r"(\d+)\s*credits", r.stdout + r.stderr)
    if "Not authenticated" in (r.stdout + r.stderr) or "expired" in (r.stdout + r.stderr).lower():
        return None
    return int(m.group(1)) if m else None


def generate_hero(prompt: str, out_path, subject_wrap: bool = True) -> Path | None:
    """Generate a hero image. Returns local path, or None to trigger Pexels fallback."""
    bal = credits()
    if bal is None:
        print("higgsfield: not authenticated (run: higgsfield auth login) — falling back", file=sys.stderr)
        return None
    if bal < COST:
        print(f"higgsfield: {bal} credits < {COST} needed — falling back to Pexels", file=sys.stderr)
        return None

    full = LIGHT_AIRY.format(subject=prompt) if subject_wrap else prompt
    r = subprocess.run(
        ["higgsfield", "generate", "create", MODEL, "--prompt", full, "--wait",
         "--wait-timeout", "10m", "--json"],
        capture_output=True, text=True, timeout=700,
    )
    out = r.stdout.strip()
    if r.returncode != 0 or not out:
        print(f"higgsfield: generation failed ({r.stderr[:200]}) — falling back", file=sys.stderr)
        return None
    try:
        data = json.loads(out)
        obj = data[0] if isinstance(data, list) else data
        url = obj.get("result_url") or obj.get("resultUrl")
    except (json.JSONDecodeError, AttributeError, IndexError):
        print("higgsfield: could not parse result — falling back", file=sys.stderr)
        return None
    if not url:
        print("higgsfield: no result_url (billed-but-empty?) — falling back", file=sys.stderr)
        return None

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(requests.get(url, timeout=60).content)
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt")
    ap.add_argument("--out")
    ap.add_argument("--check", action="store_true", help="print credit balance and exit")
    ap.add_argument("--raw", action="store_true", help="use --prompt verbatim (skip light-airy wrapper)")
    a = ap.parse_args()
    if a.check:
        print(f"credits: {credits()}")
        return
    if not a.prompt or not a.out:
        ap.error("provide --prompt and --out, or use --check")
    p = generate_hero(a.prompt, a.out, subject_wrap=not a.raw)
    print(p if p else "FALLBACK (no image generated)")


if __name__ == "__main__":
    sys.exit(main())
