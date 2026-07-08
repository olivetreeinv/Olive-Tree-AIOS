# Codex Code Review — Olive Tree Investments

Automated code review for scripts and skills using **Codex**, run via the CLI
bundled with the OpenAI ChatGPT/Codex VS Code extension. Output is structured
findings that Claude Code then applies as fixes.

**Last verified:** 2026-06-08

---

## Why

Brian's standard: every new or edited script gets reviewed for **speed,
efficiency, and Python best practices** before the task is considered done.
Codex (OpenAI) is the reviewer; Claude Code applies the fixes — two models,
two lenses.

---

## How it works

The VS Code extension `openai.chatgpt` bundles the full Codex CLI at:
```
~/.vscode/extensions/openai.chatgpt-*/bin/macos-aarch64/codex
```
`scripts/codex_review.sh` resolves that binary dynamically (survives version
bumps), runs a non-interactive review with a fixed criteria prompt, prints the
findings, and saves a copy to `.codex-review/<timestamp>.md` (gitignored).

The CLI authenticates separately from the extension — it uses your ChatGPT/
Codex subscription via device auth. No OpenAI API key required.

---

## One-time setup

```bash
# Authenticate the CLI once (opens browser, uses your ChatGPT/Codex plan)
~/.vscode/extensions/openai.chatgpt-*/bin/macos-aarch64/codex login --device-auth

# Verify
~/.vscode/extensions/openai.chatgpt-*/bin/macos-aarch64/codex login status
```

If the extension ever stops bundling the CLI, install it standalone instead:
```bash
npm i -g @openai/codex
```
The wrapper falls back to a PATH install automatically.

---

## Usage

```bash
# Everyday path — review uncommitted working-tree changes (before commit)
scripts/codex_review.sh

# Review this branch against main
scripts/codex_review.sh --base main

# Review specific files (e.g. a script you just wrote)
scripts/codex_review.sh scripts/broker_search.py

# Review every Python script in scripts/
scripts/codex_review.sh --all
```

Env overrides:
- `CODEX_BIN` — full path to a codex binary (skips auto-resolution)
- `CODEX_MODEL` — model to use (default: Codex config default)

---

## The workflow (how Claude Code uses this)

1. After writing or significantly editing a script, run:
   `scripts/codex_review.sh <file>` (or `--all` for a sweep)
2. Read the findings from stdout / `.codex-review/<ts>.md`
3. Apply the HIGH and MED fixes; surface LOW/uncertain ones to Brian
4. Re-run if a fix was substantial
5. Report what changed

This satisfies the standing rule in memory: *always Codex-review new/edited
scripts for speed, efficiency, and Python best practices before closing.*

**Enforcement (added 2026-07-07):** `scripts/heartbeat.py` flags any
`scripts/*.py` modified after the newest `.codex-review/*.md` report, so
missed reviews surface in the daily 7:45am heartbeat instead of rotting.

**Repo context:** `AGENTS.md` at the repo root carries the review guidelines
(financial-calc rules, send/delete flags, domain rules). Codex reads it
automatically in review contexts — CLI, the Claude Code plugin, or GitHub.

**Optional upgrade:** OpenAI's official Claude Code plugin
([openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc)) adds
`/codex:review` and `/codex:adversarial-review` inside Claude Code — findings
land directly in Claude's context, no markdown handoff. Install (uses the
existing ChatGPT auth):

```
/plugin marketplace add openai/codex-plugin-cc
/plugin install codex@openai-codex
/codex:setup
```

---

## Review criteria (baked into the wrapper)

1. **Speed** — redundant/sequential API or network calls that could batch or
   parallelize; repeated work; unnecessary I/O.
2. **Efficiency** — wasteful data structures, re-reads, memory.
3. **Python best practices** — error handling, resource cleanup (context
   managers), type clarity, dead code, security (no hardcoded secrets, safe
   subprocess use).

Style nitpicks are skipped. Findings come back as `file:line | severity |
issue | fix`, grouped by file.
