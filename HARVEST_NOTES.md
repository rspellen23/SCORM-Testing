# Harvest Notes — what we took from PPT Master, and what we didn't

> **Date:** 2026-06-10 · **Source:** [`hugohe3/ppt-master`](https://github.com/hugohe3/ppt-master)
> (MIT License) · cloned/vetted at `/tmp/ppt-master` (transient).
>
> James asked us to vet PPT Master against the Nova Course Builder and harvest what's useful. PPT
> Master is **not** a tool we adopt — its output is editable PowerPoint (fixed-canvas, static SVG→
> DrawingML), while ours is responsive, interactive, tracked SCORM/HTML for Intellum. Different medium
> end to end. But its architecture validates ours and several components are worth grafting. This file
> records the provenance so the borrowing is traceable and properly attributed.

## Attribution (MIT)

PPT Master is © Hugo He, MIT-licensed. The adapted material below is **re-expressed for our HTML/SCORM
medium**, not copied. Where a doc distills their reference material it says so at the top. The MIT
license permits this use with attribution; this file is that attribution.

## What we harvested and where it landed

| Harvest | From (ppt-master) | Landed in | Form |
|---|---|---|---|
| **Deck-wide image lock** (rendering + palette *usage*, locked once per course) | `references/image-generator.md` §2 | [`src/prompts.py`](src/prompts.py) — `CourseImageLock` / `make_lock` / `build_prompt_locked` | **code, shipped** |
| **Palette as a usage contract** (proportion/role, not just which colors) | image-generator.md §4 | `src/prompts.py` — `PALETTE_BEHAVIOR` | **code, shipped** |
| **HEX-as-text guard** + **simplified-figures** rule | image-generator.md §5.1 / §5.2 | `src/prompts.py` — `GLOBAL_RULES` (appended to every prompt) | **code, shipped** |
| **text_policy** (none vs embedded; editability/localization rationale) | image-generator.md §5.3 | `src/prompts.py` — `TEXT_POLICY`, `build_prompt(text_policy=…)` | **code, shipped** |
| **Image manifest** (re-rollable record, per-asset status) | image-generator.md §6 | `src/prompts.py` — `build_manifest`; `cli.py gen-prompts --manifest` | **code, shipped** |
| **Layout-pattern vocabulary** (image-as-canvas + native overlay, modifier stacking) | `references/image-layout-patterns.md` | [`schema/IMAGE_LAYOUT_PATTERNS.md`](schema/IMAGE_LAYOUT_PATTERNS.md) | **reference doc** |
| **QC-gate design** (blacklist, errors-block, no auto-fix, run-before-post-processing) | `docs/technical-design.md` §Quality Gate | [`schema/QC_GATE.md`](schema/QC_GATE.md) | **spec doc** |
| **Template taxonomy** (brand / layout / deck segment fusion) | `docs/templates-architecture.md` | this file, §Template taxonomy below | **note** |
| **TTS narration** (notes → audio) | `scripts/notes_to_audio.py`, `tts_backends/` | this file, §TTS opportunity below | **opportunity, not ported** |

The shipped code change is verified: `python src/cli.py gen-prompts control/getting-started.md
--manifest /tmp/x.json` runs clean — deck-wide palette behavior, the no-text cue, and both global
guards flow into every prompt, and the manifest tracks status per asset. The `gen-prompts` contract is
backward-compatible (existing flags unchanged; `--manifest` is additive).

## Architecture reference — for the dev department's build of the Course Creation System

PPT Master independently converged on the spine our `COURSE_CREATION_SYSTEM.md` already defines. Hand
their [`technical-design.md`](https://github.com/hugohe3/ppt-master/blob/main/docs/technical-design.md)
to whoever builds the pipeline as an app; the reasoning transfers even though the output medium differs.

| PPT Master | Our Course Creation System | Transferable lesson |
|---|---|---|
| Strategist → **single blocking "Eight Confirmations"** gate | **Gate 3** (SME script + structure approval) | bundle correlated design decisions into ONE gate; don't spread them and invite backtracking |
| `design_spec.md` (human "why") + `spec_lock.md` (machine "what") | our `design_spec` + a lockable contract | split narrative from the machine-readable contract the builder literally consumes |
| **spec_lock re-read before every page** | anti-drift on long builds | re-inject the locked values per unit to resist context-compression drift |
| **Role-switch in ONE agent, never sub-agents** | our note: page gen stays in main agent | page/slide design needs full upstream context; sub-agents drift |
| QC gate: blacklist, errors-block, **no auto-fix**, before post-processing | **Gate 5** (LMS verify) → now also [`schema/QC_GATE.md`](schema/QC_GATE.md) | validate the authored artifact early and precisely; re-author defects, don't auto-patch |
| Manifest with per-item status, idempotent re-run | our asset pipeline | track each asset's state so regeneration is incremental, not all-or-nothing |

## Template taxonomy — a refinement for our `templates/` system

ppt-master splits templates into three **kinds** with clean segment ownership and "whole-segment
replacement" fusion:

- **Brand** = identity only (color / type / logo / voice / icon style).
- **Layout** = structure only (canvas / page types / roster).
- **Deck** = a validated full replica (identity + structure), overridable by an explicit brand/layout.

Two ideas worth adopting in our `templates/` (today a flat set of archetypes + the browser editor):

1. **Separate brand identity from layout structure** so the TeleTracking brand is one reusable segment
   and course archetypes (concept-explainer, decision-scenario, software-procedure, policy) are layout
   segments — combine without duplicating the brand into each archetype.
2. **Free-design is the default; templates are opt-in, never auto-matched.** ppt-master's rationale:
   "templates are floors that become ceilings." For us this argues against forcing every course through
   a rigid template — let content shape the layout, reach for an archetype deliberately.

Not built yet — a note for when the template system is next revisited. Fits the existing
`templates/AUTHORING_GUIDE.md` + `template-editor.html` rather than replacing them.

## TTS narration — a net-new capability we don't have

`notes_to_audio.py` + `tts_backends/` turn speaker notes into narration (Edge TTS default — zero-key —
with ElevenLabs / MiniMax / Qwen / CosyVoice as upgrades). We have no audio path today. If narrated
microlearning is ever wanted, this is the reference: per-slide notes → per-slide audio → embed. Edge
TTS needs no API key, so a proof of concept is cheap. **Not ported** — flagged so it isn't re-discovered
from scratch. Decision deferred to James; depends on whether narration is a desired course feature.

## What we deliberately rejected (and why it matters)

- **SVG as our page intermediate.** ppt-master's own `why-ppt-master.md` states SVG exists to route
  *around* HTML ("HTML describes document flow; PowerPoint is a canvas"). Our target **is** responsive
  interactive HTML — the thing they escape. Adopting their fixed 1280×720 SVG canvas would reintroduce
  the constraint we avoid (our control course is *mobile*), kill interactivity (KCs, media gating, exit
  button), and weaken accessibility. **Narrow exception:** SVG is a good authoring surface for static
  *visual assets* (covers, objective plates, diagrams) if we ever want editable vector art instead of
  raster — but not for pages.
- **The SVG/DrawingML hard-constraint set** (banned `<mask>`, `fill-opacity` not `rgba()`, image-only
  `clip-path`, banned filters). These survive PowerPoint export; in HTML they only handcuff our CSS.
