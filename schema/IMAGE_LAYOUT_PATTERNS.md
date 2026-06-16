# Image-Text Layout Patterns — a vocabulary for the `*Visual:*` grammar

> **Provenance.** Adapted from `hugohe3/ppt-master` (MIT), `references/image-layout-patterns.md`.
> That catalog targets static SVG→PPTX slides; this file **translates the design vocabulary to our
> medium** — responsive HTML/SCORM microlearning — and maps each family onto our existing block set
> and `*Visual:*` slot grammar. It is a *registry to widen the menu*, not a rulebook. See
> [HARVEST_NOTES.md](../HARVEST_NOTES.md) for why we harvested it and what we did NOT take.

## The one principle worth internalizing

ppt-master's core insight ports cleanly, and it is the most underused move we have:

> **The image carries atmosphere, world-building, emotional weight.
> The native layer carries information, data, and everything editable.**

For ppt-master the native layer is SVG vector shapes. **For us the native layer is HTML/CSS/JS** —
headings, body, knowledge-check cards, buttons, callouts — rendered *over* a CSS `background-image`.
This matters more for us than for them, because our native layer is also:

- **localizable** (en-GB swaps text without regenerating art),
- **interactive** (KCs, media gating, the exit button), and
- **accessible** (real DOM text, not raster).

So the default reflex — image in one box, text in the adjacent box (`imageText` 2-col) — is the floor,
not the ceiling. The richer move is **image-as-canvas**: a full-bleed background image whose calm
region receives HTML content on top. Everything that must stay editable, exact, translated, or
interactive lives in HTML regardless of what the image shows underneath.

## How this maps to what we already build

| ppt-master family | Our equivalent today | Net-new opportunity |
|---|---|---|
| #2/#3 left/right-third image + text | `*Visual:* … · side:` (the 2-col `imageText`) | — already shipped |
| #1 full-bleed background + floating title | cover / hero banner | image-as-canvas *content* slides (below) |
| #27–#33 scrims / gradient masks for legibility | brand `transition` waves, section plates | CSS `linear-gradient` scrim over a hero so HTML text stays legible |
| #38–#46 **image-as-canvas + native overlay** | — (we don't do this yet) | **highest-value gap** — see below |
| #47/#48 small-multiples / before-after | — | a `compare` block (2 images + labels) |
| #20–#24 non-rect crops (circle/round/hex) | — | `border-radius` / `clip-path` on `*Visual:*` images |
| #64/#65 in-image text vs SVG-overlay text | our `text_policy` (see `src/prompts.py`) | already harvested into the prompt generator |

## The families, translated

**Containers (where the image sits).** Left/right third, top/bottom band, full-bleed, narrow strip,
negative-space-dominant, picture-in-picture. We already express the common ones through `*Visual:* …
· side:`. Worth adding to the grammar: a **band** option (image as a horizontal strip between two
text sections) and a **full-bleed hero-content** option (image fills the slide, HTML sits on a calm
region) — both are pure CSS, no new asset type.

**Image-as-canvas + native overlay — the gap worth closing.** This is the family ppt-master flags as
"most likely to be skipped," and we skip it entirely today. The pattern: a full-bleed scene image with
HTML drawn on top —

- annotation cards with leader lines pointing at parts of a screenshot,
- numbered hotspots over a UI with a sidebar legend (great for *software-procedure* courses),
- floating KPI/metric cards over an operations photo,
- a bordered "lens" rectangle highlighting one sub-region of a screenshot.

For us these are **HTML/CSS overlays positioned over a `background-image`** — and because the overlay is
HTML, the hotspot labels are translatable and the cards can even be interactive. This is the single
richest thing to build into the IR next, and it pairs naturally with our screenshot-heavy procedure
courses. (In ppt-master these are #38–#46; numbers kept so cross-references resolve.)

**Modifier layers (finish, stacked on a container).** Non-rectangular crops (`border-radius`,
`clip-path`), gradient scrims for text legibility, color-tint overlays to pull an off-palette image
toward TeleGreen/Teal without regenerating it, soft drop shadows, slight editorial rotation, thin
matte frames. All are one or two CSS rules. The observed-good stack: one container + rounded crop +
a top accent-gradient + a bottom fade-to-background + a small reversed-out label badge.

**Text ownership (already harvested).** ppt-master #64 (text baked into the image) vs #65 (no image
text; labels as overlay) is exactly our `text_policy` toggle in [`src/prompts.py`](../src/prompts.py).
For instructional design the default is #65 / `text_policy: none` — labels live in HTML so they stay
translatable and editable. #64 / `embedded` is the deliberate exception for a stable designed cover title.

## What we deliberately did NOT take

- **The SVG/DrawingML hard constraints** (`<clipPath>` only on `<image>`, no `<mask>`, `fill-opacity`
  not `rgba()`, banned filters). Those exist to survive PowerPoint export — irrelevant to HTML, where
  `rgba()`, `mask`, and filters all work. Importing them would only handcuff our CSS.
- **The 1280×720 fixed-canvas coordinate math.** Our pages reflow (mobile-first); absolute SVG
  positioning is the constraint we are specifically avoiding. See [HARVEST_NOTES.md](../HARVEST_NOTES.md).

## Next step for the IR

The actionable harvest here is **one net-new block**: `imageCanvas` — a full-bleed image with an
overlay region (`top|bottom|left|right|center`) carrying normal HTML children, plus an optional
`hotspots[]` list (x%, y%, label) for the annotation/legend pattern. Specced here; build when a
procedure course needs it. Until then, `*Visual:* … · side:` + the modifier CSS above covers most cases.
