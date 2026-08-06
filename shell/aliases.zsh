# shell/aliases.zsh — shell aliases that travel with the repo.
#
# Sourced from ~/.zshrc (wired up by scripts/bootstrap.sh). Keeping these in the
# repo instead of hand-copying between machines means a new machine gets them
# with the clone — and the docs that reference them stay true.
#
# Nothing here hardcodes a path or a uid: AIOS_REPO is derived from this file's
# own location, and $(id -u) resolves at runtime.

AIOS_REPO="${${(%):-%x}:A:h:h}"
export AIOS_REPO

# Restart the always-on Claude Remote Control session (launchd KeepAlive job).
# Referenced in CLAUDE.md as the documented restart command.
alias olive-rc='launchctl kickstart -k gui/$(id -u)/com.olivetree.remote-control'

# Tail the remote control log — first stop when the phone session goes quiet.
alias olive-rc-log='tail -f "$AIOS_REPO/logs/remote-control.log"'

# Status of every Olive launchd job (PID = running, non-zero third column = failing).
alias olive-jobs='launchctl list | grep olivetree'

# Run a repo script through the venv, from anywhere.
# Usage: olive-py scripts/heartbeat.py
alias olive-py='"$AIOS_REPO/.venv/bin/python"'

# Jump to the repo.
alias olive='cd "$AIOS_REPO"'
