# Course Builder — Activity Reframing Candidates

**Date:** 2026-07-02
**Author:** Claude (compiled for James Epperson)
**Scope:** Courses tab. How to get **more instructional value out of the interaction
mechanics we already shipped** — by reframing them from "games" into a palette of
general **instructional activities**, mostly through authoring-guide + prompt work,
with little to no new block code.

> This is a *candidate list*, not a plan. Companion to
> [CAPABILITY_EXPANSION_CANDIDATES_2026-06-29.md](CAPABILITY_EXPANSION_CANDIDATES_2026-06-29.md)
> (which proposes *new* capabilities). This doc proposes **new uses of existing ones.**
> Nothing here is committed.

---

## The core insight

Over the gamification track we built eight interaction mechanics: `dragDrop`,
`wordSearch`, `crossword`, `gameShow`, `quizBoard`, `speedStreak`, plus the course-level
`points/XP` and `confetti` overlays. They were built and named as **games**.

But a game is a *skin*. Underneath, each is a **general interaction pattern** that maps
to a specific kind of learning:

| The "game" | Is really a… | Which serves the learning intent… |
|---|---|---|
| Jeopardy board (`quizBoard`) | category-organized review grid | *review across 2–4 themes, learner-navigated* |
| Spin-the-wheel (`gameShow`) | randomized MCQ delivery | *retrieval practice / interleaved review* |
| Speed streak (`speedStreak`) | timed fluency drill | *build automaticity on facts that must be fast* |
| Drag-and-drop (`dragDrop`) | spatial labeling engine | *label a diagram, screenshot, or interface* |
| Crossword (`crossword`) | clue→term recall grid | *definition / terminology recall* |
| Word search (`wordSearch`) | term-exposure grid | *pre-exposure / vocabulary priming (low stakes)* |

The value we haven't captured: **teaching the tool (and the LLM) to reach for these by
learning objective, not by "let's make it fun."** Presentation trainers already do this
instinctively — a Jeopardy board in a slide deck isn't there to be a game, it's the most
engaging way to run a multi-topic recap. That's the framing we should encode.

---

## What the code actually supports (verified against the repo, HEAD of the gamification track)

Three findings that shape — and correct — the candidate list. **Check the record before
building:** two of the "obvious" reuses are already shipped as their own blocks.

1. **"Arrange items in order" is already a block: `sequence`** (alias `ordering`,
   `src/md_import.py`). It's a position-dropdown ordering activity with partial credit.
   → *Do not* reframe `dragDrop` as an ordering tool; point ordering objectives at
   `sequence`. The gap is not a missing mechanic — it's that the LLM may be underusing it.

2. **"Sort items into groups" is already a block: `categorize`.** It sorts a pool of items
   into labeled buckets via dropdowns, **multiple items per bucket**, partial credit,
   gates completion. This is the true many-into-few *grouping/classification* sorter.
   → `dragDrop` is **not** the sorter James reached for. In `dragDrop`, **each label maps
   to exactly one zone** — it's a *labeling* mechanic (one label → one spot), strongest on
   a **background diagram with x/y-positioned zones** (screenshots, clinical UI, anatomy).
   Grouping objectives → `categorize`; labeling objectives → `dragDrop`.

3. **`dragDrop` is missing from the AUTHORING_GUIDE entirely.** Every other mechanic
   (`gameShow`, `quizBoard`, `speedStreak`, `wordSearch`, `crossword`) has an authoring
   section; `dragDrop` appears only as one word in the `*Points:*` list. **The LLM
   currently has no way to know it exists or when to emit it.** This is the single
   highest-leverage fix in this doc — pure discoverability, zero runtime risk.

**Effort/Conf legend** (same as the companion doc): Effort `S` ≈ days · `M` ≈ 1–2 weeks.
Conf `H`/`M`/`L`. Because this is reframing over *already-tested* mechanics, almost
everything here is `S` and touches only `templates/AUTHORING_GUIDE.md`, the generation
prompt, and (occasionally) a block's `title`/description — **not** the 6 block-registry
sites, and **not** `dashboard/index.html` (so no UI drift guard).

---

# PART I — The activity chooser (the reframing spine)

The keystone deliverable. Today the guide describes each block in isolation. Add a
**learning-intent → activity** decision layer at the top of the block-selection section,
so generation picks the mechanic that fits the objective. One table, one prompt hook.

| The learning objective is to… | Reach for | Already framed as activity? |
|---|---|---|
| **Label** the parts of a diagram / screenshot / interface | `dragDrop` (with `image:` + `zone: … @ x,y`) | ❌ not in guide at all |
| **Classify / sort** many items into groups or bins | `categorize` | ✅ yes |
| **Order / sequence** steps of a procedure or timeline of events | `sequence` | ✅ yes |
| **Associate** pairs (term↔definition, cause↔effect, role↔tool) | `matching` | ✅ yes |
| **Recall a term** from its definition | `crossword` | ⚠️ framed as "game" |
| **Recall in context** (complete the sentence/policy) | `fillBlank` | ✅ yes |
| **Pre-expose / prime** key vocabulary before content (low stakes) | `wordSearch` | ⚠️ framed as "game" |
| **Review across 2–4 topics**, learner-navigated | `quizBoard` | ⚠️ framed as "game" |
| **Retrieval practice** — randomized-order MCQ recall | `gameShow` | ⚠️ framed as "game" |
| **Build fluency/automaticity** on facts that must be fast | `speedStreak` | ⚠️ framed as "game" |
| **Decide** — practice a judgment call with feedback | `scenario` | ✅ yes |
| **Self-check** understanding at a checkpoint | `knowledgeCheck` | ✅ yes |

| # | Candidate | What it adds | Effort | Conf | Fit / notes |
|---|---|---|---|---|---|
| R1 | **Activity-chooser decision table in AUTHORING_GUIDE** | The table above, plus a one-line rule: *pick by objective first, engagement second.* | S | H | Pure guide edit; the spine that makes every item below land. The LLM already respects the existing block-selection prose (`0b.2`). |
| R2 | **"Objective → activity" hook in the generation prompt** | When the plan step names a verb (label / classify / order / recall / decide), bias toward the matching mechanic. | S | M | Prompt-layer over the staged plan→unit flow; reinforces R1 at generation time. |

---

# PART II — Per-mechanic reuse catalog

Each mechanic below, its **non-game instructional uses**, the content shape that fits,
and what (if anything) needs to change. TeleTracking/Nova examples are illustrative.

## II-A. `dragDrop` — the spatial labeling engine *(biggest untapped mechanic)*

Its real strength is the one thing no other block does: **positioned labels on a
background image** (`image:` + `zone: <title> @ x,y`, percent coords). Zones also work
**without** an image as a labeled row.

| Non-game use | Content shape | Example |
|---|---|---|
| **Label a product screenshot / interface** | A UI capture + the names of its regions | "Drag each label onto the right area of the Transfer IQ Pro dashboard." |
| **Label a diagram / workflow chart** | A process image + step/part names | "Place each phase name on the patient-flow diagram." |
| **Label anatomy / equipment** | A clinical image + part names | "Label the components of the bed-management console." |
| **1:1 placement / assignment** (no diagram) | A few items, each with one correct bin | "Drag each alert type onto the role that owns it." |

- **Framing change:** ⭐ **Add a `dragDrop` authoring section** (grammar + "use this to
  label a diagram/interface"). This is R3 below and the top shortlist item.
- **Do NOT** pitch it for grouping (→ `categorize`) or ordering (→ `sequence`).
- **Open question to confirm before promising the "assignment" use:** can two pool items
  share one `target` zone id? The scout read the schema as *one item → one zone* but
  didn't confirm whether a zone may receive several items. If not, the no-diagram
  "assignment" use is limited to 1:1 and grouping stays firmly `categorize`'s job.

| # | Candidate | Effort | Conf | Notes |
|---|---|---|---|---|
| R3 | **Add `dragDrop` to AUTHORING_GUIDE** (grammar + "label a diagram/interface" framing + a labeling example) | S | H | Fixes finding #3. Nothing new to build — the block ships and is tested; it's simply invisible to the author. |

## II-B. `quizBoard` — the category-review board

Reframe from "competitive Jeopardy game" to **learner-navigated multi-topic review**.

| Non-game use | Content shape | Example |
|---|---|---|
| **End-of-module review across themes** | Questions grouped into 2–4 named topics | "Review board: pick a topic, answer to reveal." |
| **Recert / exam-prep coverage map** | The exam's domains as columns | Learner sees which domains they've covered. |
| **Self-directed 'weakest first' review** | Same, framed as choose-your-gap | "Start with the category you're least sure of." |

- **Framing change:** the existing guide section (`0b.2`, lines ~115–117) says
  *"competitive… review game."* Add a second sentence: *"Also the cleanest way to run a
  **structured multi-topic review** where the learner controls the order — no competition
  framing required."* Small edit, opens the block to serious review contexts.

## II-C. `gameShow` (spin-wheel) — randomized retrieval practice

The wheel is **randomized MCQ delivery**. Randomized order *is* a documented learning
technique (retrieval practice, interleaving) — the pedagogy is real, the wheel is the skin.

| Non-game use | Content shape | Example |
|---|---|---|
| **Retrieval-practice review** | A bank of recall MCQs, order shouldn't be predictable | "Spin to draw your next review question." |
| **Section warm-up / activation** | 3–5 prior-knowledge questions | Opens a section by surfacing what's known. |

- **Framing change:** add *"use when you want **randomized** recall (retrieval practice),
  not a fixed quiz order."* Note honestly: it's still MCQ — no new assessment power over
  `knowledgeCheck`; the value is the randomized, engaging delivery.

## II-D. `speedStreak` — the fluency / automaticity drill

Reframe from "beat the clock" to **fluency check**. Some facts must become *fast and
automatic* (safety codes, terminology, escalation paths). A streak of consecutive-correct
answers is a recognized fluency signal.

| Non-game use | Content shape | Example |
|---|---|---|
| **Automaticity drill** | Facts that must be instant, not just known | "Rapid recall: terminology fluency check." |
| **Formative pulse-check** | A quick run to gauge readiness | Low-stakes "are you ready to move on?" |

- **Framing change:** lead with fluency, not pressure. ⚠️ Keep the a11y posture we already
  shipped — the **timer is cosmetic** (WCAG-safe; the learner can always answer after 0).
  Frame the timer as an optional energizer, never a gate.

## II-E. `crossword` — definition / terminology recall

Pedagogically the **strongest** of the word games: the clue forces *recall* of the term
(unlike word search, which only requires *recognition*).

| Non-game use | Content shape | Example |
|---|---|---|
| **Terminology mastery check** | 8–15 term/definition pairs | End-of-module vocabulary recall. |
| **Definitions review** | Clue = definition, answer = the term | "Solve the grid to review key terms." |

- **Framing change:** present as a **terminology recall activity** in the intent table
  (R1), with "game" as the optional skin.

## II-F. `wordSearch` — vocabulary priming (low stakes, honest limits)

Be honest about its ceiling: **finding a hidden word ≠ knowing it.** Its real value is
**pre-exposure / priming** (advance-organizer effect) or a light between-section palate
cleanser — *not* assessment.

| Non-game use | Content shape | Example |
|---|---|---|
| **Vocabulary pre-exposure** | Key terms *before* the content that teaches them | Warm-up that surfaces the module's vocabulary. |
| **Low-stakes engagement break** | A short optional grid mid-course | Re-engagement between dense sections. |

- **Framing change:** in the intent table, tag it *"priming / warm-up, not assessment."*
  Steer terminology *testing* to `crossword`/`fillBlank`.

## II-G. The already-activity blocks (make sure the LLM reaches for them)

These aren't framed as games and don't need reframing — but the intent table (R1) should
name them so generation picks them for the right objective instead of defaulting to prose
+ a `knowledgeCheck`:

- **`categorize`** — classification / grouping / triage (the real "sorter").
- **`sequence`** — ordering steps, ranking, chronology.
- **`matching`** — associative pairs (term↔def, cause↔effect, role↔tool).
- **`fillBlank`** — cloze / recall-in-context / policy completion.
- **`scenario`** — decision practice with feedback.
- **`flashcard` / `comparison` / `process` / `timeline` / `accordion` / `cardGrid`** — the
  non-assessment *presentation* activities; already content-framed.

---

# PART III — Cross-cutting reframing work

| # | Candidate | What it adds | Effort | Conf | Fit / notes |
|---|---|---|---|---|---|
| R1 | **Activity-chooser decision table** (Part I) | Learning-intent → mechanic map in the guide | S | H | The spine. |
| R2 | **Objective→activity prompt hook** | Bias generation by the plan step's verb | S | M | Prompt-layer over the staged plan flow. |
| R3 | **Add `dragDrop` to AUTHORING_GUIDE** | Grammar + "label a diagram" framing + example | S | H | Fixes the discoverability gap; highest single win. |
| R4 | **Dual-framing the five "game" sections** | One added "use this when the objective is…" line per game block (quizBoard/gameShow/speedStreak/crossword/wordSearch) | S | H | Keeps the game energy; adds the instructional trigger. |
| R5 | **Organize the guide by activity category** | Group blocks under *Label · Classify · Order · Associate · Recall · Review formats · Decide* headings | S | M | Optional polish; makes the palette legible at a glance. Larger guide restructure — do after R1–R4. |
| R6 | **Per-mechanic lint / example gallery** | A worked example of each non-game use in `templates/` for the LLM to pattern-match | M | M | Carries open follow-up (1): the game blocks have no dedicated lint. Deferred; nice-to-have. |

---

# PART IV — The "confidently reframable now" shortlist

Highest value, lowest risk, all `S`/`H`, all pure guide/prompt edits over shipped-and-
tested mechanics:

1. **R3 — Add `dragDrop` to the AUTHORING_GUIDE.** It's built, tested, and invisible.
   Unlocks diagram/interface labeling — a use nothing else in the toolkit covers, and a
   strong fit for Nova product screenshots and clinical UI. *(S/H — do first.)*
2. **R1 — The activity-chooser decision table.** One table that turns eight siloed blocks
   into a coherent palette selected by learning objective. *(S/H.)*
3. **R4 — Dual-frame the five game sections.** One "use this when the objective is X" line
   each, so `quizBoard`/`gameShow`/`speedStreak`/`crossword`/`wordSearch` get reached for
   as review/fluency/recall activities, not just novelty. *(S/H.)*
4. **R2 — The objective→activity prompt hook.** Reinforces R1 at generation time. *(S/M.)*

R5 (guide-by-category) and R6 (example gallery/lint) are the follow-on polish.

## Explicitly out / cautions (honest trade-offs)

- **Do not reframe `dragDrop` as a grouper or a sequencer.** `categorize` (many-per-bucket
  grouping) and `sequence` (ordering) already own those objectives and do them better.
  Overlapping them would confuse the LLM's block choice.
- **`wordSearch` is not assessment.** Frame it as priming/warm-up or steering will produce
  weak "quizzes." Terminology *testing* → `crossword`/`fillBlank`.
- **`gameShow`/`speedStreak` add no new assessment power** over `knowledgeCheck` — their
  value is delivery (randomization, fluency), not measurement. Say so, so they're used for
  the right reason.
- **Confirm the `dragDrop` zone multiplicity** (can a zone hold >1 item?) before promising
  the no-diagram "assignment" use in the guide. If 1:1 only, keep it to labeling.
- **This is reframing, not new mechanics.** If a genuinely new interaction is wanted
  (e.g. a rank-order-with-weights block, or a many-item labeled-bin sorter distinct from
  `categorize`), that's a *build* candidate for the companion doc, not this one.

---

*Sourcing note: block inventory, grammar, and current AUTHORING_GUIDE framing were verified
against the repo on disk this session (42 block types; `dragDrop` absent from the guide;
`sequence`/`categorize` already shipped; the five word/game blocks framed as "games").
Effort/confidence are planning estimates, not commitments.*
