#!/bin/bash
# Double-click this file to launch the course-builder dashboard.
# It starts the local helper and opens the app in your browser.
cd "$(dirname "$0")/.."
echo "Starting course-builder dashboard…"
exec python3 dashboard/server.py
