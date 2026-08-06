#!/usr/bin/env python3
"""
wiki_lint.py — Health check the Olive Tree LLM Wiki.

Checks:
  - Pages missing required frontmatter fields
  - Broken [[WikiLinks]]
  - Orphaned pages (no incoming links)
  - Empty pages (< 80 chars of content)

Usage:
    python scripts/wiki_lint.py
    python scripts/wiki_lint.py --verbose   # show passing checks too
"""

import argparse
import re
from collections import defaultdict
from pathlib import Path

WIKI_ROOT = Path(__file__).parent.parent / "wiki"
CATEGORIES = ["deals", "markets", "brokers", "mfs-docs", "mfs-videos",
              "govcon-bids", "govcon-subs", "govcon-agencies", "govcon-docs", "skills"]

REQUIRED = {
    "deals":           ["type", "name", "address", "market", "units", "status"],
    "markets":         ["type", "name", "zip", "in_buy_box"],
    "brokers":         ["type", "name", "email"],
    "mfs-docs":        ["type", "title", "topic", "source_file", "date_added"],
    "mfs-videos":      ["type", "title", "topic", "url", "date_added"],
    "govcon-bids":     ["type", "title", "notice_id", "agency", "naics_code", "state", "deadline", "status"],
    "govcon-subs":     ["type", "name", "contact", "naics_codes", "states"],
    "govcon-agencies": ["type", "name", "abbreviation"],
    "govcon-docs":     ["type", "title", "topic"],
    "skills":          ["type", "name", "trigger", "status"],
}

ISSUE_ICONS = {
    "empty":         "○ EMPTY   ",
    "missing_field": "! FIELD   ",
    "broken_link":   "✗ LINK    ",
    "orphan":        "◌ ORPHAN  ",
}


def load_pages() -> dict[str, str]:
    return {
        f"{d.name}/{f.relative_to(d).with_suffix('')}": f.read_text()
        for d in (WIKI_ROOT / c for c in CATEGORIES) if d.exists()
        for f in sorted(d.rglob("*.md"))
        if not f.name.startswith("_")
    }


def frontmatter(content: str) -> dict[str, str]:
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    fm = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


def wiki_links(content: str) -> list[str]:
    return [m.split("|")[0].strip().replace(".md", "") for m in re.findall(r"\[\[([^\]]+)]]", content)]


def resolve(link: str, pages: dict[str, str]) -> bool:
    """True if link matches any known page key or stem."""
    link_lower = link.lower()
    for key in pages:
        if link_lower in (key.lower(), key.split("/")[-1].lower()):
            return True
    return False


def lint(verbose: bool = False) -> int:
    pages = load_pages()
    if not pages:
        print("Wiki is empty.")
        return 0

    issues: list[tuple[str, str, str]] = []  # (icon_key, page_key, detail)
    incoming: dict[str, list[str]] = defaultdict(list)

    for key, content in pages.items():
        cat = key.split("/")[0]

        # Empty
        if len(content.strip()) < 80:
            issues.append(("empty", key, ""))
            continue

        # Missing frontmatter fields
        fm = frontmatter(content)
        for field in REQUIRED.get(cat, []):
            val = fm.get(field, "")
            if not val or val in ("—", "null", "~"):
                issues.append(("missing_field", key, f"`{field}`"))

        # Outbound links
        for link in wiki_links(content):
            if not resolve(link, pages):
                issues.append(("broken_link", key, f"[[{link}]]"))
            else:
                # Track incoming links for orphan check
                for target_key in pages:
                    if link.lower() in (target_key.lower(), target_key.split("/")[-1].lower()):
                        incoming[target_key].append(key)

    # Orphans (no incoming links from other pages)
    for key in pages:
        if not incoming[key] and key.split("/")[-1] != "index":
            issues.append(("orphan", key, ""))

    # --- Report ---
    counts = {k: 0 for k in ISSUE_ICONS}
    for icon_key, _, _ in issues:
        counts[icon_key] += 1

    cat_counts = ", ".join(f"{c}: {sum(1 for k in pages if k.startswith(c + '/'))}" for c in CATEGORIES)
    print(f"\nWiki Lint  —  {len(pages)} pages  ({cat_counts})")
    print("─" * 60)

    if not issues:
        print("  All clear.")
    else:
        seen: set[str] = set()
        for icon_key, page_key, detail in sorted(issues, key=lambda x: (x[0], x[1])):
            line = f"  {ISSUE_ICONS[icon_key]}{page_key}  {detail}".rstrip()
            if line not in seen:
                print(line)
                seen.add(line)

    print("─" * 60)
    print(
        f"  {counts['empty']} empty  "
        f"{counts['missing_field']} missing-fields  "
        f"{counts['broken_link']} broken-links  "
        f"{counts['orphan']} orphans\n"
    )

    return len(issues)


def main():
    parser = argparse.ArgumentParser(description="Lint the Olive Tree LLM Wiki")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    exit_code = lint(verbose=args.verbose)
    raise SystemExit(0 if exit_code == 0 else 1)


if __name__ == "__main__":
    main()
