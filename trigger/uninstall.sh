#!/bin/bash
# Remove the Course Builder inbox trigger launchd agent. Reversible: your files
# in inbox/ and projects/ are left untouched.
set -u
LABEL="com.teletracking.coursebuilder.inbox"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl unload "$DEST" 2>/dev/null || true
rm -f "$DEST"
echo "Uninstalled: $LABEL (inbox/ and projects/ untouched)"
