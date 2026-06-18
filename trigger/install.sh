#!/bin/bash
# Install the Course Builder inbox trigger as a launchd agent on THIS machine.
# Resolves the local AI agent + python paths and bakes them into the plist, so
# the folder is portable: drop it anywhere, run this, and it works.
#
#   bash trigger/install.sh            # auto-detect engine (claude, else codex)
#   ENGINE=codex bash trigger/install.sh
#
# Re-running is safe (it reloads). Undo with trigger/uninstall.sh.
set -euo pipefail

TRIG="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$TRIG/com.teletracking.coursebuilder.inbox.plist.template"
LABEL="com.coursecraft.inbox"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"

DISPATCH="$TRIG/bin/dispatch.sh"
INBOX="$TRIG/inbox"
OUT_LOG="$TRIG/logs/launchd.out.log"
ERR_LOG="$TRIG/logs/launchd.err.log"

ENGINE="${ENGINE:-auto}"
CLAUDE_BIN="${CLAUDE_BIN:-$(command -v claude || true)}"
CODEX_BIN="${CODEX_BIN:-$(command -v codex || true)}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || echo /usr/bin/python3)}"

if [ -z "$CLAUDE_BIN" ] && [ -z "$CODEX_BIN" ]; then
  echo "ERROR: neither 'claude' nor 'codex' is on PATH. Install one (or set"
  echo "       CLAUDE_BIN=/path or CODEX_BIN=/path) before installing." >&2
  exit 1
fi

mkdir -p "$INBOX" "$TRIG/logs" "$TRIG/../projects" "$HOME/Library/LaunchAgents"
chmod +x "$DISPATCH" "$TRIG/bin/extract_text.py"

sed -e "s|__DISPATCH__|$DISPATCH|g" \
    -e "s|__INBOX__|$INBOX|g" \
    -e "s|__OUT_LOG__|$OUT_LOG|g" \
    -e "s|__ERR_LOG__|$ERR_LOG|g" \
    -e "s|__ENGINE__|$ENGINE|g" \
    -e "s|__CLAUDE_BIN__|$CLAUDE_BIN|g" \
    -e "s|__CODEX_BIN__|$CODEX_BIN|g" \
    -e "s|__PYTHON_BIN__|$PYTHON_BIN|g" \
    "$TEMPLATE" > "$DEST"

launchctl unload "$DEST" 2>/dev/null || true
launchctl load "$DEST"

echo "Installed + loaded: $LABEL"
echo "  watching: $INBOX"
echo "  engine:   $ENGINE  (claude=${CLAUDE_BIN:-none} codex=${CODEX_BIN:-none})"
echo "Drop a topic folder into the inbox to test. Logs: $TRIG/logs/"
