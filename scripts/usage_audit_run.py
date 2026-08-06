#!/usr/bin/env python3
"""usage_audit_run.py — launchd shim for the monthly /usage-audit skill run.

Direct `claude -p /usage-audit` as the launchd program dies with EPERM (the
claude binary has no Documents TCC grant in launchd context). goal_watch.py
proves claude -p works when spawned FROM the venv python3 under caffeinate —
this shim is that same lane for the audit. launchd: com.olivetree.usage-audit.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent

r = subprocess.run(
    ["claude", "-p", "/usage-audit", "--model", "claude-sonnet-5",
     "--allowedTools", "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,Skill"],
    cwd=REPO, text=True, timeout=3600,
)
sys.exit(r.returncode)
