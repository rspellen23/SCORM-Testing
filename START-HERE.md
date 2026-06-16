# Rays — Nova Course Builder (working export)

A self-contained, working copy of the TeleTracking **Nova Course Builder**: it turns a
Markdown script into a branded, LMS-ready course package — **SCORM 1.2** (broad compatibility)
or **cmi5/xAPI** (modern). Scrubbed for sharing: no keys, no client/control content; the
included example content is the **Responsible Use of AI** course.

## What's here
- `src/` — the engine (Python; standard library + `python-docx`)
- `player/` — the runtime (`player.js` auto-detects SCORM 1.2/2004, cmi5/xAPI, or standalone)
- `brand/`, `templates/`, `schema/`, `scorm_schema/` — brand assets, authoring grammar, IR schema, conformance XSDs
- `trigger/` — optional "drop a folder of source docs → draft microlearning scripts" inbox tool
- `sample-courses/` — ready-built Responsible AI courses you can upload to an LMS today
- `*.md` — docs (`README`, `Nova_Course_Builder_Complete_Guide`, `COURSE_CREATION_SYSTEM`, `REPEATABILITY_AND_PORTABILITY`)

## Build a course
```bash
# One microlearning
python3 src/cli.py from-md scripts.md --which 1 --out course.zip
# A whole multi-lesson course (one package, per-lesson tracking + TOC)
python3 src/cli.py from-md-course scripts.md --out course.zip                # SCORM 1.2 (default)
python3 src/cli.py from-md-course scripts.md --format cmi5 --out course.zip  # modern cmi5/xAPI
```
Add `--validate` to run the conformance lint, or check an existing package with
`python3 src/cli.py lint course.zip`.

Authoring grammar is in `templates/AUTHORING_GUIDE.md`. Optional directives: `*Graded:* pass 80`
(scored) and `*Retry:* 2` (N attempts per knowledge check).

## Test on an LMS
Upload any `sample-courses/*.zip` to **SCORM Cloud** (free) or your LMS. cmi5 packages need an
LMS/LRS that supports cmi5 (SCORM Cloud does, and acts as the LRS).
