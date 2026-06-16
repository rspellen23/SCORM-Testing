# Course Builder — Inbox Trigger

Drop a **project folder** of source documents into `inbox/`. When it stops
changing, the system reads every document together, auto-decomposes the topic
into N microlearnings, and writes **one combined script document** into
`../projects/<Topic>/` for SME review. The inbox returns to empty.

This is the *front* of the pipeline (raw docs → draft scripts). The scripts it
produces are drafts for human review, in the engine's `.md` grammar, so they
feed straight into `from-md` once approved.

## How to use it

1. Gather all the source docs for ONE topic into a folder named for the topic,
   e.g. `Transfer Request Mobile/`.
2. Drag that **whole folder** into `inbox/`.
3. Wait. When the folder settles (~15s of no changes), drafting runs.
4. Find the result in `../projects/Transfer Request Mobile/`:
   - `Transfer Request Mobile — Scripts.md` — all microlearnings (`## Microlearning 1..N`)
   - `_breakdown.md` — how it split the topic + and SME GAP notes
   - `sources/` — the original docs, kept with the project

Accepted source types: **`.docx`, `.md`, `.txt`**. PDFs are **skipped with a
note** in the log (no PDF text extractor is installed yet — convert to .docx/.md,
or ask to add `pypdf`). Keep folder names plain (avoid `| & \`).

## Install (makes it live)

```sh
bash trigger/install.sh            # auto-detects claude, else codex
# or force one:  ENGINE=codex bash trigger/install.sh
```

`install.sh` resolves this machine's `claude`/`codex`/`python3` paths, bakes them
into the launchd plist (generated from `…plist.template`), and loads it. The
folder is portable — run it from wherever the package lives.

## Uninstall (fully reversible)

```sh
bash trigger/uninstall.sh          # inbox/ and projects/ are left untouched
```

## Logs

- Per-run detail: `logs/<timestamp>_<topic>.log`
- launchd's own stdout/stderr: `logs/launchd.out.log`, `logs/launchd.err.log`

## Pieces

- `install.sh` / `uninstall.sh` — load / unload the launchd agent on this machine
- `bin/dispatch.sh` — settle → extract → engine → split → file the output
- `bin/extract_text.py` — pulls plain text from each accepted doc
- `bin/author-prompt.md` — the fixed authoring contract given to the engine
- `examples/responsible-ai-hallucination-script.md` — the gold output example
- `com.teletracking.coursebuilder.inbox.plist.template` — plist filled in by `install.sh`

## Engines (this lives on each machine, per person)

The trigger uses whichever AI agent is installed on **that** machine. The
authoring contract (`bin/author-prompt.md`) is shared, so the *structure* of the
drafts stays consistent across the team even though the underlying model differs.

| Your machine has | What runs | Setup |
|---|---|---|
| **Claude Code** (`claude`) | `claude -p --allowedTools "Read Glob Grep" <prompt>` | none — works as-is |
| **OpenAI Codex** (`codex`) | `codex exec --sandbox read-only <prompt>` | sign in to Codex once; ensure `codex` is on PATH |

Selection is automatic (`ENGINE=auto`): it picks `claude` if present, otherwise
`codex`. Force it by exporting `ENGINE=claude` or `ENGINE=codex`. Both run with
read-only file access, prompt passed as an argument (not piped — Codex hangs on a
non-TTY stdin pipe), and capture the final message from stdout.

Per-machine knobs at the top of `dispatch.sh` (or export them):
`ENGINE`, `CLAUDE_BIN`, `CODEX_BIN`, `PYTHON_BIN`. Edit `CLAUDE_BIN`/`CODEX_BIN`
if the binary isn't on launchd's minimal PATH (e.g. a different node version).

> **Codex branch is untested on James's machine** (no `codex` installed here).
> The flags follow current OpenAI docs, but the first Codex-machine run should be
> verified — see the install + drop-test below.
