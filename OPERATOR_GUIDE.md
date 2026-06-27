# Course Builder — Operator Guide

This is the **operating** manual: how to stand the tool up on a fresh machine,
run a course or deck end-to-end, read the build report, and recover from a failed
build. It is the companion to:

- **[templates/AUTHORING_GUIDE.md](templates/AUTHORING_GUIDE.md)** — how to *write* a
  course script (the §8 block grammar, knowledge checks, scenarios, objectives).
- **[README.md](README.md)** — a short orientation + the repo layout.
- **[brands/teletracking/BRAND_GUIDE.md](brands/teletracking/BRAND_GUIDE.md)** — the
  TeleTracking brand profile.

The tool is a **single-operator, local** application — it runs on your own machine
(Windows or Mac), binds to `127.0.0.1`, and has no accounts, server, or cloud
component. AI generation goes through a **subscription CLI** you log into once
(`claude` for Claude, or `codex` for ChatGPT) — never a metered API key.

---

## 1. Install (Windows and Mac)

### 1.1 Prerequisites

| Need | Why | Install |
|---|---|---|
| **Python 3.8+** | runs the whole engine | python.org (Windows: tick **"Add python.exe to PATH"**); Mac: `brew install python` or python.org |
| **Python deps** | PowerPoint/.docx/.pdf/OCR surfaces | `pip install -r requirements.txt` |
| **A subscription CLI** | AI course/deck generation | `claude` (Claude Code) **or** `codex` (ChatGPT) — see 1.3 |
| **Tesseract** *(optional)* | read text out of image sources (OCR) | see 1.4 — only if you feed images as source |

The course engine itself is pure standard library; the deps add the optional
output/input surfaces. If a dep is missing, the feature that needs it degrades with
a clear note rather than crashing.

### 1.2 Get the dependencies

```bash
# from the repo root
python -m pip install -r requirements.txt      # "python3" on Mac
```

For a fully reproducible install you can freeze the lower-bound pins in
`requirements.txt` to exact `==` versions.

### 1.3 Log into an AI provider (one-time)

AI generation shells out to a CLI you've already authenticated. Pick at least one:

- **Claude** — install Claude Code, run `claude` once and sign in. The engine calls
  it headlessly during generation.
- **ChatGPT (Codex)** — `npm install -g @openai/codex`, run `codex`, choose
  **"Sign in with ChatGPT."** The engine calls `codex exec` headlessly and scrubs any
  `OPENAI_API_KEY`/`CODEX_API_KEY` so it authenticates via your **subscription**, not a
  metered key.

The dashboard's **AI account** step shows which providers it detects. If neither is
installed, the deterministic build path (Section 3) still works — you just author the
script yourself instead of generating it.

> The deterministic CLI never needs an AI provider. Only the *generate* steps do.

### 1.4 Tesseract OCR (only if you ingest images)

OCR reads text out of `.png/.jpg/.tif/…` source files. Install the engine only if you
need that:

- **macOS:** `brew install tesseract`
- **Windows:** `winget install UB-Mannheim.TesseractOCR` (or the UB-Mannheim installer).
  The installer puts `tesseract.exe` in `C:\Program Files\Tesseract-OCR\` and does **not**
  add it to PATH — the engine **auto-detects that default location**, so no manual PATH
  edit is needed. If you install it somewhere else, add that folder to PATH.
- **Linux:** `apt-get install tesseract-ocr`

Without Tesseract, image sources are **skipped with a hint** — nothing breaks.

---

## 2. Launch the dashboard (the GUI)

| Platform | How |
|---|---|
| **macOS** | double-click `dashboard/launch.command` |
| **Windows** | double-click `dashboard\launch.bat` (or right-click `launch.ps1` → Run with PowerShell) |
| **Any** | `python dashboard/server.py` from the repo root (`python3` on Mac) |

It opens `http://127.0.0.1:<port>` in your browser. If buttons seem dead after an
update, **hard-refresh** (Cmd/Ctrl+Shift+R) — the server sends `no-store`, but a tab
left open across a restart can hold a stale page.

The folder picker in the app is an **in-browser navigator** (no native dialog). It can
reach your home folder, the repo, the temp area, and mounted/external drives
(`/Volumes` on Mac; other drive letters like `D:\` on Windows).

---

## 3. The deterministic build CLI (no AI)

For a script you already have, the CLI builds straight to a package. This path is
fully reproducible and needs no AI provider.

```bash
./build from-md-course <script.md> --images <dir> --out <out.zip> [--format cmi5] [--brand teletracking]
./build from-md        <script.md> --which N --images <dir> --out <out.zip> [--brand teletracking]
./build from-docx      <doc.docx>  --images <dir> --out <out.zip> [--brand teletracking]
./build from-rise      <raw.zip>   --out <out.zip> [--brand teletracking]
./build to-pptx        <script.md> --images <dir> --out <deck.pptx> [--brand teletracking]
./build slide          --content <data.json> --out <slide.pptx> [--brand teletracking]
```

- **Windows:** use `build.bat` with the same arguments (`build.bat from-md-course …`).
- Omit `--brand` for the neutral default profile; `--brand teletracking` applies the
  TeleTracking profile. `--validate` runs SCORM conformance and fails hard if it doesn't pass.
- Run `./build` with no arguments for the built-in help.

Every build writes a **build report** next to its artifact (Section 5).

---

## 4. The dashboard flow

The app has two tracks, each a focused stepper (a left rail shows done ✓ / current /
up-next; Back / Continue at the bottom).

### 4.1 Course track (8 steps)

1. **Project** — name the project / pick its folder.
2. **AI account** — confirm a provider is detected (Claude and/or ChatGPT).
3. **Source materials** — point at a folder of source docs (`.docx/.pdf/.html/.odt/.rtf/.md/.csv/…`
   and images via OCR). Unreadable files are listed with an actionable note (e.g. a legacy
   `.doc` to re-save as `.docx`).
4. **Generate scripts** — draft the course script **and** an SME-review `.docx` into the
   project folder. Choose a **Purpose** preset (standard / compliance / onboarding /
   product-skill / refresher) to shape voice, depth, and assessment posture.
5. **Apply SME review** — feed the reviewed `.docx` back to layer the SME's edits into the script.
6. **Output format** — pick SCORM 1.2 / SCORM 2004 / cmi5.
7. **Generate preview** — build each course into a **preview area** and review it.
   **Nothing reaches the output folder yet.** Read the build report panel here.
8. **Publish** — publish the courses you approve to the output folder as packages.

### 4.2 Slide-deck track (3 steps)

1. **Source & generate** — sources + a **Purpose** preset → generate slides.
2. **Review & edit slides** — change a layout, flip a slide's **theme** (Auto / Dark /
   Light), reorder, add/remove, or regenerate just the checked aspects (Content / Layout /
   Color). Thumbnails preview each slide.
3. **Build presentation** — render to an editable, on-brand `.pptx`.

> Review **before** publishing. The preview (step 7 / slide review) is your approval
> gate — what you see is what ships. For full-bleed image slides especially, the preview
> now matches the `.pptx` so you're approving the real thing.

---

## 5. Read the build report (your signal something's off)

The engine **never crashes on bad input** — by design it drops malformed pieces to
empty rather than failing. For an operator that's a liability, so every build emits a
**report** so a silent drop can't ship unnoticed.

- **Where:** a `<stem>.report.json` file is written **beside every artifact** (the `.zip`
  or `.pptx`). It's also how the dashboard reads results back across the build subprocess.
- **In the dashboard:** the preview step renders a **Build report** panel — **red** for an
  error, **amber** for a warning — **even on an otherwise "successful" build.**
- **What it surfaces:**
  - **Dropped/skipped blocks** — a block the flatten couldn't place, or a source the
    importer couldn't read.
  - **Missing assets** — a `*Visual:*` image referenced but not found.
  - **Lint findings** — run **at build time**, so quiz-scoring problems (e.g. a knowledge
    check that marks the wrong number of answers correct, or a duplicate option label)
    surface even for hand-authored scripts that never went through generation.
  - **SCORM conformance** — pass/fail of the package validation.

**Treat a non-empty report as "stop and look," not "done."** A green build with an amber
report still means something was dropped.

---

## 6. Recover from a failed or partial build

| Symptom | Likely cause | Fix |
|---|---|---|
| **Build report lists a dropped block** | a block type the flatten can't render, or malformed grammar | open the script, fix that block (see AUTHORING_GUIDE), rebuild |
| **Report lists a missing `*Visual:*` asset** | the image isn't in the `--images` folder / source folder | add the image (matching filename) or remove the reference, rebuild |
| **Lint error on a knowledge check** | wrong count of correct answers, duplicate option label, empty objectives, dead-end scenario | correct the question in the script, rebuild |
| **SCORM conformance fails (`--validate`)** | malformed manifest/structure | the report is still written before the failure — read it, fix, rebuild |
| **A source file was skipped** | unreadable format (legacy `.doc`), no OCR engine, or over the size cap | re-save `.doc` as `.docx`; install Tesseract for images; split an oversized source |
| **Generation hangs or errors** | provider not logged in / not on PATH | re-run `claude` or `codex` and sign in; confirm the AI-account step detects it |
| **Dashboard buttons unresponsive after an update** | stale cached page | hard-refresh (Cmd/Ctrl+Shift+R); restart the server |
| **A source on an external drive isn't reachable** | navigator allowlist | Mac: it's under `/Volumes`; Windows: the drive letter is allowed — confirm the drive is mounted |

Builds are **idempotent and safe to re-run** — fix the script or the inputs and build
again; nothing is published until you explicitly publish in step 8.

---

## 7. Quick reference

```text
Launch GUI:    dashboard/launch.command (Mac) · dashboard\launch.bat (Win) · python dashboard/server.py
Build a SCORM: ./build from-md-course script.md --images img/ --out course.zip --brand teletracking --validate
Build a deck:  ./build to-pptx script.md --images img/ --out deck.pptx --brand teletracking
Report:        <out-name>.report.json  (also shown as the dashboard Build-report panel)
Authoring:     templates/AUTHORING_GUIDE.md
Providers:     claude  (Claude Code)  ·  codex  (ChatGPT, "Sign in with ChatGPT")
```

> **Windows note:** the launchers and drive-letter source paths are implemented and
> unit-tested, but a full end-to-end Windows smoke pass (launch → build → generate →
> ingest) is the operator's to confirm on a real PC. If anything in Sections 1–2 doesn't
> behave on Windows, that's the gap to report.
