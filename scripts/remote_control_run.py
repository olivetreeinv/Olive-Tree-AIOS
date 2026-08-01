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
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent

r = subprocess.run(
    ["claude", "remote-control", "--name", "Olive AIOS"],
    cwd=REPO, text=True,
    # First run asks "Enable Remote Control? (y/n)". The answer sticks
    # (~/.claude.json remoteDialogSeen), but with no TTY under launchd an
    # unanswered re-prompt hangs the job silently instead of failing. One
    # piped "y" costs nothing and removes that failure mode.
    input="y\n",
)
sys.exit(r.returncode)
