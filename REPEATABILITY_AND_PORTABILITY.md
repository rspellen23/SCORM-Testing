# Nova Course Builder — Repeatability & Portability Spec

> **Status:** PLAN / SPEC ONLY (2026-06-09). Nothing in here is built yet. No version control,
> no remote — local folder only, by James's direction. This document defines *how* to make the
> system repeatable (same inputs → same output, by anyone) and portable (runs on another machine /
> hands off to colleagues or the dev department) so it can be executed in a later session.
>
> Companion specs: `COURSE_CREATION_SYSTEM.md` (the 6-gate human-in-the-loop process + dev-handoff
> blueprint), `schema/IR_SCHEMA.md` (the block contract), `schema/ASSET_PIPELINE.md` (art production),
> `templates/AUTHORING_GUIDE.md` (the authoring grammar).

---

## 1. Definitions & audiences

- **Repeatable** = the same course inputs produce the same SCORM output, reliably, regardless of who
  runs it or when. The *process* (Gate 1→6 in `COURSE_CREATION_SYSTEM.md`) is followed consistently.
- **Portable** = the engine moves to another machine/person without edits, and each course travels as a
  self-contained unit.
- **Three audiences, three portability needs:**
  1. **Author** (SME / instructional designer) — writes `.md` (or uses `template-editor.html`); needs no
     Python at all. Portability = the authoring contract + the zero-install editor.
  2. **Builder-operator** (currently James) — runs the CLI to produce SCORM. Portability = the engine +
     a documented one-command build.
  3. **Dev department / org** — may host the builder as a service/app. Portability = a package (or the
     rebuild-from-spec blueprint).

---

## 2. Current state — audit (OBSERVED 2026-06-09)

**Already portable (good news):**
- **Engine is pure Python standard library.** No third-party runtime deps in `src/` — `.docx` import uses
  stdlib `zipfile`+`xml`, not `python-docx`. Pillow is used *only* by the one-off transition-band crop; the
  bands are pre-cropped and committed to `brand/transitions/`, so a normal build needs nothing but Python 3.
- **No machine-specific paths in `src/`** — every input path arrives via CLI args.
- **Brand is bundled** — fonts, logo, favicon, tokens, transition bands all live in `brand/` and travel with
  the engine; the renderer copies `brand/` + `player/` into every course, so SCORM output is self-contained.

**Gaps (what this spec closes):**
- **No version control** (by current direction — revisit later). Mitigate with a VERSION + CHANGELOG + build
  stamping (§7) so snapshots are still identifiable without git.
- **No declared environment** — "Python 3, stdlib only, Pillow optional" is true but written nowhere.
- **Engine and content are mixed** — `control/` (a course) and `examples/` live inside the engine tree.
- **No one-command build** — the `from-md … --images … --hero …` incantation is undocumented per course.
- **No regression safety** — nothing asserts the 51-course corpus or the control still build after a change.
- **Two non-determinism sources in `scorm.py`** (OBSERVED):
  - files are gathered with `os.walk`/`os.listdir` (filesystem order, **unsorted**) → manifest `<file>`
    order and zip entry order vary across machines/filesystems;
  - `zipfile.write` stamps each entry with the file's **mtime** → the zip is not byte-reproducible.
- **Dev-only QA tooling is macOS-specific** — `sips`, the hardcoded Chrome path, and `open` were used in
  *sessions* (band crop, screenshot QA), never in `src/`. Must stay out of the engine and be abstracted.

---

## 3. Target architecture — separate the ENGINE from CONTENT

The keystone move. Today a course (`control/`) lives inside the engine. Split them:

```
nova-course-builder/                 ← THE ENGINE (one versioned unit; content-free)
├── src/                             ← importers, renderer, packager, prompts, cli
├── brand/                           ← fonts, logo, tokens, transitions/ (travels with engine)
├── player/                          ← player.css / player.js
├── templates/                       ← authoring templates + template-editor.html
├── schema/                          ← IR + asset + parity + this spec
├── tests/                           ← golden/regression fixtures (NEW, §5)
├── examples/                        ← tiny sample course kept for smoke tests
├── pyproject.toml  README.md  Makefile  VERSION  CHANGELOG.md   (NEW, §4/§7)
└── (NO course content here)

courses/                             ← CONTENT (each course = a portable folder, lives OUTSIDE the engine)
└── getting-started-trm/
    ├── build.json                   ← the per-course build manifest (§3.1)
    ├── getting-started.md           ← authored source
    ├── assets/                      ← slot-named screenshots + generated art (self-contained)
    ├── image_prompts.md             ← generated ChatGPT prompts (gen-prompts output)
    └── out/                         ← build output (SCORM zip + .course dir); git-ignored when git returns
```

A course folder is **self-contained and portable**: zip it, move it, and any machine with the engine can
build it. The engine never contains course content; content never contains engine code.

### 3.1 The per-course build manifest — `build.json`
Replaces the remembered CLI flags with a declared, versioned contract:
```jsonc
{
  "schema": "nova-course-build/v1",
  "engineMinVersion": "1.0.0",          // fail fast if the engine is too old
  "source": "getting-started.md",
  "which": 1,                            // which microlearning in the .md
  "title": "Getting Started with Transfer Request Mobile",
  "hero": "hero.png",
  "accent": "#1EB16A",                   // optional; defaults to TeleGreen
  "colorHierarchy": null,                // optional override for gen-prompts (per-section)
  "images": "assets",
  "out": "out/getting-started.zip"
}
```
New CLI verb: `nova-course-builder build <course-dir>` reads `build.json` and runs import→render→package.
A course author/operator never types flags again — the manifest *is* the reproducible recipe.

---

## 4. Repeatability mechanisms

1. **Declared environment.** `pyproject.toml` + `README`:
   - Runtime: **Python 3.10+, standard library only — no install step.**
   - Optional dev extra: `pillow` (regenerate transition bands), and Chrome (QA screenshots) — both
     dev-only, never required to build.
   - Pin the supported Python range; document it; CI matrix later if git/CI returns.
2. **One-command build.** `Makefile` targets + the `build <course-dir>` verb (§3.1):
   - `make build COURSE=../courses/getting-started-trm`
   - `make prompts COURSE=…`   `make test`   `make sample`
3. **Determinism fixes in `scorm.py`** (so identical inputs → identical bytes):
   - **Sort** the file walk (`sorted(os.walk …)` + `sorted(names)`) so manifest `<file>` order and zip
     order are stable.
   - Write zip entries with a **fixed `ZipInfo.date_time`** (e.g. a constant epoch) and fixed external
     attrs, so the package is byte-reproducible. Same for any other `os.listdir` consumed in order.
   - Add a `--reproducible` flag (default on) documenting the behavior.
4. **Versioned authoring contract.** The IR already stamps `"schema": "nova-course-ir/v1"`. Keep the md
   grammar (`Slide`, `*Visual:*`, `*Section:*`, `*Transition:*`, KC) documented in `AUTHORING_GUIDE.md`
   and bump the grammar version on breaking changes; `build.json.engineMinVersion` guards mismatches.
5. **Golden / regression tests** (§5) — the real guarantee that "repeatable" survives code changes.

---

## 5. Regression safety — `tests/`

The thing that makes iterating across many courses *safe*.
- **Golden build test:** build the control (`getting-started`) and assert invariants — block count,
  `skipped == {}`, accent == TeleGreen, transition + section + KC + exit-button present, SCORM opens and
  `imsmanifest.xml` validates, and (with determinism on) the zip hash matches a committed golden hash.
- **Corpus re-import test:** re-import the 51 real Rise `-raw-` exports (already validated once: 51/51,
  0 failures) and assert 0 import errors + a stable skipped-block tally. Guards Rise-parity work.
- **Prompt-generator test:** `gen-prompts` on the control yields a portrait objectives prompt, a landscape
  cover prompt, TeleGreen-always-present hierarchy, and skips screenshots.
- **Run:** `make test` locally now; wire to CI if/when git returns. Fixtures live in `tests/`; the 51-corpus
  path is passed in (kept out of the engine — it's content).

---

## 6. Portability mechanisms

1. **Keep the engine path-clean.** A tiny lint (grep for `/Users/`, `/Applications/`, `CloudStorage`,
   `OneDrive` in `src/`) in `make test` so machine paths never creep in. (Currently clean.)
2. **Self-contained output.** SCORM already bundles brand+player+assets; no CDN. Keep that invariant tested.
3. **Packaging for handoff (pick per audience):**
   - **pip-installable CLI** — `pyproject.toml` console entry point `nova-course-builder` → `pip install -e .`
     gives anyone the command without touching internals. (Zero deps → trivial.)
   - **Docker image** — freezes Python (+ Chrome for QA) so output is identical on any OS; best for the dev
     department / a build server.
   - **Rebuild-from-spec** — `COURSE_CREATION_SYSTEM.md` already lets the dev dept reconstruct it as an app;
     this spec + the schema docs are the engineering half of that handoff.
4. **Cross-platform.** The build is pure Python → already cross-platform. Quarantine the macOS-only *dev*
   tooling behind a `tools/` dir with documented alternatives:
   - band regeneration → Pillow (cross-platform; already used) — never `sips`.
   - QA screenshots → a small script that finds Chrome/Chromium by env var or PATH (not a hardcoded mac path),
     or runs in the Docker image. QA only; not part of `build`.
5. **Asset sourcing decoupled from OneDrive.** Assets live in the course's `assets/` folder, slot-named per
   the `ASSET_PIPELINE.md` contract. The flow per course: capture screenshots → run `gen-prompts` → generate
   art from the prompts → drop both into `assets/`. No build step reaches into a personal cloud folder.

---

## 7. Versioning without git (interim)

Until version control returns, keep snapshots identifiable:
- **`VERSION`** file (semver-ish, e.g. `1.0.0`) bumped on engine changes.
- **`CHANGELOG.md`** — dated, human-readable; this session's capabilities are the first entries.
- **Build stamping** — record the engine `VERSION` + `build.json` source name into a `build/<course>.manifest.json`
  beside the SCORM (and optionally a comment in `imsmanifest.xml`), so any output can be traced to the engine
  + content that produced it. (Avoid stamping a wall-clock time *inside* the SCORM if byte-reproducibility is
  wanted; keep the timestamp in the sidecar manifest instead.)
- **Snapshot/backup** — periodic dated zip of the engine folder (e.g. `nova-course-builder_v1.0.0_2026-06-09.zip`)
  to a backup location, since there's no remote. (Revisit: git local-only repo is low-cost when ready.)

---

## 8. Migration plan (ordered, no-git, executable later)

1. **Engine/content split:** move `control/` → `../courses/getting-started-trm/` (add `build.json`, an
   `assets/` with the slot-named files, keep the generated `image_prompts.md`). Keep `examples/` as a smoke
   fixture. Engine becomes content-free.
2. **Declare environment:** add `pyproject.toml` (entry point), `README.md` (setup + the one-command build),
   `VERSION`, `CHANGELOG.md`.
3. **`build <course-dir>` verb + `Makefile`:** read `build.json`; wrap import→render→package; add
   `make build/prompts/test/sample`.
4. **Determinism fixes** in `scorm.py` (sorted walk, fixed zip timestamps, `--reproducible`).
5. **`tests/`** — golden build (control) + corpus re-import + prompt-gen; `make test`; commit a golden hash.
6. **Quarantine dev tooling** into `tools/` (band-regen via Pillow; QA-screenshot with Chrome discovery).
7. **Packaging** (when handing off): verify `pip install -e .`; optionally author a `Dockerfile`.
8. **Backup/snapshot** routine for the engine folder.

**Effort:** 1–4 are a focused half-day; 5 adds the corpus fixture wiring; 6–8 are handoff-time.

---

## 9. Acceptance criteria ("done")

- A person on a **fresh machine** with only Python 3.10+ can: copy the engine folder, copy a course folder,
  run `nova-course-builder build <course-dir>` (or `make build COURSE=…`), and get the **same** valid SCORM —
  no edits, no cloud access, no extra installs.
- `make test` passes: control golden build (hash match), 51-corpus re-import (0 failures), prompt-gen checks.
- `src/` contains **zero** machine paths and **zero** third-party runtime imports (lint-enforced).
- Each SCORM is traceable to an engine version + course via its sidecar manifest.

---

## 10. Open decisions

- **DECIDED 2026-06-09 — end-state = the "Course Builder Suite" (CBS): a VS Code WORKBENCH hosting the
  agent + the CLI engine; NOT a dev-dept web app, not a bare terminal CLI, not a solo-only tool.**
  Evolution of the earlier "CLI we run" call — James: VS Code is better than a bare CLI. **It's not CLI vs
  VS Code: the CLI is the engine; VS Code is the room we operate it in.** Composition:
  - **Workbench:** VS Code with `.vscode/tasks.json` (one-click Build / Generate-prompts / New-course),
    recommended extensions (**Claude Code + Codex** — both, per James), Live Preview, Simple Browser.
  - **Operator (agent-in-editor):** Claude Code *or* Codex drives the build per the runbooks
    (**`CLAUDE.md` + `AGENTS.md`**, both). Humans direct + approve at the gates.
  - **Engine:** the Python stdlib CLI underneath (run by Tasks or the agent; never hand-typed paths).
  - **Content:** portable course folders (`course.md` + `assets/` + `build.json`).
  - **Colleagues:** **ChatGPT** for **art + scripts + ideation** via a CBS **prompt library** (scripting /
    revision / art packs) + the zero-install `template-editor.html`.
  - **Operating model = HYBRID:** James + agent operate it now; **colleagues graduate to self-serve later**
    → design Tasks/folders/runbooks self-serve-clean from the start + lean on guardrails (missing-asset
    lint, dry-run parse) since non-technical users will eventually press the buttons.
  - **Scope:** in-course art only; **Intellum catalog tile art (Figma) is OUT — an LMS concern.**
  (`COURSE_CREATION_SYSTEM.md` §11 "dev-team app" is background, not a target.)
- **Byte-reproducible zip**: nice-to-have; if any LMS rejects a fixed-epoch timestamp, fall back to a stable
  but real date. Validate against Intellum before committing the golden hash.
- **`courses/` location** — a sibling of the engine, or under OneDrive for team sharing? (Team-sharing pulls
  the OneDrive sync caveat from `failed-approaches`; prefer a local `courses/` + explicit export.)
- **Revisit git** — local-only repo is cheap and gives history/rollback even without a remote; reconsider
  when comfortable.

## 11. Provenance
- **OBSERVED (2026-06-09):** pure-stdlib engine, no machine paths in `src/`, bundled brand, not a git repo,
  no dependency declarations, the two `scorm.py` non-determinism sources, content mixed into the engine tree.
- **GENERATED (proposed, not built):** the engine/content split, `build.json` schema, the `build` verb +
  Makefile, determinism fixes, the `tests/` suite, packaging options, the no-git versioning approach, and the
  migration plan.
