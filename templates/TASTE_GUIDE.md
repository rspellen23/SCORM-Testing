# Taste Guide — the anti-slop discipline this tool applies to everything it generates

> **What this is.** The always-on *taste* rules the generators apply on top of the
> pedagogy/media rules (course) and the layout schema (deck). Where the AUTHORING
> GUIDE governs *what is taught* and the layout templates govern *how a slide is
> built*, this guide governs *whether the result looks considered or looks
> generated*. The condensed form ships inside the prompts as `TASTE_RULE`
> (`src/authoring.py`); this file is the full reasoning behind it.
>
> **Provenance.** Distilled from the open "anti-slop frontend" taste principles
> (the *taste-skill* project, MIT, github.com/leonxlnx/taste-skill). That work
> targets free-form web frontends; this guide **inverts** its core stance for our
> reality and is written in our own voice — none of its text is vendored.

---

## 0. The inversion — why a frontend taste skill can't be applied literally

The source skill's baseline is **high variance**: "reach past the default, pick an
exotic font, crank motion, go Awwwards." That is correct for a blank-canvas landing
page. It is **wrong here.** This tool emits PowerPoint (via `python-pptx`
renderers) and SCORM HTML from a **locked, brand-faithful design language** — a
fixed palette, fixed fonts (Open Sans), a fixed set of layouts, token-driven
renderers ([[reference_slide_design_language]]). Brand fidelity is the product.

So "taste" here is **not** reaching past the system. It is using the locked system
with **restraint and deliberate variety**. We keep the source skill's *anti-slop
instinct* and discard its *high-variance default*.

| Source skill says | We keep | We invert / drop |
|---|---|---|
| Pick a better font than Inter | (drop) | Fonts are brand-fixed |
| Reach for a real design system (Tailwind/Fluent) | (drop) | Our renderers *are* the system |
| `DESIGN_VARIANCE: 8`, go experimental | the anti-*sameness* instinct | the high-variance default → restraint |
| Generate hero imagery, glassmorphism, motion-physics | (drop) | N/A to pptx/SCORM |
| Anti-default discipline, cut ruthlessly, no AI tells | **keep, fully** | — |

---

## 1. Anti-sameness — variety *inside* the locked system

The single most common slop signature is **everything looking the same**: every
slide one accent, the same layout family back-to-back, the same rhythm.

- **Vary the accent across sections.** Do not pin the whole deck/course to one
  accent. The renderer auto-cycles accents when you leave them unset; reach for an
  explicit `accent` only to make a *deliberate* per-section choice, and vary it.
  (Enforced as a non-blocking nudge by `authoring.deck_palette_warnings`; serves
  [[feedback_course_color_palette_variety]].)
- **Don't repeat a layout family on consecutive slides.** Two `cards` grids in a
  row, or three `comparison` slides, read as a template. Break the rhythm.
- **Restraint is the default, not flourish.** The system already looks designed.
  Adding "visual interest" on top is how it starts looking generated.

## 2. Cut ruthlessly — one idea per slide

- Short heading, tight body. If a slide overflows, the answer is **another slide or
  a better-fitting layout**, never a smaller font or a denser cram.
- **Never split a single visualization** (chart, diagram, table) across slides — it
  is one object ([[feedback_no_split_visualizations]]).
- Long lists are a layout problem, not a length problem: a 12-row bullet list wants
  a `cards`/`comparison`/`cycles` structure or grouping, not more bullets.

## 3. Copy — no AI tells

- **Concrete verbs, not filler.** Banned as filler: *elevate, seamless, unleash,
  leverage, robust, next-gen, revolutionize, unlock, empower, streamline.*
- **No fake-precise numbers.** Cite a statistic only if it appears literally in the
  source. Invented precision (`92.4%`, `4.1×`) is a tell and a fabrication.
- **Real specifics, not placeholders.** Never "John Doe" / "Acme Corp".
- **Name a step by what it does** ("Submit the request"), not "Step 1 / Stage 1 /
  Phase 01".
- **Em-dash-as-flourish is a tell.** Prefer a period, comma, colon, or parentheses.
- **Copy self-audit before ship:** re-read every visible string and rewrite anything
  grammatically broken, cute-but-wrong, or trying to sound thoughtful.

## 4. Quotes & attribution

- Keep a quote to about three lines, trimmed to the point.
- Attribute with a **name and role**, never a bare name.

## 5. Motion & theme restraint

- Animation must be motivated (hierarchy, sequence, feedback) — not decoration.
  The `rise`/`fade` builds are deliberate; don't animate everything.
- One theme per piece. The per-slide `theme: dark|light` override exists for a
  *deliberate* single-slide flip (a contrast section break), not random
  alternation. A reader should never feel they changed decks mid-scroll.

---

## 6. Where this is applied

- **Generated output (course + deck).** `TASTE_RULE` is injected into
  `build_prompt` and `build_deck_prompt` (`src/authoring.py`), alongside the
  pedagogy/media/chart rules.
- **Dashboard chrome.** The operator tool stays neutral/clean by design; the taste
  rules that apply to it are the medium-agnostic ones (restraint, no decorative
  tells, copy discipline), not the brand-content rules.
