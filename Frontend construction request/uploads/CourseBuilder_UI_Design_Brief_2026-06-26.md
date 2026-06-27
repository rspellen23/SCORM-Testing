# Course Builder — UI Design Brief

**For:** a visual/interaction designer (e.g. Claude design) redesigning the whole app interface.
**Date:** 2026-06-26 · **Status:** complete inventory, ready to design against.
**What you're designing:** the full front-end of an internal desktop web tool. The brief below
inventories every screen, control, data point, state, and the API behind each action — so you
can redesign the interface AND know exactly what live data each panel can show.

> **The one-sentence ask:** make this powerful-but-utilitarian internal builder *beautiful* —
> calm, modern, confident, easy to move through — without removing any capability or changing
> the underlying step order (each step maps to a real pipeline stage). Keep the **tool's own
> chrome brand-neutral**; only the **content it previews/exports** is TeleTracking-branded
> (see §10).

---

## 1. What the product is

Course Builder is a local, single-user web app (a Python HTTP server serving one `index.html`,
opened in a browser on the user's own machine — **not** a public web app). It turns raw source
material (articles, Word docs, PDFs, Markdown) into two kinds of polished, on-brand output:

1. **Microlearning courses** → SCORM 1.2 / cmi5 / PowerPoint packages for a Learning Management
   System (Intellum). This is the primary job.
2. **Slide presentations** → an on-brand PowerPoint deck. Same AI pipeline, different output.

All AI generation runs on the user's **CLI subscription** (no metered API cost). The app shells
out to a local `claude` (or `codex`) binary. Generation can take seconds to minutes, so
**progress visibility and graceful waiting are central UX problems**, not afterthoughts.

### Mental model
It's a **wizard**: a vertical sequence of numbered stages. You move top to bottom; later stages
depend on earlier ones (you can't build a course before you've generated a script). Two separate
wizards live behind a top-level **mode switch**.

---

## 2. Who uses it & their jobs

- **Primary user:** an instructional designer (one person, power user, repeat sessions). They know
  the domain; they want speed, control, and trust that the output is correct and on-brand.
- **Jobs-to-be-done:**
  - "Turn this folder of source docs into N microlearning courses for the LMS."
  - "Generate a draft, send it to a subject-matter expert (SME) for review, apply their edits, ship it."
  - "Spin up a short, on-brand slide deck from this content."
  - "Regenerate just this one module / one slide / one aspect without redoing everything."
  - "Preview exactly what learners will see before anything is published."

### Emotional targets for the redesign
Trustworthy · calm under long waits · obviously-on-brand output · "I'm always in control and can
see what's happening." The current UI is functional but dense and flat; it should feel like a
considered, premium internal tool.

---

## 3. Design goals & principles

1. **Clarity of progress.** The wizard is the spine. Always show where you are, what's done, what's
   blocked, and why. Long AI steps must stream or show meaningful progress — never a blind spinner.
2. **Keep every capability.** This is an inventory of *what must remain reachable*, not a wishlist
   to trim. Reorganize and beautify; don't remove controls. Advanced/rare options can be tucked
   into progressive disclosure, but must stay accessible.
3. **Neutral, modern tool chrome.** A fresh, beautiful design system of your choosing (type scale,
   spacing, color, components). It should NOT impersonate the TeleTracking brand — that's reserved
   for the content the tool *produces* and *previews*.
4. **Preview is a first-class citizen.** Thumbnails, the slideshow viewer, and course previews are
   how the user trusts the output. Give them room and polish.
5. **Forgiving + reversible.** Reorder, regenerate, re-pick a layout, flip a theme, undo a bad
   generation. Destructive/expensive actions (publish, build-all) should read as deliberate.
6. **Dense data, calm surface.** There are a lot of fields and states. Use hierarchy, grouping, and
   restraint so it never feels like a form dump.

---

## 4. Information architecture

```
┌─ Top bar (global, persistent) ───────────────────────────────────────────┐
│  App title · [ Course creation | Slide presentation ] mode switch ·       │
│  Brand selector · Project: <name>                                         │
└───────────────────────────────────────────────────────────────────────────┘

MODE A — Course creation (default)          MODE B — Slide presentation
  1. Project                                  1. Source & generate
  2. AI account                               2. Review & edit slides
  3. Source materials                         3. Build presentation
  4. Generate microlearning scripts
  5. Apply the SME review
  6. Output format
  7. Generate preview
  8. Publish final courses

Shared overlays/components (both modes):
  • File/folder picker modal
  • Slideshow preview (full-screen)
  • Busy/spinner, result boxes, inline flash, streaming console
```

The two modes are mutually exclusive (switching hides one wizard, shows the other). The top bar,
brand selector, project context, and all shared overlays persist across both.

---

## 5. Global / cross-cutting UI (design these as a reusable system)

These appear throughout. Systematize them once.

### 5.1 Top bar
- **App identity** (left).
- **Mode switch** — two segmented buttons: `Course creation` (`#mode_course`) /
  `Slide presentation` (`#mode_slide`). One is always active.
- **Brand selector** — a `<select id="brand">` populated from the backend (`brands` list, e.g.
  `_default`, `teletracking`). Drives all previews, thumbnails, and exports. *Important and
  currently under-emphasized — it determines how everything looks.*
- **Project header** — `#hdr_project`: "No project open" → "Project: {name}". (Course mode only;
  slide mode is project-less.)

### 5.2 The wizard stage (the core repeating unit)
Each stage = a numbered badge + a heading + a one-line description + a body of controls and
results. The current markup: `.stage` › `.stage-head` (`.num` badge + `<h2>` + `.desc`) ›
`.stage-body`. Design a beautiful, consistent **stage card / step** treatment: collapsed vs active
states, a "done / blocked / current" status, and a clear visual dependency chain would be a big win.

### 5.3 AI-account status
- A status **pill** (`#ai_pill`: "Connected" green / "Not connected" gray) + a detail line
  (`#ai_status`) listing available provider CLIs or install instructions.
- A **provider selector** (`#gen_provider` in course mode, `#sl_provider` in slide mode) and a
  **Re-check** button.
- Design need: a calm "connection" affordance; clear, non-alarming "not connected → here's how" state.

### 5.4 Model selector (appears in both modes)
A `<select>` (`#gen_model_sel` / `#sl_model_sel`) with options:
`Fastest — Haiku` · `Balanced — Sonnet` (default) · `Best — Opus` · `CLI default`.
Pair with a hint ("drafts on Sonnet; the SME-review pass uses Opus"). Treat as a quality/speed dial.

### 5.5 Generation mode (course mode, stage 4)
A 2-way radio: `🧩 Parallel — all modules at once` vs `⚡ Streaming — one pass, watch it write live`.
This is a meaningful choice (speed vs live visibility) — design it as a clear toggle with a one-line
trade-off, not a buried radio.

### 5.6 Busy / waiting
Every long action disables its button and shows a spinner **with an elapsed-seconds counter**.
Because AI calls can run 30s–several minutes, design a genuinely reassuring wait state
(progress, elapsed time, what's happening, ability to keep reading). Streaming actions render a
live text console (`<pre class="gen-live">`) of model output as it writes.

### 5.7 Result feedback
- **Result boxes:** color-coded success (`.ok`, green) / error (`.err`, red), each with an icon, a
  label, an optional file name, action buttons (Preview / Open / Show in Finder), and an expandable
  `<details>` log for failures.
- **Inline flash** (slide rows): a short status line that goes green (success) or red (error).
- **Validation:** e.g. an unreadable slide shows "⚠ this slide's content is unreadable — regenerate it."
- Design a coherent **status/feedback language** (success, error, warning, in-progress, empty).

### 5.8 File/folder picker modal
A modal (`#picker`) for choosing folders/files without a native OS dialog: title, breadcrumb
(`#pk_crumb`), a scrollable listing (`#pk_list`), a "Selected folder" line, and Use/Cancel. Modes:
folder-only, file-only, or both; can filter by extension (e.g. `md, txt, docx, pdf`). Used by nearly
every "Browse…" button. Design one elegant picker; it's heavily reused.

### 5.9 Security note (invisible to design)
Every POST carries a CSRF token via a transparent `window.fetch` wrapper; reads are confined to
allowed roots. **No UI implications** — listed so you know POSTs "just work"; don't design auth.

---

## 6. MODE A — Course creation (8 stages)

The pipeline: set up a project → connect AI → point at sources → generate scripts → (optionally)
apply an SME's review → choose output formats → build a preview → publish. Each stage below lists
its purpose, controls, the data it shows, key states, and the API it calls.

### Stage 1 — Project
*"Every project keeps all its files in its own folder, so you can reopen and continue it any time."*
- **Controls:** workspace folder (`#ws`, readonly + Browse + **Use**) · new project name (`#newproj`
  + **Create**) · existing-project dropdown (`#projlist` + **Open**).
- **Data shown:** `#proj_current` — current project banner + recent-projects list (name + updated date).
- **States:** empty ("Pick a projects location… and click Use"); project-open success banner;
  silent autosave ("saved ✓").
- **API:** `POST /api/workspace`, `/api/project/new`, `/api/project/open`, `/api/project/save`;
  bootstrap `GET /api/init` supplies the projects list.
- **Design note:** this is the "open/create" home base. A project picker that feels like a real
  document workspace (recents, last-opened, path) would elevate the whole app.

### Stage 2 — AI account
*"Generation runs on your subscription (no API cost). Connect by logging into its CLI once."*
- **Controls:** provider selector (`#gen_provider`) · **Re-check**.
- **Data shown:** connection pill (`#ai_pill`) + detail (`#ai_status`).
- **API:** `GET /api/ai-status` → `{providers: {claude:{label,available,install}, …}}`.

### Stage 3 — Source materials
*"The documents and images the course is built from. Filled in from your project; change if needed."*
- **Controls:** source folder/file (`#src`, Browse filtered to `md/txt/docx/pdf`, + **Refresh**) ·
  images folder (`#img`, Browse).
- **Data shown:** `#src_files` — "Selected file: X" or "Source documents (N): a, b, c…".
- **API:** `GET /api/ls`, `/api/listfiles`.
- **Design note:** a clear "these are your inputs" panel — file chips, counts, maybe thumbnails for
  images — builds confidence before the expensive generate step.

### Stage 4 — Generate microlearning scripts
*"Draft the script + an SME review document into the project folder."*
- **Controls:** title (`#gen_title`) · objectives (`#gen_obj`, textarea) · audience (`#gen_aud`,
  textarea) · **archetype** selector (`#gen_arch`, course-structure templates — see §9.5) · unit
  count (`#gen_units`, default "auto") · **model** (`#gen_model_sel`) · **generation mode** radio
  (`#gen_mode`: parallel/streaming) · **Generate scripts** (`#gen_go`).
- **Expandable "capability note"** (`<details>`): what the AI can build (knowledge checks,
  drag-to-sort, flashcards, animations…). Good candidate for a polished "what's possible" affordance.
- **Data shown:** `#gen_results` (success/error, unit count, file path, lint errors; or a live
  streaming `<pre>`); `#script_modules` — the list of generated microlearnings, **each with a ↻
  Regenerate button** (optional guidance) for re-drafting just that module.
- **States:** button → spinner + elapsed; parallel mode shows per-unit progress (spinner → ✓/✗);
  streaming mode shows live text; lint errors in a red box.
- **API:** `POST /api/plan` → `/api/script-unit` (×N) → `/api/save-course` (parallel/staged), or
  `/api/generate` / `/api/generate-stream` (one-shot), or `/api/regenerate-unit` (one module).
- **Design note:** this is the heaviest, most-watched moment. The plan→units→assemble flow is a
  great opportunity for a real progress timeline.

### Stage 5 — Apply the SME review
*"Upload the reviewed document (edits + comments); the script is updated and re-saved."*
- **Controls:** reviewed `.docx` picker (`#rev_doc`) · **Update script from review** (`#rev_go`).
  Marked optional ("skip if no changes were requested").
- **Data shown:** `#script_status` (current script path) · `#rev_results` (success + count of
  comments applied + lint).
- **API:** `POST /api/revise` (and `/api/review` to (re)render an SME doc from a script).
- **Domain context:** the human-in-the-loop step — an SME edits a Word doc (tracked changes +
  comments) and those are merged back. Worth making feel like a clean "round-trip with a human."

### Stage 6 — Output format
*"Choose the formats and scope to produce."*
- **Controls:** format checkboxes (`#b_fmt`: **SCORM 1.2** (default on) · cmi5/xAPI · PowerPoint) ·
  **Run lint** (`#b_validate`, on) · **Include animations** (`#b_animate`, on) · build-scope radio
  (`#b_scope`: **This unit** / **Every unit**) · unit dropdown (`#b_which`, populated from the
  script's "## Microlearning N" sections; disabled when scope = Every unit).
- **API:** `GET /api/scan` to enumerate units.
- **Domain note:** each microlearning ships as its own independent **single-SCO** package; the LMS
  sequences them. (Don't merge them in the UI's mental model.)

### Stage 7 — Generate preview
*"Build the courses to a preview area and review each before publishing — nothing reaches the
output folder yet."*
- **Controls:** **Generate preview** (`#b_go`) · **↻ Refresh** (`loadCourses`).
- **Data shown:** `#b_results` — per-format result boxes (✓/✗, label like "SCORM 1.2 (preview)",
  file name, **Preview** button → opens the playable course; expandable log on failure);
  `#all_courses` — every built course grouped by unit ("📦 Microlearning N" + 👁 Preview, "· not yet
  published" badge for staged).
- **API:** `POST /api/build`, `GET /api/courses`, `GET /preview/<path>` (serves the actual learner-
  facing course player).
- **Design note:** "preview before publish" is the trust gate. The course preview is the real
  learner experience — give it a confident, framed presentation.

### Stage 8 — Publish final courses
*"Publish the approved packages into the project's output folder — ready to upload to the LMS."*
- **Data shown:** `#b_publish` in two sections — **Pending** (approved-but-unpublished items, each
  with **Publish ▸**; plus **Publish all approved**) and **Published** (file name + **Show in
  Finder**, plus **Open output folder**).
- **States:** empty ("Generate a preview in step 7 first"); pending; published.
- **API:** `POST /api/publish`, `GET /api/reveal` (open in Finder).
- **Design note:** publish is the irreversible, "this goes to the LMS" act — make it feel
  deliberate and final, with a clear before/after (pending → published).

---

## 7. MODE B — Slide presentation (3 stages + a console + a viewer)

Turns source docs into an on-brand PowerPoint deck. Project-less; lighter than course mode.

### Stage 1 — Source & generate
*"Point at your raw content (articles, docs); the AI converts it into slides using the shared
layout templates. Same pipeline as a course — the output is a deck."*
- **Controls:** source folder/file (`#sl_src`, Browse `md/txt/docx/pdf` + Refresh) · images folder
  (`#sl_images`, Browse + **Clear**) · provider (`#sl_provider`) · title (`#sl_title`) · slide count
  (`#sl_n`, "auto") · focus (`#sl_focus`, textarea) · audience (`#sl_aud`, textarea) · **Purpose
  preset** (`#sl_preset`: General / Formal / Debrief / Workshop / Client / Pitch — see §9.4) ·
  **model** (`#sl_model_sel`) · **Generate presentation** (`#sl_gen`).
- **Data shown:** `#sl_gen_results`.
- **API:** `POST /api/generate-deck` / `/api/generate-deck-stream`.

### Stage 2 — Review & edit slides  ← *the heart of slide mode*
*"The generated slides land here. Change a layout, flip its theme (Auto / Dark / Light), reorder,
add or remove, or regenerate the checked aspects — same templates as the course blocks."*
- **Controls:** **▶ Preview slideshow** (`#sl_preview_btn`) · the **deck list** (`#deck_list`, one
  row per slide — see §7.1) · **Add slide** layout dropdown (`#deck_add_layout`) + **+ Add slide** ·
  **Open JSON…** (load a deck spec from disk).
- **API (per row):** `POST /api/regenerate-slide`, `/api/slide-svg` (thumbnails),
  `/api/deck-svg` (preview).

#### 7.1 The per-slide row (the "regenerate console")  — design this carefully
Each slide is one dense, powerful row. Anatomy, left → right:
1. **Thumbnail** (`.slide-thumb`) — a live, faithful SVG poster of the actual slide; click opens the
   slideshow at that slide. Cached; re-renders only when the slide changes.
2. **Number chip** (`.slide-n`).
3. **Layout dropdown** (`.sl-layout`) — pick from the 16 layouts (§9.1).
4. **Theme dropdown** (`.sl-theme`) — `Auto theme` / `Dark` / `Light`. "Auto" uses the layout's
   natural theme; Dark/Light flips just the color theme. (Bold/emphasized when not Auto.)
5. **Slide title** (read-only, derived from content).
6. **Scope checkboxes** (`.scope`): **Content** (AI rewords text, keeps layout & colors) · **Layout**
   (AI picks a better-fitting layout) · **Color** (instant local accent reshuffle, no AI).
7. **↻ Regenerate** — runs the checked scopes (Color-only is instant; Content/Layout call the AI).
8. **↑ ↓ ✕** — reorder / remove.
9. **Guidance row** (below): a `↳` "what should change?" text box (guides Content/Layout regen) +
   an inline status/flash line.
- **Design challenge:** this row packs a thumbnail, two dropdowns, a title, three scoped toggles, a
  primary action, reorder controls, a guidance field, and a status line — today it's cramped. Make it
  legible and elegant (consider a card with the thumbnail prominent, scopes as a clear segmented
  control, and the guidance/flash as a calm secondary line). This is the single most important
  component to get right in slide mode.

#### 7.2 Slideshow preview (full-screen overlay `#sl_show`)
- One slide at a time, rendered as a faithful SVG poster (matches the exported PowerPoint exactly).
- Controls: counter (`#show_count`, "3 / 10") · transition picker (`#show_tx`: fade / slide / wipe /
  none) · **‹ Back** / **Next ›** · **✕** close. Keyboard: →/Space/PageDown next, ←/PageUp prev, Esc
  close. Respects reduced-motion.
- **Design note:** this is the "see your deck" moment — give it a premium, distraction-free
  presentation-viewer feel (dark stage, generous margins, smooth transitions).

### Stage 3 — Build presentation
*"Render the slides to an editable, on-brand PowerPoint deck."*
- **Controls:** file name (`#sl_name`) · **deck transition** (`#sl_transition`: none/fade/cut/push/
  wipe/split/cover) · **element animation** (`#sl_animate`: rise (default)/fade/flyleft/flyright/
  none) · output folder (`#sl_out`, Browse) · **Build presentation** (`#sl_go`).
- **Data shown:** `#sl_results` (success + .pptx path).
- **API:** `POST /api/deck`.

---

## 8. Reusable component inventory (build a real design system)

Systematize these — they recur everywhere:

| Component | Where used | Notes for design |
|---|---|---|
| **Wizard stage / step card** | every stage (11 total) | number badge, title, desc, body; needs done/current/blocked states |
| **Primary / ghost / xs buttons** | everywhere | clear hierarchy: primary action vs secondary vs tiny inline |
| **Select dropdown** | brand, model, archetype, preset, layout, theme, transitions | many; unify styling, including "default" emphasis |
| **Status pill** | AI connection | green ready / gray waiting |
| **Result box** | generate/build/publish results | success/error variants, icon, label, file, action buttons, expandable log |
| **Inline flash line** | slide rows, validation | success/error text, transient |
| **Busy button + elapsed timer** | all long actions | reassuring multi-minute waits |
| **Streaming console** | streaming generation | live `<pre>` of model text |
| **File/folder picker modal** | all "Browse…" | folder/file/both modes, ext filters, breadcrumb |
| **Slide row (regen console)** | slide mode | the dense hero component — §7.1 |
| **Live thumbnail** | slide rows | SVG poster, cached, click-to-preview |
| **Full-screen preview overlay** | slideshow + course preview | premium viewer |
| **Segmented toggle / radio pair** | mode switch, generation mode, build scope | clear binary choices with trade-off hints |
| **Checkbox group** | output formats, regen scopes | |
| **Expandable details** | capability note, failure logs | progressive disclosure |
| **Empty states** | every results panel before first run | guide the next action |

---

## 9. Data model (so panels can show real data)

### 9.1 Slide object & the 16 layouts
A deck is an ordered array of slides. Each slide:
```json
{ "layout": "infographic", "content": { /* layout-specific JSON */ }, "theme": "dark" }
```
`theme` is optional (`"dark"` | `"light"`); omit = the layout's natural theme.
**The 16 layouts** (each has a fixed content schema; designer should know the vocabulary):
`divider` (title/section break) · `agenda` (numbered TOC) · `sectionheader` (numbered section
break) · `process` (numbered steps) · `cycles` (circular/looping process) · `comparison` (2–3
columns) · `timeline` (phased milestones: NOW/NEXT/LATER/FUTURE) · `infographic` (poster: challenge
+ framework cards + goals) · `cards` (equal-height card grid) · `quote` (callout + attribution) ·
`statement` (one big principle) · `bullets` (list) · `closing` (thank-you / CTA) · `chart` (bar/
line/pie/stacked/grouped) · `image` (full image + caption) · `imagetext` (image + text).
Within content, repeated elements carry an **accent** enum: `primary` · `secondary` · `tertiary` ·
`dark` (resolved to brand colors at render). The "Color" scope reshuffles these.

### 9.2 Course script & IR
A course is authored as a Markdown script: a title + optional curriculum rationale + grading
directives (`*Graded:* pass 80`, `*Retry:* 2`), then repeating `## Microlearning N: Title` units.
Each unit is slides + knowledge-checks, using a rich block grammar (`*Visual:*`, `*Cards:*`,
`*Process:*`, `*Timeline:*`, `*Comparison:*`, `*Chart:*`, `*Flashcard:*`, `*Categorize:*`,
`*Accordion:*`, `*Quote:*`, `*Statement:*`, `*Note:*`, `*Video:*`, etc.). On build, this parses to a
**course IR** (`course-ir/v1`: ordered typed blocks — heading, paragraph, list, table, visual,
video, knowledgeCheck, cardGrid, accordion, process, flashcard, categorize, timeline, comparison,
chart, infographic, …) which the course player renders. *Design implication:* a course is a
sequence of varied, interactive block types — previews and module lists can surface block counts,
types, knowledge-checks, and assets.

### 9.3 Output formats
SCORM 1.2 · cmi5/xAPI · PowerPoint. Courses are built one independent single-SCO package per
microlearning. Optional lint (conformance check) and scroll-triggered entrance animations.

### 9.4 Deck purpose presets (slide mode)
`general` (let the material decide) · `formal` (exec-ready, 10–12) · `debrief` (retrospective,
6–10) · `workshop` (instructional, 10–16) · `client` (benefit-led, 8–12) · `pitch` (persuasive,
8–12). Presets change the deck's arc, voice, and length — same layouts, same brand.

### 9.5 Course archetypes (course mode)
`concept-explainer` · `software-procedure` · `decision-scenario` · `policy-acceptable-use` ·
`onboarding-company` · `onboarding-role`. Each implies a teaching structure (e.g. goal→steps→
demo→mistakes→recap→KC).

### 9.6 Models & generation modes
Models: Haiku (fastest) / Sonnet (balanced, default) / Opus (best) / CLI default. Modes: **parallel**
(plan, then all units concurrently — fast) vs **streaming** (one live pass — watchable). Streaming
endpoints send raw model text, then a sentinel, then a final JSON result.

---

## 10. Output brand vs tool chrome (important distinction)

- **The tool's own UI:** keep it **brand-neutral and modern** — your design system, not TeleTracking.
- **The content it previews & exports** (slide thumbnails, the slideshow, the course player, the
  built .pptx/SCORM): this **is** TeleTracking-branded, and your layouts must frame it without
  clashing. So you should *know* the output palette/typography even though you won't apply it to the
  chrome. Provide neutral "stage" surroundings (e.g. a soft gray/dark canvas) that make
  TeleTracking-green content pop.

**TeleTracking output kit (for context, not for the chrome):**
- **Primary:** TeleGreen `#1EB16A`. **Darks:** Navy `#003E51`, Deep Navy `#0B2C37`, Charcoal
  `#394047`. **Accents:** Teal `#00A5A7`, Blue `#63ACDB`, Yellow `#F1C700`, Orange `#F69000`, Red
  `#CB4B3C`. **Neutrals:** Slate `#6C7782`, Light Gray `#C7CFD6`, Gray `#EDF0F0`, White.
- **Type (output):** Open Sans (body) / Open Sans Condensed (display).
- **Logo:** white wordmark on dark, color on light.
- Decks render dark-themed by default (navy bg, white ink, green footer band with white wordmark);
  the per-slide theme flag can flip individual slides to light. Your viewer/thumbnail frames should
  look great against both.

> If you'd rather the chrome subtly echo the green for cohesion, that's a judgment call — but the
> brief's default is **neutral chrome, branded content**. (See open question Q3.)

---

## 11. API surface (what data is available behind each action)

Local HTTP server; GET = reads, POST = actions (CSRF-protected, transparent to UI).

**Bootstrap:** `GET /api/init` → `{home, brands, folders, providers, archetypes, workspace,
workspace_set, projects, layouts, slide_examples, slides_out}` — populates every dropdown and the
project list.

**Reads:** `/api/ai-status` (provider availability) · `/api/ls` (folder listing for picker) ·
`/api/listfiles` · `/api/scan` (units in a script) · `/api/readjson` · `/api/courses` (built
previews) · `/api/reveal` (open in Finder) · `/preview/<path>` (serve the course player).

**Course actions:** `/api/project[/new|/open|/save]` · `/api/workspace` · `/api/plan` →
`/api/script-unit` → `/api/save-course` (staged generation) · `/api/generate[-stream]` (one-shot) ·
`/api/regenerate-unit` · `/api/review` · `/api/revise` (apply SME doc) · `/api/build` (SCORM/cmi5/
pptx) · `/api/publish`.

**Slide actions:** `/api/generate-deck[-stream]` · `/api/regenerate-slide` · `/api/slide-svg`
(one thumbnail) · `/api/deck-svg` (whole-deck preview) · `/api/deck` (build .pptx).

Each returns a small JSON object (typical keys: `ok`, `out`/file path, `units`/`count`, `lint_ok`,
`lint_errors`, `slides`, `svg(s)`, `log`, `results`). Streaming endpoints emit live text, a
`<<<COURSE_BUILDER_RESULT>>>` sentinel, then final JSON.

---

## 12. States & feedback to design for (checklist)

- **Empty** (no project / no source / no slides / no results yet) — each panel needs a guiding empty state.
- **Loading / waiting** — spinner + elapsed seconds; streaming live console; per-unit progress.
- **Success** — green result box, file paths, Preview/Open/Finder actions.
- **Error** — red box + expandable log; inline red flash; lint-error list.
- **Warning / validation** — e.g. unreadable slide, "fix invalid JSON on slide N", missing source.
- **Disabled / blocked** — later stages gated on earlier ones; unit dropdown disabled when scope=all.
- **Dirty / unsaved** vs **saved ✓**.
- **Staged vs published** (course mode) — clear "not yet published" → "published" transition.

---

## 13. Accessibility & platform

- Desktop browser, mouse + keyboard. The slideshow already supports arrow-key/Esc nav and
  `prefers-reduced-motion`; keep and extend keyboard support (it's a power-user tool).
- Honor reduced-motion across new transitions/animations.
- Sufficient contrast in both the neutral chrome and against branded (green/navy) content.
- It's a single-window desktop tool; responsive-to-phone is **not** a requirement, but it should
  handle a range of desktop widths and a lot of on-screen data gracefully.

---

## 14. Constraints — what NOT to change

- **Step order & dependencies** map to a real pipeline; keep the wizard sequence and gating.
- **The 16 layout names, the preset/archetype sets, the output formats** are fixed engine vocabulary
  — you can restyle and re-present them, not rename or remove them.
- **Slide content is AI-generated, not hand-typed** in the UI (there is no raw-text editor by design —
  the user regenerates with scopes + guidance instead). Don't reintroduce a JSON/text editor as the
  primary edit surface.
- **No metered-API / cloud assumptions** — it's local and subscription-CLI-driven.

---

## 15. Open questions for the designer

- **Q1.** Should the wizard stay a single long scroll, or become a stepped/collapsible flow (one
  active stage at a time with a progress rail)? The long-scroll is simple; a stepper would reduce
  density. *Recommendation: a progress rail + focus-the-current-stage pattern, with completed stages
  collapsible.*
- **Q2.** How prominent should the **brand selector** be? It silently controls all output looks;
  today it's a small top-bar dropdown.
- **Q3.** Neutral chrome vs a subtle brand echo (see §10) — confirm the intended degree of
  TeleTracking presence in the tool itself.
- **Q4.** The slide row (§7.1) — card layout with a big thumbnail, or a refined dense row? This is the
  highest-leverage component to prototype both ways.
- **Q5.** Course mode and slide mode share a lot but look like one app — should they share a stronger
  visual frame, or feel like two distinct "products" under one roof?

---

*Source of truth: the running app is `dashboard/index.html` + `dashboard/server.py` in the
course-builder project; engine vocab in `src/slide_layouts.py`, `src/authoring.py`,
`templates/slide-layouts/*.example.json`. This brief was generated from a full read of those files
on 2026-06-26 and reflects the current build (16 layouts; per-slide dark/light theme flag; parallel
+ streaming generation; SCORM/cmi5/pptx output).*
