#!/usr/bin/env python3
"""
wiki_query.py — Natural language query over the Olive Tree LLM Wiki.

Usage:
    python scripts/wiki_query.py "What's the basis per unit on the Chattanooga deal?"
    python scripts/wiki_query.py --cat deals "any deals over 30 units?"
    python scripts/wiki_query.py --cat markets "which markets have the best cap rates?"
"""

import argparse
import sys
from pathlib import Path

import anthropic

WIKI_ROOT = Path(__file__).parent.parent / "wiki"
CATEGORIES = ["deals", "markets", "brokers", "mfs-docs", "mfs-videos",
              "govcon-bids", "govcon-subs", "govcon-agencies", "govcon-docs", "skills"]
MODEL = "claude-sonnet-4-6"
TOP_K = 10          # max pages sent as context
CONTENT_CAP = 1500  # chars per page in context

client = anthropic.Anthropic()


def load_pages(category: str | None = None) -> dict[str, str]:
    dirs = [WIKI_ROOT / c for c in (CATEGORIES if category is None else [category])]
    return {
        f"{d.name}/{f.stem}": f.read_text()
        for d in dirs if d.exists()
        for f in sorted(d.glob("*.md"))
    }


def rank_pages(query: str, pages: dict[str, str]) -> list[tuple[str, str]]:
    """Score pages by query-word overlap; return top K."""
    words = set(query.lower().split())
    scored = sorted(
        ((sum(1 for w in words if w in v.lower()), k, v) for k, v in pages.items()),
        reverse=True,
    )
    return [(k, v) for _, k, v in scored[:TOP_K]]


SYSTEM = """\
You are the Olive Tree Investments knowledge assistant. Answer using only the wiki pages
provided as context. Cite sources with [[page/name]] syntax. If the information isn't in
the wiki, say "Not in wiki yet." — never guess or fill in from general knowledge."""


def query(question: str, category: str | None = None) -> str:
    pages = load_pages(category)
    if not pages:
        return "Wiki is empty. Run `python scripts/wiki_ingest.py` to add content."

    relevant = rank_pages(question, pages)
    context = "\n\n".join(
        f"### [[{k}]]\n{v[:CONTENT_CAP]}" for k, v in relevant
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM,
        messages=[{
            "role": "user",
            "content": f"Wiki context:\n{context}\n\nQuestion: {question}",
        }],
    )
    return resp.content[0].text


def main():
    parser = argparse.ArgumentParser(description="Query the Olive Tree LLM Wiki")
    parser.add_argument("question", nargs="+")
    parser.add_argument("--cat", choices=CATEGORIES, metavar="{" + ",".join(CATEGORIES) + "}", help="Limit search to one category")
    args = parser.parse_args()

    question = " ".join(args.question)
    print(f"\n{query(question, args.cat)}\n")


if __name__ == "__main__":
    main()
