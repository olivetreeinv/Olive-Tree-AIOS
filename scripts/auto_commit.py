#!/usr/bin/env python3
"""
auto_commit.py — daily safety-net snapshot to a dedicated `autosave` branch.

Snapshots the full working tree (tracked + untracked, respecting .gitignore) onto
refs/heads/autosave and pushes it — WITHOUT switching branches, staging anything
on your current branch, or touching your index. It does this with a throwaway
temp index + git plumbing (write-tree / commit-tree / update-ref), so your real
feature branch and `git status` are completely undisturbed.

Recover anything later with:  git checkout autosave -- path/to/file
(launchd runs this via python3 — /bin/sh can't read scripts in ~/Documents.)
"""

import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOG = REPO / "logs" / "auto-commit.log"
BRANCH = "autosave"


def git(*args, env=None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, env=env)


def main() -> None:
    LOG.parent.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Stage everything into a THROWAWAY index so the real index is never touched.
    tmp_index = tempfile.NamedTemporaryFile(delete=False, suffix=".idx").name
    env = {**os.environ, "GIT_INDEX_FILE": tmp_index}
    try:
        git("read-tree", "HEAD", env=env)      # seed temp index from current commit
        git("add", "-A", env=env)              # stage all working-tree changes into temp index
        tree = git("write-tree", env=env).stdout.strip()

        parent = git("rev-parse", "-q", "--verify", f"refs/heads/{BRANCH}").stdout.strip()
        if parent and git("rev-parse", f"{parent}^{{tree}}").stdout.strip() == tree:
            with LOG.open("a") as f:
                f.write(f"[{stamp}] No changes — skipped.\n")
            return

        args = ["commit-tree", tree, "-m", f"autosave {stamp}"]
        if parent:
            args += ["-p", parent]
        commit = git(*args, env=env).stdout.strip()
        git("update-ref", f"refs/heads/{BRANCH}", commit)   # no `git commit` → post-commit hook stays quiet

        push = git("push", "origin", BRANCH)
        ok = "✓ pushed" if push.returncode == 0 else f"local only (push failed: {push.stderr.strip()[:100]})"
        with LOG.open("a") as f:
            f.write(f"[{stamp}] autosave {commit[:8]} — {ok}\n")
    finally:
        try:
            os.unlink(tmp_index)
        except OSError:
            pass


if __name__ == "__main__":
    main()
