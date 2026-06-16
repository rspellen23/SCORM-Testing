# QC Gate — a pre-package validator for the course IR

> **Provenance.** Pattern adapted from `hugohe3/ppt-master` (MIT) — `docs/technical-design.md`
> §Quality Gate and `scripts/svg_quality_checker.py`. The *checks* below are ours (our blocks, our
> brand, our LMS); only the **gate design** is harvested. See [HARVEST_NOTES.md](../HARVEST_NOTES.md).

## Why a gate, and why here

ppt-master's lesson: an LLM-assembled artifact is non-deterministic, so defects (a banned construct, a
dropped element) surface late — "export failed at page 14" or, worse, a silently broken slide. A cheap
validator that runs **before** packaging turns a late, vague failure into an early, precise one:
"KC on slide 3 has no Incorrect-feedback branch — fix it" beats discovering it in Intellum after upload.

This is the engineering form of our **Gate 5 (LMS Verify)** — pulled earlier, into the build itself.

## Four design rules (taken verbatim from ppt-master, because they're right)

1. **Blacklist, not whitelist.** Enumerate the narrow set of things that are *known-bad*; leave
   everything else allowed. A whitelist needs constant maintenance as blocks evolve.
2. **Errors block; warnings don't.** An error aborts packaging. A warning is logged and the build
   proceeds. Severity is a deliberate per-check choice.
3. **No auto-fix.** A defect is re-authored in the source, not silently patched. Auto-fix loses the
   author's intent (ppt-master's example: a banned construct was used *for a reason*; the substitute
   needs the same intent re-applied). For us: a missing KC branch is a content decision, not a typo.
4. **Run before post-processing.** Validate the IR as authored, before `render_course` /
   `scorm.package` rewrite anything — otherwise the rewrite can mask the source-level defect.

## Where it plugs in

In [`src/cli.py`](../src/cli.py), every build path funnels through `_emit(ir, blobs, out_zip)`, which
calls `render.render_course(...)` then `scorm.package(...)`. The gate runs **at the top of `_emit`**,
before `render_course`, reading the IR and the `blobs` keyset:

```
def _emit(ir, asset_blobs, out_zip, keep_dir=False):
    errors, warnings = validate_ir(ir, asset_blobs)        # <-- new gate
    for w in warnings: print("  ⚠", w)
    if errors:
        for e in errors: print("  ✗", e)
        raise SystemExit(f"QC gate: {len(errors)} error(s) — fix the source and rebuild.")
    render.render_course(ir, course_dir, asset_blobs)
    ...
```

It reuses the existing `ir["_stats"]["skipped"]` signal (already surfaced today) rather than
re-deriving it: a non-empty `skipped` becomes a **warning** (something in the source didn't map to a
known block — the Rise `variant` render-whitelist class of issue).

## The checks (our content, our brand, our LMS)

Each check is `ERROR` (blocks) or `WARN` (logs). Severity reflects "will this ship broken to a learner?"

| # | Check | Severity | Rationale |
|---|---|---|---|
| 1 | **Slide 1 is Learning Objectives** (the standard, James 2026-06-08) | ERROR | every course opens on objectives; a missing one is a structural defect |
| 2 | **Every knowledge check has BOTH a Correct and an Incorrect feedback branch** | ERROR | guards the exact bug we already fixed (feedback always showing "correct") from regressing |
| 3 | **Every asset referenced by a block exists in `blobs`** (image / screenshot / gif slot resolves) | ERROR | a missing asset renders a broken slide; mirrors `ASSET_PIPELINE.md` missing-asset lint |
| 4 | **An exit-course block is present** (SCORM finish) | ERROR | without it the learner can't signal completion |
| 5 | **Completion gating is attached only to observable media** (video/audio with a player), never to a bare embed | WARN | gating an unobservable element can deadlock completion |
| 6 | **Accent colors resolve to the official brand hexes** (TeleGreen #1EB16A et al.), no stray accent | WARN | catches the teal→TeleGreen accent drift class we corrected |
| 7 | **`_stats.skipped` is empty** | WARN | a skipped node = source the importer didn't recognize; review before shipping |
| 8 | **No block type outside the known IR set** (the render whitelist) | ERROR | an unknown type silently renders nothing — fail loud instead |

> Checks 1–4 and 8 are ERROR because they ship a visibly or functionally broken course. 5–7 are WARN
> because they are usually fine and the author should eyeball them, not be blocked.

## Implementation note

A single `validate_ir(ir, blobs) -> (errors, warnings)` in a new `src/validate.py`, pure-Python, no
deps, walking `ir`'s slides/blocks. It is **read-only** — it never mutates the IR (rule 3). Wire it
into `_emit` as above so *every* build path (`from-rise`, `from-docx`, `from-md`, `from-ir`) is gated
by construction, not per-command. Specced here; build alongside the next real course so the checks are
calibrated against actual content rather than guessed.
