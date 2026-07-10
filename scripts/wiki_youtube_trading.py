#!/usr/bin/env python3
"""
wiki_youtube_trading.py — Ingest trading/options education into the Olive Tree Trading Desk wiki.

Pipeline:
  1. enumerate  — list videos, keep long-form (>= min_minutes)
  2. fetch      — download + clean auto-captions (free, no API key)
  3. map        — Haiku distills each transcript into a trading-video wiki page
                  and emits trading-strategy candidates (JSON sidecar)
  4. synthesize — Opus ranks all candidates into _trading-upgrades.md

Usage:
    python scripts/wiki_youtube_trading.py --channel "<playlist_url>"
    python scripts/wiki_youtube_trading.py --channel "<playlist_url>" --min-minutes 15 --out-subdir kenneth-suna
    python scripts/wiki_youtube_trading.py --stage map        # re-run just one stage
    python scripts/wiki_youtube_trading.py --limit 5           # cap videos (testing)

Resumable: skips videos whose page already exists. Nothing touches Brian's
strategies — proposals land in _trading-upgrades.md for approval.
"""

import argparse
import concurrent.futures as cf
import datetime
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
WIKI = ROOT / "wiki"
_TRADING = WIKI / "trading-desk"          # root; subdir set at runtime by --out-subdir
LOG = WIKI / "_log.md"

MIN_SECONDS = 900                    # long-form trading classes (>= 15 min); overridden by --min-minutes
MAP_MODEL = "claude-haiku-4-5"       # cheap per-video distill
SYNTH_MODEL = "claude-opus-4-8"      # judgment pass over all candidates
CHANNEL = "https://www.youtube.com/playlist?list=PLY6UDCqCE9mpF31PMqkpW8Nu9ztilxamz"  # Kenneth Suna

# Brian's trading strategies this pipeline may propose changes to (proposals only).
TARGET_SKILLS = ["trading-desk"]

# ---- env / client -----------------------------------------------------------
_env = ROOT / ".env"
if not os.environ.get("ANTHROPIC_API_KEY") and _env.exists():
    for _l in _env.read_text().splitlines():
        _l = _l.strip()
        if _l and not _l.startswith("#") and "=" in _l:
            _k, _, _v = _l.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

import anthropic  # noqa: E402

# Retry 429s with backoff (tier-1 orgs have low TPM); throttle stays under the cap.
client = anthropic.Anthropic(max_retries=6)

# --- token-rate throttle: keep Haiku input under the org TPM limit -----------
TPM_LIMIT = 45000          # headroom under the 50K/min Haiku input cap
_throttle_lock = threading.Lock()
_window: list[tuple[float, int]] = []  # (timestamp, tokens)


def throttle(tokens: int) -> None:
    """Block until sending `tokens` keeps the rolling 60s usage under TPM_LIMIT."""
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


# ---- stage 1: enumerate -----------------------------------------------------
def enumerate_channel(channel: str, min_seconds: int = MIN_SECONDS) -> list[dict]:
    print(f"[enumerate] {channel}")
    r = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--print", "%(duration)s\t%(title)s\t%(id)s", channel],
        capture_output=True, text=True,
    )
    vids = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        dur, title, vid = parts
        try:
            dur = float(dur)
        except ValueError:
            continue
        if dur >= min_seconds:
            vids.append({"id": vid, "title": title, "duration": int(dur)})
    print(f"[enumerate] {len(vids)} videos (>= {min_seconds//60} min)")
    return vids


# ---- stage 2: fetch transcripts --------------------------------------------
def clean_vtt(text: str) -> str:
    out, last = [], None
    for line in text.splitlines():
        if "-->" in line or line.strip().isdigit():
            continue
        if line.startswith(("WEBVTT", "Kind:", "Language:")) or not line.strip():
            continue
        t = re.sub(r"<[^>]+>", "", line).strip()
        if not t or t == last:
            continue
        out.append(t)
        last = t
    return " ".join(out)


def fetch_transcript(vid: str, raw: Path) -> str | None:
    dest = raw / f"{vid}.txt"
    if dest.exists() and dest.stat().st_size > 500:
        return dest.read_text()
    subprocess.run(
        ["yt-dlp", "--skip-download", "--write-auto-sub", "--sub-lang", "en.*",
         "--sub-format", "vtt", "-o", str(raw / "%(id)s.%(ext)s"),
         f"https://www.youtube.com/watch?v={vid}"],
        capture_output=True, text=True,
    )
    # yt-dlp may emit en.vtt, en-US.vtt, en-orig.vtt, etc. — match any.
    subs = sorted(raw.glob(f"{vid}*.vtt"))
    if not subs:
        return None
    tmp = subs[0]
    txt = clean_vtt(tmp.read_text(encoding="utf-8", errors="ignore"))
    for s in subs:
        s.unlink(missing_ok=True)
    if len(txt.split()) < 200:
        return None
    dest.write_text(txt)
    return txt


# ---- stage 3: map (Haiku per video) ----------------------------------------
MAP_PROMPT = """Distill this transcript of a Kenneth Suna trading/options education video for Brian Norton's AIOS.
Brian runs the Premium Desk: $50k portfolio, covered call + cash-secured put wheels, targeting $1,250/mo premium.

Video title: {title}

Return STRICT JSON, no prose:
{{
  "trading_relevant": "yes" | "partial" | "no",
  "strategy": one of ["covered-calls","cash-secured-puts","wheels","iron-condors","spreads","market-analysis","risk-management","psychology","other"],
  "summary": "2-3 sentence summary of the trading-relevant content (or note it's off-topic)",
  "takeaways": ["concrete tactic/threshold/rule Kenneth teaches", ...up to 7, quote specific numbers/Greeks/thresholds],
  "strategy_candidates": [
     {{"strategy": one of {skills}, "change": "specific minimal improvement to premium desk", "evidence": "what in the video supports it"}}
  ]
}}
Only include strategy_candidates when the video gives a concrete, actionable rule for options selling. Empty list if none.

TRANSCRIPT:
{transcript}"""


def map_video(v: dict, out: Path, cand: Path, collection: str = "") -> dict | None:
    vid, title = v["id"], v["title"]
    page = out / f"{slugify(title)}-{vid}.md"
    cand_f = cand / f"{vid}.json"
    if page.exists() and cand_f.exists():
        return json.loads(cand_f.read_text())

    raw = out / "_transcripts"
    txt = fetch_transcript(vid, raw)
    if not txt:
        print(f"[map] NO TRANSCRIPT {vid} {title[:40]}")
        return None

    prompt = MAP_PROMPT.format(title=title, skills=TARGET_SKILLS, transcript=txt)
    throttle(len(prompt) // 4 + 400)  # ~4 chars/token; +overhead for schema
    resp = client.messages.create(
        model=MAP_MODEL, max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": {
            "type": "object",
            "properties": {
                "trading_relevant": {"type": "string", "enum": ["yes", "partial", "no"]},
                "strategy": {"type": "string"},
                "summary": {"type": "string"},
                "takeaways": {"type": "array", "items": {"type": "string"}},
                "strategy_candidates": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"strategy": {"type": "string"}, "change": {"type": "string"}, "evidence": {"type": "string"}},
                    "required": ["strategy", "change", "evidence"], "additionalProperties": False}},
            },
            "required": ["trading_relevant", "strategy", "summary", "takeaways", "strategy_candidates"],
            "additionalProperties": False,
        }}},
    )
    data = json.loads(next((b.text for b in resp.content if b.type == "text"), "{}"))
    data["id"], data["title"], data["duration"] = vid, title, v["duration"]

    # build frontmatter extras for non-root collections
    extra_fm = ""
    if collection:
        extra_fm = f"collection: {collection}\ncontent_type: trading-education\n"

    # write the wiki page
    tk = "\n".join(f"{i+1}. {t}" for i, t in enumerate(data["takeaways"])) or "—"
    page.write_text(
        f"""---
type: trading-video
{extra_fm}title: {title.replace('"', "'")}
strategy: {data['strategy']}
instructor: Kenneth Suna
trading_relevant: {data['trading_relevant']}
video_id: {vid}
url: https://www.youtube.com/watch?v={vid}
duration_min: {v['duration']//60}
date_added: {datetime.date.today()}
---

## Summary
{data['summary']}

---

## Key Takeaways
{tk}

---

## Source
[Watch on YouTube](https://www.youtube.com/watch?v={vid}) — {v['duration']//60} min
"""
    )
    cand_f.write_text(json.dumps(data, indent=2))
    print(f"[map] {data['trading_relevant']:7} {data['strategy']:20} {title[:40]}")
    return data


# ---- stage 4: synthesize (Opus) --------------------------------------------
def synthesize(all_data: list[dict], out_dir: Path) -> None:
    cands = []
    for d in all_data:
        for c in d.get("strategy_candidates", []):
            c = dict(c)
            c["from"] = d["title"]
            c["video_id"] = d["id"]
            cands.append(c)
    if not cands:
        print("[synth] no candidates")
        return

    prompt = f"""You are improving Brian Norton's Premium Desk options-selling strategy using tactics mined from {len(all_data)} Kenneth Suna trading education videos.

Below are {len(cands)} raw strategy-improvement candidates extracted per-video.

Produce a RANKED, de-duplicated list of concrete upgrades. For each:
- **Strategy** + **Title** of the change
- **Why it matters** (1 line, tie to premium generation or risk control)
- **Paste-ready change** (a snippet or rule — Greeks, entry rules, position sizing, etc.)
- **Confidence** (high/med/low) and **source videos**

Merge duplicates. Drop anything vague. Lead with the highest-leverage changes for the $50k covered-call + CSP wheel. This is a PROPOSAL doc — Brian approves before anything is applied.

CANDIDATES:
{json.dumps(cands, indent=2)}"""

    resp = client.messages.create(
        model=SYNTH_MODEL, max_tokens=8000,
        thinking={"type": "adaptive"}, output_config={"effort": "high"},
        messages=[{"role": "user", "content": prompt}],
    )
    body = "".join(b.text for b in resp.content if b.type == "text")
    upgrades_file = out_dir / "_trading-upgrades.md"
    upgrades_file.write_text(
        f"""---
type: trading-video-synthesis
title: Trading Strategy Upgrade Proposals from Kenneth Suna Videos
generated: {datetime.date.today()}
source_videos: {len(all_data)}
candidates_considered: {len(cands)}
status: AWAITING BRIAN'S APPROVAL — no strategies modified
---

{body}
"""
    )
    u = resp.usage
    print(f"[synth] -> {upgrades_file}  (in={u.input_tokens} out={u.output_tokens} "
          f"~${u.input_tokens*15/1e6 + u.output_tokens*75/1e6:.2f})")


# ---- driver -----------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default=CHANNEL)
    ap.add_argument("--stage", choices=["all", "enumerate", "map", "synthesize"], default="all")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--min-minutes", type=int, default=15,
                    help="Minimum video duration in minutes (default 15)")
    ap.add_argument("--out-subdir", default="kenneth-suna",
                    help="Write pages under wiki/trading-desk/<subdir>/ instead of the root. "
                         "Example: --out-subdir kenneth-suna (default)")
    args = ap.parse_args()

    min_seconds = args.min_minutes * 60

    # Runtime paths — subdir lets playlist runs land under kenneth-suna/ etc.
    out = _TRADING / args.out_subdir if args.out_subdir else _TRADING
    raw = out / "_transcripts"
    cand = out / "_candidates"
    collection = args.out_subdir  # used as frontmatter collection: value

    # IDs already ingested anywhere under trading-desk (root + all subdirs) — skip in this run
    root_ids: set[str] = set()
    if args.out_subdir:
        for page in _TRADING.glob("**/*.md"):
            if page.name.startswith("_") or page.parent == out:
                continue
            # extract video_id from frontmatter
            for line in page.read_text().splitlines():
                m = re.match(r"^\s*video_id:\s*(\S+)", line)
                if m:
                    root_ids.add(m.group(1))
                    break

    for d in (out, raw, cand):
        d.mkdir(parents=True, exist_ok=True)

    idx = out / "_index.json"
    if args.stage in ("all", "enumerate") or not idx.exists():
        vids = enumerate_channel(args.channel, min_seconds=min_seconds)
        # Dedup against root if running in a subdir
        if root_ids:
            before = len(vids)
            vids = [v for v in vids if v["id"] not in root_ids]
            print(f"[enumerate] Skipped {before - len(vids)} already in root trading-desk")
        idx.write_text(json.dumps(vids, indent=2))
    else:
        vids = json.loads(idx.read_text())
    if args.limit:
        vids = vids[:args.limit]
    if args.stage == "enumerate":
        return

    results = []
    if args.stage in ("all", "map"):
        print(f"[map] {len(vids)} videos on {args.workers} workers")
        with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
            for r in ex.map(lambda v: _safe_map(v, out, cand, collection), vids):
                if r:
                    results.append(r)
    else:
        for f in cand.glob("*.json"):
            results.append(json.loads(f.read_text()))

    if args.stage in ("all", "synthesize"):
        synthesize(results, out)

    rel = sum(1 for r in results if r.get("trading_relevant") in ("yes", "partial"))
    print(f"\n[done] {len(results)} distilled | {rel} trading-relevant | pages in {out}")
    # Log only when the map stage actually ran — avoid dup entries on re-synthesize.
    if args.stage in ("all", "map"):
        label = f"trading-desk/{args.out_subdir}" if args.out_subdir else "kenneth-suna"
        with LOG.open("a") as f:
            f.write(f"\n- {datetime.date.today()} youtube-ingest: {len(results)} videos, "
                    f"{rel} trading-relevant, {label}\n")


def _safe_map(v, out, cand, collection):
    try:
        return map_video(v, out, cand, collection)
    except Exception as e:  # one bad video shouldn't kill the batch
        print(f"[map] ERROR {v['id']}: {e}")
        return None


if __name__ == "__main__":
    main()
