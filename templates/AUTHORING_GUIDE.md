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

**Pick the activity by LEARNING OBJECTIVE first, engagement second.** Each interactive block is a
general activity pattern, not just a "game" — choose the one whose interaction matches what the learner
must *do* with the knowledge:

| When the learner must… | Reach for |
|---|---|
| **Label** parts of a diagram, screenshot, or interface | `*DragDrop:*` (add `image:` + `zone: … @ x,y` to place labels on the picture) |
| **Classify / sort** many items into groups, bins, or queues | `*Categorize:*` |
| **Order** the steps of a procedure or a chronology | `*Sequence:*` |
| **Associate** pairs (term↔definition, cause↔effect, role↔tool) | `*Matching:*` |
| **Recall a term in context** (complete a sentence or policy) | `*FillBlank:*` |
| **Recall a term from its definition** | `*Crossword:*` |
| **Prime / pre-expose** key vocabulary before you teach it (recognition only, low stakes) | `*WordSearch:*` |
| **Review across 2–4 topics**, learner-navigated | `*QuizBoard:*` |
| **Practise retrieval** with questions in randomized order | `*GameShow:*` |
| **Build fluency** on facts that must become fast and automatic | `*SpeedStreak:*` |
| **Decide** — practise a judgment call with feedback | `*Scenario:*` |
| **Reflect** — apply the lesson to their own experience in their own words (open-ended, no single right answer) | `*Reflection:*` |
| **Self-check** understanding at a checkpoint | a Knowledge Check (`*Question:*`) |

The "game" blocks (`*GameShow:*`/`*QuizBoard:*`/`*SpeedStreak:*`/`*Crossword:*`/`*WordSearch:*`) are
review, recall, and fluency activities with an engaging skin — reach for them when the objective fits,
not merely for novelty. Full grammar for every block is in §2.

Match the *shape of the content* to the block. The engine's structures and what each is for, grouped
by the **learning action** the learner performs (interactive activities) and by presentation role
(everything else). Within each group, pick by objective first (§0b.2 table above):

**Interactive activities — grouped by what the learner DOES:**

- **Label** — put names on the parts of a diagram / screenshot / interface → `*DragDrop:*` (drag each
  label onto its target; add an `image:` + positioned `zone:`s to label a picture) — the only block that
  puts labels on an image.
- **Classify** — sort / triage items into groups → `*Categorize:*` (a pool of items dragged into 2–4
  labeled buckets, many per bucket; partial credit) — the tool for grouping decisions.
- **Order** — put steps or events in the right sequence → `*Sequence:*` (the learner arranges shuffled
  steps; partial credit) — use when the *order* is the learning.
- **Associate** — pair things that go together (term↔definition, cause↔effect, role↔tool) → `*Matching:*`
  (dropdown pairing; partial credit).
- **Recall** — retrieve a term or fact:
  - **in context** → `*FillBlank:*` (type the missing word into a sentence or policy; lenient matching,
    partial credit) — harder and more durable than picking an option.
  - **from its definition** → `*Crossword:*` (an interlocking crossword from your clue/answer pairs) — a
    recall activity; the clue does the teaching.
  - **prime / pre-expose** key vocabulary before teaching it → `*WordSearch:*` (a find-the-word puzzle
    built from a short term list) — recognition-only, low stakes: a warm-up, *not* an assessment (test
    terms with `*Crossword:*` or `*FillBlank:*`).
- **Review formats** — energize a multi-question review:
  - **randomized retrieval practice** → `*GameShow:*` (a spin-the-wheel quiz from your
    question/answer/option sets) — the wheel draws questions unpredictably (a real retrieval-practice
    effect); a lively end-of-unit review; the build shuffles options.
  - **learner-navigated across 2–4 topics** → `*QuizBoard:*` (a Jeopardy-style category board — pick a
    tile, answer its MCQ, higher rows worth more points) — a structured multi-topic review; the
    competition framing is optional. Best when your questions group into 2–4 named categories.
  - **fluency on facts that must be fast and automatic** → `*SpeedStreak:*` (questions answered one at a
    time, building a consecutive-correct streak, with an optional cosmetic timer) — an energetic fluency
    drill; best for a short set of quick recall questions.
- **Decide** — practise a judgment call → `*Scenario:*` (situation + choices + feedback; mark the best
  `preferred`) — judgment practice, not a scored question.
- **Reflect** — have the learner apply the lesson to their own experience in their own words →
  `*Reflection:*` (an open-response textarea; on submit a `model:` answer + `criteria:` rubric reveal so
  the learner self-assesses) — **non-graded, completion-only**. Use for a metacognitive checkpoint
  ("How would you handle X on your unit?", "What will you do differently?") where there is no single
  right answer, so it can't be a `*Question:*`. There is no runtime AI scorer (a published course runs
  offline), so you **author the `model:` answer and `criteria:` yourself** — write the response a strong
  learner would give, and the 2–4 things a good answer includes, so the learner has a concrete benchmark.

**Presentation & pacing formats — how the teaching substance is shown:**

- **Ordered steps / a how-to / a pipeline** → `*Process:*` (numbered, single-column).
- **2–3 things compared, A vs B, old vs new, options** → `*Comparison:*` (side-by-side panels).
- **Phases, a roadmap, dates, chronology** → `*Timeline:*`.
- **One big idea = a problem + a framework + goals** → `*Infographic:*` poster.
- **Parallel peer items** (features, roles, components, gates) → `*Cards:*` grid.
- **Real quantitative data from the source** → `*Chart:*` (numbers must appear LITERALLY in the
  source; cite a `source:` — never fabricate; see §2 / the build rejects a sourceless chart).
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

### 2.1 Course-level & structural rules

> The unit skeleton and course-wide directives every script obeys, whatever activities it uses.


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
- **Points / XP overlay (optional).** Add a course-level line `*Points:* on` to turn on a
  **motivational** points-and-levels HUD in the topbar. Every scorable block (knowledge check,
  categorize, matching, sequencing, fill-in-the-blank, drag-drop, word search, crossword)
  automatically earns points — no per-block authoring — weighted by how demanding it is
  (checks < questions < games), with partial-credit blocks awarding a pro-rata share. As points
  accrue the learner climbs level tiers (Novice → Proficient → Skilled → Expert). It is **purely
  cosmetic**: it never changes the graded score, the pass/fail result, the completion gate, or
  what's reported to the LMS — so you can add it to any course, graded or not. Omit the line for
  no overlay. To weight categories differently, append overrides on the same line:
  `*Points:* on check=10 question=15 game=25`. Prefer turning this on for courses that have at
  least a few interactive/quiz blocks (it stays hidden when a course has nothing scorable).
- **Confetti celebration (optional).** Add a course-level line `*Celebrate:* on` to fire a brief
  **confetti burst** at the course's win moments: passing a graded quiz, leveling up an XP tier
  (when `*Points:*` is on), and reaching 100% completion. Like the points overlay it is **purely
  cosmetic** — it never changes the score, the pass/fail result, the completion gate, or what's
  reported to the LMS — and it automatically respects the learner's reduced-motion setting (no
  burst then). `*Celebrate:* on` enables all three moments; tune them individually with
  `pass=/level=/complete=`, e.g. `*Celebrate:* on level=off` for pass + completion only. Omit the
  line for no confetti. Alias: `*Confetti:*`. A natural pairing with `*Points:*` on upbeat courses.
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
### 2.2 Presentation & pacing blocks

> How the teaching substance itself is shown, and how the unit is paced.

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
  takeaway: <OPTIONAL — one plain-language sentence: the single most important insight>
  ```
  - **Numbers MUST be literal source figures** — never estimate, extrapolate, or invent. Values use
    NO thousands separators (comma is the delimiter): write `1200`, not `1,200`. Use `null` for a gap.
  - **`source:` is mandatory.** A chart without it is **rejected by the build** (no-invented-metrics
    rule). `pie` uses exactly one series; bar/line/stacked/grouped take one or more.
  - **`takeaway:` is optional** — one plain-language sentence stating the chart's "so what" (the key
    insight), drawn only from the plotted numbers. It renders beneath the chart so the reader doesn't
    have to interpret the figures unaided.
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
### 2.3 Interactive activity blocks — grouped by the learning action

> Pick by objective first (see the §0b.2 table). Every activity here is scorable into a graded quiz
> by wrapping it in a graded `*Section:*` (see §Graded), and earns points under the `*Points:*` overlay.

**Label — put names on the parts of a diagram, screenshot, or interface**

- **Label a diagram / screenshot / interface → `*DragDrop:*` (parser-supported).** A labeling activity:
  the learner drags each label onto its correct target — or picks it from the per-label menu, which is
  the keyboard/touch-accessible source of truth (partial credit — each label on its right target scores).
  Its distinctive strength, which no other block has, is **positioned labels over a background image**:
  add an `image:` and give each `zone:` an `@ x,y` percent coordinate to place it on the picture. Use it
  to **label a product screenshot, a workflow diagram, a clinical UI, or equipment**. Without an image
  the zones render as a labeled row. Grammar (`image:` optional, `zone: <title> [@ x,y]`, `item: <label>
  -> <zone title>`, lone `:::` closes; aliases `*Drag-and-Drop:*`, `*Drag:*`):
  ```
  *DragDrop:* prompt: Drag each label onto the right area of the dashboard.
  image: assets/dashboard_screen.png
  zone: Active queue @ 22,30
  zone: Alerts panel @ 70,18
  zone: Patient detail @ 50,72
  item: Where new requests appear -> Active queue
  item: Where stalled steps surface -> Alerts panel
  item: Where you open one request -> Patient detail
  :::
  ```
  `@ x,y` are percentages of the image (0–100; left, top). Use `*DragDrop:*` for **labeling** (each label
  → its one correct spot); for sorting many items into groups use `*Categorize:*`, and for ordering steps
  use `*Sequence:*` — those own those objectives. To score it into a graded quiz, wrap it in a graded
  `*Section:*` (see §Graded).
**Classify — sort items into groups, bins, or queues**

- **Sort into groups → `*Categorize:*` (parser-supported).** A classification activity: the learner
  sorts a pool of items into 2–4 labeled buckets — **many items per bucket** — via a dropdown per item
  (partial credit — each item in its correct bucket scores). This is the tool for **classification /
  grouping / triage** objectives (which alert goes to which team, which request belongs in which queue).
  Grammar (`bucket:` lines name the groups, `item: <text> -> <bucket title>` assigns each item, `->`/`=>`
  also written `»`, lone `:::` closes; alias `*Sort:*`):
  ```
  *Categorize:* prompt: Sort each request into the queue that owns it.
  bucket: Urgent
  bucket: Routine
  item: ICU bed with no assignment yet -> Urgent
  item: Rapid-response call -> Urgent
  item: Scheduled next-day transfer -> Routine
  :::
  ```
  Use **2–4 buckets** and enough items that each bucket gets **at least two** — grouping needs a few per
  group. (For placing one label on one spot, use `*DragDrop:*` labeling instead.) To score it into a
  graded quiz, wrap it in a graded `*Section:*` (see §Graded).
**Order — arrange steps or events into the correct sequence**

- **Put steps in order → `*Sequence:*` (parser-supported).** An ordering activity: the learner arranges
  a shuffled set of steps into the correct sequence (partial credit — each step in its right position
  scores). Use it whenever the **ORDER is the learning** — a procedure, a workflow, a chronology, or a
  ranking. **List the `step:` lines in the CORRECT order** — the authoring order IS the answer; the build
  shuffles them for the learner. Grammar (`step:` lines in correct order, lone `:::` closes; aliases
  `*Order:*`, `*Ordering:*`):
  ```
  *Sequence:* prompt: Put the transfer steps in the order they happen.
  step: Receive the transfer request
  step: Verify bed availability
  step: Assign the bed
  step: Notify the receiving unit
  :::
  ```
  Use **3–7 steps**, each a short self-contained action. To score it into a graded quiz, wrap it in a
  graded `*Section:*` (see §Graded).
**Associate — pair things that go together**

- **Match pairs → `*Matching:*` (parser-supported).** An association activity: the learner pairs each
  LEFT item with its correct RIGHT partner from a dropdown (partial credit — per pair). Use it for
  **term↔definition, cause↔effect, role↔tool, feature↔benefit** — any 1:1 association. Grammar (`pair:
  <left> -> <right>` lines, lone `:::` closes; alias `*Match:*`):
  ```
  *Matching:* prompt: Match each role to what it does.
  pair: Charge nurse -> Approves urgent transfers
  pair: Bed manager -> Assigns available beds
  pair: Transport -> Moves the patient between units
  :::
  ```
  Use **3–6 pairs** with distinct, unambiguous partners (the rights become the answer choices — avoid two
  that could both fit one left). To score it into a graded quiz, wrap it in a graded `*Section:*` (see
  §Graded).
**Recall — retrieve a term or fact**

- **Complete the sentence → `*FillBlank:*` (parser-supported).** A cloze / recall-in-context activity:
  the learner types the missing word(s) into a sentence (partial credit — per blank; matching is lenient
  — case-insensitive, whitespace-tolerant). Use it to check **recall in context** — completing a policy,
  a definition, or a procedure line — which is harder and more durable than recognizing an option. Put
  `___` where the input goes; after `->` list the accepted answers, `|`-separated for synonyms. Grammar
  (`blank:` lines, `___` marks the input, `->` then a `|`-separated accept-list, lone `:::` closes;
  aliases `*Fill:*`, `*Cloze:*`):
  ```
  *FillBlank:* prompt: Complete each statement from this lesson.
  blank: Active transfer requests first appear on the ___. -> dashboard
  blank: When a step stalls, you ___ the request. -> escalate | escalate it
  :::
  ```
  Keep each accepted answer short (a word or two) and list the real synonyms so a correct answer isn't
  marked wrong. To score it into a graded quiz, wrap it in a graded `*Section:*` (see §Graded).
- **Term definitions → `*Crossword:*` (parser-supported).** An interlocking numbered crossword
  generated from your clue/answer pairs: the learner reads each numbered clue and types the answer
  into the grid (partial credit — solved N of M). Unlike a word search (which only asks learners to
  RECOGNISE a spelled-out word), the crossword makes them RECALL the term from its definition, so
  **always give each answer a real clue** — the clue is where the learning happens. Use the exact
  APPROVED terms (product/feature/workflow names from the glossary). You supply ONLY the answers and
  clues — **the build GENERATES and numbers the grid** and interlocks the words, so never draw cells
  yourself. Grammar (`word:` lines, `| clue` after the answer, lone `:::` closes):
  ```
  *Crossword:* prompt: Solve the clues to fill the grid with terms from this lesson.
  word: DASHBOARD | Where active items appear at a glance
  word: ESCALATE | Raise the priority when a step stalls
  word: HANDOFF | Passing responsibility for a patient to another team
  :::
  ```
  Use **5–10 single-word answers** that share letters (they must interlock — an answer that can't
  cross the others is dropped); shorter, letter-varied terms interlock best. Spaces/punctuation are
  ignored in the grid; the full term shows in the clue heading. To score it into a graded quiz, wrap
  it in a graded `*Section:*` (see §Graded).
- **Vocabulary reinforcement → `*WordSearch:*` (parser-supported).** A find-the-word puzzle
  generated from a short term list: the learner finds each hidden word in a letter grid (partial
  credit — found N of M). Use it to consolidate the 5–10 KEY TERMS a unit teaches (a *Remember*-level
  recall game), never as a substitute for a knowledge check or judgment practice. Prefer the exact
  APPROVED terms (product/feature/workflow names from the glossary) so the game reinforces house
  vocabulary. You supply ONLY the words (and an optional clue each) — **the build GENERATES the
  grid**, so never draw letters yourself. Grammar (`term:` lines, an optional `| clue`, lone `:::`
  closes the block):
  ```
  *WordSearch:* prompt: Find the five workflow terms from this lesson.
  term: DASHBOARD | Where active items appear at a glance
  term: ESCALATE | Raise the priority when a step stalls
  term: HANDOFF
  :::
  ```
  Use **5–10 single-word terms** (spaces/punctuation are ignored in the grid; the full term still
  shows in the word list). An optional `prompt:` on the header sets the intro line; each `term:` may
  add `| <clue>` to show a short definition beside the word. To score it into a graded quiz, wrap it
  in a graded `*Section:*` (see §Graded).
**Review formats — energize a multi-question review**

- **Playful review quiz → `*GameShow:*` (parser-supported).** A spin-the-wheel game: each question
  becomes a wheel slice, the learner spins to draw one, answers it, then spins again (partial credit —
  answered N of M correctly). Use it to make a set of **multiple-choice recall/comprehension questions**
  feel like a game show — a lighter, higher-energy alternative to a plain run of knowledge checks, best
  as an end-of-unit review of 4–8 questions. Each question is a group of lines: `q:` the stem, `a:` the
  correct answer, then one or more `option:` (wrong answers); a new `q:` starts the next question. The
  build SHUFFLES the options, so list the correct one on `a:` and never worry about answer position.
  Grammar (a new `q:` starts each slice, lone `:::` closes the block):
  ```
  *GameShow:* prompt: Spin the wheel to review what this lesson covered.
  q: Where do active transfer requests appear first?
  a: On the dashboard
  option: In the archived report
  option: In the admin console
  q: What should you do when a step stalls?
  a: Escalate the request
  option: Delete the request
  option: Wait for it to expire
  :::
  ```
  Use **4–8 questions**, each with **one correct `a:` and 2–3 `option:` distractors**. An optional
  `prompt:` on the header sets the intro line. To score it into a graded quiz, wrap it in a graded
  `*Section:*` (see §Graded).
- **Category-board review quiz → `*QuizBoard:*` (parser-supported).** A Jeopardy-style board: your
  questions are grouped into **named categories** (columns); each becomes a tile worth escalating
  points (top row lowest, bottom row highest). The learner picks any tile, answers its MCQ, and the
  tile flips correct/incorrect (weighted partial credit — "scored N of M points"). Use it to make a
  **multi-topic recall review** feel competitive — a natural fit when your questions fall into 2–4
  themes. Each category is a `category:` line followed by its question groups (`q:` stem, `a:` correct
  answer, one or more `option:` distractors; a new `q:` starts the next tile, a new `category:` the
  next column). The build SHUFFLES the options, so list the correct one on `a:` and never worry about
  position. Grammar (a new `category:` starts each column, lone `:::` closes the block):
  ```
  *QuizBoard:* prompt: Pick a tile to test what this lesson covered.
  category: Queues
  q: Where do active transfer requests appear first?
  a: On the dashboard
  option: In the archived report
  option: In the admin console
  q: What should you do when a step stalls?
  a: Escalate the request
  option: Delete the request
  category: Roles
  q: Who approves an urgent transfer?
  a: The charge nurse
  option: Any visitor
  option: The patient
  :::
  ```
  Use **2–4 categories** of **2–4 questions each** (order each category easiest-first — the point
  value rises down the column), one correct `a:` and 2–3 `option:` distractors per tile. An optional
  `prompt:` sets the intro line. To score it into a graded quiz, wrap it in a graded `*Section:*` (see
  §Graded). Aliases: `*Jeopardy:*`, `*Board:*`.
- **Fast streak drill → `*SpeedStreak:*` (parser-supported).** A brisk one-at-a-time MCQ run: the
  learner answers each question in sequence, building a **consecutive-correct streak** shown on a
  scoreboard, then finishes with a tally (partial credit — "answered N of M correctly"). Use it to make
  a short set of **quick recall/comprehension questions** feel like an arcade drill — higher-energy than
  a plain run of knowledge checks, best for 4–8 questions. Each question is a group of lines: `q:` the
  stem, `a:` the correct answer, then one or more `option:` (wrong answers); a new `q:` starts the next
  question. The build SHUFFLES the options, so list the correct one on `a:` and never worry about
  position. An optional `timer: N` on the header adds a per-question countdown of N seconds — but the
  timer is purely for motivation (a speed bonus): it **never** affects correctness or the score, and the
  learner can always answer after it runs out, so it stays fully accessible. Put `prompt:` LAST on the
  header if you also set a timer. Grammar (a new `q:` starts each question, lone `:::` closes):
  ```
  *SpeedStreak:* timer: 15 prompt: How fast can you clear this review?
  q: Where do active transfer requests appear first?
  a: On the dashboard
  option: In the archived report
  option: In the admin console
  q: What should you do when a step stalls?
  a: Escalate the request
  option: Delete the request
  option: Wait for it to expire
  :::
  ```
  One correct `a:` and 2–3 `option:` distractors per question. Omit `timer:` for an untimed streak drill.
  To score it into a graded quiz, wrap it in a graded `*Section:*` (see §Graded). Aliases: `*RapidFire:*`,
  `*Streak:*`.
**Decide — practise a judgment call with feedback**

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

**Reflect — apply the lesson in the learner's own words (open response, non-graded)**

- **Open-response reflection → `*Reflection:*` (parser-supported).** A free-text checkpoint: the
  learner types a response into a textarea and, on submit, a **model answer** + **rubric criteria**
  reveal so they self-assess. It is **non-graded and completion-only** — it never contributes to the
  quiz score, the pass gate, or points/XP; it just gates completion once answered. Use it for
  metacognition and transfer ("How would you apply this on your unit?", "What will you do
  differently?") where there is no single correct answer — so it can't be a `*Question:*`. Grammar
  (a lone `:::` closes the block):
  ```
  *Reflection:* How would you apply the escalation policy to a delay you have seen on your unit?
  model: A strong answer names the on-call coordinator as the first contact, cites the 15-minute
  threshold, and explains documenting the delay in the transfer record.
  criteria: Identifies the correct first point of contact
  criteria: References the time threshold
  criteria: Mentions documentation
  :::
  ```
  The prompt follows the marker (extra prose lines below it extend the prompt). **Author the `model:`
  answer and `criteria:` yourself** — a published course runs offline with no AI grader, so the model
  answer and rubric ARE the feedback: write the response a strong learner would give and 2–4 things a
  good answer includes, giving the learner a concrete benchmark to compare against. Both `model:` and
  `criteria:` are optional (a bare prompt still works as a pure reflection), but include them whenever
  you can — the self-assessment is the point. Aliases: `*Reflect:*`, `*OpenResponse:*`, `*FreeText:*`.
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
