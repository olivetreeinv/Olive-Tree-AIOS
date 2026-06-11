"""
AI Code Review — GitHub Actions entry point.

Reads the PR diff, sends it to Claude for structured review, posts inline
comments via the GitHub API, and exits 1 if any CRITICAL findings exist
(which fails the required status check and blocks the merge).

Required env vars:
  ANTHROPIC_API_KEY — Anthropic API key
  GITHUB_TOKEN      — GitHub token (auto-set by Actions)
  REPO              — owner/repo  (e.g. "olivetreeinv/olive-aios")
  PR_NUMBER         — pull request number
  BASE_SHA          — base commit SHA
  HEAD_SHA          — head commit SHA
"""

import json
import os
import subprocess
import sys

import anthropic
from github import Github

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MODEL = "claude-sonnet-4-6"
MAX_DIFF_CHARS = 80_000  # trim very large diffs to fit context window

SYSTEM_PROMPT = """You are a senior software engineer performing a code review.
Your mandate: find issues that BREAK PRODUCTION. Ignore style, formatting, naming, and linting.

Focus exclusively on:
- SECURITY: SQL injection, command injection, auth bypass, exposed secrets, insecure deserialization, path traversal
- BUSINESS LOGIC: wrong financial calculations, off-by-one errors, incorrect conditionals, missing transaction boundaries
- PERFORMANCE: N+1 queries, unbounded loops, blocking calls, memory leaks
- ARCHITECTURE: race conditions, swallowed exceptions, missing error handling at system boundaries, tight coupling that masks failures
- EDGE CASES: None/null inputs, zero denominators, empty collections, unexpected API response shapes

Always flag (regardless of scope) any code touching: auth, payments/financials, or data deletion.

Severity rules:
- CRITICAL: breaks production, exposes data, corrupts records, or is exploitable. Examples: SQL injection, auth bypass, wrong fee calculation, unguarded bulk delete, plaintext secret.
- WARNING: degrades reliability/performance but does not block. Examples: N+1 query, missing retry, swallowed exception with no log.
- INFO: low-risk observation, no action required.

CRITICAL issues BLOCK the merge. Warnings do not.

Respond with ONLY valid JSON matching this schema:
{
  "summary": "<1-2 sentence overall assessment>",
  "verdict": "APPROVED" | "BLOCKED",
  "findings": [
    {
      "severity": "CRITICAL" | "WARNING" | "INFO",
      "file": "<relative file path>",
      "line": <integer | null>,
      "category": "SECURITY" | "BUSINESS_LOGIC" | "PERFORMANCE" | "ARCHITECTURE" | "EDGE_CASE" | "AUTH_FLAG" | "PAYMENT_FLAG" | "DELETION_FLAG",
      "finding": "<concise description of the issue>",
      "recommendation": "<specific fix or mitigation>"
    }
  ]
}

If there are zero findings, return an empty findings array and verdict APPROVED.
Do not include any text outside the JSON object."""

REVIEW_PROMPT = """Review the following git diff for the pull request.

{diff}

Return only the JSON review object."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_diff() -> str:
    result = subprocess.run(
        ["git", "diff", os.environ["BASE_SHA"], os.environ["HEAD_SHA"]],
        capture_output=True, text=True, check=True
    )
    diff = result.stdout
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n\n[diff truncated — review remaining files manually]"
    return diff


def run_review(diff: str) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": REVIEW_PROMPT.format(diff=diff)}],
    )
    raw = message.content[0].text.strip()
    # Strip markdown code fences if the model wraps the JSON
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def post_pr_comments(review: dict, pr) -> None:
    """Post inline review comments and a summary comment on the PR."""
    commit = pr.get_commits().reversed[0]

    for f in review.get("findings", []):
        if f.get("line") and f.get("file"):
            emoji = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🔵"}.get(f["severity"], "⚪")
            body = (
                f"{emoji} **{f['severity']}** [{f['category']}]\n\n"
                f"{f['finding']}\n\n"
                f"**Recommendation:** {f['recommendation']}"
            )
            try:
                pr.create_review_comment(
                    body=body,
                    commit=commit,
                    path=f["file"],
                    line=f["line"],
                )
            except Exception:
                # Line may not exist in diff context — fall back to a regular comment
                pr.create_issue_comment(
                    f"{emoji} **{f['severity']}** `{f['file']}:{f['line']}` — {f['finding']}\n\n"
                    f"**Recommendation:** {f['recommendation']}"
                )

    # Summary comment
    criticals = [f for f in review.get("findings", []) if f["severity"] == "CRITICAL"]
    warnings = [f for f in review.get("findings", []) if f["severity"] == "WARNING"]
    verdict_line = (
        "## ❌ BLOCKED — resolve all critical issues before merging"
        if review["verdict"] == "BLOCKED"
        else "## ✅ APPROVED — no critical issues found"
    )
    summary = (
        f"## AI Code Review\n\n"
        f"{verdict_line}\n\n"
        f"**Summary:** {review['summary']}\n\n"
        f"| Severity | Count |\n|---|---|\n"
        f"| 🔴 Critical | {len(criticals)} |\n"
        f"| 🟡 Warning | {len(warnings)} |\n\n"
        f"*Critical issues block merge. Warnings are informational.*"
    )
    pr.create_issue_comment(summary)


def write_result(review: dict) -> None:
    criticals = sum(1 for f in review.get("findings", []) if f["severity"] == "CRITICAL")
    warnings = sum(1 for f in review.get("findings", []) if f["severity"] == "WARNING")
    with open("review_result.json", "w") as fh:
        json.dump({
            "verdict": review["verdict"],
            "critical_count": criticals,
            "warning_count": warnings,
            "summary": review.get("summary", ""),
        }, fh)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    diff = get_diff()
    if not diff.strip():
        print("No diff found — nothing to review.")
        write_result({"verdict": "APPROVED", "findings": [], "summary": "No changes detected."})
        return 0

    print(f"Reviewing diff ({len(diff):,} chars)...")
    review = run_review(diff)

    # Post comments to GitHub PR
    gh = Github(os.environ["GITHUB_TOKEN"])
    repo = gh.get_repo(os.environ["REPO"])
    pr = repo.get_pull(int(os.environ["PR_NUMBER"]))
    post_pr_comments(review, pr)

    write_result(review)

    criticals = sum(1 for f in review.get("findings", []) if f["severity"] == "CRITICAL")
    if criticals > 0:
        print(f"BLOCKED: {criticals} critical issue(s) found. Resolve before merging.")
        return 1

    print(f"APPROVED: 0 critical issues. {sum(1 for f in review.get('findings', []) if f['severity'] == 'WARNING')} warning(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
