# Course Builder — Capability Expansion Candidates

**Date:** 2026-06-29
**Author:** Claude (compiled for James Epperson)
**Scope:** Presentations tab + Courses tab. An itemized, industry-benchmarked list of
capabilities that could be **confidently added** to the Course Builder, given its actual
architecture and operating constraints.

> This is a *candidate list*, not a plan. Nothing here is committed. The next step is for
> James to pick the items worth turning into a build plan (à la
> [AUDIT_AND_REMEDIATION_PLAN_2026-06-26.md](AUDIT_AND_REMEDIATION_PLAN_2026-06-26.md)).

---

## How this was built

Benchmarked against two sets, via live 2025–2026 web research:

- **(A) Comparable software** — direct competitors.
  - *AI presentation generators:* Gamma, Beautiful.ai, Canva (Magic Studio), Microsoft
    Copilot in PowerPoint / Designer, Google Gemini in Slides, Pitch, Plus AI, Decktopus,
    Presentations.ai (and Tome, which *exited* presentations for sales-enablement).
  - *E-learning authoring:* Articulate (Rise/Storyline + AI Assistant), Adobe Captivate,
    iSpring, Elucidat, Evolve (Intellum), Coursebox AI, Synthesia 3.0, 7taps, SC Training.
- **(B) Tangential products** — same *workflow*, different purpose/industry.
  - *Design/doc/canvas:* Figma/FigJam, Webflow, Framer, Canva, Miro, Notion.
  - *AI media generation:* Synthesia, HeyGen, ElevenLabs, Descript, Whisper/Piper/Kokoro (OSS).
  - *Generative-iteration UX:* Cursor, GitHub Copilot, Vercel v0, Replit, Claude Code.
  - *BI auto-narrative:* Power BI Copilot, Tableau Pulse, Looker.
  - *Brand-voice + localization:* Jasper, Writer, Copy.ai; Lokalise, Crowdin, Phrase, DeepL.

### Feasibility legend

Every candidate is tagged against **our** reality, not a generic SaaS wishlist.

- **Effort:** `S` ≈ days · `M` ≈ 1–2 weeks · `L` ≈ multi-week / its own focused build.
- **Conf** (confidence we can ship it well on the current architecture): `H` / `M` / `L`.
- **Fit:** one line on how it sits on what already exists (token renderer, IR-JSON edit
  surface, subprocess build seam + `.report.json`, SCORM packager, dual subscription-CLI
  providers, single-operator, Win+Mac, **never a metered API**).

### Hard constraints that shaped the list (read before judging any item)

1. **No metered APIs, ever** ([[feedback_never_use_claude_api]]). This rules out cloud AI
   media billed per-call (Synthesia/HeyGen avatars, ElevenLabs voices) as *built-in*
   features — they appear only as **optional, user-supplies-their-own-seat integrations**.
   It *favors* the open-source local stack (Whisper captions, Piper/Kokoro TTS) which is
   free and commercially licensed.
2. **Operator-grade, not SaaS** ([[feedback_course_builder_operator_target]]). Single
   operator → real-time multiplayer co-editing and viewer-engagement analytics are **low
   fit** (deferred/out). Async **SME review** *is* in-scope (it matches James's existing
   green-text review workflow [[feedback_sme_pass_propagation]]).
3. **Output goes to Intellum.** Engagement analytics live in the LMS, so we don't rebuild
   them — but **xAPI/cmi5** (richer than SCORM tracking) is a real, in-scope differentiator.
4. **Cross-platform first** ([[feedback_cross_platform_first.md]]) and **neutral naming**
   ([[feedback_neutral_naming]]).

---

## Current state (what already ships — do NOT re-propose)

**Presentations tab:** 16 token-driven, template-faithful layouts; dark/light theme flag;
brand blueprint + design tokens; native `.pptx` export + faithful SVG preview/slideshow;
native bar/line/pie charts; image library + hero/full/banner/imagetext modes + OCR;
entrance animations (fade/rise/fly) + transitions; 5 deck purpose presets
(general/formal/debrief/workshop/pitch); per-slide regenerate with Content/Layout/Color
scope toggles; per-slide theme + layout pickers; JSON edit modal; Claude+codex providers
with model selector + streaming; pagination with the no-split-visualization rule.

**Courses tab:** ~30 §8 block types (incl. `knowledgeCheck`, `objectives`, `scenario`
[linear], `continue` gating, `categorize`, `flashcard`, `process`, `timeline`,
`comparison`, `chart`, `infographic`, `cardGrid`, `accordion`, `table`, media blocks);
multi-select KCs; graded courses with pass threshold + retry + mastery + resume
(suspend_data); 6 archetypes (concept-explainer, software-procedure, decision-scenario,
policy-acceptable-use, onboarding-company, onboarding-role); 5 course presets
(standard/compliance/onboarding/product-skill/refresher); staged plan→unit→assemble
generation with auto-derived objectives; ingestion of `.docx/.md/.html/.odt/.rtf/.csv/.pdf`
+ image OCR; **SCORM 1.2 + cmi5/xAPI** export with conformance lint (the player runtime is
2004-ready but there is **no SCORM 2004 packager yet**); structured `.report.json` build
report; player a11y (aria-live, sr-only correct/incorrect, disabled-on-lock).

---

# PART I — PRESENTATIONS TAB

## I-A. Generation & input

| # | Capability | What it adds | Inspired by | Effort | Conf | Fit / notes |
|---|---|---|---|---|---|---|
| P1 | **URL / webpage → deck** | Paste a URL; fetch + extract readable text as a source alongside files. | Beautiful.ai, Decktopus, Presentations.ai | S | H | New reader in the existing `read_sources` chain; mirrors `.html` handling already present. |
| P2 | **Editable outline before build** | Generate the slide outline (titles + one-liners) and let the operator approve/reorder *before* full generation runs. | Plus AI, Decktopus, Gamma | M | H | Courses already have a plan step; port that pattern to the deck flow. Cuts wasted regen. |
| P3 | **Multi-candidate slide generation** | Generate N (e.g. 3) layout/voice treatments of a slide; operator picks. Optional auto-rank against brand+density rules. | Vercel v0 (3 variations), Cursor 2.x multi-agent judging | M | H | Extends per-slide regenerate; the renderer is deterministic so N candidates are cheap to preview. |
| P4 | **Intent → layout ("describe the slide")** | Operator types intent ("compare the 3 deployment models"); engine picks the right layout, not a generic bullet list. | Power BI/Looker NL-to-viz; Canva Magic Design | M | M | `LAYOUT_MATCH` heuristics already exist; expose as a per-slide "from a sentence" action. |
| P5 | **Image-doc / screenshot → deck** | Feed screenshots; OCR + layout into an imagetext/hero deck. | Gemini, Synthesia doc-to-video | S | H | OCR ingestion already exists; just route image sources into the deck prompt. |

## I-B. Design intelligence & brand governance

| # | Capability | What it adds | Inspired by | Effort | Conf | Fit / notes |
|---|---|---|---|---|---|---|
| P6 | **Brand-kit from URL/PDF** | Auto-extract palette, logo, fonts from a company site or brand PDF to bootstrap a new `blueprint.json`. | Canva Brand Kit Builder, Presentations.ai "Brand Sync" | M | M | Produces a draft blueprint for operator review; biggest unlock for serving a *new* brand fast. |
| P7 | **Brand compliance checker** | Pre-export pass flags off-palette colors, logo misuse, contrast failures; offers auto-fix. | Decktopus/Copilot Brand Checker; Webflow AI quality review | M | H | Natural extension of the build report; deterministic checks over the slide IR + tokens. |
| P8 | **Per-section palette variety enforcement** | Detect & nudge when every slide defaults to one accent; suggest palette rotation. | (internal rule [[feedback_course_color_palette_variety]]) | S | H | A lint rule; the recolor machinery already exists. |

## I-C. Data & visuals

| # | Capability | What it adds | Inspired by | Effort | Conf | Fit / notes |
|---|---|---|---|---|---|---|
| P9 | **Editable chart data + more chart types** | Inline data editor; add stacked/horizontal/donut/area; CSV/paste → chart. | Gamma (editable chart block, Mar 2026), Canva Magic Charts | M | H | `chart_svg.py` already does bar/line/pie + native slide; additive. Honors no-split rule. |
| P10 | **Auto-narrative / auto-caption for charts** | Generate the speaker-note or on-slide takeaway sentence that explains a chart. | Power BI Smart Narrative, Looker summaries | S | H | Prompt-layer; one extra field per data slide. High value, low cost. |
| P11 | **Auto speaker notes per slide** | One-click generate presenter notes for the whole deck. | Copilot, Gemini, Pitch, Decktopus | S | H | Pure prompt-layer over existing slide IR. |
| P12 | **More diagram layouts** | Org chart, process *variants* (info-left/right/numbered) — both already on the staged backlog. | Miro/FigJam diagram gen | M/L | M | `process variant` flag is decided ([[reference_slide_design_language]]); Org Chart is the hardest adaptive one. |
| P13 | **Generated images (optional)** | AI-generated slide imagery. | Gamma, Canva Dream Lab, Copilot DALL·E | L | L | ⚠️ Needs an image model — no good *non-metered* local path today. Keep image **library** as default; treat as future/integrate-only. |

## I-D. Interactivity & delivery

| # | Capability | What it adds | Inspired by | Effort | Conf | Fit / notes |
|---|---|---|---|---|---|---|
| P14 | **Interactive HTML deck export** | Export the SVG slideshow as a standalone, self-contained interactive HTML deck (keyboard nav already built). | Gamma web decks, Canva website export | M | H | The SVG slideshow + transitions exist; package as a portable `.html`. |
| P15 | **Narrated-video export of a deck** | Per-slide narration (local TTS) assembled into an MP4 with captions. | Narakeet, Gemini-in-Vids, Plus AI Narrator | L | M | Uses **local Piper/Kokoro TTS + Whisper captions** (no metered API). Subprocess seam fits the build model. See X-media. |
| P16 | **Viewer engagement analytics** | Who viewed which slide, time-per-slide. | Pitch, Beautiful.ai, Gamma, Decktopus | — | — | ❌ **Low fit / out:** single-operator tool; decks go to PowerPoint/Intellum which own delivery. Listed for completeness. |

## I-E. Editing & iteration (the AI loop) — *cross-cuts both tabs; see Part III*

## I-F. Collaboration & review — *cross-cuts both tabs; see Part III*

---

# PART II — COURSES TAB

## II-A. Generation & input

| # | Capability | What it adds | Inspired by | Effort | Conf | Fit / notes |
|---|---|---|---|---|---|---|
| C1 | **URL / video-transcript → course** | Add URL fetch + (local Whisper) transcript ingestion as course sources. | Coursebox, 7taps Transformer, Synthesia | M | M | URL reader = S; transcript needs local Whisper (no metered API). |
| C2 | **SCORM/Rise → course re-import** | Ingest an existing published course zip (Rise/SCORM) into the IR for modernization. | 7taps SCORM transform | M | M | We already decode Rise exports ([[reference_rise_html_export_text_extraction]]); promote to a first-class importer. |
| C3 | **Bulk-create from a manifest CSV** | One spreadsheet of rows → batch-generate many courses/units. | Canva Bulk Create, Webflow/Framer CMS, Figma Buzz | M | H | Direct fit with the NovaCoursesMaster CSV workflow ([[feedback_csv_scope_only]]); IR is already the unit of generation. |

## II-B. Assessment & interaction depth

| # | Capability | What it adds | Inspired by | Effort | Conf | Fit / notes |
|---|---|---|---|---|---|---|
| C4 | **More question types** | Matching, sequencing/ordering, fill-in-the-blank, hotspot — beyond MCQ + categorize. | Articulate, Captivate, Evolve, Coursebox | M (each) | H | Each is a new stable block + player scorer; `categorize`/multi-select prove the pattern. |
| C5 | **Question bank + randomization** | Pull N random items from a pool per attempt. | Storyline, Elucidat, Evolve | M | M | New block + player selection logic; pairs with graded mode. |
| C6 | **Aggregate / final quiz + section pass thresholds** | A graded end-of-course quiz with SCORM subscore reporting. | Storyline, Elucidat | M | H | Already DEFERRED on the backlog; scoring/mastery plumbing exists. |
| C7 | **AI-graded free-text (rubric)** | Score short written answers against a rubric via the subscription CLI; instant feedback. | Coursebox AI grading | M | M | Prompt-layer at runtime is tricky offline in SCORM; viable as an authoring-time *draft-feedback* aid. |
| C8 | **Completion certificate** | Generate a branded certificate on pass. | Coursebox, most LMS authoring | S | M | Template + merge fields; Intellum may already issue these — confirm before building. |

## II-C. Branching & personalization

| # | Capability | What it adds | Inspired by | Effort | Conf | Fit / notes |
|---|---|---|---|---|---|---|
| C9 | **Scenario TRUE branching in the player** | Choices route to distinct next states (not just linear feedback). | Elucidat, Synthesia if/else, 7taps Role Play | M | H | Grammar + renderer exist; this is the deferred player-navigation half. On backlog. |
| C10 | **Variables & conditional show/hide** | Role/answer-driven content paths in one course. | Storyline variables, Elucidat Rules | L | M | New runtime state model in the player; larger lift, high payoff for adaptive courses. |

## II-D. Accessibility

| # | Capability | What it adds | Inspired by | Effort | Conf | Fit / notes |
|---|---|---|---|---|---|---|
| C11 | **WCAG conformance pass + report** | Automated alt-text presence, contrast, heading order, keyboard checks in the build report; AI-drafted alt text. | Evolve (WCAG out-of-box), Webflow AI review, Framer quality review | M | H | Strong fit — extends `.report.json`; a real differentiator (Synthesia/7taps/Coursebox all weak here). Healthcare audience makes this valuable. |
| C12 | **Captions/transcripts for any media block** | Auto SRT/VTT for video/audio via local Whisper. | Whisper/whisper.cpp (MIT, local) | M | H | No metered API; mandatory human-review step for the WCAG ~99% bar. |

## II-E. Standards, packaging & delivery

| # | Capability | What it adds | Inspired by | Effort | Conf | Fit / notes |
|---|---|---|---|---|---|---|
| C13 | **SCORM 2004 packaging** | Add the missing 2004 packaging path. | iSpring, Lectora, Articulate (all ship 1.2 + 2004) | S | H | ✅ The player is **already 2004-ready** (`player.js` detects `API_1484_11`); only `scorm.py` lacks the packager. **cmi5/xAPI export already ships** (`src/cmi5.py`) — so 2004 is the one missing standard. Low-risk additive. |
| C14 | **Always-current / re-publish without re-upload** | (Note only) 7taps "Dynamic SCORM" loads live content. | 7taps | — | — | ❌ Out: requires a hosting backend + live internet; conflicts with portable offline-SCORM goal. Documented as a deliberate non-goal. |

## II-F. Media (narration / video / captions) — *shared engine; see X-media*

## II-G. Localization

| # | Capability | What it adds | Inspired by | Effort | Conf | Fit / notes |
|---|---|---|---|---|---|---|
| C15 | **One-source → translated course** | Translate a built course via the subscription CLI, preserving layout/IR/bindings. | Canva/Figma/Framer translate, Coursebox 100+ lang | M | H | Direct fit with the Spanish/UK localization work ([[project_uk_localization_audit]]); LLM translation honors the no-metered rule. |
| C16 | **Glossary / termbank + banned-words guardrail** | Enforce approved terms ("Transfer IQ Pro", never "the transfer tool"); ban prohibited words at generation time. | DeepL glossary, Writer guardrails, Crowdin | M | H | Serves [[feedback_match_system_terminology]] + [[feedback_neutral_naming]] + UK term flagging ([[feedback_uk_localization_flagging]]). Lint + prompt-layer. |
| C17 | **Translation memory** | Reuse previously approved translations across courses/updates. | Lokalise, Crowdin, Phrase | M | M | A local store keyed by source string; proposes prior wording to cut SME re-review. |

## II-H. Observability & QA

| # | Capability | What it adds | Inspired by | Effort | Conf | Fit / notes |
|---|---|---|---|---|---|---|
| C18 | **Self-healing generation loop** | After generation, run the build-report lints and have the model auto-fix violations *before* showing the operator. | Copilot/Replit/Claude Code self-test loops | M | H | The lints + `.report.json` already exist; loop them back into `generate()`. High leverage — hides boring failures. |
| C19 | **Voice / reading-level lint** | Flag tone drift from the chosen preset, and flag reading level vs. audience. | Jasper off-brand flagging, Writer guardrails | M | M | Extends lint; pairs with the course presets already in place. |
| C20 | **Consistency check on appended content** | When a unit is added to an existing course, check it against the rest for term/voice drift. | Crowdin File Consistency, Vector Memory | M | M | Fits the staged unit model; runs at assemble time. |

---

# PART III — CROSS-CUTTING (both tabs)

## X-iteration. The generative iteration UX

The single highest-leverage cluster — these make *every* generate/regenerate feel
trustworthy. From codegen IDEs (Cursor, Copilot, v0, Replit, Claude Code).

| # | Capability | What it adds | Inspired by | Effort | Conf | Fit / notes |
|---|---|---|---|---|---|---|
| X1 | **Diff + accept/reject on regenerate** | Show old-vs-new (element-level) and let the operator keep the new title but reject the new body — not all-or-nothing. | Cursor inline diff, v0 | M | M | Regenerate exists; add a diff/merge UI over the slide/block IR. |
| X2 | **Regenerate-with-instruction** | Steer a regen by sentence ("make it more visual / clinical / 3 bullets") instead of a blind reroll. | v0, Cursor, all | S | H | The deck slide-row already has a guidance field; generalize to courses + make it conversational. |
| X3 | **Checkpoint / rewind** | Auto-snapshot before each AI edit; one-click restore the deck/course (distinct from git). | Claude Code `/rewind`, Replit, v0 versions | M | H | Local-only tool → cheap to snapshot the IR/build per edit. Also = version history (below). |
| X4 | **Plan/approve-before-generate** | Surface the structure as an editable plan signed off before expensive generation. | Claude Code/Cursor Plan Mode | M | H | Courses have a plan step; make it a true approval gate, extend to decks (=P2). |
| X5 | **Edit-in-place on the live preview** | Click an element on the rendered slide and edit it via a panel + a prompt box on that object. | Vercel v0 Design Mode | L | M | Bigger UI build on the SVG preview; powerful but the largest item here. |
| X6 | **Predictive consequent edits** | Rename a key term / change an objective → offer the downstream edits (recap slide, quiz, summary). | Copilot Next Edit Suggestions, Cursor Tab | L | L | Consistency propagation; advanced, do after X1–X3. |

## X-reuse. Reuse, components & data-binding

From Figma / Webflow / Framer / Notion / Canva — the "define once, propagate" family.

| # | Capability | What it adds | Inspired by | Effort | Conf | Fit / notes |
|---|---|---|---|---|---|---|
| X7 | **Saved custom templates / starters** | Save a slide layout or a whole course as a reusable starter; duplicate-and-edit. | Notion templates, Figma/Webflow cloneables, Miro | M | H | `templates/slide-layouts/*.example.json` is half of this; add operator-saved templates. |
| X8 | **Shared component/snippet library** | Reusable branded blocks (objectives panel, callout, KC shell) that propagate on edit. | Figma Team Libraries, Webflow components, Notion synced blocks | L | M | Maps to a component layer over the IR; biggest structural change, biggest reuse payoff. |
| X9 | **Brand-kit from URL/PDF** (= P6) | Bootstrap a brand blueprint automatically. | Canva, Presentations.ai | M | M | Listed once; serves both tabs. |
| X10 | **CSV/Sheet → bulk generate** (= C3) | Spreadsheet-driven batch build. | Canva Bulk Create, Framer/Webflow CMS import | M | H | Listed once; serves both tabs. |

## X-voice. Brand voice & governance

From Jasper / Writer / Copy.ai / DeepL — make output sound house-consistent automatically.

| # | Capability | What it adds | Inspired by | Effort | Conf | Fit / notes |
|---|---|---|---|---|---|---|
| X11 | **House-voice from examples** | Upload 3–5 approved courses/decks; learn the instructional voice; apply to all generation. | Jasper Brand Voice, Writer, Copy.ai | M | M | Prompt-layer profile, like presets but learned from samples. |
| X12 | **Approved-facts grounding ("memory")** | Generate only from a vetted facts store (product names, workflow steps) to curb hallucination. | Jasper Memory, Writer knowledge | M | M | Aligns with the IR/source-grounded model; a curated source library per brand/product. |

## X-review. Versioning & SME review

| # | Capability | What it adds | Inspired by | Effort | Conf | Fit / notes |
|---|---|---|---|---|---|---|
| X13 | **Version history + restore** | Named versions of a build with one-click restore (beyond local git). | Canva (1000 versions), Figma, Framer, Webflow | M | H | Builds on X3; operator-facing, not git-facing. |
| X14 | **Async SME review mode** | Share a draft to a reviewer (no login) who comments per-block/slide and marks complete; comments flow back. | 7taps SME Review, Webflow Reviewer role, Figma comments | L | M | Strong fit with the existing green-text SME workflow ([[feedback_sme_pass_propagation]]); needs a lightweight share surface. |
| X15 | **Approval gate before publish** | Require sign-off before a course/deck is marked final. | Canva/Webflow approval workflows | M | M | Pairs with X14; a status field + gate in the build flow. |

## X-media. Local AI media (narration · captions · video)

A shared media engine serving both tabs — built **only** on the free, commercially-licensed
local stack to honor the no-metered-API rule.

| # | Capability | What it adds | Inspired by | Effort | Conf | Fit / notes |
|---|---|---|---|---|---|---|
| X16 | **Local TTS narration per block/slide** | Generate per-block/per-slide voiceover with **Piper or Kokoro (Apache/MIT, offline)**. | Narakeet pattern; Synthesia/Murf (as inspiration only) | L | M | Subprocess seam like the build pipeline; no per-call cost. Cloud voices only if user supplies their own seat. |
| X17 | **Local auto-captions (SRT/VTT)** (= C12) | Offline Whisper captions for any media. | Whisper/whisper.cpp (MIT) | M | H | Best free/local/compliant win; mandatory human-review step. |
| X18 | **Narrated-video export** (= P15) | Assemble narration + slides → MP4 + captions, SCORM-wrappable. | Narakeet, Gemini-in-Vids | L | M | Composes X16 + X17 + ffmpeg; feeds the existing SCORM packager. |
| X19 | **AI avatar / talking-head video** | Script → presenter video. | Synthesia, HeyGen, Coursebox | — | — | ❌ **Integrate-only:** no viable non-metered self-hosted path. Export the script to the user's own Synthesia/HeyGen seat; never built-in billing. |

---

# PART IV — The "confidently addable now" shortlist

If the goal is high-confidence, well-fitted wins (mostly `H` confidence, `S`/`M` effort,
sitting cleanly on existing seams), these are the strongest candidates:

1. **C18 Self-healing generation loop** — reuse the build-report lints to auto-fix before the operator sees output. *(M/H — highest leverage, pure reuse.)*
2. **C11 WCAG conformance pass** + **C12/X17 local Whisper captions** — accessibility is a genuine differentiator and a healthcare-audience fit. *(M/H, no metered API.)*
3. **P10 chart auto-narrative + P11 auto speaker notes** — cheap prompt-layer, immediately useful. *(S/H.)*
4. **C16 glossary/termbank + banned-words guardrail** — directly serves terminology fidelity + neutral naming + UK localization. *(M/H.)*
5. **C15 one-source → translated course** — leverages the subscription CLI for the ES/UK workstreams. *(M/H.)*
6. **X2 regenerate-with-instruction + X3 checkpoint/rewind (→ X13 version history)** — make the AI loop trustworthy. *(S–M / H.)*
7. **C3/X10 CSV → bulk generate** — fits the NovaCoursesMaster catalog workflow. *(M/H.)*
8. **P1 URL→deck, P2 editable outline, P9 editable charts + more types** — round out generation/visuals. *(S–M / H.)*
9. **C6 aggregate/final quiz + C4 more question types + C9 scenario true branching** — the deferred assessment/branching backlog. *(M / H.)*

## Explicitly OUT or gated (and why)

- **Viewer engagement analytics** (P16) — single-operator; delivery owned by PowerPoint/Intellum.
- **Real-time multiplayer co-editing** — operator-grade, not SaaS.
- **Dynamic/live-hosted SCORM** (C14) — needs a hosting backend; conflicts with portable offline SCORM.
- **Built-in AI avatars / premium cloud voices** (X19) / **AI image generation** (P13) — no non-metered path; integrate-only or future.
- **Anything requiring codex** — parked until James has ChatGPT/Codex access (P1/P3/P4 of the audit plan).

---

*Sourcing note: comparable + tangential capabilities were confirmed via live 2025–2026 web
research across vendor docs, release notes, and trade press. Current-state facts were
verified against the repo on disk (HEAD `97d0932`). Effort/confidence are estimates for
planning, not commitments.*
