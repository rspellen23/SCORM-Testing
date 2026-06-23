# CourseCraft

A self-contained course-building system. The **full engine ships inside this
folder** (`./src`) — nothing outside it is required, so you can copy or move this
folder anywhere (e.g. Google Drive) and it still runs.

One Markdown (or Word) source → branded, tracked **SCORM 1.2 / cmi5**, an editable
**PowerPoint**, or an SME-review **Word** doc. Carries no client data.

## Build
```bash
./build from-md-course script.md --images ./imgs --out course.zip   # SCORM
./build from-md-course script.md --images ./imgs --out course.zip --format cmi5
./build to-pptx        script.md --images ./imgs --out deck.pptx     # PowerPoint
./build from-docx      doc.docx  --images ./imgs --out course.zip
./build from-rise      raw.zip                   --out course.zip    # import a Rise export
./build cover --title '...' --out ./art
./build --help
```

## Dashboard (GUI)
```bash
./dashboard/launch.command         # double-click on macOS
# or: python3 ./dashboard/server.py
```

## Customize the brand
Edit `brand/brand.json` (name, `defaultAccent`, `palette`, `accentSnap`,
`cmi5IdBase`, fonts) and drop assets into `brand/` (`logo`, `favicon`, optional
`fonts/`, `transitions/`, `backgrounds/`, `icons/`). Anything you omit falls back
to `brands/_default`. The profile shipped here is a neutral **starter** — make it
yours.

## Layout
```
src/         the engine (CLI, importers, renderer, SCORM/cmi5/PPTX/DOCX exporters)
player/      runtime JS/CSS for built courses
schema/      IR schema + docs
scorm_schema/ bundled SCORM conformance XSDs
templates/   authoring guide + archetypes + browser template editor
brands/      _default neutral fallback brand
brand/       this edition's brand profile (override _default here)
dashboard/   local GUI server (no external services)
build        the launcher wrapper
```

## Requirements
- `python3` (engine is standard library only)
- `python-pptx` — only for `to-pptx` (`pip install python-pptx`)
- `python-docx` — only for `.docx` import / SME-review export (`pip install python-docx`)

> The private **operating layer** (agent runbooks, prompt library, LLM setup) is
> what makes this edition more capable than a stripped company fork — it is not
> stored in this folder.
