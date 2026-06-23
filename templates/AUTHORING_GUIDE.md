# Microlearning Authoring Guide — the contract I apply to every script

> **What this is.** The always-on rules for drafting a microlearning *script*
> (the §8 markdown the build consumes). Read this **plus** one archetype file from this folder,
> then produce a clean, conformant `## Microlearning` unit. This guide is the front-half analog of
> the §9.1 build template: it governs *what I write*; the IR blocks govern *how it's built*.
>
> **Golden rule:** the script must parse through `src/md_import.py` on the first try. Every rule
> below exists because the parser (or a learner) depends on it.

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
  `**Slide 1 — Learning Objectives**`, a `*Visual:*` line, and a short "you will be able to…" list
  (3–5 learner-facing outcomes). These mirror the formal objectives in Build Notes. *(This is a
  required standard — never omit the objectives slide.)*
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

## 4. The Build-Notes block (under the cut marker)

```
**Articulate Build Notes:**
Subject: <one line>
Estimated Length: <e.g. 11 min>
Learning Objectives:
- <objective — traceable to a Context-Pack objective or gap>
Confidence Score: <High | Medium | Low — flag any slide built on thin sourcing>
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
  default = the brand accent `#1EB16A`).

## 6. How to use a template

1. Read this guide + the chosen archetype file (`concept-explainer.md`, `software-procedure.md`,
   `decision-scenario.md`, or `policy-acceptable-use.md`).
2. Follow the archetype's **slide-role plan**; fill each `{{PLACEHOLDER}}` with grounded content.
3. **Strip all `<!-- guidance -->` comments and the role labels** from the final output — they're
   for me, not the learner.
4. Self-check against §2 before returning: parses? meta under the marker? KC well-formed? in budget?
