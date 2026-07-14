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


def git(*args, env=None, timeout=120) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, env=env, timeout=timeout)


def _checked(result: subprocess.CompletedProcess, step: str, stamp: str) -> subprocess.CompletedProcess:
    """Verify a git plumbing call succeeded; log and abort the run otherwise."""
    if result.returncode != 0:
        with LOG.open("a") as f:
            f.write(f"[{stamp}] ERROR at {step} (exit {result.returncode}): {result.stderr.strip()[:300]}\n")
        raise SystemExit(1)
    return result


def main() -> None:
    LOG.parent.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Stage everything into a THROWAWAY index so the real index is never touched.
    tmp_index = tempfile.NamedTemporaryFile(delete=False, suffix=".idx").name
    env = {**os.environ, "GIT_INDEX_FILE": tmp_index}
    try:
        _checked(git("read-tree", "HEAD", env=env), "read-tree", stamp)      # seed temp index from current commit
        _checked(git("add", "-A", env=env), "add", stamp)                    # stage all working-tree changes into temp index
        tree = _checked(git("write-tree", env=env), "write-tree", stamp).stdout.strip()

        parent = git("rev-parse", "-q", "--verify", f"refs/heads/{BRANCH}").stdout.strip()
        if parent and git("rev-parse", f"{parent}^{{tree}}").stdout.strip() == tree:
            with LOG.open("a") as f:
                f.write(f"[{stamp}] No changes — skipped.\n")
            return

        args = ["commit-tree", tree, "-m", f"autosave {stamp}"]
        if parent:
            args += ["-p", parent]
        commit = _checked(git(*args, env=env), "commit-tree", stamp).stdout.strip()
        _checked(git("update-ref", f"refs/heads/{BRANCH}", commit), "update-ref", stamp)   # no `git commit` → post-commit hook stays quiet

        push = git("push", "origin", BRANCH)
        ok = "✓ pushed" if push.returncode == 0 else f"local only (push failed: {push.stderr.strip()[:100]})"
        with LOG.open("a") as f:
            f.write(f"[{stamp}] autosave {commit[:8]} — {ok}\n")
    except subprocess.TimeoutExpired as e:
        with LOG.open("a") as f:
            f.write(f"[{stamp}] ERROR: {e.cmd} timed out after {e.timeout}s\n")
        raise SystemExit(1)
    finally:
        try:
            os.unlink(tmp_index)
        except OSError:
            pass


if __name__ == "__main__":
    main()
