# Rise-Parity Block Expansion — design spec (implement next session)

> **Goal.** Close the gap between what the 51 real TeleTracking Rise courses use and what our IR /
> renderer can reproduce, so courses built by this system can **emulate the visual + interactive
> variety** of the existing catalog. This is a **design/mapping spec only** — no code is changed yet;
> it defines the exact Rise→IR mapping, the renderer/player approach, the §9.1 cost, and the
> accessibility contract for each new block, plus the build order. Extends
> [`IR_SCHEMA.md`](IR_SCHEMA.md) §9.1 and resolves the design half of risk #9.

> **⚠ CORRECTION (2026-06-08, supersedes the first draft).** An earlier version of this spec claimed
> the 188 `mondrian` blocks were "all empty → pure section-styling, resolve with a cheap band param."
> **That was wrong** — it read the *lesson-level* block (whose `items:[]` is empty) and missed that
> the content lives in **`course.mondrian.blockuments` + `course.mondrian.items`**, referenced by
> **`blockumentId`**. The mondrians are **custom content blocks carrying real instruction**, including
> **Learning Objectives** (see §1). Decoding them is a substantial new effort, not a parameter.

## Motivation — the measured gap (OBSERVED, decoding all 51 `-raw-` exports this session)
The importer currently drops these (via `block_to_ir`'s `skipped` tally):

| Skipped Rise block | Count | Reality / resolution |
|---|---|---|
| `mondrian/mondrian` (**custom blocks**) | 188 | **NOT empty** — a free-form canvas in `course.mondrian` carrying **~1,981 positioned nodes** (838 shape · 536 group · 366 text(tiptap) · 241 image). Template-based. **Real content, incl. objectives (23 courses).** → §1, a **custom-block decoder** (significant). |
| `interactive/accordion` | 3 | → new `accordion` block (§2) |
| `flashcard/flashcard` | 3 | → new `flashcard` block (§4) |
| `interactive-fullscreen/process` | 3 | → new `process` block (§5) |
| `interactive/tabs` | 1 | → new `tabs` block (§3) |

**Acceptance test:** the 10 interactives → their types is the *easy* win (skip count 198→188). The
**188 custom blocks** are the hard, high-value win — measured not by "0 skips" but by **content
recovery**: re-import the 50 custom-block courses and confirm objectives + template content (Before/
After, Pros/Cons, Process, …) now appear in the IR. The 51 courses are the regression corpus.

---

## 1. Custom blocks (mondrian / blockuments) — the free-form canvas  ·  cost: **HIGH (new decoder)**

**Rise reality (OBSERVED).** A lesson-level `mondrian` block carries `items:[]` **plus** a
`blockumentId` and a `settings.backgroundType`. The *content* lives in **`course.mondrian`**:
- `blockuments{ }` — keyed by id; each `{ title, children, layers, triggers, responsive }`. The
  **`title`** is a **template name** (the semantic hint): `Custom Block`(102), `Before and After`(28),
  `Pros and Cons`(22), `Simple/Stepped Process Vertical`(16), `Bio`(9), `Myth vs. Fact`(5),
  `Key Concept`, `Do's and Don'ts`, `Mission`, …
- `items{ }` — positioned nodes keyed by id, each with `blockumentId`, `parentId`, `type ∈
  {text, image, shape, group}`, and `states.default` carrying **absolute geometry** (`x,y,width,
  height,rotation`) + (for text) a **tiptap JSON doc** (`states.default.text.json`, prosemirror-style)
  + (for image) an asset ref. `group` nests children; `shape` is usually decorative.

**Decode strategy — two tiers (recognize the template; don't pixel-reproduce the canvas).**

**Tier A — template-mapped (tractable, do first).** The blockument `title` tells us the structure, so
map each known template → a **clean semantic IR block**, pulling the text/image items by role
(reading order = sort items by `states.default.y` then `x`, descend `group`s):
| Blockument template | → IR block |
|---|---|
| Before and After · Pros and Cons · Myth vs. Fact · Do's and Don'ts | `table` (2-col) or `imageText` pair |
| Simple/Stepped Process Vertical | **`process`** (reuse §5 — one block serves Rise process *and* these) |
| Key Concept · Mission | `note` / `statement` callout |
| Bio | `imageText` |
| **Learning-Objectives** custom blocks (23 courses) | the objectives list → `list` under a heading (+ our Slide-1 objectives visual) |

**Tier B — generic "Custom Block" (102, hard).** No template hint → **best-effort linearization**:
sort items by (y,x), emit `text`(tiptap→HTML) + `image` in reading order, **drop pure-decorative
shapes**, flag the block **low-confidence** for SME review (per the §11 "no silent truncation" rule —
log what was dropped). Free-form geometry is **not** reproduced; we recover the *content*, re-flowed
into the brand layout.

**Hard dependencies to build:**
1. **tiptap-JSON → HTML** converter (`doc → paragraphs/marks/lists`; map `textStyle/bold/italic/link`
   → sanitized inline HTML, same surface as `clean_html`). This is the keystone — 366 text nodes.
2. **blockument → items resolver** (`course.mondrian.items` filtered by `blockumentId`, grouped by
   `parentId`, ordered by geometry).
3. **template fingerprinting** (by `title`, with a fallback when `title=="Custom Block"`).
4. **asset resolution** for canvas `image` items (extend `_resolve_image` to the canvas `assets`).

**Separate, still-true note — the `backgroundType` styling.** Independent of content, the mondrian
`settings.backgroundType` (LIGHT/TINT/ACCENT) is a real section-band treatment → an optional `band`
param on the emitted block(s). Minor; bundle it with the decoder, not as the headline.

> This is the **biggest single content-recovery item** in the catalog and the hardest. Recommend a
> **proof-of-concept first**: decode ONE objectives block + ONE "Before and After" end-to-end
> (blockument → items → tiptap → IR) to validate Tier A before committing to all template types.

---

## 2. Accordion  ·  §9.1 cost: **NEW TYPE (low)**

**Rise reality:** `family=interactive, variant=accordion`, `items:[{title, description(HTML), media.image?}]`.

**IR:**
```jsonc
{ "type": "accordion", "items": [ { "title": "Show and Hide Columns", "html": "<p>…</p>", "src": "assets/…"? } ], "gated": false }
```
- **Importer:** `title`→title, `clean_html(description)`→html, `_resolve_image(media)`→src.
- **Renderer:** native `<details><summary>title</summary>…html…</details>` per item — **keyboard +
  screen-reader accessible for free**, no JS required. Brand the `<summary>` marker.
- **Player:** none (native disclosure).
- **a11y:** native `<details>` gives expand/collapse semantics out of the box; just ensure focus ring
  + contrast.

---

## 3. Tabs  ·  §9.1 cost: **NEW TYPE (medium — JS + ARIA)**

**Rise reality:** `family=interactive, variant=tabs`, **same item shape as accordion**
(`{title, description, media.image?}`), `settings.cardMode`, `backgroundType:TINT`.

**IR:** identical shape to accordion, different type:
```jsonc
{ "type": "tabs", "items": [ { "title": "From the Protocols dictionary", "html": "…", "src": "assets/…"? } ] }
```
- **Importer:** **shared with accordion** — one helper maps `interactive/{accordion,tabs}` →
  `{type, items[]}`; only the `type` string differs.
- **Renderer:** a `role="tablist"` of `<button role="tab" aria-controls>` + `role="tabpanel"`
  regions; first tab active.
- **Player:** small tab-switch handler (show/hide panels, manage `aria-selected` +
  roving `tabindex`, Left/Right arrow keys). ~20 lines, self-contained.
- **a11y:** WAI-ARIA tabs pattern (roving tabindex, arrow-key nav, `aria-selected`). Mandatory.

---

## 4. Flashcards  ·  §9.1 cost: **NEW TYPE (medium — JS flip + CSS + ARIA)**

**Rise reality:** `family=flashcard`, `items:[{ front:{type, media.image?, description}, back:{media.image?, description} }]`.

**IR:**
```jsonc
{ "type": "flashcard", "items": [ { "frontHtml": "…", "frontSrc": "assets/…"?, "backHtml": "…", "backSrc": "assets/…"? } ] }
```
- **Importer:** `front.description`→frontHtml, `back.description`→backHtml, each `media`→src.
  `front.type:"fullimage"` ⇒ image-forward front.
- **Renderer:** a card grid; each card a `<button aria-pressed>` with a `.nv-card-inner` that
  CSS-3D-flips on toggle. Front + back faces.
- **Player:** click/Enter/Space toggles `aria-pressed` + `.flipped`. ~12 lines.
- **a11y:** real `<button>` semantics, `aria-pressed` state, both faces in DOM (screen reader reads
  both), prefers-reduced-motion disables the 3D flip.

---

## 5. Process / stepper  ·  §9.1 cost: **NEW TYPE (medium — JS stepper, static fallback)**

**Rise reality:** `family=interactive-fullscreen, variant=process`,
`items:[{ type:"intro"|"step", title, media.image?, description }]`, `settings.showStepLabel`.

**IR:**
```jsonc
{ "type": "process", "items": [ { "title": "What is it?", "html": "…", "src": "assets/…"?, "kind": "intro"|"step" } ] }
```
- **Importer:** items→steps; carry `type`→kind.
- **Renderer:** **progressive-enhancement** — render a semantic **ordered list of steps** (fully
  readable with no JS); JS upgrades it to a one-step-at-a-time stepper with Prev/Next + a progress
  dots row.
- **Player:** stepper nav (~25 lines). **Optional completion gating:** like media `requireComplete`,
  a `requireComplete:true` can require **all steps viewed** before the course completes (client-side,
  so observable — unlike embeds). Default off.
- **a11y:** steps are an `<ol>`; stepper controls are buttons with `aria-current="step"`; focus moves
  to the revealed step.

---

## Completion semantics (consistency with the media model)
Interactive blocks are **client-side**, so unlike embeds their interaction **is** observable. Each of
`tabs` / `flashcard` / `process` MAY take **`requireComplete: true`** to fold into the completion
tally (all tabs opened / all cards flipped / all steps viewed) — the same `data-require` mechanism the
player already uses for media. **Default off**; accordion stays optional/non-gating. Keep the rule:
*only observable interactions can gate completion.*

## Cost summary + build order (next session)
| # | Block | Cost tier | Why this order |
|---|---|---|---|
| 1 | **accordion** | New type (low) | Native `<details>` → a11y free, no JS. Quick win. |
| 2 | **tabs** | New type (medium) | Shares the importer + item shape with accordion. |
| 3 | **process** | New type (medium) | Static `<ol>` fallback ships value; **reused by the custom-block "Process" templates** (#5). |
| 4 | **flashcard** | New type (medium) | Most JS/CSS of the interactives. |
| 5 | **custom-block decoder** (mondrian) | **HIGH (new subsystem)** | tiptap→HTML + blockument resolver + template mapping. Biggest content recovery (objectives + 188 blocks). **Start with a 1-block PoC.** Build last / as its own track, but highest *value*. |

Each block ships the full slice: **IR type/param → `ir.schema.json` + `IR_SCHEMA.md` → `render.py`
case → `player.js`/`player.css` (where interactive) → `rise_import.py` mapping → verify by
re-importing the 51-course corpus and confirming the skip count drops.**

## Authoring-template wiring (once built)
The archetypes' **Visuals/Media plan** + guidance gain these as options (and the
`template-editor.html` can expose them later):
- **software-procedure** → `process` for the step-by-step; `tabs` for variant paths.
- **concept-explainer** → `tabs` for "compare A vs B"; `flashcard` for term ↔ definition.
- **decision-scenario** → `accordion` for "reveal the debrief"; `flashcard` for signal ↔ response.
- **policy-acceptable-use** → `accordion` for FAQ / optional detail; `tabs` for "Do vs Don't".
Any block may sit inside a **`band`** section for emphasis.

## Provenance
- **OBSERVED** (this session): all counts; mondrian `items:[]` + `backgroundType` distribution; the
  item shapes of accordion/tabs/flashcard/process — decoded live from the `-raw-` zips via
  `rise_import._decode`. The current handled/skipped split is from running `block_to_ir` over the corpus.
- **GENERATED** (proposed, not built): the `band` parameter + run-grouping; the four IR block shapes;
  the renderer/player/a11y approach and the optional `requireComplete` extension; the build order and
  template wiring. Nothing here is implemented yet.
