**Subject:** The TeleTracking Course Builder — Capability Showcase
**Estimated Length:** 8–10 minutes
**Learning Objectives:** Understand what the Course Builder is, how it works, where people stay in control, what it takes to run, and where it could go next — while seeing the full range of interactive blocks it can produce.
**Confidence Score:** N/A (internal overview / capability demo)

## Microlearning 1: Meet the TeleTracking Course Builder

**Slide 1 — What You'll Take Away**
*Visual:* graphic · A single calm figure looking toward a small set of simple goal markers, conveying focus and readiness to learn · slot: `objectives.png` · side: left
This short overview shows how I now build training in-house — faster, on-brand, and tracked. It also doubles as a tour: nearly every block on these slides is a different capability of the Course Builder. By the end you'll be able to:
- Describe what the TeleTracking Course Builder is and the problem it solves
- Explain how it turns ordinary content into polished, tracked courses
- Recognize where people stay firmly in control
- Identify what it takes to run it, and where it could grow

**Slide 2 — The Old Way vs The New Way**
For years, building a single course meant licensed authoring tools, vendor lock-in, and long turnaround times. Here is the contrast in one view:
*Comparison:*
::: panel
heading: The Old Way
sublabel: Licensed tools
- Per-seat licenses and vendor lock-in
- Every edit reopens a proprietary tool
- Each brand or language refresh means rework
callout: Slow, costly, and out of our hands.
::: panel
heading: The Course Builder
sublabel: In-house
- No per-seat authoring licenses
- Edit plain text, rebuild in seconds
- Re-brand or re-localize with no rebuild
callout: Fast, and fully in our control.
:::

**Slide 3 — What the Course Builder Is**
*Infographic:* What the Course Builder Is
subtitle: Plain content in — a branded, tracked course out.
footer: One in-house system. No licenses, no vendor wait.
::: left
heading: THE CHALLENGE
intro: Building courses the old way meant:
callout: Slow, costly, and locked to a vendor.
- Licensed tools — per-seat costs and lock-in
- Slow turnaround — every edit reopens a proprietary tool
- Rework — each brand or language redo starts over
::: right
heading: WHAT IT IS
sublabel: 3 PILLARS
::: card
num: 1
title: In-house
body: Our own system — no licenses, no vendor.
accent: primary
::: card
num: 2
title: Branded
body: TeleTracking identity applied automatically.
accent: secondary
::: card
num: 3
title: Tracked
body: Registers completion in our learning platform.
accent: tertiary
::: goals
label: THE PAYOFF
::: goal
title: Faster
body: Days, not weeks.
accent: primary
::: goal
title: Consistent
body: On-brand, every time.
accent: secondary
:::
*Note:* It is not a replacement for our people's expertise — it is a power tool that lets a small team produce far more, far faster.

**Slide 4 — How It Works**
*Visual:* decorative · A simple left-to-right flow of three soft rounded shapes feeding into one polished output card, conveying an automated content-to-course pipeline · slot: `how-it-works.png`
The system follows one clean path, every time:
*Process:*
::: step
title: Bring content
body: Author in Word or Markdown, or import an existing course.
::: step
title: Convert
body: The engine structures it into one standard internal format.
::: step
title: Brand & render
body: TeleTracking colors, fonts, logo, and interactive blocks, applied automatically.
::: step
title: Package
body: Out comes a standards-based course file, ready to upload and track.
:::

**Slide 5 — One Build, Every Format**
Because the content is stored once in a neutral format, the *same* course can be published to whatever standard our platform needs — with no rework.

| Output | Use |
| --- | --- |
| SCORM 1.2 | Broadest LMS compatibility |
| SCORM 2004 | Richer tracking and sequencing |
| cmi5 / xAPI | Modern learning analytics |

*Statement:* Author once. Publish to any standard. Re-brand or re-localize without rebuilding from scratch.

**Slide 6 — The Payoff, Illustrated**
The engine can also render data directly into a course as a native, on-brand chart — generated from numbers, not pasted as a picture:
*Chart:* bar
title: Weeks to ship one course (illustrative)
categories: Licensed vendor path, Course Builder
series: Weeks = 6, 1
yLabel: Weeks
source: Illustrative example for this demo — not measured data.

*Note:* These figures are illustrative, included to demonstrate the chart block. Real metrics would carry a cited source.

**Slide 7 — Where People Stay in Control**
*Visual:* graphic · A calm figure standing at a row of checkpoint markers along a path, hand raised in an approving gesture, conveying human review and sign-off at key gates · slot: `hitl.png` · side: right
The system automates the *assembly*, not the *judgment*. People stay in the loop at every gate that matters — expand each one:
*Accordion:*
::: item
title: Content & accuracy
body: Subject-matter experts write and approve the substance.
::: item
title: Course art
body: Every image is generated by a person, reviewed, and chosen on purpose.
::: item
title: Brand sign-off
body: A human confirms it looks right before it ships.
::: item
title: Final approval
body: Nothing publishes without a person saying yes.
:::

**Slide 8 — Quick Sort: Who Owns What?**
Drag-free sorting check — match each task to who owns it:
*Categorize:* prompt: Sort each task by who owns it.
bucket: The system handles
bucket: People own
item: Applying brand colors and fonts -> The system handles
item: Structuring content into the course format -> The system handles
item: Packaging the standards-based course file -> The system handles
item: Writing and approving the content -> People own
item: Choosing and reviewing the art -> People own
item: Final sign-off before it ships -> People own
:::

**Slide 9 — What It Takes to Run**
*Visual:* decorative · The Course Builder workspace in VS Code · slot: `screenshot-vscode.png`
The engine itself is lightweight and runs on an ordinary laptop — no special hardware. Here is the whole kit:
*Cards:* columns: 2
::: card
title: The engine
teaser: Runs on a standard laptop — no servers, no GPUs.
::: card
title: Authoring
teaser: Word, Markdown, or the browser-based template editor.
::: card
title: The AI layer
teaser: An LLM to draft content and assist the build.
::: card
title: Brand profile
teaser: TeleTracking colors, fonts, and logo — already built in.
:::

**Slide 10 — Two Ways to Power It**
The AI layer is a plug-in choice — the engine works the same either way. Flip each card:
*Flashcard:*
::: card
front: Enterprise ChatGPT
back: The likely default — the business already has an enterprise plan, so there's nothing new to buy or host.
::: card
front: Air-Gapped Open Model
back: An on-premise model like Qwen or Mistral, for when content can't leave our walls. The engine doesn't care which it talks to.
:::
*Note:* Backend-agnostic by design — not locked to any one AI vendor.

**Slide 11 — The Principle Behind It**
*Quote:* The machine speeds up the work. People still own what goes out the door. · by: Course Builder design principle

**Slide 12 — Dig Deeper**
Most learners do not need the internals — but when they do, a single button opens the detail in place, without cluttering the slide:
*Button:* See the technical detail · secondary · modal
::: modal
heading: Under the hood
body: The engine is a compact Python standard-library system — no servers, no GPUs. It reads Word or Markdown, converts to a neutral course format, applies a swappable brand profile, and emits SCORM 1.2, SCORM 2004, or cmi5. It runs air-gapped; the AI layer only assists authoring.
:::

**Slide 13 — What It Could Grow Into**
*Visual:* decorative · A winding road with milestone markers, representing the capability roadmap ahead · slot: `roadmap.png`
Today it builds courses. The same engine and content can power much more, in stages:
*Timeline:*
::: milestone
phase: Today
title: Courses
body: Branded, tracked microlearning from plain content.
accent: primary
::: milestone
phase: Next
title: More than courses
body: Release notes, job aids, email digests, and slide decks from one source.
accent: secondary
::: milestone
phase: Then
title: Practice
body: Click-through simulations and AI roleplay in real product workflows.
accent: tertiary
::: milestone
phase: Later
title: Customer academies
body: Scale the same training out to the hospitals we serve.
accent: dark
::: milestone
phase: Ongoing
title: A feedback loop
body: Use completion and quiz data to auto-flag courses for refresh.
accent: primary
:::
*Note:* A fuller capability roadmap accompanies this overview.

**Slide 14 — Proof: This Course Built Itself**
*Section:* green
You just experienced the product. This entire overview — the branding, the layout, the comparison, the infographic, the process steps, the chart, the accordion, the sorting check, the flashcards, the knowledge check — was authored as plain text and assembled by the Course Builder. What you see is what it produces.
*Section:* end
*Visual:* decorative · This very course, built and rendered by the Course Builder · slot: `screenshot-player.png`
*Transition:* gold bottom

**Slide 15 — Knowledge Check**
*Question:* What is the best one-line description of the TeleTracking Course Builder?
- A) A new licensed authoring tool we purchased from a vendor
- B) An in-house system that turns content into branded, tracked courses, with people in control at every gate
- C) A fully automated AI that writes and publishes training with no human involvement
- D) A replacement for our instructional design team
*Correct Answer:* B
*Feedback — Correct:* Exactly. It is our own system, it automates the assembly, and people own the content, the art, and the final sign-off.
*Feedback — Incorrect:* Not quite. It is in-house (not a purchased license), and people stay in control of content, art, and approval — the system speeds up the assembly, it does not replace judgment.

**Slide 16 — Where It Stands, and Your Part**
The Course Builder is real, working, and already producing branded courses that track in our platform. I built it, and I want to keep developing it — growing what it can do for TeleTracking.
*Statement:* Approve this for more development by me.
*Note:* A nod that this is worth pursuing is all it takes. I'll keep building.

**Articulate Build Notes:**
Subject: The TeleTracking Course Builder — capability showcase / leadership overview
Estimated Length: 8–10 min
Learning Objectives:
- Understand what the Course Builder is and the problem it solves
- See the full range of interactive block types it can render
- Recognize where people stay in control of the work
Confidence Score: N/A (internal overview)
Design Rationale: Problem-centered open (Knowles need-to-know) via the Old-vs-New comparison; the infographic and process give the learner a whole-then-parts mental model (Merrill demonstration); the accordion, sort, and flashcards add active processing at the points where control and choice matter (Gagné event 6, elicit performance); the knowledge check sits near the end (Gagné event 6→8) with a debrief in the closing statement. Block variety here is deliberate — this unit doubles as a capability tour, so each major section showcases a distinct block while still carrying real content.
Build Notes: Capability-showcase variant of the leadership overview. Reuses the 8 existing image slots (objectives/challenge/how-it-works/hitl/roadmap/screenshot-vscode/screenshot-player/hero). The chart on Slide 6 is illustrative demo data, clearly labeled; replace with sourced metrics before any external use.

**Sources & Further Reading:**
- Companion document: Future Capability Extensions
- Companion document: Image Prompts and Screenshot Guide
