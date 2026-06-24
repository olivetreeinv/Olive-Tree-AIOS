#!/usr/bin/env python3
"""
wiki_query.py — Natural language query over the Olive Tree LLM Wiki.

Backed by the unified AIOS hybrid retrieval layer (aios_recall.py).
Replaces the original word-overlap ranking with FTS5 + semantic search,
cutting input tokens and improving recall across synonyms.

Usage:
    python scripts/wiki_query.py "What's the basis per unit on the Chattanooga deal?"
    python scripts/wiki_query.py --cat deals "any deals over 30 units?"
    python scripts/wiki_query.py --cat markets "which markets have the best cap rates?"
    python scripts/wiki_query.py --layer memory "expense sourcing rule"
"""

import argparse
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# Ensure repo root is importable
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.aios_recall import recall  # noqa: E402

CATEGORIES = ["deals", "markets", "brokers", "mfs-docs", "mfs-videos",
              "govcon-bids", "govcon-subs", "govcon-agencies", "govcon-docs", "skills"]
LAYERS     = ["wiki", "reference", "memory"]
MODEL      = "claude-sonnet-4-6"
TOP_K      = 10     # chunks sent to Claude (vs. 10 whole pages before)
CONTENT_CAP = 1500  # chars per chunk in context

client = anthropic.Anthropic()

SYSTEM = """\
You are the Olive Tree Investments knowledge assistant. Answer using only the
wiki/knowledge-base chunks provided as context. Cite sources with [[path#heading]]
syntax. If the information isn't in the provided context, say "Not in wiki yet."
— never guess or fill in from general knowledge."""


def query(question: str, category: str | None = None, layer: str | None = None) -> str:
    hits = recall(question, layer=layer, category=category, k=TOP_K)

    if not hits:
        return (
            "Index is empty or no matching content found. "
            "Run `python scripts/aios_index.py` to build the index."
        )

    context = "\n\n".join(
        f"### {h.citation}\n{h.content[:CONTENT_CAP]}" for h in hits
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM,
        messages=[{
            "role":    "user",
            "content": f"Knowledge base context:\n{context}\n\nQuestion: {question}",
        }],
    )
    return resp.content[0].text


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the Olive Tree knowledge base")
    parser.add_argument("question", nargs="+")
    parser.add_argument(
        "--cat",
        choices=CATEGORIES,
        metavar="{" + ",".join(CATEGORIES) + "}",
        help="Limit search to one wiki category",
    )
    parser.add_argument(
        "--layer",
        choices=LAYERS,
        help="Limit search to one knowledge layer (wiki, reference, memory)",
    )
    args = parser.parse_args()

    question = " ".join(args.question)
    print(f"\n{query(question, category=args.cat, layer=args.layer)}\n")


if __name__ == "__main__":
    main()
