# Course IR (Intermediate Representation) — schema

The IR is the **contract** between every stage. Importers (Rise, .docx) emit IR; the
renderer + packager consume it. One IR JSON file + an `assets/` folder = a complete course.

```jsonc
{
  "schema": "course-ir/v1",
  "id": "managing-bed-requests",        // slug; used for filenames + SCORM identifier
  "title": "Managing Bed Requests",
  "locale": "en",                        // "en" | "en-GB"
  "accent": "#3B82F6",                   // course accent (defaults to the brand accent)
  "hero": {                              // optional cover
    "image": "assets/hero.jpg",
    "title": "Managing Bed Requests",
    "subtitle": ""
  },
  "blocks": [ /* ordered list, see below */ ]
}
```

## Course-level directives (optional)

Set anywhere in the source `.md`; each maps to a top-level IR key: `*Graded:* pass <N>`
(scored course → `graded`/`passingScore`), `*Retry:* <N>` (`retry`), `*Gate:* on|off`
(`gateCompletion`), `*Preset:* <key>` (`preset`), and `*Points:* on` (gamification #3 →
`xp` = `{weights, tiers}`). `*Points:*` turns on a points/XP **motivational** overlay: a
topbar HUD that auto-derives an XP total (each scorable block weighted by category
check/question/game, partial-credit blocks pro-rata) and a level tier. It is **purely
cosmetic** — it never affects the graded score, the completion gate, or the LMS score, and
it re-derives from the same block state already in suspend_data (so it survives resume with
no extra state). Optional weight overrides ride the same line: `*Points:* on check=10 question=15 game=25`.

`*Celebrate:* on` (gamification #6 → `celebrate` = `{pass, level, complete}`, alias `*Confetti:*`)
turns on a **confetti** celebration: a zero-dependency canvas burst the player fires at the course's
win moments — passing a graded quiz (`pass`), an XP tier level-up (`level`), and reaching 100%
completion (`complete`). Also **purely cosmetic** (never affects the score, gate, or LMS record); the
player skips it under `prefers-reduced-motion` and creates the canvas ad hoc (no persistent DOM, no
suspend state — each one-shot fires once and is suppressed on resume). `on` enables all three; tune
per-trigger with `pass=/level=/complete=` (e.g. `*Celebrate:* on level=off`).

## Block types (Tier 1 + Tier 2)

Every block is `{ "type": "...", ...fields, "gated": false }`.
`gated: true` means the block is hidden until the preceding `continue` block is clicked
(the renderer wraps gated runs in a reveal container).

| type | fields | notes |
|---|---|---|
| `heading`     | `level` (1–3), `html` | section title; `level:1/2` render as a navy band |
| `paragraph`   | `html` | body copy (sanitized inline HTML: strong/em/a/ul/li kept) |
| `headingParagraph` | `level`, `headingHtml`, `html` | combined heading + body. **Coming soon — import-only:** no authoring grammar; produced by the Rise/docx importers only |
| `image`       | `src`, `alt`, `caption`, `variant` (`full`/`hero`) | full-width figure |
| `imageText`   | `src`, `alt`, `html`, `side` (`left`/`right`) | image beside text |
| `video`       | `mode` (`file`/`embed`), `src`, `poster`, `captions`, `captionsLang`, `caption`, `aspect`, `title`, `requireComplete` | `file` = self-hosted `<video>` bundled in the zip (+ `<track>` captions); `embed` = streamed responsive `<iframe>` |
| `audio`       | `src`, `caption`, `transcript`, `requireComplete` | `<audio>` + optional collapsible transcript |
| `embed`       | `src`, `title`, `aspect`, `height`, `caption` | generic interactive `<iframe>` (H5P / sim / widget) |
| `note`        | `html` | callout box (accent left-border) |
| `statement`   | `html` | large centered emphasis line |
| `list`        | `ordered` (bool), `items` ([html,…]) | numbered/bulleted |
| `table`       | `html` | passthrough `<table>` HTML (sanitized) |
| `divider`     | — | spacer rule |
| `transition`  | `color` (green/gold/dark/blue/teal), `band` (top/bottom) | brand "ribbon" wave divider; reusable, color-swappable. Renders a pre-cropped band from `brand/transitions/<color>-<band>.png` (`green`=brand-accent default). Decorative (`aria-hidden`). md grammar: `*Transition:* <color> <band>` |
| `continue`    | `text` (default "CONTINUE") | gate; reveals the next gated run (progressive reveal). md: `*Continue:* <button label>` — every block after it (in the unit) is hidden until clicked |
| `objectives`  | `intro?` (lead-in line), `items` ([html,…]) | learning-objectives list ("you will be able to…"). md: `*Objectives:* [intro]` + `- ` bullets |
| `knowledgeCheck` | `prompt`, `multi` (bool), `options` [{`html`,`correct`}], `feedback`, `feedbackIncorrect` | interactive; **unscored** by default, scored under `*Graded:*`. `multi` (multiple `*Correct Answer:*` letters) → toggle + Submit, scored all-correct/none-wrong |
| `quote`       | `html` (quote text), `attribution`, `src` (optional bg image) | pull-quote; with `src` the image is a tinted full-bleed background. md: `*Quote:* <text> · by: <name> · slot:`bg`` |
| `accordion`   | `entries` [{`title`, `html`, `src?`}] | native `<details>` disclosure (a11y for free, no JS). md: `*Accordion:*` + `::: item` (title:/body:/slot:) groups, lone `:::` closes |
| `process`     | `entries` [{`title`, `html`, `src?`, `kind?`}] | numbered ordered-step list (static, accessible). md: `*Process:*` + `::: step` groups |
| `flashcard`   | `entries` [{`frontHtml`, `frontSrc?`, `backHtml`, `backSrc?`}] | CSS 3D-flip cards; click/Enter/Space toggles `aria-pressed`, both faces in DOM, reduced-motion safe. Non-gating. md: `*Flashcard:*` + `::: card` (front:/back:/frontslot:/backslot:) |
| `categorize`  | `buckets` [{`id`, `title`}], `pool` [{`html`, `target`}], `prompt?`, `feedback`, `feedbackIncorrect` | sort each pool item into its correct bucket. Accessible **select-to-place** base (a Check button validates + locks); drag is a future enhancement. **Gates completion** once checked. md: `*Categorize:*` + `bucket:`/`item: <text> -> <bucket>` lines, lone `:::` closes |
| `dragDrop`    | `zones` [{`id`, `title`, `x?`, `y?`}], `pool` [{`html`, `target`}], `src?`, `prompt?`, `feedback`, `feedbackIncorrect`, `objective?` | drag each label onto its correct zone. Accessible **select-to-place** base ("Place in…" per label) IS the source of truth; native pointer drag just sets it. Optional background diagram (`src`) with zones positioned at `x`/`y` percent (drag-label-on-diagram). Check validates + locks with **partial credit** ("placed N of M"). **Gates completion** once checked. md: `*DragDrop:*` + optional `image: <src>`, `zone: <title> [@ x,y]`, `item: <label> -> <zone>` lines, lone `:::` closes |
| `wordSearch`  | `grid` [[char,…],…], `words` [{`text`, `clue?`, `r`, `c`, `dr`, `dc`, `dir`}], `size`, `prompt?`, `feedback`, `feedbackIncorrect`, `objective?` | find hidden words in a letter grid. The grid is GENERATED at build time (`src/wordsearch.py`) from the authored term list, so a course builds byte-identically. Learner drags across the letters (or clicks first + last letter — keyboard/touch accessible); a Check button validates + locks with **partial credit** ("found N of M"). **Gates completion** once checked. md: `*WordSearch:*` + `term: <WORD> [\| <clue>]` lines, lone `:::` closes |
| `crossword`   | `grid` [[char\|null,…],…], `words` [{`text`, `clue?`, `r`, `c`, `dir` (across\|down), `num`}], `rows`, `cols`, `prompt?`, `feedback`, `feedbackIncorrect`, `objective?` | interlocking numbered crossword. The layout is GENERATED at build time (`src/crossword.py`) from the authored clue/answer pairs (a blocked cell is `null`), so a course builds byte-identically; an answer that can't interlock is dropped. White cells are single-letter text inputs (keyboard/touch accessible); a Check button validates + locks with **partial credit** ("solved N of M"). **Gates completion** once checked. md: `*Crossword:*` + `word: <ANSWER> [\| <clue>]` lines, lone `:::` closes |
| `gameShow`    | `slices` [{`q`, `options` [str,…], `answer` (correct index)}], `prompt?`, `feedback`, `feedbackIncorrect`, `objective?` | spin-the-wheel review game. Each authored MCQ becomes one wheel slice; options are shuffled at build time (`src/gameshow.py`) so `answer` is fixed and resume-stable. The learner spins (animated wheel + a keyboard/reduced-motion-safe Spin button that lands on the next slice), answers the drawn question, then spins again. Scored with **partial credit** ("answered N of M correctly"). **Gates completion** once every slice is answered. md: `*GameShow:*` + repeated `q: <stem>` / `a: <correct>` / `option: <distractor>` lines (a new `q:` starts the next slice), lone `:::` closes |
| `quizBoard`   | `board` [{`name`, `tiles` [{`q`, `options` [str,…], `answer` (correct index), `value`}]}], `cols`, `rows`, `prompt?`, `feedback`, `feedbackIncorrect`, `objective?` | Jeopardy-style category board. Each category is a column; its authored MCQs become tiles numbered top-down with an **escalating point value** (row 1 lowest). Options are shuffled at build time (`src/quizboard.py`, reusing `src/gameshow.py`) so `answer` is fixed and resume-stable; a question missing its stem/answer/every distractor is dropped, an empty column is dropped. The learner picks any tile, answers its MCQ (keyboard-navigable buttons), and the tile flips correct/incorrect. Scored with **weighted partial credit** ("scored N of M points"). **Gates completion** once every tile is answered. md: `*QuizBoard:*` (aliases `*Jeopardy:*`/`*Board:*`) + repeated `category: <name>` then `q:`/`a:`/`option:` groups (a new `q:` starts the next tile, a new `category:` the next column), lone `:::` closes |
| `speedStreak` | `rounds` [{`q`, `options` [str,…], `answer` (correct index)}], `timer?` (seconds), `prompt?`, `feedback`, `feedbackIncorrect`, `objective?` | fast one-at-a-time MCQ run. The learner answers questions in sequence, building a **consecutive-correct streak**; options are shuffled at build time (`src/speedstreak.py`, reusing `src/gameshow.py`) so `answer` is fixed and resume-stable. An optional `timer` (per-question countdown, whole seconds) adds a **cosmetic** speed bonus + combo score — correctness and the graded score have NO time limit, so it stays accessible (no WCAG 2.2.1 timing problem) and deterministic. Scored with **partial credit** ("answered N of M correctly"); the streak/combo is motivational only, never part of the grade. **Gates completion** once every round is answered. md: `*SpeedStreak:*` (aliases `*RapidFire:*`/`*Streak:*`) + optional `timer: N`, then repeated `q: <stem>` / `a: <correct>` / `option: <distractor>` lines (a new `q:` starts the next round), lone `:::` closes |
| `matching`    | `pairs` [{`id`, `left`, `right`}], `prompt?`, `feedback`, `feedbackIncorrect` | match each left item to its correct right partner (a select of every right, shown reversed). Check validates + locks with **partial credit** ("matched N of M"). **Gates completion** once checked. md: `*Matching:*` + `pair: <left> -> <right>` lines, lone `:::` closes |
| `sequence`    | `steps` [{`id`, `html`}] (array order = correct order), `prompt?`, `feedback`, `feedbackIncorrect` | put the steps in the correct order — each step (shown reversed) carries a position select 1..N. Check validates + locks with **partial credit** ("placed N of M"). **Gates completion** once checked. md: `*Sequence:*` (or `*Order:*`) + `step: <text>` lines in correct order, lone `:::` closes |
| `fillBlank`   | `blanks` [{`id`, `before`, `after`, `answers` []}], `prompt?`, `feedback`, `feedbackIncorrect` | fill-in-the-blank text entry — each blank is a text input between `before`/`after`, graded against an accept-list with **lenient** matching (trim / collapse whitespace / case-insensitive). Check validates + locks with **partial credit** ("answered N of M"). **Gates completion** once checked. md: `*FillBlank:*` (or `*Fill:*`) + `blank: <text with ___> -> <answer> \| <alt>` lines, lone `:::` closes |
| `questionBank`| `draw` (int), `questions` [ &lt;question block&gt; ], `objective?` | randomized question POOL — holds `knowledgeCheck`/`matching`/`sequence`/`fillBlank` children; the player draws `draw` of them per attempt (C5), shuffles KC option order, and persists the drawn set in suspend_data (resume-stable). Inside a graded `*Section:*` every drawn child rolls into the section subscore. md: `*Bank:* draw <N>` + question children, `*Bank:* end` (or lone `:::`) closes |
| `scenario`    | `scenes` [{`title`, `html`, `responses` [{`html`, `feedback`, `preferred?`}]}] | decision walk-through — each scene's narrative + response options with feedback (preferred path highlighted). Renders **linearly** (true branching navigation is a future track). md: `*Scenario:*` + `::: scene` (title:/prose/`- <response> · preferred · feedback:`) |
| `reflection`  | `prompt?`, `model?` (HTML), `criteria?` [str…] | free-text / open-response reflection — **non-graded, completion-only** (no `objective`, never in the graded score, pass gate, or XP). The learner types a response into a textarea; on submit the `model` answer + `criteria` rubric **reveal** for self-assessment. There is no runtime AI scorer (SCORM runs offline) — the `model`/`criteria` are authored at build time (the LLM writes them from the course content). **Gates completion** once answered. md: `*Reflection:*` (aliases `*Reflect:*`/`*OpenResponse:*`/`*FreeText:*`) `<prompt>` + optional `model:` and `criteria:` lines, lone `:::` closes |
| `button`      | `label`, `action` (`link`/`modal`), `href` (link) or `modal` (panel), `buttonVariant` (`primary`/`secondary`), `arrow` (bool) | CTA: external link or modal trigger. md: `*Button:*` + `::: modal` fence for the modal variant |
| `cardGrid`    | `cards` [{`title`, `teaser`, `icon`, `href?`, `modal?`}], `columns` (1–4), `requireOpen` (bool) | card grid; cards may be plain, link, or modal-opening. `requireOpen` gates completion until every modal card is opened. md: `*Cards:*` + `::: card` groups |
| `timeline`    | `milestones` [{`title`, `html`, `accent?`}], `accent?` | ordered roadmap on a vertical brand axis (HTML parity with the `timeline` slide layout). md: `*Timeline:*` + `::: milestone` groups |
| `comparison`  | `panels` [{`heading`, `sublabel?`, `items` [html…], `callout?`, `accent?`}], `accent?` | 2–3 side-by-side panels (old-vs-new / A-B-C). md: `*Comparison:*` + `::: panel` groups |
| `chart`       | `chart` (`bar`/`line`/`pie`/`stackedBar`/`groupedBar`), `categories` [str…], `series` [{`name`, `data` [num/null…]}], `xLabel?`, `yLabel?`, **`source` (REQUIRED)**, `takeaway?` | engine-drawn inline SVG (no JS, brand-colored, sr-only data-table). `source:` is mandatory — the lint rejects a sourceless chart (no-invented-metrics). `takeaway:` is an optional one-line insight rendered with the chart. md: `*Chart:*` + `categories:`/`series: Name = a,b`/`source:`/`takeaway:` lines |
| `infographic` | `infographic` {`title`, `subtitle?`, `left`{`heading`,`intro`,`items`}, `right?`/`cards?`, `goals?`, `footer?`} | poster-style overview as a flowing HTML section. Consumes the **same content object** as the `infographic` slide layout (`b["infographic"]` == slide content). md: `*Infographic:*` + `::: left/right/card/goals/goal` fences |
| `sectionStart`| `color` (green/gold/dark/blue/teal) | opens a colored section band (wraps the blocks until `sectionEnd`). md: `*Section:* <color>` |
| `sectionEnd`  | — | closes the current colored section. md: `*Section:* end` |

> **Fence convention (shared with `cardGrid`):** inside `*Accordion:*`/`*Process:*`/`*Flashcard:*`, each entry opens with `::: item`/`::: step`/`::: card` and a **single lone `:::` closes the whole block** — there is **no per-entry closer**. (Adding one closes the block early — the known cardGrid gotcha.)

## Importer responsibilities
- Resolve Rise media references → a real filename copied into `assets/`.
- Sanitize block HTML: drop `data-editor-id`, unwrap the editor `<div>`, strip
  Rise-theme-coupled inline `color`/`font-size` styles (our brand CSS owns those),
  keep semantic tags (`strong`, `em`, `a`, `ul`/`ol`/`li`, `table`, `br`).
- Carry the course accent from the Rise `theme.colorAccent` if present (else the brand accent).

## Renderer responsibilities
- Emit one self-contained HTML page (no external CDN), link `brand/tokens.css`,
  `player/player.css`, `player/player.js`.
- Wrap each run of blocks after a `continue` (until the next `continue`) in a
  `.nv-gated` container so the player can reveal it.

## Media blocks (multi-media support)
- **Self-hosted** (`video mode:"file"`, `audio`): `src` points at an `assets/<file>` bundled in
  the zip — fully offline, no CDN. `video file` may carry a `poster` and a `.vtt` `captions` track
  (508/WCAG). `audio` may carry a `transcript` (collapsible).
- **Embedded/streamed** (`video mode:"embed"`, `embed`): `src` is an `https` URL rendered in a
  responsive `<iframe>` (`aspect` `W:H`, default 16:9; `embed` may pin `height` px). Depends on the
  host being reachable from the LMS.
- **Completion gating:** `requireComplete:true` adds the media to the course-completion tally — the
  player marks it done on the media `ended` event. **Honored only for self-hosted `video file` /
  `audio`** (the `ended` event is observable). It is **ignored for `embed` and `video embed`** —
  cross-origin iframes don't expose playback state. The renderer emits `data-require="1"` only on the
  observable cases.

## Packager responsibilities
- Wrap the rendered course dir in a SCORM 1.2 `imsmanifest.xml` (+ 2004 supported at runtime).
- Zip with `index.html` at the SCO root; **every file under the course dir** (brand, player, and all
  bundled media in `assets/`) is listed as a `<file>` under the single `sco` resource.
- **Completion-only, unscored:** the manifest carries **no `masteryscore`** (a mastery score with no
  reported `cmi.core.score` strands some LMSs at `incomplete`). The player drives
  `lesson_status`/`completion_status` → `completed`.
