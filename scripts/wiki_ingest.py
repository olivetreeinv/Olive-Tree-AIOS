#!/usr/bin/env python3
"""
wiki_ingest.py — Process raw sources into the Olive Tree LLM Wiki.

Usage:
    python scripts/wiki_ingest.py                    # process all files in wiki/raw/
    python scripts/wiki_ingest.py path/to/file.pdf   # ingest a single file
    python scripts/wiki_ingest.py --dry-run          # classify only, write nothing
"""

import argparse
import datetime
import json
import os
import re
import shutil
import sys
import urllib.request
from pathlib import Path

# Load .env if ANTHROPIC_API_KEY not already in environment
_env_file = Path(__file__).parent.parent / ".env"
if not os.environ.get("ANTHROPIC_API_KEY") and _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

import anthropic

WIKI_ROOT = Path(__file__).parent.parent / "wiki"
INBOX = WIKI_ROOT / "raw"
LOG = WIKI_ROOT / "_log.md"
SCHEMA = WIKI_ROOT / "SCHEMA.md"

# haiku for cheap classification; sonnet for page generation
CLASSIFY_MODEL = "claude-haiku-4-5-20251001"
GENERATE_MODEL = "claude-sonnet-4-6"

client = anthropic.Anthropic()


# ---------------------------------------------------------------------------
# YouTube support
# ---------------------------------------------------------------------------

_YT_RE = re.compile(r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})")


def extract_video_id(url: str) -> str | None:
    m = _YT_RE.search(url)
    return m.group(1) if m else None


def fetch_youtube_title(video_id: str) -> str:
    """Scrape the video title from the YouTube page — no API key needed."""
    try:
        req = urllib.request.Request(
            f"https://www.youtube.com/watch?v={video_id}",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read(65536).decode("utf-8", errors="replace")
        m = re.search(r'"title":"([^"]+)"', html)
        return m.group(1) if m else video_id
    except Exception:
        return video_id


def fetch_transcript(video_id: str) -> tuple[str, list[dict]]:
    """
    Returns (plain_text, segments) where segments = [{text, start, duration}].
    Raises RuntimeError if transcript is unavailable.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
    except ImportError:
        raise RuntimeError("youtube-transcript-api not installed: pip3 install youtube-transcript-api")

    try:
        segments = YouTubeTranscriptApi.get_transcript(video_id)
    except (NoTranscriptFound, TranscriptsDisabled) as e:
        raise RuntimeError(f"No transcript available for {video_id}: {e}")

    plain = " ".join(s["text"] for s in segments)
    return plain, segments


def segments_to_timestamped(segments: list[dict]) -> str:
    """Convert segments to a readable timestamped transcript."""
    lines = []
    for s in segments:
        mins, secs = divmod(int(s["start"]), 60)
        lines.append(f"[{mins}:{secs:02d}] {s['text']}")
    return "\n".join(lines)


def ingest_youtube(url: str, dry_run: bool = False) -> list[str]:
    """Ingest a YouTube video directly from its URL."""
    video_id = extract_video_id(url)
    if not video_id:
        print(f"  Could not extract video ID from: {url}")
        return []

    print(f"\n→ YouTube: {url}")
    print(f"  Fetching transcript for video_id={video_id}...")

    try:
        plain_text, segments = fetch_transcript(video_id)
    except RuntimeError as e:
        print(f"  {e}")
        return []

    title = fetch_youtube_title(video_id)
    print(f"  Title: {title}")
    print(f"  Transcript: {len(plain_text)} chars, {len(segments)} segments")

    timestamped = segments_to_timestamped(segments)
    meta = {
        "source_type": "mfs_video",
        "title": title,
        "youtube_url": url,
        "topic": None,
        "instructor": None,
        "confidence": "high",
    }

    schema = SCHEMA.read_text() if SCHEMA.exists() else ""
    written: list[str] = []
    slug = slugify(title)
    dest = WIKI_ROOT / "mfs-videos" / f"{slug}.md"

    if dest.exists():
        print(f"    exists — skipping: mfs-videos/{slug}.md")
        return []

    # Use timestamped transcript so Claude can populate the Timestamps table
    content = f"Title: {title}\nURL: {url}\n\n{timestamped}"
    page = gen_page("mfs-video", content, meta, schema)

    if write_page(dest, page, dry_run):
        written.append(f"mfs-videos/{slug}.md")

    if written and not dry_run:
        append_log(
            f"**Source:** YouTube `{url}`  \n"
            f"**Title:** {title}  \n"
            f"**Pages:** `mfs-videos/{slug}.md`"
        )

    return written


# ---------------------------------------------------------------------------
# File reading
# ---------------------------------------------------------------------------

def read_source(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                return "\n".join(p.extract_text() or "" for p in pdf.pages)
        except ImportError:
            return (
                f"[PDF — install pdfplumber to parse: pip install pdfplumber]\n"
                f"Filename: {path.name}"
            )
    content = path.read_text(errors="replace")
    # If file is just a YouTube URL, return it as-is for ingest_youtube routing
    return content


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

CLASSIFY_PROMPT = """\
Classify this document for Olive Tree Investments and extract entities. Return JSON only — no prose.

Filename: {filename}
Content (first 2000 chars):
{snippet}

Return exactly this JSON structure:
{{
  "source_type": "deal_om|t12|rent_roll|broker_email|broker_profile|market_report|mfs_document|mfs_video|govcon_document|other",
  "deal_name": "string or null",
  "address": "string or null",
  "market": "city/submarket name or null",
  "broker_name": "string or null",
  "broker_email": "string or null",
  "broker_company": "string or null",
  "units": "integer or null",
  "asking_price": "string or null",
  "title": "document or video title or null",
  "topic": "e.g. underwriting, deal-analysis, capital-raising, asset-management, govcon-strategy, govcon-bidding, govcon-subcontracting, or null",
  "instructor": "instructor/presenter name or null",
  "youtube_url": "YouTube URL if present or null",
  "confidence": "high|medium|low"
}}

Use mfs_document for PDFs, worksheets, or course materials from Multifamily Schooled.
Use mfs_video for YouTube transcripts, video notes, or files containing a YouTube URL from Multifamily Schooled.
Use govcon_document for government contracting plans, bid strategies, SAM.gov guides, subcontracting playbooks, or any federal contracting reference material."""


def classify(content: str, filename: str) -> dict:
    resp = client.messages.create(
        model=CLASSIFY_MODEL,
        max_tokens=512,
        system="You are a real estate document classifier for Olive Tree Investments, a multifamily syndication firm.",
        messages=[{
            "role": "user",
            "content": CLASSIFY_PROMPT.format(filename=filename, snippet=content[:2000]),
        }],
    )
    raw = resp.content[0].text.strip()
    # Strip markdown fences if model wraps in ```json
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"source_type": "other", "confidence": "low"}


# ---------------------------------------------------------------------------
# Page generation
# ---------------------------------------------------------------------------

def _call(system: str, user: str, max_tokens: int = 2048) -> str:
    resp = client.messages.create(
        model=GENERATE_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


_PAGE_SYSTEMS = {
    "govcon-doc": (
        'You maintain the Olive Tree Investments LLM Wiki. Generate a GovCon reference document\n'
        'wiki page in markdown with YAML frontmatter. Extract key strategy points, action items,\n'
        'and takeaways directly applicable to Olive Tree\'s federal subcontracting model.\n'
        'Write "—" for unknowns. Use [[WikiLink]] syntax to link related bids, subs, or agencies.\n'
        'Follow the mfs-doc page template from the schema but use type: govcon-doc.\n\nSchema:\n{schema}'
    ),
    "deal": (
        'You maintain the Olive Tree Investments LLM Wiki. Generate a deal wiki page in markdown\n'
        'with YAML frontmatter. Extract actual numbers from the source — never invent values.\n'
        'Write "—" for anything unknown. Use [[WikiLink]] syntax for market and broker cross-references.\n'
        'Follow the deal page template exactly as defined in the schema below.\n\nSchema:\n{schema}'
    ),
    "market": (
        'You maintain the Olive Tree Investments LLM Wiki. Generate a market wiki page in markdown\n'
        'with YAML frontmatter. Extract concrete data points only. Write "—" for unknowns.\n'
        'Use [[WikiLink]] syntax. Follow the market page template from the schema.\n\nSchema:\n{schema}'
    ),
    "broker": (
        'You maintain the Olive Tree Investments LLM Wiki. Generate a broker wiki page in markdown\n'
        'with YAML frontmatter. Extract contact info and deal history. Write "—" for unknowns.\n'
        'Use [[WikiLink]] syntax. Follow the broker page template from the schema.\n\nSchema:\n{schema}'
    ),
    "mfs-doc": (
        'You maintain the Olive Tree Investments LLM Wiki. Generate a Multifamily Schooled document\n'
        'wiki page in markdown with YAML frontmatter. Extract key takeaways, action items, and\n'
        'terms that are directly applicable to multifamily acquisitions. Write "—" for unknowns.\n'
        'Use [[WikiLink]] syntax to link related deals, videos, or docs.\n'
        'Follow the mfs-doc page template from the schema.\n\nSchema:\n{schema}'
    ),
    "mfs-video": (
        'You maintain the Olive Tree Investments LLM Wiki. Generate a Multifamily Schooled video\n'
        'wiki page in markdown with YAML frontmatter. Extract key concepts, timestamps (if present),\n'
        'and action items applicable to multifamily acquisitions. Write "—" for unknowns.\n'
        'Use [[WikiLink]] syntax to link related deals, docs, or markets.\n'
        'Follow the mfs-video page template from the schema.\n\nSchema:\n{schema}'
    ),
}
_PAGE_CAPS = {"deal": 8000, "market": 8000, "broker": 4000, "mfs-doc": 10000, "mfs-video": 10000, "govcon-doc": 10000}
_PAGE_TOKENS = {"deal": 2048, "market": 2048, "broker": 1024, "mfs-doc": 2048, "mfs-video": 2048, "govcon-doc": 2048}


def gen_page(page_type: str, content: str, meta: dict, schema: str) -> str:
    """Generate a wiki page. page_type: 'deal' | 'market' | 'broker'."""
    cap = _PAGE_CAPS[page_type]
    return _call(
        _PAGE_SYSTEMS[page_type].format(schema=schema),
        f"Metadata:\n{json.dumps(meta, indent=2)}\n\nDocument:\n{content[:cap]}",
        max_tokens=_PAGE_TOKENS[page_type],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower().strip()).strip("-")


def write_page(path: Path, content: str, dry_run: bool) -> bool:
    """Write page, skipping if it already exists. Returns True if written."""
    if path.exists():
        print(f"    exists — skipping: {path.relative_to(WIKI_ROOT)}")
        return False
    if not dry_run:
        path.write_text(content)
    print(f"    {'[dry] ' if dry_run else ''}wrote: {path.relative_to(WIKI_ROOT)}")
    return True


def append_log(entry: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    with LOG.open("a") as f:
        f.write(f"\n## {timestamp}\n{entry}\n")


# ---------------------------------------------------------------------------
# Main ingest logic
# ---------------------------------------------------------------------------

def ingest_file(source_path: Path, dry_run: bool = False, force_type: str | None = None) -> list[str]:
    print(f"\n→ {source_path.name}")
    content = read_source(source_path)
    if force_type:
        meta = {"source_type": force_type, "title": source_path.stem, "confidence": "forced"}
        source_type = force_type
    else:
        meta = classify(content, source_path.name)
        source_type = meta.get("source_type", "other")
    print(f"  type={source_type}  confidence={meta.get('confidence', '?')}")

    schema = SCHEMA.read_text() if SCHEMA.exists() else ""
    written: list[str] = []

    def _maybe_write(page_type: str, name: str, folder: str) -> None:
        slug = slugify(name)
        dest = WIKI_ROOT / folder / f"{slug}.md"
        if not dest.exists():
            page = gen_page(page_type, content, meta, schema)
            if write_page(dest, page, dry_run):
                written.append(f"{folder}/{slug}.md")

    if source_type in ("deal_om", "t12", "rent_roll"):
        _maybe_write("deal", meta.get("deal_name") or source_path.stem, "deals")
        if meta.get("market"):
            _maybe_write("market", meta["market"], "markets")
        if meta.get("broker_name"):
            _maybe_write("broker", meta["broker_name"], "brokers")

    elif source_type == "market_report":
        _maybe_write("market", meta.get("market") or source_path.stem, "markets")

    elif source_type in ("broker_email", "broker_profile"):
        _maybe_write("broker", meta.get("broker_name") or source_path.stem, "brokers")
        if meta.get("deal_name"):
            _maybe_write("deal", meta["deal_name"], "deals")

    elif source_type == "mfs_document":
        _maybe_write("mfs-doc", meta.get("title") or source_path.stem, "mfs-docs")

    elif source_type == "govcon_document":
        folder = WIKI_ROOT / "govcon-docs"
        folder.mkdir(exist_ok=True)
        _maybe_write("govcon-doc", meta.get("title") or source_path.stem, "govcon-docs")

    elif source_type == "mfs_video":
        _maybe_write("mfs-video", meta.get("title") or source_path.stem, "mfs-videos")

    else:
        print("  skipped (type=other)")
        return []

    if written and not dry_run:
        append_log(
            f"**Source:** `{source_path.name}`  \n"
            f"**Type:** {source_type}  \n"
            f"**Pages:** {', '.join(f'`{p}`' for p in written)}  \n"
            f"**Meta:** deal={meta.get('deal_name')}, market={meta.get('market')}, "
            f"broker={meta.get('broker_name')}"
        )
        processed = INBOX / "processed"
        processed.mkdir(exist_ok=True)
        shutil.move(str(source_path), str(processed / source_path.name))
        print(f"  moved to raw/processed/")

    return written


def main():
    parser = argparse.ArgumentParser(description="Ingest sources into the Olive Tree LLM Wiki")
    parser.add_argument("source", nargs="?", help="File to ingest (default: all files in wiki/raw/)")
    parser.add_argument("--url", help="YouTube URL to ingest directly")
    parser.add_argument("--force-type", metavar="TYPE", help="Skip classifier; force source_type (e.g. mfs_document, govcon_document)")
    parser.add_argument("--dry-run", action="store_true", help="Classify and print — write nothing")
    args = parser.parse_args()

    total_written: list[str] = []

    # Direct YouTube URL
    if args.url:
        total_written.extend(ingest_youtube(args.url, dry_run=args.dry_run))
        print(f"\nDone. {len(total_written)} page(s) written.")
        return

    if args.source:
        source_path = Path(args.source)
        # Auto-detect YouTube URLs in small text files
        if source_path.suffix.lower() in (".txt", ".url") and source_path.stat().st_size < 4096:
            raw = source_path.read_text().strip()
            if extract_video_id(raw):
                total_written.extend(ingest_youtube(raw, dry_run=args.dry_run))
                print(f"\nDone. {len(total_written)} page(s) written.")
                return
        files = [source_path]
    else:
        if not INBOX.exists():
            INBOX.mkdir(parents=True)
        files = sorted(
            f for f in INBOX.iterdir()
            if f.is_file() and not f.name.startswith(".")
        )

    if not files:
        print("Nothing to ingest. Drop files into wiki/raw/ first.")
        sys.exit(0)

    for f in files:
        # Auto-detect YouTube URLs dropped into raw/ (skip if force_type set)
        if not args.force_type and f.suffix.lower() in (".txt", ".url") and f.stat().st_size < 4096:
            raw = f.read_text().strip()
            if extract_video_id(raw):
                total_written.extend(ingest_youtube(raw, dry_run=args.dry_run))
                if not args.dry_run:
                    processed = INBOX / "processed"
                    processed.mkdir(exist_ok=True)
                    shutil.move(str(f), str(processed / f.name))
                continue
        total_written.extend(ingest_file(f, dry_run=args.dry_run, force_type=args.force_type))

    print(f"\nDone. {len(total_written)} page(s) written.")


if __name__ == "__main__":
    main()
