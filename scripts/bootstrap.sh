#!/bin/sh
# bootstrap.sh — bring a fresh clone of the Olive AIOS to a working state.
#
# Safe to re-run. Nothing here hardcodes a path or a username: the repo locates
# itself, so it works under any directory or account.
#
# Usage:
#   scripts/bootstrap.sh                # venv + deps + index (no scheduled jobs)
#   scripts/bootstrap.sh --with-launchd # also install the launchd jobs

set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

echo "==> repo: $REPO"
mkdir -p logs

# --- Python interpreter -----------------------------------------------------
# Prefer Homebrew 3.13; fall back to whatever python3 is on PATH.
if [ -x /opt/homebrew/bin/python3.13 ]; then
	PY=/opt/homebrew/bin/python3.13
elif command -v python3.13 >/dev/null 2>&1; then
	PY="$(command -v python3.13)"
else
	PY="$(command -v python3)"
	echo "    warning: python3.13 not found, using $PY ($("$PY" -V 2>&1))"
	echo "    install a modern Python with: brew install python@3.13"
fi
echo "==> interpreter: $PY ($("$PY" -V 2>&1))"

# --- virtualenv -------------------------------------------------------------
if [ ! -x "$REPO/.venv/bin/python" ]; then
	echo "==> creating .venv"
	"$PY" -m venv "$REPO/.venv"
else
	echo "==> .venv already exists ($("$REPO/.venv/bin/python" -V 2>&1))"
fi

echo "==> installing dependencies"
"$REPO/.venv/bin/python" -m pip install --upgrade pip -q
"$REPO/.venv/bin/pip" install -q -r "$REPO/requirements.txt"

# --- .env -------------------------------------------------------------------
if [ ! -f "$REPO/.env" ]; then
	echo "==> no .env found - copy your keys in before running any skill"
	[ -f "$REPO/.env.example" ] && cp "$REPO/.env.example" "$REPO/.env" && echo "    seeded .env from .env.example"
fi

# --- knowledge index --------------------------------------------------------
echo "==> building the knowledge index (first run downloads the embedding model)"
"$REPO/.venv/bin/python" "$REPO/scripts/aios_index.py"

# --- shell aliases ----------------------------------------------------------
# Wire ~/.zshrc to the repo's alias file so olive-rc / olive-py / olive-jobs
# exist on this machine too. Idempotent.
ZSHRC="$HOME/.zshrc"
if [ -f "$REPO/shell/aliases.zsh" ] && ! grep -q "shell/aliases.zsh" "$ZSHRC" 2>/dev/null; then
	printf '\n# Olive AIOS shell aliases (tracked in the repo, so new machines get them too)\n[ -f "%s/shell/aliases.zsh" ] && source "%s/shell/aliases.zsh"\n' "$REPO" "$REPO" >>"$ZSHRC"
	echo "==> added the repo alias file to $ZSHRC (open a new shell to pick it up)"
else
	echo "==> shell aliases already wired (or shell/aliases.zsh missing)"
fi

# --- scheduled jobs (opt-in) ------------------------------------------------
if [ "$1" = "--with-launchd" ]; then
	echo "==> installing launchd jobs"
	sh "$REPO/scripts/install_launchd.sh"
else
	echo "==> skipping launchd jobs (re-run with --with-launchd to install them)"
fi

echo
echo "Bootstrap complete."
echo "Run scripts with: .venv/bin/python scripts/<name>.py"
