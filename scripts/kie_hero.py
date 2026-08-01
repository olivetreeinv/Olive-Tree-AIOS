#!/usr/bin/env python3
"""
kie_hero.py — generate a light-&-airy carousel hero via kie.ai, with a safe
credit check. Returns a local image path (or MP4 for motion), or None so the
caller falls back to Pexels. Drop-in replacement for higgsfield_hero.py.

kie.ai is a pay-per-generation reseller API (one key, many models):
  - image:  GPT Image 2  (`gpt-image-2-text-to-image`)  ~6 credits (~$0.03)
  - motion: image-to-video model (Sora 2 / Kling) — set MOTION_MODEL below

All kie jobs are async: createTask -> poll recordInfo -> resultJson.resultUrls.
Guards the 2026-06-30 billed-but-empty incident: checks balance BEFORE spending
and verifies a real result URL came back before writing.

CLI:
    python3 scripts/kie_hero.py --prompt "Atlanta Midtown skyline" --out output/hero.png
    python3 scripts/kie_hero.py --prompt "..." --out hero.mp4 --motion   # image->video
    python3 scripts/kie_hero.py --check                                   # credit balance only
"""
from __future__ import annotations
import argparse
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://api.kie.ai/api/v1/jobs"
VEO_BASE = "https://api.kie.ai/api/v1/veo"  # Veo has its own endpoint, not /jobs
IMAGE_MODEL = "gpt-image-2-text-to-image"
MOTION_MODEL = "veo3_fast"  # kie doesn't carry Luma; Veo 3 Fast is the cheapest quality video (~$0.40/8s)
IMAGE_COST = 6  # credits; motion is far higher — checked live, not hardcoded
LIGHT_AIRY = ("Bright, light and airy editorial real estate photograph. {subject}. "
              "Soft natural daylight, airy whites, gentle depth of field, clean negative "
              "space, premium magazine quality. No text, no people, no logos.")


def _key() -> str | None:
    key = os.environ.get("KIE_API_KEY")
    if key:
        return key
    env = ROOT / ".env"  # not always exported into the shell
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("KIE_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


def _headers(key):
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def credits() -> float | None:
    """Available credit balance, or None if unauthenticated/unreadable."""
    key = _key()
    if not key:
        return None
    try:
        r = requests.get("https://api.kie.ai/api/v1/chat/credit", headers=_headers(key), timeout=30)
        return float(r.json()["data"])
    except (requests.RequestException, KeyError, ValueError, TypeError):
        return None


def _run_task(key, model, input_obj, out_path, poll_s=6, timeout_s=600) -> Path | None:
    """createTask -> poll -> download first result URL. None on any failure."""
    try:
        r = requests.post(f"{BASE}/createTask", headers=_headers(key),
                          json={"model": model, "input": input_obj}, timeout=60)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        print(f"kie: createTask request failed ({e}) — falling back", file=sys.stderr)
        return None
    if data.get("code") != 200 or not data.get("data", {}).get("taskId"):
        print(f"kie: createTask failed ({data.get('msg')}) — falling back", file=sys.stderr)
        return None
    task_id = data["data"]["taskId"]
    print(f"kie: task {task_id} created (billed — recoverable via /recordInfo)", file=sys.stderr)

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(poll_s)
        try:
            rec = requests.get(f"{BASE}/recordInfo", headers=_headers(key),
                               params={"taskId": task_id}, timeout=30).json()
        except requests.RequestException:
            continue  # transient blip mid-poll must not abandon a billed task
        state = rec.get("data", {}).get("state")
        if state == "success":
            import json
            urls = json.loads(rec["data"]["resultJson"] or "{}").get("resultUrls") or []
            if not urls:
                print("kie: success but no resultUrls (billed-but-empty?) — falling back", file=sys.stderr)
                return None
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                dl = requests.get(urls[0], timeout=120)
                dl.raise_for_status()
            except requests.RequestException:
                continue  # result stays available — retry download next poll
            out_path.write_bytes(dl.content)
            return out_path
        if state == "fail":
            print(f"kie: generation failed ({rec['data'].get('failMsg')}) — falling back", file=sys.stderr)
            return None
    print("kie: timed out waiting for result — falling back", file=sys.stderr)
    return None


def generate_hero(prompt, out_path, aspect_ratio="4:3", subject_wrap=True) -> Path | None:
    """Generate a hero still. Returns local path, or None to trigger Pexels fallback."""
    key = _key()
    if not key:
        print("kie: KIE_API_KEY not set — falling back", file=sys.stderr)
        return None
    bal = credits()
    if bal is not None and bal < IMAGE_COST:
        print(f"kie: {bal} credits < {IMAGE_COST} needed — falling back to Pexels", file=sys.stderr)
        return None
    full = LIGHT_AIRY.format(subject=prompt) if subject_wrap else prompt
    inp = {"prompt": full, "aspect_ratio": aspect_ratio}
    for attempt in range(3):  # GPT Image 2 intermittently 500s upstream; failed gens cost 0 credits
        p = _run_task(key, IMAGE_MODEL, inp, out_path)
        if p:
            return p
        if attempt < 2:
            print(f"kie: retrying image ({attempt + 1}/2)...", file=sys.stderr)
    return None


def generate_motion(image_url, out_path, prompt="Subtle slow cinematic push-in, gentle parallax") -> Path | None:
    """Animate a still (public image URL) into a short MP4 via Veo 3 Fast. None on failure.
    Veo uses its own endpoint + poll shape, distinct from the /jobs models."""
    import json
    key = _key()
    if not key:
        return None
    try:
        resp = requests.post(f"{VEO_BASE}/generate", headers=_headers(key),
                             json={"model": MOTION_MODEL, "prompt": prompt,
                                   "imageUrls": [image_url], "mode": "FIRST_AND_LAST_FRAMES_2_VIDEO"},
                             timeout=60)
        resp.raise_for_status()
        r = resp.json()
    except requests.RequestException as e:
        print(f"kie/veo: generate request failed ({e}) — falling back", file=sys.stderr)
        return None
    task_id = r.get("data", {}).get("taskId")
    if r.get("code") != 200 or not task_id:
        print(f"kie/veo: generate failed ({r.get('msg')}) — falling back", file=sys.stderr)
        return None
    print(f"kie/veo: task {task_id} created (billed — recoverable via /record-info)", file=sys.stderr)
    deadline = time.time() + 900
    while time.time() < deadline:
        time.sleep(10)
        try:
            rec = requests.get(f"{VEO_BASE}/record-info", headers=_headers(key),
                               params={"taskId": task_id}, timeout=30).json().get("data", {})
        except requests.RequestException:
            continue  # transient blip mid-poll must not abandon a billed task
        flag = rec.get("successFlag")
        if flag == 1:
            resp = rec.get("response") or {}
            # resultUrls is the primary field; fullResultUrls only for extended videos
            urls = resp.get("resultUrls") or resp.get("fullResultUrls") or resp.get("originUrls") or []
            if not urls:
                print(f"kie/veo: success but no video url (billed!) — raw response: {json.dumps(resp)}",
                      file=sys.stderr)
                return None
            out_path = Path(out_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                dl = requests.get(urls[0], timeout=180)
                dl.raise_for_status()
            except requests.RequestException:
                continue  # result stays available — retry download next poll
            out_path.write_bytes(dl.content)
            return out_path
        if flag in (2, 3):
            print(f"kie/veo: failed ({rec.get('errorMessage')}) — falling back", file=sys.stderr)
            return None
    print("kie/veo: timed out — falling back", file=sys.stderr)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt")
    ap.add_argument("--out")
    ap.add_argument("--aspect", default="4:3")
    ap.add_argument("--motion", action="store_true", help="image-to-video (--prompt is an image URL)")
    ap.add_argument("--check", action="store_true", help="print credit balance and exit")
    ap.add_argument("--raw", action="store_true", help="use --prompt verbatim (skip light-airy wrapper)")
    a = ap.parse_args()
    if a.check:
        print(f"credits: {credits()}")
        return
    if not a.prompt or not a.out:
        ap.error("provide --prompt and --out, or use --check")
    p = (generate_motion(a.prompt, a.out) if a.motion
         else generate_hero(a.prompt, a.out, aspect_ratio=a.aspect, subject_wrap=not a.raw))
    print(p if p else "FALLBACK (no image generated)")


if __name__ == "__main__":
    sys.exit(main())
