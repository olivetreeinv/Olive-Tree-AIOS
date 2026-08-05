#!/usr/bin/env python3
"""remote_control_run.py — launchd shim for the always-on Remote Control session.

`claude remote-control` as the launchd program dies with EPERM (the claude binary
has no Documents TCC grant in launchd context) — the same failure usage_audit_run.py
works around. Spawning it FROM the venv python3 under caffeinate is the lane that
works. launchd: com.olivetree.remote-control.

Long-running on purpose: this is a server that holds the phone's session open, so
there is no timeout. launchd KeepAlive restarts it after the ~10-minute network
timeout or a reboot.
"""
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).parent.parent

# The phone's environment list accumulates entries for this same directory —
# observed three, only one live at a time — and ids get recycled across restarts,
# so "the one that worked last time" is not a reliable tell. Under one shared
# name they were indistinguishable, and tapping a dead entry lands you in a cloud
# sandbox ("Allocating sandbox") with none of this machine's state. Stamping the
# start time makes the live entry self-identifying.
SESSION_NAME = f"Olive AIOS {datetime.now().strftime('%m-%d %H:%M')}"


def _claude_bin() -> str:
    """Resolve the claude binary. launchd strips PATH to /usr/bin:/bin, and a
    non-login shell won't have Homebrew on PATH either — bare "claude" then
    raises FileNotFoundError, which reads as a confusing "file not found"."""
    return (
        shutil.which("claude")
        or next((p for p in ("/opt/homebrew/bin/claude", "/usr/local/bin/claude",
                             os.path.expanduser("~/.claude/local/claude")) if os.path.exists(p)), None)
        or "claude"  # last resort: let subprocess raise the usual FileNotFoundError
    )


r = subprocess.run(
    [_claude_bin(), "remote-control", "--name", SESSION_NAME],
    cwd=REPO, text=True,
    # First run asks "Enable Remote Control? (y/n)". The answer sticks
    # (~/.claude.json remoteDialogSeen), but with no TTY under launchd an
    # unanswered re-prompt hangs the job silently instead of failing. One
    # piped "y" costs nothing and removes that failure mode.
    input="y\n",
)
sys.exit(r.returncode)
