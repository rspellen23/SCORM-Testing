# Nova Course Builder

Turns course content into **TeleTracking-branded HTML microlearnings packaged as SCORM**
that track completion in Intellum. Built 2026-06-04.

Two front doors into the same pipeline:

```
[.docx + image folder] ─┐
                        ├─→ Course IR ─→ branded HTML ─→ SCORM 1.2/2004 zip
[Rise -raw- export]   ─┘
```

- **Architecture:** our own static template (Option A), styled from the TeleTracking
  brand kit — not Rise's runtime. (Option B = emit Rise JSON, deferred research thread.)
- **Brand:** Open Sans / Open Sans Condensed fonts + the official color palette, both
  bundled in `brand/`. Accents snap to the nearest official brand hex.
- **Knowledge checks:** interactive multiple-choice with feedback, **unscored**
  (completion-only to the LMS).

## Usage

```bash
# Author a new course from Word + a folder of named images
python3 src/cli.py from-docx course.docx --images ./images --out build/course.zip

# Re-skin an existing Rise export into our branded SCORM
python3 src/cli.py from-rise rise-raw.zip --out build/course.zip

# Just inspect the IR an importer produces
python3 src/cli.py import-rise rise-raw.zip --out build/course.ir.json
```

Then upload `build/course.zip` to Intellum as a `CourseScorm`.

## Authoring grammar (.docx)

See the header of [`src/docx_import.py`](src/docx_import.py). Heading 1/2/3 map to
title/section/subheading; normal paragraphs and lists pass through; line markers add
structure: `[HERO: file | title | subtitle]`, `[IMG: file | alt | caption]`,
`[IMG-LEFT/RIGHT: file | alt]`, `[NOTE] …`, `[STATEMENT] …`, `[CONTINUE]`, and a
`[KC] … [/KC]` block (`Q:` prompt, `*` correct option, `-` wrong option, `FB:` feedback).

## Layout

```
brand/      tokens.css (palette + @font-face), fonts/, Logo.png, Favicon.png
player/     player.css (block styles), player.js (nav + KC + SCORM 1.2/2004 API)
schema/     IR_SCHEMA.md
src/        common.py, rise_import.py, docx_import.py, render.py, scorm.py, cli.py
examples/   sample_course.docx + sample_images/
build/      output
```

## Validated (2026-06-04)
- **51/51** Rise courses (EN+UK) import with **0 failures**, 713 blocks, **0 unresolved images**.
- Full round-trip `Managing Bed Requests`: Rise → IR → branded HTML → 22 MB SCORM,
  valid `imsmanifest.xml`, sanitized HTML (0 editor cages, 0 stranded white-on-navy text).
- `.docx` authoring path: hero, bands, note, list, continue-gating, KC all render.

## Known gaps / next steps
- **`mondrian` blocks are skipped** (188 across the library). They store content by
  reference (`blockumentId`/`globalBlockId`) outside the inline tree; some are decorative,
  some may carry primary copy. Importer logs the count per course so content-heavy ones
  are visible. Recovering them = the deferred Option-B research thread.
- **Tier-3 blocks** (accordion, tabs, flashcard, fullscreen process) skipped in v1.
- **Not yet uploaded to Intellum** — needs James's manual upload + completion-tracking test.
- **SCORM schema `.xsd` files** are referenced, not bundled (matches the working v6 packages);
  add them if any target LMS rejects the manifest.
