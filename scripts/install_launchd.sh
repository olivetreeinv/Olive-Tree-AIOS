#!/bin/sh
# install_launchd.sh — install every launchd job from launchd/*.plist.tmpl
#
# launchd does NOT expand ~, $HOME, or environment variables in ProgramArguments
# or WorkingDirectory, so plists must carry absolute paths. Rather than hardcode
# them in the repo, the templates use a __REPO__ placeholder that this script
# substitutes at install time. Move the repo or change username -> just re-run.
#
# Usage:
#   scripts/install_launchd.sh            # install + load all jobs
#   scripts/install_launchd.sh --list     # show what would be installed
#   scripts/install_launchd.sh --uninstall # unload + remove all jobs

set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"
TMPL_DIR="$REPO/launchd"
DEST_DIR="$HOME/Library/LaunchAgents"

[ -d "$TMPL_DIR" ] || { echo "no launchd/ directory at $TMPL_DIR"; exit 1; }
mkdir -p "$DEST_DIR" "$REPO/logs"

for tmpl in "$TMPL_DIR"/*.plist.tmpl; do
	[ -e "$tmpl" ] || { echo "no templates found in $TMPL_DIR"; exit 1; }
	label="$(basename "$tmpl" .plist.tmpl)"
	dest="$DEST_DIR/$label.plist"

	case "$1" in
	--list)
		echo "$label -> $dest"
		continue
		;;
	--uninstall)
		launchctl unload "$dest" 2>/dev/null || true
		rm -f "$dest"
		echo "removed $label"
		continue
		;;
	esac

	# Verify the interpreter and target script exist before installing a job
	# that would otherwise fail silently at 7:45am with nobody watching.
	if [ ! -x "$REPO/.venv/bin/python" ]; then
		echo "SKIP $label: $REPO/.venv/bin/python missing - run scripts/bootstrap.sh first"
		continue
	fi
	target="$(sed "s|__REPO__|$REPO|g" "$tmpl" | grep -o "$REPO/scripts/[a-z_]*\.py" | head -1)"
	if [ -n "$target" ] && [ ! -f "$target" ]; then
		echo "SKIP $label: target script $target does not exist"
		continue
	fi

	sed "s|__REPO__|$REPO|g" "$tmpl" >"$dest"
	launchctl unload "$dest" 2>/dev/null || true
	launchctl load "$dest"
	echo "installed + loaded $label"
done

case "$1" in
--list | --uninstall) ;;
*)
	echo
	echo "Loaded Olive jobs:"
	launchctl list | grep olivetree || echo "  (none - check logs/ for errors)"
	;;
esac
