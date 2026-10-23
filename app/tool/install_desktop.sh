#!/bin/bash

# ============================================================================
# Install the leetcode-guard app's .desktop entry for the current user.
#
# Renders tool/leetcode-guard-app.desktop.in with absolute paths into this
# checkout (the repo deploys from its working tree), validates it, and puts
# it under ~/.local/share/applications. StartupWMClass matches the window's
# --class (lib/desktop/browser.dart), so the taskbar shows the app's icon.
#
# Usage: install_desktop.sh [--dry-run]
#   --dry-run   print the entry and where it would go; write nothing
# ============================================================================

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_NAME
TOOL_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
readonly TOOL_DIR
APP_DIR="$(dirname "$TOOL_DIR")"
readonly APP_DIR
readonly TEMPLATE="${TOOL_DIR}/leetcode-guard-app.desktop.in"
readonly LAUNCHER="${TOOL_DIR}/leetcode_guard_app.sh"
readonly ICON="${APP_DIR}/assets/icon/icon.png"
readonly APPS_DIR="${XDG_DATA_HOME:-${HOME}/.local/share}/applications"
readonly TARGET="${APPS_DIR}/leetcode-guard-app.desktop"

DRY_RUN=0
TEMP_DIR=""

cleanup() {
	if [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]]; then rm -rf "$TEMP_DIR"; fi
}
trap cleanup EXIT

die() {
	echo "${SCRIPT_NAME}: $*" >&2
	exit 1
}

# Installs a missing pacman package non-interactively (sudo may prompt).
ensure_pkg() {
	local cmd="$1" pkg="$2"
	command -v "$cmd" >/dev/null 2>&1 && return 0
	if ((DRY_RUN)); then
		echo "would install: ${pkg} (for ${cmd})"
		return 0
	fi
	sudo pacman -S --needed --noconfirm "$pkg"
}

render() {
	# Paths contain '/', so '|' delimits; they never contain '|'.
	sed -e "s|@LAUNCHER@|${LAUNCHER}|" -e "s|@ICON@|${ICON}|" "$TEMPLATE"
}

main() {
	[[ -f $TEMPLATE ]] || die "missing ${TEMPLATE}"
	[[ -x $LAUNCHER ]] || die "launcher not executable: ${LAUNCHER}"
	[[ -f $ICON ]] || die "missing icon ${ICON}"
	ensure_pkg desktop-file-validate desktop-file-utils
	ensure_pkg curl curl
	ensure_pkg xdg-open xdg-utils

	TEMP_DIR="$(mktemp -d)"
	local rendered="${TEMP_DIR}/leetcode-guard-app.desktop"
	render >"$rendered"
	if command -v desktop-file-validate >/dev/null 2>&1; then
		desktop-file-validate "$rendered"
	fi

	if ((DRY_RUN)); then
		echo "would write: ${TARGET}"
		echo "----"
		cat "$rendered"
		echo "----"
		echo "would run: update-desktop-database ${APPS_DIR}"
		return 0
	fi
	mkdir -p "$APPS_DIR"
	install -m 0644 "$rendered" "$TARGET"
	if command -v update-desktop-database >/dev/null 2>&1; then
		update-desktop-database "$APPS_DIR"
	fi
	echo "installed: ${TARGET}"
}

while [[ $# -gt 0 ]]; do
	case $1 in
	--dry-run)
		DRY_RUN=1
		shift
		;;
	-h | --help)
		echo "Usage: ${SCRIPT_NAME} [--dry-run]"
		exit 0
		;;
	*)
		echo "Usage: ${SCRIPT_NAME} [--dry-run]" >&2
		exit 2
		;;
	esac
done

main
