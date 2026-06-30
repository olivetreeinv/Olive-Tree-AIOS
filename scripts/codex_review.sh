#!/usr/bin/env bash
#
# codex_review.sh — Olive Tree Investments
# Runs a Codex code review on scripts/skills for speed, efficiency, and Python
# best practices, then prints findings for Claude Code to act on.
#
# Uses the Codex CLI bundled with the OpenAI ChatGPT/Codex VS Code extension —
# no separate install needed. Resolves the binary dynamically so it survives
# extension version bumps.
#
# Usage:
#   scripts/codex_review.sh                  # review uncommitted working-tree changes
#   scripts/codex_review.sh --base main      # review this branch vs main
#   scripts/codex_review.sh FILE [FILE...]   # review specific files (e.g. all scripts)
#   scripts/codex_review.sh --all            # review every script in scripts/
#
# One-time setup (see references/codex-review.md):
#   1. The extension is installed (provides the bundled CLI).
#   2. codex login --device-auth   (authenticate the CLI once)
#
# Env overrides:
#   CODEX_BIN     full path to a codex binary (skips auto-resolution)
#   CODEX_MODEL   model to use (default: Codex config default)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$REPO_ROOT/.codex-review"
mkdir -p "$OUT_DIR"
TS="$(date +%Y%m%d-%H%M%S)"
OUT_FILE="$OUT_DIR/$TS.md"

# ── Resolve the codex binary ───────────────────────────────────────────────
resolve_codex() {
  if [[ -n "${CODEX_BIN:-}" && -x "${CODEX_BIN:-}" ]]; then
    echo "$CODEX_BIN"; return
  fi
  # Newest bundled copy from the VS Code extension (handles version bumps)
  local arch="darwin-$(uname -m)"      # e.g. darwin-arm64
  local bin_arch="macos-$(uname -m)"   # e.g. macos-arm64
  [[ "$(uname -m)" == "arm64" ]] && bin_arch="macos-aarch64"
  local found
  found="$(ls -dt "$HOME"/.vscode/extensions/openai.chatgpt-*-"$arch"/bin/"$bin_arch"/codex 2>/dev/null | head -1 || true)"
  if [[ -n "$found" && -x "$found" ]]; then echo "$found"; return; fi
  # Fall back to a PATH install (e.g. npm i -g @openai/codex)
  if command -v codex >/dev/null 2>&1; then command -v codex; return; fi
  echo ""
}

CODEX="$(resolve_codex)"
if [[ -z "$CODEX" ]]; then
  echo "❌ Could not find the Codex CLI." >&2
  echo "   Confirm the OpenAI ChatGPT/Codex VS Code extension is installed," >&2
  echo "   or install the CLI: npm i -g @openai/codex" >&2
  exit 1
fi

# ── Confirm the CLI is authenticated ───────────────────────────────────────
if ! "$CODEX" login status >/dev/null 2>&1; then
  echo "❌ Codex CLI is not logged in." >&2
  echo "   Run once:  \"$CODEX\" login --device-auth" >&2
  exit 1
fi

MODEL_ARG=()
[[ -n "${CODEX_MODEL:-}" ]] && MODEL_ARG=(-m "$CODEX_MODEL")

REVIEW_CRITERIA='Review strictly for: (1) speed — redundant or sequential API/network calls that could be batched or parallelized, repeated work, unnecessary I/O; (2) efficiency — wasteful data structures, re-reads, memory; (3) Python best practices — error handling, resource cleanup (context managers), type clarity, dead code, security (no hardcoded secrets, safe subprocess use). For each finding give: file:line, severity (HIGH/MED/LOW), the issue in one line, and the concrete fix. Group findings by file. Skip style nitpicks. If a file is clean, say so in one line.'

cd "$REPO_ROOT"

# ── Mode selection ─────────────────────────────────────────────────────────
if [[ $# -eq 0 ]]; then
  echo "🔍 Codex review — uncommitted working-tree changes" >&2
  "$CODEX" review --uncommitted ${MODEL_ARG[@]+"${MODEL_ARG[@]}"} "$REVIEW_CRITERIA" | tee "$OUT_FILE"

elif [[ "${1:-}" == "--base" ]]; then
  echo "🔍 Codex review — vs base branch: ${2:?need a branch name}" >&2
  "$CODEX" review --base "$2" ${MODEL_ARG[@]+"${MODEL_ARG[@]}"} "$REVIEW_CRITERIA" | tee "$OUT_FILE"

else
  # Explicit files or --all: review named files via exec (read-only sandbox)
  if [[ "${1:-}" == "--all" ]]; then
    FILES=()
    while IFS= read -r f; do FILES+=("$f"); done < <(find scripts -name '*.py' -type f | sort)
  else
    FILES=("$@")
  fi
  FILE_LIST="$(printf '%s\n' "${FILES[@]}")"
  echo "🔍 Codex review — ${#FILES[@]} file(s)" >&2
  PROMPT="You are doing a non-interactive code review. Review ONLY these files:
$FILE_LIST

$REVIEW_CRITERIA

Output a single markdown report. Do not modify any files."
  "$CODEX" exec --sandbox read-only ${MODEL_ARG[@]+"${MODEL_ARG[@]}"} "$PROMPT" | tee "$OUT_FILE"
fi

echo "" >&2
echo "📄 Saved: ${OUT_FILE#"$REPO_ROOT"/}" >&2
