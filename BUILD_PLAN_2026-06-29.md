# Course Builder — Capability Build Plan (High-Confidence Batch)

**Date:** 2026-06-29
**Source:** the high-confidence items from
[CAPABILITY_EXPANSION_CANDIDATES_2026-06-29.md](CAPABILITY_EXPANSION_CANDIDATES_2026-06-29.md).
**Ordering (James's directive):** ship **quick wins (S effort) first**, then build up through
the **medium (M) tasks**. Every item here is **Confidence = H**. The L-effort and
lower-confidence items are deliberately **out of this plan** — reassess them after this batch
is done and shipped working.

## How to use this doc
- Execute **top-to-bottom**. Phase 1 (quick wins) before Phase 2.
- One item = one local commit (repo stays **local-only, NO remote, NO Drive** —
  [[feedback_course_builder_repo_isolation]]). Check the box when committed + tested.
- Touchpoints name the **files/functions + the integration seam**, not line numbers
  (these are new features; line refs drift — anchor on disk at build time).
- **Every item ships with tests** (pytest for `src/`; `node --test 'tests/test_*.js'` for
  `player.js`) and must keep the existing suite green.
- Honors the standing constraints: **no metered APIs**, cross-platform (Win+Mac),
  neutral naming, operator-grade.

### Disposable test env (unchanged recipe)
`python3 -m venv` + `pip install pytest jsonschema python-pptx python-docx pypdf Pillow`
(pyproject `pythonpath=src`, no editable install on Py 3.9). System-python pre-commit
pytest gate SKIPS — verify via the venv. Player gate: `node --test 'tests/test_*.js'`.

---

# PHASE 1 — Quick wins (Effort S · Confidence H)

### [Q1] Chart auto-narrative (P10)
- **Goal:** Every data/chart slide (deck) and `chart` block (course) gets an auto-generated
  one-line takeaway/insight sentence so the operator doesn't hand-write chart prose.
- **Touchpoints:** `src/authoring.py` — add a "write one plain-language takeaway for this
  chart" instruction to `build_deck_prompt` (chart slides) and the course chart guidance;
  carry the takeaway as a `caption`/`note` field already supported by the chart renderer
  (`src/chart_svg.py` / `slide_layouts` chart source line).
- **DoD:** a generated chart carries a takeaway line rendered under/with it; pytest asserts
  the prompt injects the instruction and the parser preserves the field. No metered calls.
- [x] Done — `takeaway:` field on the `chart` block + deck `chart` content. Parser
  (`md_import._parse_chart`), course SVG renderer (`chart_svg.render_chart` →
  `.nv-chart-takeaway`), deck PPTX renderer (`slide_layouts._render_chart`, shrinks the
  plot only when present so no-takeaway decks are byte-identical), prompt instruction
  (`authoring.CHART_RULE`), IR schema + IR_SCHEMA.md + AUTHORING_GUIDE.md.
  Tests in `tests/test_chart_guardrail.py` (5 new). 204→209 pytest, node 10 green.

### [Q2] Auto speaker notes per slide (P11)
- **Goal:** One-click "generate speaker notes" for a deck; notes ride into the `.pptx`.
- **Touchpoints:** `src/authoring.py` (`build_deck_prompt` emits an optional per-slide
  `notes`); `src/slide_layouts.py` `export_deck`/`_add_slide` writes notes to the PPTX
  notes slide; `dashboard/index.html` + `server.py` add the action.
- **DoD:** each slide can carry `notes`; PPTX export includes them on the notes page;
  button triggers generation; pytest on the notes-write path.
- [x] Done — optional `notes` string per deck slide (sibling to `layout`/`theme`).
  `slide_layouts._write_notes` writes it to the PPTX notes page in both export paths
  (`export_deck` + `_export_deck_native`); rides only the FIRST paginated page
  (`_cont`); a notes-free deck creates NO notes slide (byte-identical). Prompt:
  `authoring.build_deck_prompt` documents the optional field; one-click action =
  `authoring.generate_notes` / `build_deck_notes_prompt` + `server.do_deck_notes`
  (`/api/deck-notes`); `do_deck` carries `notes` (drops blank). Dashboard: per-row
  notes textarea + deck-level "📝 Generate speaker notes" button (preserved across
  layout-change/regen). `lint_deck` rejects non-string notes. Tests in
  `tests/test_deck_notes.py` (12). 209→221 pytest, node 10 green.

### [Q3] Per-section palette-variety lint (P8)
- **Goal:** Warn (don't block) when a deck defaults every slide to one accent, nudging the
  palette-variety rule ([[feedback_course_color_palette_variety]]).
- **Touchpoints:** `src/authoring.py` `lint_deck` — new rule counting distinct accents
  across color-driven layouts; surface in the build report panel.
- **DoD:** a mono-accent multi-slide deck raises one warning; a varied deck is clean;
  pytest in `tests/test_lint_validation.py` (or deck-lint test).
- [x] Done

### [Q4] SCORM 2004 packaging (C13)
- **Goal:** Add the missing 2004 packaging path. The player runtime is **already
  2004-ready** (`player.js` detects `API_1484_11`); only `src/scorm.py` lacks the packager
  (cmi5/xAPI already ship in `src/cmi5.py`).
- **Touchpoints:** `src/scorm.py` — add a 2004 manifest (`adlcp`/`imsss`/`adlseq`
  namespaces) + 2004 XSDs, mirroring the 1.2 single/multi-SCO builders; `src/cli.py` —
  add `scorm2004` to the `--format` choices (or `--scorm-version`); `src/scorm_lint.py` —
  validate the 2004 manifest.
- **DoD:** `from-md … --format scorm2004` produces a zip that passes `scorm_lint`
  (and `xmllint` when present); pytest builds + lints a 2004 package; 1.2 path unchanged.
- [x] Done

### [Q5] Regenerate-with-instruction (course) (X2)
- **Goal:** Steer a unit/slide regeneration by sentence ("make it more clinical / 3 KCs /
  warmer"), not a blind reroll. Decks already have a per-slide guidance field — bring the
  same to courses and make it first-class.
- **Touchpoints:** `dashboard/server.py` `do_regenerate_unit` + `src/authoring.py`
  `build_unit_prompt` accept a `guidance` string; `dashboard/index.html` course step adds
  the field (mirror the slide-row guidance control).
- **DoD:** a regenerate call with guidance routes the text into the unit prompt; pytest
  asserts the guidance reaches the assembled prompt.
- [x] Done — guidance is now FIRST-CLASS. `authoring.build_unit_prompt` gained a
  `guidance=""` param woven in as a labeled "REVISION GUIDANCE (apply it faithfully — …
  but never the HARD OUTPUT RULES or §8 grammar)" block (mirrors the slide path's
  `build_regen_slide_prompt`); `server.do_regenerate_unit` now passes `guidance=` INTO
  the builder instead of tacking it on after the prompt returned. Dashboard: the
  module-regen list gained an inline per-module steer field (`#mod_guide_<n>`, `.modrow`
  styled like the slide-row `sl-guide`) replacing the blocking `prompt()` dialog;
  `regenModule` reads it via `val('mod_guide_'+which)`. Tests in
  `tests/test_regen_guidance.py` (7). 236→243 pytest, node 10 green.

### [Q6] URL → deck/course source (P1, partial C1)
- **Goal:** Paste a URL; fetch + extract readable text as a source alongside files.
- **Touchpoints:** `src/authoring.py` — new `_read_url()` (stdlib `urllib` fetch →
  reuse the existing `.html` tag-strip path) wired into the source set; `dashboard` adds a
  URL input. Respect the existing byte caps; offline/onfail → skip-with-note.
- **DoD:** a reachable URL becomes a readable source; an unreachable one yields an
  actionable skip note; pytest with a `file://` or local fixture (no live network in tests).
- [x] Done — `authoring._read_url(url)` (stdlib `urllib`, no metered API; accepts
  http/https/file, 20s timeout, honors `_MAX_SOURCE_BYTES`, reuses `_strip_markup` for
  HTML/XML, rejects binary by content-type) + `_coerce_urls` (newline/comma string or
  list). `read_sources(path, urls=None)` fetches each URL as an extra `===== SOURCE URL`
  doc alongside files, respects the total byte cap, and skips unreachable/oversized URLs
  with an actionable note (no path/folder required when URLs are given). Threaded
  `urls=` through `generate`/`generate_deck`/`regenerate_slide` and the server
  (`_read_sources_or_error` + every course/deck entry point passes `p.get("urls")`).
  Dashboard: a "Source links" textarea on BOTH the course step (`#src_urls`) and the
  slide step (`#sl_urls`); genPreflight/genDeck/regen payloads carry `urls`; the
  source-required guards now accept URLs-only. Tests in `tests/test_url_source.py` (12,
  file:// fixtures, no network). 243→255 pytest, node 10 green.

### [Q7] Image/screenshot → deck (P5)
- **Goal:** Route OCR'd image sources into the **deck** prompt (the course side already
  OCRs via Tesseract).
- **Touchpoints:** `dashboard` deck source picker accepts image extensions; deck ingestion
  in `server.py`/`authoring.py` calls the existing `read_sources` (already OCR-aware).
- **DoD:** images in a deck source folder are OCR'd into the deck prompt; missing-Tesseract
  degrades with the existing hint; pytest on the wiring.
- [x] Done — ★ ANCHOR FINDING: the functional core was ALREADY wired. The deck source
  picker already accepted image extensions and already advertised "images via OCR"
  (label), and `generate_deck` → the shared OCR-aware `read_sources` already routes a
  source-folder image through `_ocr_image` (degrading to skip-with-hint when Tesseract is
  absent) — both inherited from the `7ea87f1` source-ingestion broadening since course and
  deck share `read_sources`. So Q7's real gap was the DoD's missing TEST COVERAGE on the
  deck path + a discoverability nit. This commit: `tests/test_deck_image_source.py` (3 —
  OCR text reaches the deck prompt via `generate_deck`, missing-Tesseract degrades with
  the hint, picker accepts image exts + advertises OCR) + the deck source empty-state
  message now mentions images/OCR for parity with the course side. 255→258 pytest, node 10.

---

# PHASE 2 — Core build-up (Effort M · Confidence H)

> Ordered by leverage + dependency. X9 (checkpoint) precedes X10 (version history);
> Q-captions (P2-C12) pairs with the WCAG pass.

### [M1] Self-healing generation loop (C18)  ⟵ highest leverage
- **Goal:** After generation, run the build-time `lint()` + import warnings; if there are
  violations, re-prompt the model to fix them (up to N rounds) **before** the operator sees
  output. Hides the boring failures the system can already detect.
- **Touchpoints:** `src/authoring.py` `generate()` (and the staged unit path) wraps the
  existing `lint()` in a fix-and-recheck loop; cap rounds; surface any residual issues in
  the build report.
- **DoD:** a deliberately lint-broken generation is auto-fixed within N rounds (or residuals
  are reported, never silently shipped); pytest with a stub provider that returns a broken-
  then-fixed payload.
- [x] Done

### [M2] WCAG conformance pass + AI alt text (C11)
- **Goal:** Automated accessibility checks in the build report (alt-text presence on
  `image`/`imageText`, heading order, brand-token contrast, KC labels) + AI-drafted alt text
  at generation time. A genuine differentiator (most AI tools are weak here).
- **Touchpoints:** `src/build_report.py` (new a11y check section); `src/render.py` (ensure
  alt is emitted); `src/authoring.py` (alt-text drafting in the prompt). Human-review note
  for the WCAG bar.
- **DoD:** report lists a11y findings; a missing-alt course is flagged; pytest on each check.
- [x] Done

### [M3] Local captions for media (C12 / X17)
- **Goal:** Auto SRT/VTT for `video`/`audio` blocks via **local Whisper** (whisper.cpp /
  faster-whisper) — free, offline, commercially licensed. No metered API.
- **Touchpoints:** new `src/captions.py` (subprocess to a local whisper binary if present,
  else skip-with-note like Tesseract); `src/md_import.py` media blocks accept a caption
  track; `src/render.py` emits `<track kind="captions">`. Pair with M2.
- **DoD:** a media block with local audio gets an SRT/VTT when whisper is installed; graceful
  skip-with-note otherwise; pytest on the wiring + the degrade path.
- [x] Done

### [M4] Glossary / termbank + banned-words guardrail (C16)
- **Goal:** Enforce approved terms (e.g., "Transfer IQ Pro", never "the transfer tool") and
  ban prohibited words at generation time — serving terminology fidelity, neutral naming,
  and UK term flagging.
- **Touchpoints:** a brand-level `glossary.json` (preferred terms + banned list); inject into
  course/deck prompts (`src/authoring.py`); add a lint rule in `src/md_import.py` that flags
  banned words / wrong terms in generated md.
- **DoD:** a banned word in output raises a lint error; preferred terms appear in the prompt;
  pytest on the lint + injection.
- [x] Done

### [M5] One-source → translated course (C15)
- **Goal:** Translate a built course (md/IR) via the subscription CLI into a target language,
  preserving block structure/bindings — for the ES/UK workstreams.
- **Touchpoints:** new `authoring.translate_course()` (structure-preserving translate prompt
  via the provider); `src/cli.py` subcommand; `dashboard` action. Reuse M4's glossary.
- **DoD:** a course md → translated md with identical block structure; pytest with a stub
  provider; no metered calls.
- [x] Done

### [M6] CSV → bulk generate (C3 / X10)
- **Goal:** A manifest CSV (one row per course/unit: objective, audience, archetype, preset,
  sources) → batch-generate — fits the NovaCoursesMaster workflow.
- **Touchpoints:** new `authoring.generate_batch()`; `src/cli.py` `from-csv` subcommand;
  `dashboard` batch action. Reuse the per-course `generate()`.
- **DoD:** a 2-row CSV produces 2 courses with the right params per row; pytest with a stub
  provider.
- [x] Done

### [M7] Editable chart data + more chart types (P9)
- **Goal:** Add stacked/horizontal/donut/area; CSV/paste → chart data; make chart data
  editable in the dashboard.
- **Touchpoints:** `src/chart_svg.py` (new types, reuse the hardened `_fmt`); `dashboard`
  chart-edit UI; `src/md_import.py` chart parse. Honors the no-split-visualization rule.
- **DoD:** new chart types render in SVG + native PPTX; data is editable; pytest +
  raster-verify one new type each theme.
- [x] Done

### [M8] Editable deck outline before build (P2)
- **Goal:** Generate the slide outline (titles + one-liners), let the operator approve/reorder
  before full generation — cuts wasted regen. (Courses already have a plan step; port it.)
- **Touchpoints:** `src/authoring.py` `build_deck_plan_prompt`; `dashboard/server.py`
  `do_deck_plan`; `dashboard/index.html` deck step.
- **DoD:** an editable outline is shown before generate; approved outline drives generation;
  pytest on the plan prompt + parse.
- [x] Done

### [M9] Multi-candidate slide generation (P3)
- **Goal:** Regenerate returns N (e.g. 3) treatments; operator picks; optional auto-rank
  against brand + density rules.
- **Touchpoints:** `dashboard/server.py` `do_regenerate_slide` (an `n` param);
  `dashboard/index.html` candidate picker. Renderer is deterministic so previews are cheap.
- **DoD:** N candidates returned and selectable; pytest on the multi-return path.
- [x] Done

### [M10] Brand compliance checker — deck (P7)
- **Goal:** Deck-side analogue of M2: flag off-palette colors, logo misuse, contrast
  failures in the slide IR before export; offer auto-fix.
- **Touchpoints:** `src/build_report.py` / `lint_deck` (`src/authoring.py`) new checks over
  slide tokens.
- **DoD:** an off-brand color/contrast issue is flagged; pytest on each check.
- [x] Done

### [M11] Interactive HTML deck export (P14)
- **Goal:** Export the SVG slideshow as a standalone, self-contained interactive `.html`
  deck (keyboard nav already exists).
- **Touchpoints:** `src/slide_svg.py` `render_deck_svg` → a self-contained HTML wrapper;
  `src/cli.py` `deck --format html`; `dashboard` output option.
- **DoD:** a `.html` deck opens and navigates offline (no external assets); pytest builds it
  and asserts self-containment.
- [x] Done

### [M12] More question types: matching · sequencing · fill-in-the-blank (C4)
- **Goal:** Add three stable assessment blocks beyond MCQ + categorize (table stakes across
  Articulate/iSpring/Captivate/Evolve). *May split into 3 commits.*
- **Touchpoints:** `src/blocks.py` (3 new stable types); `src/md_import.py` (grammar +
  lint); `src/render.py` (HTML); `player/player.js` (pure scorers, mirroring
  `categorize`/multi-select); PPTX flatten in `src/slide_layouts.py`/pptx export.
- **DoD:** each type authors, renders, scores, and resumes (suspend_data); pytest + a
  `node --test` scorer test per type.
- [x] Done

### [M13] Aggregate / final quiz + section pass thresholds (C6)
- **Goal:** A graded end-of-course quiz with section-level thresholds and SCORM/cmi5
  subscore reporting (previously deferred; scoring/mastery plumbing exists).
- **Touchpoints:** `src/md_import.py` (quiz grammar); `player/player.js` (aggregate scoring +
  gate); `src/scorm.py`/`src/cmi5.py` (subscore reporting).
- **DoD:** a final quiz scores, gates completion, and reports to the LMS; pytest + node tests.
- [x] Done

### [M14] Scenario TRUE branching in the player (C9)
- **Goal:** Scenario choices route to **distinct** next scenes (not just linear feedback) —
  the deferred player-navigation half (grammar + renderer already exist).
- **Touchpoints:** `src/md_import.py` `_parse_scenario` (per-choice target); `player/player.js`
  (scenario navigation state); `src/render.py` (data attributes).
- **DoD:** choosing a response routes to its target scene; a linear scenario still works;
  `node --test` covers the routing.
- [x] Done

### [M15] Checkpoint / rewind (X3)
- **Goal:** Auto-snapshot the IR/project before each AI edit; one-click restore (distinct
  from git; cheap because the tool is local).
- **Touchpoints:** `dashboard/server.py` (snapshot dir per project, write before regen/edit);
  `dashboard/index.html` (rewind control).
- **DoD:** a snapshot is captured before each AI edit and restorable; pytest on the
  snapshot/restore endpoints.
- [x] Done

### [M16] Version history + restore (X13)  ⟵ depends on M15
- **Goal:** Named versions of a build with one-click restore (operator-facing, not git).
- **Touchpoints:** builds on M15's snapshot store; `dashboard/server.py` (name/list/restore)
  + `dashboard/index.html` UI.
- **DoD:** name, list, and restore versions; pytest on the version endpoints.
- [x] Done

### [M17] Saved custom templates / starters (X7)
- **Goal:** Save a slide layout or a whole course as a reusable starter; duplicate-and-edit.
  (`templates/slide-layouts/*.example.json` is half of this already.)
- **Touchpoints:** a templates store + `dashboard/server.py` save/list; `dashboard/index.html`
  "save as template" + "new from template".
- **DoD:** save a template and start a new project/deck from it; pytest on save/list/instantiate.
- [x] Done

---

# Deferred to post-batch reassessment

Not in this plan (revisit after Phase 1+2 ship working), per directive:
- **L-effort H-ish items:** local TTS narration (X16), narrated-video export (P15/X18),
  edit-in-place on preview (X5), shared component library (X8), async SME review (X14),
  Org Chart layout (P12), variables/conditional paths (C10).
- **Lower-confidence (M conf):** intent→layout (P4), brand-kit-from-URL (P6), diff/
  accept-reject (X1), house-voice (X11), facts grounding (X12), approval gate (X15),
  AI-graded free-text (C7), question banks (C5), certificates (C8), SCORM/Rise re-import
  (C2), video-transcript→course (C1), translation memory (C17), voice/reading-level lint
  (C19), append-consistency check (C20).
- **Out entirely** (constraints): viewer analytics, multiplayer, cloud avatars/voices,
  AI image generation, dynamic/live-hosted SCORM. See the candidates doc's "OUT" section.

---

*Execution order is the list order: Q1 → Q7, then M1 → M17. Reassess the deferred set once
this batch is shipped and verified working.*
