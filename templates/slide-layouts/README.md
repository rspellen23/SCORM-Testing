# Slide layouts (standalone infographic slides)

Reusable, on-brand single-slide PowerPoint templates — separate from course
builds. Edit a JSON content file, run one command, get an editable `.pptx`.
Colors come from the active **brand**, so the same template renders branded or
neutral.

## Make a slide
```bash
# from an edition folder (brand is applied automatically):
./build slide --content my-slide.json --out my-slide.pptx

# or call the engine directly with an explicit brand:
python3 src/cli.py slide --content my-slide.json --layout infographic \
    --out my-slide.pptx --brand <brand-dir-or-name>
```

## Make a new slide from this template
1. Pick a layout (see **Layouts** below) and copy its `*.example.json` to a new file.
2. Replace the placeholder text. Every section is optional — delete a key to drop
   that section. Card/step/column `accent` is a brand role (see **Accents**).
3. Run `./build slide --content <yourfile>.json --layout <name> --out <slide>.pptx`
   (omit `--layout` for the default `infographic`; add `--brand teletracking` to brand it).
4. Open the `.pptx` and fine-tune in PowerPoint if needed.

## Layouts
Select with `--layout <name>` (default `infographic`).

- **infographic** — header band (title + subtitle) · left "challenge" column
  (heading + intro + bulleted items + callout) · right "framework" column
  (heading + sublabel + numbered cards) · goals row (label chip + cards) ·
  footer band. Example: `infographic.example.json`.
- **process** — header band (title + subtitle) · optional intro line · a row of
  3–6 connected numbered step cards (top accent strip · numbered circle · title
  · body) joined by chevrons · optional footer band. Best for pipelines and
  how-it-works sequences. Example: `process.example.json`.
  ```bash
  ./build slide --content process.example.json --layout process --out steps.pptx --brand teletracking
  ```
- **comparison** — header band · optional intro · 2–3 side-by-side panels, each
  with an accent header bar (heading) · optional sublabel · bulleted items (up to
  6) · optional callout box · optional footer band. Best for old-vs-new or option
  A/B/C. Example: `comparison.example.json`.
- **timeline** — header band · optional intro · a horizontal axis with 3–6
  numbered milestones alternating above and below the line, each a card with a
  phase chip · title · body · optional footer band. Best for roadmaps. Example:
  `timeline.example.json`.
- **divider** — full-bleed branded title screen: optional kicker label + accent
  rule · large centered title · optional subtitle · optional footer band; `bg`
  selects the background brand role (`dark` default). Use as a section break or a
  course/deck title slide. Example: `divider.example.json`.
- **agenda** — header band · optional intro · a numbered table of contents: each
  entry is a large accent numeral + section title + optional one-line description,
  in 1 or 2 columns (2 auto-engages past 5 items, up to ~8). Modeled on the
  official TeleTracking "Agenda" layout. Example: `agenda.example.json`.
- **closing** — full-bleed branded closing/thank-you screen: optional kicker · a
  large headline (default "Thank you") · optional supporting line · optional
  `contact` lines · the brand wordmark centered near the bottom; `bg` selects the
  background brand role (`dark` default). Modeled on the official "Closing Slide".
  Example: `closing.example.json`.

## Deck purpose presets
When generating a whole deck from source material (slide-presentation tab, or
`authoring.generate_deck(..., preset=)`), a **purpose preset** shapes the deck's
**structure, voice, and length** — all on the *same* brand standard and the same
layouts. The difference between a pitch and a workshop is the slide arc and tone,
never divergent styling. Presets (`authoring.DECK_PRESETS`):

- **general** — neutral default; let the material decide.
- **formal** — executive-ready: title → agenda → section dividers → comparison /
  infographic / process → a `statement` takeaway → `closing`. Polished, concise.
- **debrief** — retrospective: context → `timeline`/`process` of events →
  what-worked-vs-didn't `comparison` → takeaways `bullets` → `closing`. Candid, factual.
- **workshop** — instructor-led training: `agenda` of objectives → one concept per
  slide (`infographic`/`process`/`cards`) → recap → `closing`. Plain-language, "you".
- **client** — external/customer: overview → value & capabilities (`cards`/
  `comparison`) → how-it-works (`process`) → outcomes → `closing` with contact.
  Benefit-led, jargon-light; internal aliases/acronyms avoided.
- **pitch** — persuasive: problem → solution → differentiation → proof → the ask →
  `closing`. Big confident statements, minimal text.

The preset is a prompt layer only (no renderer changes). The dashboard slide tab
exposes it as the **Purpose** selector; a drift test keeps the two in sync.

## Accents
Card/goal `accent` is a brand role: `primary` · `secondary` · `tertiary` ·
`dark`. Omit it to auto-cycle through the four. Roles map to the brand palette
(e.g. green / teal / blue / navy).

## Content schema
See the header of `src/slide_layouts.py` for the full schema. Bulleted `items`
accept either `"a plain line"` or `["bold lead", " rest of the line"]`.

There is also a pre-built `.pptx` master in this folder you can duplicate and
type over directly in PowerPoint, no command needed.
