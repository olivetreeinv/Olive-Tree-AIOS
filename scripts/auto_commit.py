#!/usr/bin/env python3
"""
auto_commit.py — daily safety-net commit of the repo.

Replaces auto-commit.sh: launchd-spawned /bin/sh can't read scripts in
~/Documents (macOS TCC → "Operation not permitted"), but python3 can. Same job,
runnable from launchd.

Commits any working-tree changes on the CURRENT branch with a dated message.
Does NOT push. Skips cleanly when there's nothing to commit.
"""

import subprocess
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOG = REPO / "logs" / "auto-commit.log"


def _git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


def main() -> None:
    LOG.parent.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    _git("add", "-A")
    staged = _git("diff", "--cached", "--shortstat").stdout.strip()
    with LOG.open("a") as f:
        if not staged:
            f.write(f"[{stamp}] No changes — skipped.\n")
            return
        r = _git("commit", "-m", f"Daily auto-commit {datetime.now():%Y-%m-%d}")
        ok = "✓" if r.returncode == 0 else f"FAILED: {r.stderr.strip()[:120]}"
        f.write(f"[{stamp}] {ok}  {staged}\n")


if __name__ == "__main__":
    main()
