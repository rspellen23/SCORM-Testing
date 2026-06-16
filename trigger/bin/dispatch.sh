#!/bin/bash
# Course Builder — inbox dispatcher.
#
# Fired by launchd whenever trigger/inbox/ changes. For each PROJECT FOLDER
# dropped into the inbox, it waits until the folder stops changing (settle),
# extracts the text of every accepted source doc, asks `claude -p` to
# auto-decompose the corpus into N microlearning scripts, and writes one
# combined script document into projects/<Topic>/. The inbox returns to empty.
#
# Reversible: this script is inert until the launchd agent is loaded.
# Idempotent: a folder is processed once, then moved out of the inbox.

set -u

# --- paths -------------------------------------------------------------------
# Derive the package root from this script's own location (trigger/bin/), so the
# whole folder is portable — drop it anywhere and it still resolves.
REPO="${REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
TRIG="$REPO/trigger"
INBOX="$TRIG/inbox"
PROJ="$REPO/projects"
LOGS="$TRIG/logs"
PROMPT="$TRIG/bin/author-prompt.md"
EXTRACT="$TRIG/bin/extract_text.py"
LOCK="$TRIG/.dispatch.lock"

# --- engine (per-machine) ----------------------------------------------------
# This tool lives on each person's machine and uses whichever agent that box
# has. install.sh bakes the resolved binary paths into the launchd plist's
# environment; these are the fallbacks when run by hand. Override by exporting
# ENGINE / CLAUDE_BIN / CODEX_BIN.
# launchd has a minimal PATH and no nvm; seed the usual install spots first.
export PATH="$HOME/.nvm/versions/node/current/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
ENGINE="${ENGINE:-auto}"
CLAUDE_BIN="${CLAUDE_BIN:-$(command -v claude 2>/dev/null || true)}"
CODEX_BIN="${CODEX_BIN:-$(command -v codex 2>/dev/null || true)}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 2>/dev/null || echo /usr/bin/python3)}"

# We run OUTSIDE any interactive session here; clear the nested-session guards
# so the headless agent will run under launchd.
unset CLAUDECODE CLAUDE_CODE_ENTRYPOINT 2>/dev/null || true

# Resolve which engine to use on this machine.
detect_engine() {
  case "$ENGINE" in
    claude|codex) echo "$ENGINE"; return ;;
  esac
  if [ -x "$CLAUDE_BIN" ] || command -v claude >/dev/null 2>&1; then echo claude; return; fi
  if command -v "$CODEX_BIN" >/dev/null 2>&1; then echo codex; return; fi
  echo none
}

# Draft with the local engine. Prompt is passed as an ARG (never piped) and
# stdin is /dev/null so neither agent blocks waiting on a non-TTY pipe. Both
# run with cwd=$REPO (so the prompt's relative doc paths resolve) and read-only
# file access; both print only their final message to stdout.
run_engine() {
  local prompt="$1" engine; engine="$(detect_engine)"
  case "$engine" in
    claude) ( cd "$REPO" && "${CLAUDE_BIN:-claude}" -p --allowedTools "Read Glob Grep" "$prompt" </dev/null ) ;;
    codex)  ( cd "$REPO" && "${CODEX_BIN:-codex}" exec --sandbox read-only "$prompt" </dev/null ) ;;
    *)      return 1 ;;
  esac
}

# --- settle tuning -----------------------------------------------------------
TICK=5            # seconds between folder fingerprints
STABLE_NEEDED=3   # consecutive unchanged fingerprints = settled (~15s quiet)
MAX_TICKS=36      # hard cap (~3 min) so a stuck copy can't loop forever

mkdir -p "$INBOX" "$PROJ" "$LOGS"

log() { echo "[$(/bin/date '+%Y-%m-%d %H:%M:%S')] $*"; }

# Single-instance: mkdir is atomic. If another run holds the lock, exit; the
# main loop below re-scans, so nothing dropped during a run is lost.
if ! mkdir "$LOCK" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

# Fingerprint = sorted (path,size,mtime) of every real file in the folder.
fingerprint() {
  find "$1" -type f ! -name '.*' -exec /usr/bin/stat -f '%N %z %m' {} \; \
    | sort | /sbin/md5 2>/dev/null || \
  find "$1" -type f ! -name '.*' -exec /usr/bin/stat -f '%N %z %m' {} \; \
    | sort | md5sum
}

process_one() {
  local dir="$1" name run_log out proj corpus breakdown scripts ts
  name="$(basename "$dir")"
  ts="$(/bin/date '+%Y%m%d-%H%M%S')"
  run_log="$LOGS/${ts}_$(echo "$name" | tr ' /' '__').log"

  {
    log "PROJECT: $name"

    # ---- settle: wait until the folder stops changing -----------------------
    local prev cur stable=0 i=0
    prev="$(fingerprint "$dir")"
    while [ "$i" -lt "$MAX_TICKS" ]; do
      sleep "$TICK"; i=$((i + 1))
      cur="$(fingerprint "$dir")"
      if [ "$cur" = "$prev" ]; then stable=$((stable + 1)); else stable=0; fi
      prev="$cur"
      [ "$stable" -ge "$STABLE_NEEDED" ] && break
    done
    log "settled after ${i} tick(s)"

    touch "$dir/.processing"

    # ---- extract the combined corpus ----------------------------------------
    proj="$PROJ/$name"
    mkdir -p "$proj/sources"
    corpus="$proj/sources/_corpus.txt"
    if ! "$PYTHON_BIN" "$EXTRACT" "$dir" > "$corpus" 2>>"$run_log.extract"; then
      cat "$run_log.extract" 2>/dev/null
      log "ABORT: no readable source documents — leaving folder in inbox for you to check"
      rm -f "$dir/.processing"
      rm -rf "$proj"
      return 1
    fi
    cat "$run_log.extract" 2>/dev/null; rm -f "$run_log.extract"

    # ---- draft with the local engine (read-only; output captured from stdout) --
    local filled engine
    engine="$(detect_engine)"
    if [ "$engine" = "none" ]; then
      log "ABORT: no drafting engine found (need 'claude' or 'codex' on PATH) — folder left in inbox"
      rm -f "$dir/.processing"
      rm -rf "$proj"
      return 1
    fi
    filled="$(sed -e "s|{{TOPIC}}|$name|g" -e "s|{{CORPUS_PATH}}|$corpus|g" "$PROMPT")"
    log "drafting with engine: $engine ..."
    out="$( run_engine "$filled" 2>>"$run_log.engine" )"
    if [ -z "$out" ]; then
      cat "$run_log.engine" 2>/dev/null
      log "ABORT: $engine returned no output — folder left in inbox"
      rm -f "$dir/.processing"
      return 1
    fi
    rm -f "$run_log.engine"

    # ---- split the delimited response into the two artifacts ----------------
    breakdown="$proj/_breakdown.md"
    scripts="$proj/${name} — Scripts.md"
    printf '%s' "$out" | /usr/bin/awk '
      /^===BREAKDOWN===/ { sec="b"; next }
      /^===SCRIPTS===/   { sec="s"; next }
      sec=="b" { print > B }
      sec=="s" { print > S }
    ' B="$breakdown" S="$scripts"

    if [ ! -s "$scripts" ]; then
      log "WARN: delimiters not found; saving raw output to ${name} — Scripts.md"
      printf '%s' "$out" > "$scripts"
      : > "$breakdown"
    fi

    # ---- finalize: keep sources with the project, empty the inbox -----------
    /bin/mv "$dir"/* "$proj/sources/" 2>/dev/null
    /bin/mv "$dir"/.[!.]* "$proj/sources/" 2>/dev/null
    rm -f "$proj/sources/.processing"
    rmdir "$dir" 2>/dev/null || rm -rf "$dir"

    log "DONE -> $proj"
    log "  scripts:   $scripts"
    log "  breakdown: $breakdown"
  } 2>&1 | /usr/bin/tee -a "$run_log"
}

# Re-scan after each pass so folders that arrive *during* a run are caught
# without waiting for another launchd event.
while :; do
  found=0
  for dir in "$INBOX"/*/; do
    [ -d "$dir" ] || continue                  # no project folders
    [ -e "${dir}.processing" ] && continue     # shouldn't persist, but be safe
    found=1
    process_one "$dir"
  done
  [ "$found" -eq 0 ] && break
done
