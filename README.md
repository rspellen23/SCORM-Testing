# course-builder

One **company-agnostic** course-building system. The full engine ships inside this
folder (`./src`) — nothing outside it is required, so you can copy or move this
folder anywhere (e.g. Google Drive) and it still runs.

The system itself carries **no company references and no client data**. All
branding (names, colors, logo, fonts) is loaded from an external **brand profile**
under `./brands` at build time. Exports conform to whichever brand you load; the
system stays neutral.

One Markdown (or Word) source → branded, tracked **SCORM 1.2 / cmi5**, an editable
**PowerPoint**, or an SME-review **Word** doc.

## Build
```bash
# Neutral by default (no --brand needed):
./build from-md-course script.md --images ./imgs --out course.zip            # SCORM
./build from-md-course script.md --images ./imgs --out course.zip --format cmi5
./build to-pptx        script.md --images ./imgs --out deck.pptx             # course → PowerPoint
./build slide --content data.json --out slide.pptx                          # standalone infographic slide
./build from-docx      doc.docx  --images ./imgs --out course.zip
./build from-rise      raw.zip                   --out course.zip            # import a Rise export
./build from-ir        course.ir.json            --out course.zip
./build cover --title '...' --out ./art
./build --help

# Apply branding — load an external brand profile:
./build from-md-course script.md --images ./imgs --out course.zip --brand teletracking
```

## Transitions
Add slide-to-slide motion to any PowerPoint output with `--transition`
(works on both `slide` and `to-pptx`):
```bash
./build slide   data.json --layout process --out s.pptx --transition fade
./build to-pptx script.md  --images ./imgs  --out deck.pptx --transition push --transition-dir l
```
Effects: `none` · `fade` · `cut` · `push` · `wipe` · `split` · `cover`
(`--transition-dir l|r|u|d` for push/wipe/cover; `--transition-speed slow|med|fast`).
For `to-pptx` the transition is applied to every slide. (Morph is intentionally
unsupported — it needs per-shape matching and risks corrupt decks.)

## Branding (external)
Brand profiles live under `brands/`:
- `brands/_default` — neutral fallback; used when no `--brand` is given.
- `brands/teletracking` — the TeleTracking profile (colors, logo, fonts, transitions).
- Add your own: `brands/<name>/` with `brand.json` + `tokens.css` + assets
  (`logo`, `favicon`, optional `fonts/`, `transitions/`, `backgrounds/`, `icons/`).
  Anything a profile omits falls back to `brands/_default`.

Select a profile by name (`--brand <name>` → `brands/<name>`) or by absolute path
(`--brand /path/to/profile`). To distribute a purely neutral copy, omit company
brand folders (e.g. `brands/teletracking`) when copying.

## Slide templates
Reusable single-slide PowerPoint templates live in `templates/slide-layouts/`
(a `.pptx` master to duplicate in PowerPoint **and** a JSON-driven generator via
`./build slide`). See `templates/slide-layouts/README.md`.

## Dashboard (GUI)
```bash
./dashboard/launch.command         # double-click on macOS
# or: python3 ./dashboard/server.py
```

## Layout
```
src/          the engine (CLI, importers, renderer, SCORM/cmi5/PPTX/DOCX exporters)
player/       runtime JS/CSS for built courses
schema/       IR schema + docs
scorm_schema/ bundled SCORM conformance XSDs
templates/    authoring guide + archetypes + browser template editor
brands/       brand profiles (_default neutral; teletracking; add your own)
dashboard/    local GUI server (no external services)
build         the launcher wrapper
```

## Requirements
- `python3` (the course engine is standard library only)
- `python-pptx` — slide / deck / `to-pptx` PowerPoint output
- `python-docx` — `.docx` source import / SME-review export
- `pypdf` — reading `.pdf` source documents
- `Pillow` — cover / art compositing
- A subscription CLI for AI generation — `claude` (Claude Code) or `codex` (ChatGPT)

Install the libraries in one step: `pip install -r requirements.txt`

## Development & tests
The engine is also an installable package with a test suite.
```bash
python -m pip install --upgrade pip      # editable install needs a modern pip (PEP 660)
pip install -e ".[dev]"                  # installs the package + pytest + jsonschema
python -m pytest                          # run the golden-IR suite (<1s)
course-builder --help                     # the installed console entry point
```
The suite covers: `.md`→IR parser round-trip (golden), schema validation of every
importer's output, renderer HTML snapshot, SCORM-manifest conformance lint, and the
no-fabricated-metrics chart-`source:` guardrail. After an **intentional**
parser/renderer change, refresh the snapshots with:
```bash
UPDATE_GOLDENS=1 python -m pytest
```
A local commit gate runs the suite automatically (`.githooks/pre-commit`, activated
via `git config core.hooksPath .githooks`). It skips gracefully until dev deps are
installed; bypass once with `git commit --no-verify`. `.github/workflows/ci.yml`
mirrors the gate for CI if a remote is ever added (this repo is local-only by
policy). Schema validation is **optional at runtime** — `jsonschema` is only needed
for the strict gate; bare-`python3` SCORM builds still work air-gapped without it.
