# Microlearning Authoring Guide — the contract I apply to every script

> **What this is.** The always-on rules for drafting a microlearning *script*
> (the §8 markdown the build consumes). Read this **plus** one archetype file from this folder,
> then produce a clean, conformant `## Microlearning` unit. This guide is the front-half analog of
> the §9.1 build template: it governs *what I write*; the IR blocks govern *how it's built*.
>
> **Golden rule:** the script must parse through `src/md_import.py` on the first try. Every rule
> below exists because the parser (or a learner) depends on it.

---

## 0. Instructional-design foundations — the pedagogy behind every choice

> A script isn't just a parseable file; it's one piece of a **curriculum** built for an **adult
> learner**. Structural validity (§2) is the floor — these foundations are the bar. They are **always
> on, regardless of archetype**, and they make every structural choice **defensible**: for any unit
> you should be able to say *"it's built this way because of X principle."* Record that reasoning in
> the **Design Rationale** (§4) — that's how a reviewer gets a straight answer to *"why is it
> structured like this?"*

These four lenses each govern a different tier of the work:

**0.1 Adult-learner posture — Knowles (cross-cutting + the archetype's frame).** Write for an adult
who is busy, experienced, and self-directed:
- **Relevance / need-to-know** — open by making the stake explicit: the problem this removes, what
  they'll be able to do. Never "here's a feature"; always "here's the pain this solves."
- **Build on prior experience** — assume competence; connect new material to what they already do,
  and invite them to relate it to their own work.
- **Problem-centered, not content-centered** — frame around a real task or decision the learner
  faces, not an abstract tour of the topic.
- **Self-direction & respect** — concise, no padding, no busywork; give the *why* so they can judge
  for themselves. Adults resent box-ticking.
- **Internal motivation** — appeal to doing the job better, mastery, autonomy — not compliance for
  its own sake.
  Each **archetype** states the specific adult-learner *pain point* it serves — read it and let it
  set the framing.

**0.2 Each unit addresses one need, completely — Merrill's First Principles (per microlearning).**
Every `## Microlearning` unit should: be **problem/task-centered** (anchored to a real task/question,
stated early) → **activate prior knowledge** (connect to what they already know before adding new) →
**demonstrate** (show it — example, walkthrough, worked case, visual — don't just tell) → **apply**
(the KC and any scenario are *practice*, not a quiz tax) → **integrate** (close by tying it back to
the job: when they'll use it, how it transfers).

**0.3 The within-unit teaching sequence — Gagné's Nine Events (per microlearning).** A well-built
unit rides this spine (the archetype slide-plans are designed to satisfy it): **1** gain attention
(hook) → **2** inform objectives (Slide 1) → **3** recall prior learning (connect to experience) →
**4** present the content → **5** provide guidance (examples / analogy / diagram) → **6** elicit
performance (the KC / scenario) → **7** provide feedback (both KC feedback paths) → **8** assess (the
KC outcome) → **9** enhance retention & transfer (recap + "where you'll use this"). **Don't label
these in the script** — they're the spine, not headings.

**0.4 The set must cover the curriculum — backward design (across units).** When the source is
decomposed into multiple units (curriculum mapping): derive the **full set of learning points** the
source supports; ensure **every point lands in some unit** — no gap, no silent drop; **sequence by
prerequisite** (earlier units enable later ones; never reference what hasn't been taught); **no
redundancy** (each unit earns its place — merge or re-scope overlaps). The **unit count is driven by
complete coverage of the source, never by the number of objectives listed** (one objective may span
several units; one unit may serve several objectives).
When a course has **more than one unit**, record the curriculum-level reasoning once in the **file
preamble** (above the first `## Microlearning`, where it's ignored by the parser) as a bold line:
`**Curriculum Rationale:** <why this set of units and this order — the coverage/sequence decision>`.
That answers *"why these units, in this order?"* the same way the per-unit Design Rationale answers
*"why is this unit built this way?"*

---

## 0b. Media & layout design principles — how content picks its treatment

§0 governs *what* to teach and *why*. This section governs *how each piece is presented* —
which block, how many columns, which media (or none). These are not style preferences; they are
grounded in the science of multimedia learning (Mayer's **Cognitive Theory of Multimedia
Learning**; Clark & Mayer, *e-Learning and the Science of Instruction*; **cognitive load
theory**). Every presentation choice should trace to one of these, and the unit's
**Design Rationale** (see §4) must name the presentation choices, not only the pedagogy.

### 0b.1 Media — does this content need a visual, and which kind? (Mayer: coherence, signaling, contiguity)

- **DEFAULT IS NONE.** Add a visual only when it *carries information* or *genuinely aids pacing*.
  Gratuitous "filler" decoration measurably **hurts** learning (coherence principle — extraneous
  material competes for working memory). Never add an image just to fill space or "look finished."
- **Screenshot** (`*Visual:* screenshot`) → software UI, "where do I click," "what does this look
  like." The information *is* the interface.
- **Video / GIF** (Build-Notes Media plan, not `*Visual:*`) → a sequence or motion that must be
  *seen performed* over time (a demo, an animation of a flow). A still cannot carry motion.
- **Diagram** (`*Visual:* diagram`) → structure, flow, relationships, architecture, before→after
  states. The value is the spatial arrangement.
- **Decorative** (`*Visual:* decorative`) → a purely emotional/pacing hook with no information to
  convey. Use sparingly, at a **section opener** only; decorative ⇒ no caption.
- One visual per idea, placed **adjacent to the text it supports** (spatial-contiguity principle).
- Do not narrate an on-screen image in prose word-for-word (redundancy principle) — let the caption
  and the figure carry it; the prose adds what the image cannot.

### 0b.2 Layout & density — which block, and single vs multi-column? (cognitive load, split-attention, item parallelism)

Match the *shape of the content* to the block. The engine's structures and what each is for:

- **Ordered steps / a how-to / a pipeline** → `*Process:*` (numbered, single-column).
- **2–3 things compared, A vs B, old vs new, options** → `*Comparison:*` (side-by-side panels).
- **Phases, a roadmap, dates, chronology** → `*Timeline:*`.
- **One big idea = a problem + a framework + goals** → `*Infographic:*` poster.
- **Parallel peer items** (features, roles, components, gates) → `*Cards:*` grid.
- **Real quantitative data from the source** → `*Chart:*` (numbers must appear LITERALLY in the
  source; cite a `source:` — never fabricate; see §2 / the build rejects a sourceless chart).
- **A "what would you do?" decision case** → `*Scenario:*` (situation + choices + feedback; mark the
  best `preferred`) — judgment practice, not a scored question.
- **A predict-then-reveal / paced reveal** → a `*Continue:*` gate (hides what follows until clicked).
- **The teaching substance itself** → ordinary **paragraphs**, single-column.

Density rule: use a **multi-column** block (comparison / cards) **only** when the items are *truly
parallel* and short enough to scan side-by-side. If they are sequential, dependent, or long, keep a
**single column** — forcing serial content into columns splits attention and raises load.

### 0b.3 Emphasis — note vs statement vs paragraph (signaling — emphasis only works when sparse)

- **Paragraph** = the actual teaching exposition (the substance carrying the content).
- **`*Note:*`** = a *secondary* aside set apart from the main flow — a caution, a tip, an exception,
  a "good to know." If it is core teaching, it belongs in a paragraph, not a note.
- **`*Statement:*`** = one memorable principle or takeaway you want to *land*. Use it **rarely**
  (≈ one per unit). Over-emphasis is self-defeating: if everything is highlighted, nothing is
  (signaling principle).

---

## 1. Output target

A single microlearning unit in the **§8 grammar**, ready to drop into a `.md` and build with
`python src/cli.py from-md <file>.md --which N`. One unit ≈ **one SCORM SCO** (a multi-unit course
is several units in one `.md`, each built separately and bundled in an your LMS Path).

## 2. Hard grammar rules (parser-enforced — break these and the build breaks)

- **Unit header:** exactly one `## Microlearning N: <Title>` per unit. Text before the first
  `## Microlearning` is preamble and is **ignored** — never put learner content there.
- **Slides:** `**Slide K — Heading**` on its own line. Use an **em dash** `—` (en dash `–` or hyphen
  `-` also parse, but standardize on em). Number slides sequentially from 1.
- **Body:** plain paragraphs (blank-line separated) · `- ` bullets · `1.` numbered lists ·
  GitHub pipe tables (`| a | b |` + `|---|---|`). Inline: `**bold**`, `*italic*`, `` `code` ``,
  `[text](https://…)`. **No headings inside a slide body** other than the `**Slide K —**` line.
- **Knowledge check:** a slide is a KC if its heading contains *"Knowledge Check"* **or** its body
  has `*Question:*`. Format:
  ```
  **Slide K — Knowledge Check**
  *Question:* <prompt>
  - A) <option>
  - B) <option>
  - C) <option>
  - D) <option>
  *Correct Answer:* C
  *Feedback — Correct:* <text>
  *Feedback — Incorrect:* <text>
  ```
  **≥2 options, exactly one correct.** KCs are **unscored** (completion-only) by default. A KC with
  zero parsed options is dropped — always use the `- A)` form.
- **Multi-select ("choose all that apply").** List **more than one** letter on the answer line —
  `*Correct Answer:* A, C` (also `A and C` / `A/C`) — and the check becomes multi-select: the options
  render as toggles the learner commits with a **Submit** button, scored **all-correct / none-wrong**
  (every right option picked, no wrong one). Use it only for genuine "select all" questions: mark
  **at least two** correct and **leave at least one wrong** (the lint rejects "all correct"). One
  letter = ordinary single-select. Both feedback lines work the same.
- **Retry (optional).** Add a course-level line `*Retry:* <N>` to give learners up to **N attempts**
  per KC: a wrong answer eliminates that choice and prompts "try again" until they're correct or
  attempts run out (then it locks + reveals). Omit it (or `0`) for one-shot. In a **graded** course
  the score reflects the **final** answer within the allowed attempts.
- **Graded (scored) courses — opt-in.** Add a line `*Graded:* pass <N>` anywhere in the file (the
  preamble is the natural home; it applies to every microlearning in the file). Then every KC counts
  toward a percent score, the learner must reach `<N>`% to be marked **passed** (else **failed**), and
  each KC is reported to the LMS as a `cmi.interactions` record. Omit the line for the default
  completion-only behavior. (Format is chosen at *build* time, not in the script:
  `--format scorm` (default) or `--format cmi5`; under cmi5 the same pass mark becomes the AU
  `masteryScore` and pass/fail is reported as xAPI `passed`/`failed` statements.)
- **Slide 1 is ALWAYS Learning Objectives, with a visual.** Every unit opens with
  `**Slide 1 — Learning Objectives**`, a `*Visual:*` line, and an `*Objectives:*` block — a short
  "you will be able to…" list (3–5 learner-facing outcomes). These mirror the formal objectives in
  Build Notes. *(This is a required standard — never omit the objectives slide.)* Grammar:
  ```
  *Objectives:* After this lesson, you will be able to:
  - Identify the three transfer types
  - Decide which queue a request belongs in
  - Escalate an urgent case correctly
  ```
  The text after the marker is an optional lead-in (a sensible default is supplied if you omit it);
  each `- ` bullet is one outcome. Start outcomes with an observable verb (identify, decide, apply —
  not "understand"). Use `*Objectives:*` only for the Slide-1 outcomes list, not for ordinary bullets.
- **In-slide visuals use the `*Visual:*` directive** (parser-supported — parallel to `*Question:*`):
  ```
  *Visual:* <type> · <description / alt text> · slot: `<asset-filename>`
  ```
  - `<type>` = `screenshot` · `graphic` · `diagram` · `photo` · `decorative` (a styling hint;
    `decorative` ⇒ no caption). The build emits an `image` block at the directive's position
    (put it right under the slide heading for an image-above-text slide).
  - `<slot>` = the asset's filename in the **labelled-asset folder**. Two sources:
    **Figma-exported `.svg`** (decorative / diagram elements) and **screenshots / graphics** (`.png`/
    `.jpg`). The build resolves the slot by name (`--images <folder>`); if the file isn't there yet,
    the reference stays `assets/<slot>` until it's supplied (slot-naming, §10).
  - Use the §10 naming convention: `<slug>_<slide#>_<role>.<ext>` (e.g. `mbr_3_screen.png`,
    `mbr_1_objectives.svg`). One `*Visual:*` per slide; for two images use two slides or a follow-up.
  - **Video / audio are NOT `*Visual:*`** — they stay in the Build-Notes Media plan (they build to
    `video`/`audio` IR blocks). `*Visual:*` is images/SVG only.
- **Data → `*Chart:*` (parser-supported).** When the source has REAL quantitative data that a chart
  conveys better than a table or prose, emit a chart. Grammar: a `*Chart:*` line naming the type,
  then `key: value` lines until a blank line.
  ```
  *Chart:* bar            (bar | line | pie | stackedBar | groupedBar; column/donut/grouped also accepted)
  title: Quarterly admits
  categories: Q1, Q2, Q3, Q4
  series: Admits = 120, 145, 130, 160
  series: Discharges = 110, 140, 125, 155     (repeat `series:` for more; omit the `Name =` for one unnamed series)
  yLabel: Patients
  xLabel: Quarter
  source: <REQUIRED — the source doc/table these numbers came from>
  ```
  - **Numbers MUST be literal source figures** — never estimate, extrapolate, or invent. Values use
    NO thousands separators (comma is the delimiter): write `1200`, not `1,200`. Use `null` for a gap.
  - **`source:` is mandatory.** A chart without it is **rejected by the build** (no-invented-metrics
    rule). `pie` uses exactly one series; bar/line/stacked/grouped take one or more.
- **Overview poster → `*Infographic:*` (parser-supported).** A poster-style summary block — a
  challenge column, a framework column of numbered cards, a goals strip, and a footer. It renders as
  a flowing on-brand HTML section in the course AND, with the **same content**, as the `infographic`
  slide layout (`./build slide --layout infographic`). Use it for a section/topic overview, not for
  body teaching. Grammar (flat `:::` fences; a lone `:::` closes the whole block):
  ```
  *Infographic:* Initiative or Topic Title
  subtitle: One-line tagline.
  footer: One line summarizing the outcome.
  ::: left
  heading: THE CHALLENGE
  intro: Summarize the problem this addresses:
  callout: What happens if this isn't solved.
  - Key problem one — short supporting detail
  - Key problem two — short supporting detail
  :::
  ::: right
  heading: FRAMEWORK OR APPROACH
  sublabel: 4 COMPONENTS
  :::
  ::: card
  num: 1
  title: Component one
  body: What it does, in one short sentence.
  accent: primary
  :::
  ::: goals
  label: OUR GOALS
  :::
  ::: goal
  title: Goal one
  body: Short description of the goal.
  accent: primary
  :::
  ```
  `accent` is a brand role (`primary|secondary|tertiary|dark`; omit to auto-cycle). Repeat `::: card`
  and `::: goal` per item. Every section is optional — drop the fences you don't need.
- **Decision practice → `*Scenario:*` (parser-supported).** A "what would you do?" case: one or more
  scenes, each a situation plus response choices with feedback, with the best choice marked
  `preferred`. It renders as a LINEAR decision walk-through (every scene shown, the preferred path
  marked) — use it for judgment/decision practice (a natural fit for the **decision-scenario**
  archetype), NOT as a scored question (use a KC for that). Grammar (`::: scene` fences; a lone `:::`
  closes the block):
  ```
  *Scenario:*
  ::: scene
  title: Urgent ICU transfer
  A nurse calls about an urgent ICU transfer with no bed assigned yet. What do you do first?
  - Accept and start the bed assignment · preferred · feedback: Right — for an urgent case, secure the bed first.
  - Ask them to submit a written request · feedback: Too slow; urgent cases can't wait on paperwork.
  :::
  ```
  Each scene: an optional `title:`, prose narrative lines (the situation / the decision prompt), then
  `- ` response lines. On a response, append `· preferred` to mark the model answer and
  `· feedback: <text>` for its coaching. **Mark exactly one `preferred` response per scene** (the lint
  flags a scene with choices but no preferred). Repeat `::: scene` for a multi-step case.
- **Progressive reveal → `*Continue:*` (parser-supported).** Insert `*Continue:* <button label>` to
  GATE the rest of the unit: everything after the marker is hidden until the learner clicks the
  button. Use it deliberately — to make learners commit before a reveal (predict-then-confirm) or to
  pace a dense unit — never as filler. Omit the label for a default **CONTINUE**; multiple gates give
  a step-by-step reveal.
  ```
  Predict what the system does before you continue.
  *Continue:* Reveal the answer
  Here's what actually happens: …
  ```
- **Author-meta block — ORDERING IS LOAD-BEARING.** The build cuts everything from the first line
  that starts `**Articulate Build Notes` or `**Sources`. So:
  - The meta block **must open with** `**Articulate Build Notes:**`.
  - **Never** place `Subject` / `Estimated Length` / `Learning Objectives` / `Confidence` *above*
    that marker — anything above it **leaks to the learner**. Put all meta **under** the marker.

## 3. Two parser facts to write around

- **Both feedback paths reach the learner.** `*Feedback — Correct:*` and `*Feedback — Incorrect:*`
  are both captured; the player shows whichever matches the answer the learner picked. Always write
  both.
- **In-slide images/media are NOT authored in the markdown.** `md_import` does **not** parse
  `![]()`; only the cover/hero is consumed (`--hero`). When a slide needs a visual (screenshot,
  demo GIF, video, diagram), **do not** write a markdown image. Instead record it under
  **Build Notes** as a **VISUAL line** (see §4) — Segment C inserts the real `image`/`video`/`audio`/
  `embed` block into the IR by slot-name during the build.
- **Coming-soon block type — do NOT author it.** `headingParagraph` renders and validates but has
  **no authoring grammar yet** — it is produced only by the docx importer (import-only stub). The
  lint rejects a `*HeadingParagraph:*` marker so it can't silently degrade. (`scenario` and
  `continue` are now fully authorable — see their grammar in §2.)

## 4. The Build-Notes block (under the cut marker)

```
**Articulate Build Notes:**
Subject: <one line>
Estimated Length: <e.g. 11 min>
Learning Objectives:
- <objective — traceable to a Context-Pack objective or gap>
Confidence Score: <High | Medium | Low — flag any slide built on thin sourcing>
Design Rationale: <WHY this unit is structured the way it is, named to the §0 principles so the
  choice is defensible. 1–3 short lines. e.g. "Problem-centered open (Knowles need-to-know);
  demonstrate→apply per Merrill; KC placed at Gagné event 6 (elicit performance), debrief at 9
  (transfer). Scoped to one learning point per backward-design coverage map.">
Visuals / Media plan:
- Slide 4: VIDEO (file) — demo of <X>; slot `<course-slug>_4_demo.mp4`; requireComplete: true
- Slide 6: IMAGE — <description>; slot `<course-slug>_6_diagram.png`
Build Notes: <anything the builder/reviewer should know>

**Sources & Further Reading:**
- <source the prose is drawn from — every claim must trace to one>
```

- **Visuals/Media plan** is the bridge to the new media blocks. Use the §10 slug naming
  (`<slug>_<n>_<role>.<ext>`) so Segment C resolves the asset with no manual mapping. Mark
  `requireComplete: true` only for **self-hosted** `video file` / `audio` you want to gate completion
  on (embeds can't be gated — see Segment D.0).

## 5. Voice, level & length

- **Voice:** clear, direct, **second person ("you")**, **active voice**, healthcare-
  operations context, concrete product examples. No hype, no filler, no "in today's fast-paced
  world." Plain professional language; define a term the first time it appears.
- **Length / time budget (the 10–15-min rule):** ~**900–1,500 body words + 2–4 KCs** per unit
  (`unit_minutes ≈ body_words/130 + 0.75·KCs + 0.25·images`). That's typically **5–8 content slides
  + 1–2 KCs**. If a topic won't fit, **split it into two units** — don't overrun.
- **Grounding:** every slide's prose traces to a **source segment** *and* serves the unit's
  **objective/gap**. Do **not** invent product behavior — this trains real software; fabrication is a
  correctness defect. If sourcing is thin, lower the Confidence Score and flag the slide.
- **Accent/color:** don't set colors in the script. Brand styling is applied at build (renderer
  default = the brand accent (the active brand sets the hex)).

## 6. How to use a template

1. Read this guide + the chosen archetype file (`concept-explainer.md`, `software-procedure.md`,
   `decision-scenario.md`, or `policy-acceptable-use.md`).
2. Follow the archetype's **slide-role plan**; fill each `{{PLACEHOLDER}}` with grounded content.
3. **Strip all `<!-- guidance -->` comments and the role labels** from the final output — they're
   for me, not the learner.
4. Self-check against §2 before returning: parses? meta under the marker? KC well-formed? in budget?
