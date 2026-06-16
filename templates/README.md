# Authoring Templates — microlearning scaffolds (Segment C, front-half)

Templates the **drafting step** (me, the LLM) consumes to write conformant, on-pattern microlearning
scripts. Layered: one always-on guide + one bare skeleton + named archetypes. They govern *what the
script says*; the §9.1 IR block model governs *how it's built*. See `COURSE_CREATION_SYSTEM.md` §4.

## Editing templates visually — `template-editor.html` (for non-VS-Code colleagues)
**Double-click `template-editor.html`** to open it in any web browser — no install, nothing to set up.
It's a guided form for maintaining the archetypes (slide roles, headings, the guidance that steers
Claude). You **can't break the format**: the structural markers (`**Slide K —**`, the KC grammar, the
`**Articulate Build Notes:**` cut) are generated for you, never typed.

Workflow for colleagues:
1. Open `template-editor.html`; pick a template from the dropdown. It loads the current ones.
2. Edit fields on the left; the **live preview** on the right is the exact `.md` that will be saved.
   Your work **autosaves in that browser**.
3. Click **⬇ Export Template (.md)** and send the downloaded file to James, who drops it into this
   folder (replacing the old one). The editor and these `.md` files are kept **identical** by design.
- *Import* loads an existing `.md` (best-effort) or a `.json` backup to keep editing. *Reset* restores
  the built-in defaults. Editing the *content* fields is always safe; the export is always conformant
  (verified: every archetype the editor emits parses through `md_import` with the meta correctly cut).

## Files
| File | Role |
|---|---|
| `template-editor.html` | **Visual editor** for the archetypes — open in any browser, no install (see above). Exports `.md` identical to the files here. |
| `AUTHORING_GUIDE.md` | **Always read first.** Voice, time budget, the §8 grammar rules, the META_CUT gotcha, the Visuals/Media plan convention. Applies to every script. |
| `_skeleton.md` | Bare conformant unit — use when no archetype fits. |
| `concept-explainer.md` | Teach an idea/model/term (what → why → how → apply → recap → KC). |
| `software-procedure.md` | Do a task in Nova (goal → steps → demo → mistakes → recap → KC). |
| `decision-scenario.md` | Apply a rule to a situation (rule → criteria → scenario → decision KC → debrief). |
| `policy-acceptable-use.md` | Compliance (core rule → why → do/don't → when unsure → KC). |

## How to use (the drafting protocol)
1. Pick the archetype that matches the teaching job (or `_skeleton.md`).
2. Read `AUTHORING_GUIDE.md` **+** that archetype file.
3. Follow the archetype's slide-role plan; fill every `{{PLACEHOLDER}}` with content grounded in a
   real source segment and the unit's objective.
4. **Delete all `<!-- guidance -->` comments and role labels** — they're authoring aids, not learner
   content.
5. Self-check against the guide §2 (parses? meta under the marker? KC well-formed? in budget?), then
   build: `python src/cli.py from-md <unit>.md --which N --out build/<unit>.zip`.

## Visuals & the objectives slide (added 2026-06-08)
- **Slide 1 is always Learning Objectives** + a visual — built into all four archetypes and `_skeleton`.
- **In-slide visuals** use the `*Visual:* type · description · slot: \`file\`` directive (parser-
  supported). The editor exposes Type / Description / Slot fields per content slide. Sources: Figma
  `.svg` element art + a labelled folder of screenshots/graphics, resolved by slot name (`--images`).
  Video/audio stay in the Build-Notes Media plan. Full asset-production design:
  [`../schema/ASSET_PIPELINE.md`](../schema/ASSET_PIPELINE.md).

## Extending
- **New archetype** = a new file here following the same shape (role-plan comment header + fillable
  §8 body). Cheap — no code change; the build only cares that the *output* is §8-conformant.
- Keep templates emitting the **§8 contract verbatim** — every parser rule in `AUTHORING_GUIDE.md` §2
  is load-bearing. New media still goes through the **Visuals/Media plan** in Build Notes (resolved to
  IR `image`/`video`/`audio`/`embed` blocks at build), not as markdown images.
