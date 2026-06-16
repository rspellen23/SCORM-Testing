# Visual Asset Pipeline — design spec (implement next session)

> **Goal.** Define how every image a course needs is produced, named, and resolved — so visuals are
> brand-consistent and the build wires them in by **slot name** with no manual mapping. This is the
> §10 work, now grounded in the 2026-06-08 requirements: **Figma-exported SVGs** for decorative/
> element art, a **labelled folder of screenshots/graphics**, a **required objectives visual**, and
> **cover / header / hero** images for the LMS. *Design only — the `*Visual:*` grammar + slot resolver
> are already built (#17); this spec covers the asset-production half that feeds them.*

## What's already implemented (the consumption side)
- **`*Visual:*` directive** (`md_import`) → an `image` block, slot resolved against `--images`
  (verified). `type ∈ screenshot|graphic|diagram|photo|decorative`.
- **Hero/cover** → IR `hero` via `--hero` (resolved against the same folder).
- **Media blocks** (`image`/`video`/`audio`/`embed`) in the IR + renderer + packager.
- **Slot resolver:** filename match (case-insensitive) in the `--images` folder; unresolved slots keep
  `assets/<slot>` for later supply. **This spec defines what populates that folder.**

## Asset taxonomy (the four kinds)
| Kind | Source | Format | Slot name |
|---|---|---|---|
| **Decorative / element art** | **Figma** (export per frame) | `.svg` | `<slug>_<n>_<role>.svg` · e.g. `mbr_1_objectives.svg` |
| **Screenshots / graphics** | labelled folder (authored/captured) | `.png` / `.jpg` | `<slug>_<n>_<role>.png` · e.g. `mbr_3_screen.png` |
| **Objectives visual** | Figma template (per unit) | `.svg` | `<slug>_1_objectives.svg` (always Slide 1) |
| **LMS cover / hero / mobile** | Path-B compositor | `.png` / `.jpg` | `<slug>_cover.png` · `<slug>_hero.jpg` · `<slug>_hero_mobile.jpg` |

**Naming is the contract** (`<slug>_<slide#>_<role>.<ext>`): the `*Visual:*` slot and the resolver
already speak it; the production flows below must emit exactly these names so resolution is automatic.

## Flow 1 — Figma → SVG export (decorative + element art)
- **Path A only is needed here:** Figma REST **export** (token, JIT) of named frames → one `.svg`
  each. Decorative/diagram elements are used **as-is** (no composition), so the REST export-only
  constraint (2026-06-02 audit) is not a blocker.
- Input: a list of `{figma_node_id → slot_name}`. Output: `<slot>.svg` files dropped into the
  labelled-asset folder. SVG rides in `<img>` (renderer) and zips fine into SCORM (verified path).
- **a11y refinement:** `decorative` visuals should resolve to **`alt=""`** (screen-reader-ignored).
  Small `md_import` follow-up — today `decorative` suppresses the caption but still sets `alt=desc`;
  change to empty alt for `type=decorative`.

## Flow 2 — Labelled screenshot/graphic folder (the resolver source)
- The folder **is** the `--images` argument. Authored screenshots/graphics are dropped in, named by
  slot. Optionally a `manifest.csv` (`slot, description, source`) for QA — lets us flag any
  `*Visual:*` slot with no matching file **before** build (a "missing-asset" lint).
- Build-time check to add: after parse, list `image` blocks whose `src` is still `assets/<slot>`
  (unresolved) and **warn loudly** (consistent with the "no silent truncation" guardrail).

## Flow 3 — Cover / header / hero for the LMS (Path-B compositor)
The LMS needs three tile images (the §6 bulk-CSV columns) plus the in-course cover:
| Output | Used by | Composition |
|---|---|---|
| `<slug>_cover.png` | IR `hero` (in-course cover band) | background plate **+ centered course icon** (Path B) |
| `<slug>_hero.jpg` | bulk-CSV **Hero Image URL** | wide crop of the cover |
| `<slug>_hero_mobile.jpg` | bulk-CSV **Mobile Hero Image URL** | tall/mobile crop |
| (cover art) | bulk-CSV **Cover Art URL** | = `<slug>_cover.png` |
- **Compositor (Path B):** a deterministic image lib (Pillow / sharp / resvg) composites
  `background + icon` from a JSON spec → the named outputs. Figma designs the **plates**; per-course
  composition runs in code (reproducible, no Figma-in-the-loop at runtime).
- **Header:** the in-course top banner is the renderer's `.nv-topbar` (brand logo) — no per-course
  header image needed unless a course wants a custom band; decide in build.
- These outputs must be hosted at **public HTTPS** for the LMS tile columns (Segment D).

## Image-prompt generator (ChatGPT art) — IMPLEMENTED 2026-06-09
Leadership generates course art (covers, Learning Objectives plates, in-lesson illustrations) with
ChatGPT using a fixed TeleTracking style preamble + a per-asset description. The builder now **emits
the paste-ready prompt for every art asset a course needs**, so the prompt is waiting when art is.
- **Constant** (`src/prompts.py` `STYLE`): the verbatim style + full palette + "small accents only" +
  "one clear idea" + the avoid-list (no readable text / photorealism / anime / glossy 3D / mascots).
- **Variables:** (1) **color hierarchy** per module section (`--hierarchy`, default = TeleGreen dominant,
  Teal + Deep Navy secondary); (2) **orientation** per asset role; (3) the **asset description** (the
  `Asset type:` line, from the `*Visual:*`/cover description).
- **Orientation rule (the gap leadership flagged):** `cover→landscape` (16:9), `objectives→portrait`
  (2:3/3:4, sits beside the objectives column), `aside`(any `side:` 2-col)→portrait, `full→landscape`,
  `spot→square`. Override per asset with `*Visual:* … · orient: portrait|landscape|square`.
- **Generatable vs captured:** `type=screenshot` = a real capture (skipped, no prompt); every other
  type (illustration/graphic/photo/diagram) gets a prompt. Each prompt is labeled by its **slot
  filename** so the generated image is saved with the name the resolver expects.
- **CLI:** `python src/cli.py gen-prompts <md> --hero <slot> [--hierarchy "…"] --out <file>` →
  one prompt per asset. Run it at design time; hand the file to whoever generates the art.

## Transition bands (brand ribbon dividers) — IMPLEMENTED 2026-06-09
Nearly every TeleTracking course separates sections with the brand **ribbon** wave graphic. These are
now a first-class, reusable `transition` block (no per-course asset work):
- **Source:** `Articulate Assets/<Color>_Transition_OMNI.png` (~3423×2470; all colors share dims).
- **Canonical crop (pre-cropped ONCE into brand assets, not per course):** full width, **top band**
  `y 690→990`, **bottom band** `y 1500→1800` (a ~12%-tall slice of the ribbon's upper / lower curve).
  Derived from the live "Getting Started" control (Teal_Transition_OMNI cropped top≈698/bottom≈1516 in
  the half-scale crush). The bands live at `brand/transitions/<color>-<band>.png` and bundle into every
  course automatically (renderer copies `brand/` wholesale).
- **Colors built:** green (TeleGreen default), gold, dark, blue, teal. The off-brand teal the control
  shipped is replaced by green by default.
- **Authoring:** `*Transition:* <color> <band>` (e.g. `*Transition:* green top`). Regenerate bands with
  the crop constants above if brand art changes.

## Objectives visual (the new Slide-1 standard)
Every unit's Slide 1 carries `*Visual:* graphic · … · slot: \`<slug>_1_objectives.svg\``. Produce a
**branded objectives plate** in Figma (a template frame: brand band + "Learning Objectives" + an
illustration) exported per unit, or a single reusable decorative SVG if per-unit art isn't warranted.
Decision for next session: per-unit vs. one shared objectives graphic.

## Build order (next session)
1. **Missing-asset lint** (Flow 2) — cheapest, highest safety; warn on any unresolved `*Visual:*`/hero slot.
2. **`decorative ⇒ alt=""`** refinement in `md_import` (Flow 1 a11y).
3. **Figma SVG export script** (Flow 1) — node-id → slot `.svg`, JIT token.
4. **Path-B cover/hero/mobile compositor** (Flow 3) — background + icon → the 3 LMS crops + cover.
5. **Objectives-plate** decision + template (per-unit vs shared).
**Acceptance:** a unit with a `*Visual:*` on every slide + the objectives slide builds to SCORM with
all slots resolved from the folder, and the LMS tile gets cover + hero + mobile-hero URLs.

## Open decisions
- Per-unit objectives plate vs. one shared graphic.
- Whether decorative SVGs need brand-token theming at export, or are pre-branded in Figma.
- Manifest-driven QA (`manifest.csv`) vs. folder-only.
- Custom per-course header band vs. the standard brand topbar.

## Provenance
- **OBSERVED/RECALLED:** the `*Visual:*` grammar + slot resolver are implemented + verified this
  session; `--hero` resolution and the bulk-CSV Cover/Hero/Mobile columns are existing facts
  (`md_import.py`, §6). Figma REST = export-only is from the 2026-06-02 capability audit.
- **GENERATED (proposed, not built):** the asset taxonomy + naming table, Flows 1–3, the missing-asset
  lint, the `decorative⇒alt=""` refinement, the Path-B crop set, and the objectives-plate options.
