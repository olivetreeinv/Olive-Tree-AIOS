#!/usr/bin/env python3
"""
Perplexity Sonar lookup — Olive Tree Investments

A thin CLI/module over Perplexity's REST API (OpenAI-compatible chat
completions). Lets the AIOS pull a live, web-grounded, *cited* second opinion
on stack/architecture/tradeoff questions and fold it into its own reasoning.

Usage (standalone):
  python3 scripts/perplexity.py "Best backend stack for a real-time trading desk in 2026?"
  python3 scripts/perplexity.py "..." --model sonar-reasoning
  python3 scripts/perplexity.py "..." --json          # raw answer + citations as JSON

Usage (as module):
  import sys; sys.path.insert(0, "scripts")
  import perplexity
  result = perplexity.ask("Best vector DB for a small RAG app?")
  print(result["answer"])      # the prose
  print(result["citations"])   # list of source URLs

Models:
  sonar            — cheap, fast, web-grounded answers
  sonar-pro        — deeper, more citations; best for stack/architecture calls (default)
  sonar-reasoning  — chain-of-thought for harder tradeoff decisions

Requirements:
  pip3 install requests python-dotenv
  PERPLEXITY_API_KEY set in .env

To get your API key:
  1. Log in at perplexity.ai
  2. Settings → API → add a payment method / buy credits
  3. Generate key (pplx-...) → add to .env as PERPLEXITY_API_KEY=your_key

Cost: usage-billed per request (separate from any Perplexity subscription).
sonar-pro runs ~fractions of a cent to ~1c+ per query by response/search depth.
"""

import argparse
import json
import os
import sys

import requests

try:
    from dotenv import load_dotenv
    _env = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    load_dotenv(_env)
except ImportError:
    pass

PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"
DEFAULT_MODEL = "sonar-pro"

# Keeps answers tight and operator-grade rather than essay-length — and tells
# Sonar to be explicit about tradeoffs, which is the whole point of asking it.
SYSTEM_PROMPT = (
    "You are a senior staff engineer advising on technology choices. Be direct "
    "and concise. Lead with a recommendation, then the key tradeoffs that would "
    "change it. Prefer mature, well-supported options. Call out cost and "
    "operational burden. No filler."
)


_MISSING_KEY_HELP = (
    "PERPLEXITY_API_KEY not set in .env\n"
    "  1. Log in at perplexity.ai\n"
    "  2. Settings → API → add payment method / buy credits\n"
    "  3. Generate key → paste into .env: PERPLEXITY_API_KEY=pplx-..."
)


def _api_key():
    """Return the API key, or raise RuntimeError if unset.

    Raises (rather than sys.exit) so the documented module path —
    perplexity.ask(...) — gives importers a catchable error instead of
    killing their process. main() turns it into a CLI exit.
    """
    key = os.getenv("PERPLEXITY_API_KEY", "").strip()
    if not key:
        raise RuntimeError(_MISSING_KEY_HELP)
    return key


def ask(question, model=DEFAULT_MODEL, system=SYSTEM_PROMPT, timeout=60,
        max_tokens=800):
    """Ask Perplexity a question. Returns {answer, citations, model, usage}.

    Raises requests.HTTPError on a non-2xx response so callers can surface the
    real API error (bad key, no credits, rate limit) instead of a silent None.

    max_tokens caps the response length — Sonar bills partly on output, so an
    explicit cap keeps a quick stack check from running up an open-ended bill.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": question})

    resp = requests.post(
        PERPLEXITY_URL,
        headers={
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
        },
        json={"model": model, "messages": messages, "max_tokens": max_tokens},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()

    answer = data["choices"][0]["message"]["content"].strip()
    # Perplexity returns sources as top-level "citations" (URLs). Newer payloads
    # may also carry richer "search_results"; prefer citations, fall back.
    citations = data.get("citations") or [
        r.get("url") for r in data.get("search_results", []) if r.get("url")
    ]
    return {
        "answer": answer,
        "citations": citations,
        "model": data.get("model", model),
        "usage": data.get("usage", {}),
    }


def render_markdown(result):
    """Format an ask() result as markdown: answer + numbered sources."""
    lines = [result["answer"]]
    if result["citations"]:
        lines.append("\n**Sources:**")
        for i, url in enumerate(result["citations"], 1):
            lines.append(f"{i}. {url}")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(
        description="Perplexity Sonar lookup — web-grounded, cited answers."
    )
    p.add_argument("question", help="The question to ask Perplexity.")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"sonar | sonar-pro | sonar-reasoning (default: {DEFAULT_MODEL})")
    p.add_argument("--max-tokens", type=int, default=800,
                   help="Cap response length to control cost (default: 800).")
    p.add_argument("--json", action="store_true",
                   help="Print raw result (answer + citations + usage) as JSON.")
    args = p.parse_args()

    try:
        result = ask(args.question, model=args.model, max_tokens=args.max_tokens)
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        body = e.response.text[:300] if e.response is not None else ""
        print(f"ERROR: Perplexity API returned {status}: {body}")
        sys.exit(1)
    except requests.RequestException as e:
        print(f"ERROR: request to Perplexity failed: {e}")
        sys.exit(1)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_markdown(result))


if __name__ == "__main__":
    main()
