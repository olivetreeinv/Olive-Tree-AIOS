#!/usr/bin/env python3
"""
wiki_clientclub.py — Ingest Multifamily Schooled course videos into wiki/mfs-videos/course/.

Pipeline:
  1. enumerate   — Playwright auth + walk ClientClub API → _clientclub_index.json
  2. transcribe  — yt-dlp download + ffmpeg audio + Groq whisper → _transcripts/{post_id}.txt
  3. map         — Haiku distill each transcript → course/{slug}-{post_id[:8]}.md
  4. synthesize  — Opus ranks all candidates → _skill-upgrades-clientclub.md

Usage:
    python scripts/wiki_clientclub.py --stage enumerate
    python scripts/wiki_clientclub.py --stage all --limit 3  # smoke test
    python scripts/wiki_clientclub.py --stage all            # full run (78 videos)

Resumable: skips videos whose transcript / wiki page already exists.
"""

import argparse
import concurrent.futures as cf
import datetime
import json
import math
import os
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
WIKI = ROOT / "wiki"
OUT = WIKI / "mfs-videos" / "course"
RAW = OUT / "_transcripts"
CAND = OUT / "_candidates"
IDX = OUT / "_clientclub_index.json"
LOG = WIKI / "_log.md"

MAP_MODEL = "claude-haiku-4-5"
SYNTH_MODEL = "claude-opus-4-8"

PRODUCT_ID = "41f274ef-7b97-4b70-8fd8-a4086f1b515a"
LOCATION_ID = "rCxcNVyUUodqRgoUBbIj"
BASE_URL = "https://multifamilyschooled-login.app.clientclub.net"
MEMBERSHIP_API = "https://services.leadconnectorhq.com/membership"

TARGET_SKILLS = ["deal-analysis", "lets-get-to-work", "market-research", "broker-search"]

# ---- env / clients ----------------------------------------------------------
_env = ROOT / ".env"
if not os.environ.get("ANTHROPIC_API_KEY") and _env.exists():
    for _l in _env.read_text().splitlines():
        _l = _l.strip()
        if _l and not _l.startswith("#") and "=" in _l:
            _k, _, _v = _l.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

import anthropic  # noqa: E402
import groq as groq_lib  # noqa: E402

client = anthropic.Anthropic(max_retries=6)
groq_client = groq_lib.Groq(api_key=GROQ_API_KEY)

# Rate throttle for Haiku (same as wiki_youtube.py)
TPM_LIMIT = 45000
_throttle_lock = threading.Lock()
_window: list[tuple[float, int]] = []


def throttle(tokens: int) -> None:
    while True:
        with _throttle_lock:
            now = time.time()
            _window[:] = [(t, n) for t, n in _window if now - t < 60]
            used = sum(n for _, n in _window)
            if used + tokens <= TPM_LIMIT or not _window:
                _window.append((now, tokens))
                return
            wait = 60 - (now - _window[0][0]) + 0.5
        time.sleep(max(wait, 1.0))


def slugify(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s.lower()).strip()
    return re.sub(r"[\s_-]+", "-", s)[:70] or "untitled"


# ---- stage 1: auth + enumerate ----------------------------------------------
def _get_token_via_playwright() -> tuple[str, dict]:
    """
    Inject Chrome ClientClub cookies into headless Chromium, load /home,
    intercept the first membership API request, and return the token-id + headers.
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    print("[enumerate] Extracting Chrome cookies via yt-dlp …")
    import tempfile as _tf
    _cookie_file = Path(_tf.mktemp(suffix=".txt"))
    try:
        subprocess.run(
            ["yt-dlp", "--cookies-from-browser", "chrome",
             "--cookies", str(_cookie_file),
             "--skip-download", BASE_URL],
            capture_output=True, text=True, timeout=60,
        )
        raw_cookie_text = _cookie_file.read_text() if _cookie_file.exists() else ""
    finally:
        _cookie_file.unlink(missing_ok=True)

    # Parse Netscape-format cookies file
    cookies = []
    for line in raw_cookie_text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.strip().split("\t")
        if len(parts) < 7:
            continue
        domain, _, path, secure, _exp, name, value = parts[:7]
        cookies.append({
            "name": name, "value": value,
            "domain": domain.lstrip("."), "path": path,
            "secure": secure.upper() == "TRUE",
        })

    if not cookies:
        raise RuntimeError(
            "No cookies exported from Chrome. "
            "Make sure you are logged into Multifamily Schooled in Chrome. "
            "If Chrome is open, close it and retry — yt-dlp needs exclusive DB access."
        )

    captured: dict = {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context()
        ctx.add_cookies(cookies)
        page = ctx.new_page()

        def on_request(req):
            if ("services.leadconnectorhq.com/membership" in req.url
                    and not captured and "token-id" in req.headers):
                captured.update(req.headers)

        page.on("request", on_request)

        urls_to_try = [
            f"{BASE_URL}/courses/products/{PRODUCT_ID}",
            f"{BASE_URL}/home",
            (f"{BASE_URL}/courses/products/{PRODUCT_ID}/categories/"
             "ac7d7648-b473-4479-8c2e-e7c14e166131/posts/"
             "79a9847a-7e26-42de-bcb4-971301fab9dd"),
        ]
        print(f"[enumerate] Loading product page to capture token-id …")
        for url in urls_to_try:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
            except PWTimeout:
                pass
            final_url = page.url
            print(f"[enumerate]   landed on: {final_url[:80]}")
            # Wait up to 15s for a membership API request with token-id
            deadline = time.time() + 15
            while time.time() < deadline and not captured:
                page.wait_for_timeout(500)
            if captured:
                break
            page.wait_for_timeout(2000)

        browser.close()

    if not captured or "token-id" not in captured:
        raise RuntimeError(
            "Could not capture token-id from ClientClub SPA.\n"
            "Workaround: pass the token manually with --token-id <value>.\n"
            "Get it from Chrome DevTools → Network tab → any request to "
            "services.leadconnectorhq.com → Request Headers → token-id."
        )

    token_id = captured["token-id"]
    print("[enumerate] token-id captured")
    return token_id, captured


def _api_headers(token_id: str, extra: dict) -> dict:
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


def enumerate_posts(product_id: str = PRODUCT_ID, token_id: str = "") -> list[dict]:
    import httpx

    if token_id:
        extra_hdrs: dict = {}
        print("[enumerate] Using supplied token-id")
    else:
        token_id, extra_hdrs = _get_token_via_playwright()
    hdrs = _api_headers(token_id, extra_hdrs)

    def get(url: str) -> dict:
        resp = httpx.get(url, headers=hdrs, timeout=20)
        resp.raise_for_status()
        return resp.json()

    # Fetch categories
    cats_url = (f"{MEMBERSHIP_API}/locations/{LOCATION_ID}/categories"
                f"?productId={product_id}&limit=100")
    cats_raw = get(cats_url)
    # API may return a list directly or wrap in {"categories": [...]} / {"data": [...]}
    if isinstance(cats_raw, list):
        cats_all = cats_raw
    else:
        cats_all = cats_raw.get("categories") or cats_raw.get("data") or []
    categories = [c for c in cats_all
                  if not c.get("productId") or c.get("productId") == product_id]
    print(f"[enumerate] {len(categories)} categories found")

    posts = []
    for cat in categories:
        cid = cat.get("id") or cat.get("_id")
        cat_title = cat.get("title", "Unknown")
        posts_url = (f"{MEMBERSHIP_API}/locations/{LOCATION_ID}/posts"
                     f"?category_id={cid}&product_id={product_id}&limit=100")
        try:
            pd = get(posts_url)
        except Exception as e:
            print(f"[enumerate] WARN: could not fetch posts for {cat_title}: {e}")
            continue
        raw_posts = (pd if isinstance(pd, list)
                     else pd.get("posts") or pd.get("data") or [])
        cat_vids = 0
        for p in raw_posts:
            if p.get("contentType") != "video":
                continue
            post_id = p.get("id") or p.get("_id")
            # Per-post detail has asset_urls with the actual video URL
            try:
                detail = get(f"{MEMBERSHIP_API}/locations/{LOCATION_ID}/posts/{post_id}")
                if isinstance(detail, dict):
                    # unwrap if wrapped
                    detail = detail.get("post") or detail
                assets = detail.get("asset_urls") or {}
            except Exception:
                assets = p.get("asset_urls") or {}
            posts.append({
                "post_id": post_id,
                "title": p.get("title", "Untitled"),
                "category_title": cat_title,
                "sequence_no": p.get("sequenceNo", 0),
                "mp4_url": assets.get("url", ""),
                "m3u8_url": assets.get("processedUrl", ""),
                "source_url": (f"{BASE_URL}/courses/products/{product_id}"
                               f"/categories/{cid}/posts/{post_id}"),
            })
            cat_vids += 1
        print(f"[enumerate]   {cat_title}: {len(raw_posts)} posts, {cat_vids} video(s)")

    print(f"[enumerate] Total video posts: {len(posts)}")
    return posts


# ---- stage 2: transcribe ----------------------------------------------------
GROQ_MODEL = "whisper-large-v3-turbo"
CHUNK_SECONDS = 1140   # 19 min — safely under Groq's 25MB limit for mono/16kHz audio
MAX_BYTES = 24_000_000


def _download_audio(mp4_url: str, m3u8_url: str, dest_mp3: Path) -> bool:
    """Download video and extract mono 16kHz audio.

    Prefers mp4_url (cdn.courses.apisystem.tech — publicly accessible, no auth).
    Falls back to m3u8_url only if no mp4 available.
    """
    src = mp4_url or m3u8_url
    if not src:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        tmp_media = Path(tmp) / "media"
        r = subprocess.run(
            ["yt-dlp", "-o", str(tmp_media), src],
            capture_output=True, timeout=1200,
        )
        media_files = sorted(Path(tmp).glob("media*"))
        if r.returncode != 0 or not media_files:
            return False
        media = media_files[0]
        # Extract audio: mono, 16kHz, 48kbps mp3
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", str(media),
             "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k",
             str(dest_mp3)],
            capture_output=True, timeout=300,
        )
        return r.returncode == 0 and dest_mp3.exists()


def _split_audio(mp3: Path) -> list[Path]:
    """Split mp3 into ≤CHUNK_SECONDS chunks if > MAX_BYTES. Returns list of chunk paths."""
    if mp3.stat().st_size <= MAX_BYTES:
        return [mp3]
    try:
        duration_r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(mp3)],
            capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        print(f"[transcribe] WARN: ffprobe timed out on {mp3.name}")
        return [mp3]
    if duration_r.returncode != 0:
        print(f"[transcribe] WARN: ffprobe failed on {mp3.name}: {duration_r.stderr.strip()[:200]}")
        return [mp3]
    try:
        total_sec = float(duration_r.stdout.strip())
    except ValueError:
        return [mp3]
    n_chunks = math.ceil(total_sec / CHUNK_SECONDS)
    chunks = []
    for i in range(n_chunks):
        start = i * CHUNK_SECONDS
        out = mp3.with_stem(f"{mp3.stem}_chunk{i:02d}")
        try:
            r = subprocess.run(
                ["ffmpeg", "-y", "-i", str(mp3), "-ss", str(start),
                 "-t", str(CHUNK_SECONDS), "-c", "copy", str(out)],
                capture_output=True, timeout=900,
            )
        except subprocess.TimeoutExpired:
            print(f"[transcribe] WARN: ffmpeg chunk {i} timed out on {mp3.name}")
            continue
        if r.returncode != 0:
            print(f"[transcribe] WARN: ffmpeg chunk {i} failed on {mp3.name}: {r.stderr.decode(errors='ignore')[:200]}")
            continue
        if out.exists():
            chunks.append(out)
    return chunks or [mp3]


def transcribe_post(p: dict) -> str | None:
    post_id = p["post_id"]
    dest = RAW / f"{post_id}.txt"
    if dest.exists() and dest.stat().st_size > 200:
        return dest.read_text()

    print(f"[transcribe] {p['title'][:50]} ({post_id[:8]})")
    with tempfile.TemporaryDirectory() as tmp:
        mp3 = Path(tmp) / f"{post_id}.mp3"
        if not _download_audio(p["mp4_url"], p["m3u8_url"], mp3):
            print(f"[transcribe] WARN: download failed for {post_id}")
            return None

        chunks = _split_audio(mp3)
        texts = []
        for chunk in chunks:
            with chunk.open("rb") as fh:
                result = groq_client.audio.transcriptions.create(
                    model=GROQ_MODEL,
                    file=(chunk.name, fh, "audio/mpeg"),
                    response_format="text",
                )
            texts.append(result if isinstance(result, str) else result.text)

    full = " ".join(t.strip() for t in texts if t.strip())
    if len(full.split()) < 100:
        print(f"[transcribe] WARN: transcript too short for {post_id}")
        return None
    dest.write_text(full)
    print(f"[transcribe] OK  {len(full.split())} words → {dest.name}")
    return full


# ---- stage 3: map (Haiku per video) ----------------------------------------
MAP_PROMPT = """Distill this transcript of a Justin Brennan multifamily mentorship video for Brian Norton's AIOS.
Brian buys 15-50 unit value-add multifamily in GA/TN/AL. His drag is deal sourcing + underwriting.

Video title: {title}
Module: {module}

Return STRICT JSON, no prose:
{{
  "deal_relevant": "yes" | "partial" | "no",
  "topic": one of ["deal-analysis","market-research","broker-search","capital-raise","asset-mgmt","mindset","other"],
  "summary": "2-3 sentence summary of the deal-relevant content (or note it's off-topic)",
  "takeaways": ["concrete tactic/threshold/script Justin teaches", ...up to 7, quote specific numbers/phrasings],
  "skill_candidates": [
     {{"skill": one of {skills}, "change": "specific minimal improvement", "evidence": "what in the video supports it"}}
  ]
}}
Only include skill_candidates when the video gives a concrete, actionable rule. Empty list if none.

TRANSCRIPT:
{transcript}"""


def map_post(p: dict) -> dict | None:
    post_id = p["post_id"]
    title = p["title"]
    module = p["category_title"]
    slug = slugify(f"{module}-{title}")
    page = OUT / f"{slug}-{post_id[:8]}.md"
    cand_f = CAND / f"{post_id}.json"
    if page.exists() and cand_f.exists():
        return json.loads(cand_f.read_text())

    txt = RAW / f"{post_id}.txt"
    if not txt.exists():
        print(f"[map] NO TRANSCRIPT {post_id[:8]} {title[:40]}")
        return None
    transcript = txt.read_text()

    prompt = MAP_PROMPT.format(title=title, module=module, skills=TARGET_SKILLS,
                               transcript=transcript)
    throttle(len(prompt) // 4 + 400)
    resp = client.messages.create(
        model=MAP_MODEL, max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": {
            "type": "object",
            "properties": {
                "deal_relevant": {"type": "string", "enum": ["yes", "partial", "no"]},
                "topic": {"type": "string"},
                "summary": {"type": "string"},
                "takeaways": {"type": "array", "items": {"type": "string"}},
                "skill_candidates": {"type": "array", "items": {
                    "type": "object",
                    "properties": {
                        "skill": {"type": "string"},
                        "change": {"type": "string"},
                        "evidence": {"type": "string"},
                    },
                    "required": ["skill", "change", "evidence"],
                    "additionalProperties": False,
                }},
            },
            "required": ["deal_relevant", "topic", "summary", "takeaways", "skill_candidates"],
            "additionalProperties": False,
        }}},
    )
    data = json.loads(next((b.text for b in resp.content if b.type == "text"), "{}"))
    data["id"] = post_id
    data["title"] = title
    data["module"] = module

    tk = "\n".join(f"{i+1}. {t}" for i, t in enumerate(data["takeaways"])) or "—"
    page.write_text(
        f"""---
type: mfs-video
collection: course
title: {title.replace('"', "'")}
topic: {data['topic']}
instructor: Justin Brennan
source: Multifamily Schooled (One on One Mentorship)
module: {module}
content_type: course-video
deal_relevant: {data['deal_relevant']}
post_id: {post_id}
url: {p['source_url']}
date_added: {datetime.date.today()}
---

## Summary
{data['summary']}

---

## Key Takeaways
{tk}

---

## Source
[Watch on Multifamily Schooled]({p['source_url']}) — Module: {module}
"""
    )
    cand_f.write_text(json.dumps(data, indent=2))
    print(f"[map] {data['deal_relevant']:7} {data['topic']:14} {title[:45]}")
    return data


# ---- stage 4: synthesize (Opus) --------------------------------------------
def synthesize(all_data: list[dict]) -> None:
    cands = []
    for d in all_data:
        for c in d.get("skill_candidates", []):
            c = dict(c)
            c["from"] = d["title"]
            c["post_id"] = d.get("id", "")
            cands.append(c)
    if not cands:
        print("[synth] no candidates")
        return

    skills_ctx = {}
    for s in TARGET_SKILLS:
        f = ROOT / ".claude" / "skills" / s / "SKILL.md"
        if f.exists():
            skills_ctx[s] = f.read_text()[:5000]

    prompt = (
        f"You are improving Brian Norton's multifamily AIOS skills using tactics mined from "
        f"{len(all_data)} Justin Brennan course videos (One on One Mentorship 1:1).\n\n"
        f"Below are {len(cands)} raw skill-improvement candidates, plus the current skill files.\n\n"
        "Produce a RANKED, de-duplicated list of concrete upgrades. For each:\n"
        "- **Skill** + **Title** of the change\n"
        "- **Why it matters** (1 line, tie to Brian's sourcing/underwriting drag)\n"
        "- **Paste-ready change** (a snippet or before/after — must fit the existing skill structure)\n"
        "- **Confidence** (high/med/low) and **source videos**\n\n"
        "Merge duplicates. Drop anything vague or already covered. Lead with highest-leverage changes. "
        "PROPOSAL ONLY — Brian approves before anything is applied.\n\n"
        f"CURRENT SKILLS:\n{json.dumps({k: v[:3000] for k, v in skills_ctx.items()})}\n\n"
        f"CANDIDATES:\n{json.dumps(cands, indent=2)}"
    )

    resp = client.messages.create(
        model=SYNTH_MODEL, max_tokens=12000,
        thinking={"type": "adaptive"}, output_config={"effort": "high"},
        messages=[{"role": "user", "content": prompt}],
    )
    body = "".join(b.text for b in resp.content if b.type == "text")
    out = OUT / "_skill-upgrades-clientclub.md"
    out.write_text(
        f"""---
type: mfs-video-synthesis
title: Skill Upgrade Proposals from Multifamily Schooled Course Videos
generated: {datetime.date.today()}
source_videos: {len(all_data)}
candidates_considered: {len(cands)}
status: AWAITING BRIAN'S APPROVAL — no skills modified
---

{body}
"""
    )
    u = resp.usage
    print(f"[synth] -> {out}  (in={u.input_tokens} out={u.output_tokens} "
          f"~${u.input_tokens*15/1e6 + u.output_tokens*75/1e6:.2f})")


# ---- driver -----------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage",
                    choices=["all", "enumerate", "transcribe", "map", "synthesize"],
                    default="all")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--product", default=PRODUCT_ID)
    ap.add_argument("--token-id", dest="token_id", default="",
                    help="Skip Playwright and supply token-id directly (from Chrome DevTools). "
                         "Get it: DevTools → Network → any leadconnectorhq.com request → "
                         "Request Headers → token-id")
    args = ap.parse_args()

    for d in (OUT, RAW, CAND):
        d.mkdir(parents=True, exist_ok=True)

    # Stage 1: enumerate — force only when explicitly requested or no index exists
    if args.stage == "enumerate" or not IDX.exists():
        posts = enumerate_posts(args.product, token_id=args.token_id)
        IDX.write_text(json.dumps(posts, indent=2))
        print(f"[enumerate] Wrote {IDX}")
    else:
        posts = json.loads(IDX.read_text())
        print(f"[enumerate] Loaded {len(posts)} posts from index")

    if args.limit:
        posts = posts[:args.limit]
    if args.stage == "enumerate":
        return

    # Stage 2: transcribe
    if args.stage in ("all", "transcribe", "map"):
        missing = [p for p in posts
                   if not (RAW / f"{p['post_id']}.txt").exists()]
        if missing:
            print(f"[transcribe] {len(missing)} videos need transcription "
                  f"({args.workers} workers)")
            with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
                list(ex.map(transcribe_post, missing))
        else:
            print("[transcribe] All transcripts present — skipping")
    if args.stage == "transcribe":
        return

    # Stage 3: map
    results = []
    if args.stage in ("all", "map"):
        to_map = [p for p in posts
                  if not (OUT / f"{slugify(p['category_title']+'-'+p['title'])}-{p['post_id'][:8]}.md").exists()
                  or not (CAND / f"{p['post_id']}.json").exists()]
        already = [p for p in posts if p not in to_map]
        for p in already:
            cf_path = CAND / f"{p['post_id']}.json"
            if cf_path.exists():
                results.append(json.loads(cf_path.read_text()))

        print(f"[map] {len(to_map)} to map, {len(already)} already done")
        with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
            for r in ex.map(lambda p: _safe_map(p), to_map):
                if r:
                    results.append(r)
    else:
        for f in CAND.glob("*.json"):
            results.append(json.loads(f.read_text()))

    if args.stage in ("all", "synthesize") and results:
        synthesize(results)

    rel = sum(1 for r in results if r.get("deal_relevant") in ("yes", "partial"))
    print(f"\n[done] {len(results)} distilled | {rel} deal-relevant | pages in {OUT}")
    if args.stage in ("all", "map"):
        with LOG.open("a") as f:
            f.write(f"\n- {datetime.date.today()} clientclub-ingest: {len(results)} course videos, "
                    f"{rel} deal-relevant, product {PRODUCT_ID[:8]}…\n")


def _safe_map(p):
    try:
        return map_post(p)
    except Exception as e:
        print(f"[map] ERROR {p['post_id'][:8]}: {e}")
        return None


if __name__ == "__main__":
    main()
