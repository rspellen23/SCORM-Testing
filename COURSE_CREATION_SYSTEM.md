# Course Creation System — Re-creatable Specification

> **What this is.** A complete, implementation-ready specification of TeleTracking's
> microlearning Course Creation pipeline, organized around the **human decision points that
> bookend it**: **leadership context + source documentation → full 10–15 minute microlearning
> scripts (SME-approved) → branded courses built to company standard (SME-approved again) →
> SCORM packages that track completion in Intellum.**
>
> **Who this is for.** The TeleTracking development department, to build this process as an
> app (e.g. with Claude Code or Codex). It is written so the system can be **re-created from
> scratch** without access to the original author. Every contract is defined; every segment has
> explicit inputs, outputs, and responsibilities; every gate names who acts and on what.
>
> **The organizing idea.** This pipeline is **anchored on its Human-in-the-Loop (HitL) gates**,
> not on a linear stage count. **Six gates** are where a human supplies input or gives approval;
> the automated **segments** between them are simply the machinery that carries the work from one
> gate to the next. Nothing crosses a gate without a human action. The spine splits into an
> **offline authoring half** (Gates 1–4) and an **Intellum delivery half** (Segment D → Gate 6).
>
> **Status of the reference implementation.** The **back half** (approved script → SCORM) exists
> and is validated end-to-end against Intellum (`nova-course-builder/`, built 2026-06-04; upload +
> publish test confirmed working). The **front half** (context + docs → scripts) and the **two
> review gates** are currently human/LLM judgment; this document specifies them so they can be
> codified. Source of truth for the back half is the code in `src/`; this document describes its
> interfaces. **Two areas — course-creation templates (Segment C) and visual-asset specs (§10) —
> are intentionally deferred to a future session and marked as placeholders, not invented here.**

---

## 0. The pipeline — a HitL-anchored spine

```
─────────────────────────  AUTHORING HALF (offline)  ─────────────────────────
●  GATE 1 — CONTEXT INTAKE       objectives · gaps · audience · metrics · constraints
│                                ⟡ optional read-only Intellum peek — name/slug dedup only
│  ╰─ Segment A:  assemble + validate the Context Pack
│
●  GATE 2 — POINT TO SOURCES     select source-documentation folder(s)/refs
│  ╰─ Segment B:  ingest → normalize → decompose AND draft full scripts
│                 (10–15-min microlearnings) → lint → render review .docx
│
●  GATE 3 — SME SCRIPT + STRUCTURE APPROVAL
│         review scripts + breakdown together; ⟲ edits / additions / subtractions to scripts & structure
│  ╰─ Segment C:  CREATE the courses from approved scripts — using brand TEMPLATES
│                 (uniform, company standard); compose cover images (background + centered icon)
│                 + place premade, slot-named in-slide images          [build & asset specs: §10, deferred]
│
●  GATE 4 — FINAL COURSE APPROVAL
│         review the BUILT courses; final sign-off, ⟲ minor edits only
│
──────────────────────  DELIVERY HALF (one Intellum session)  ─────────────────
│  ╰─ Segment D:  apply minor edits → package as SCORM (upload-ready) → ⟡ host →
│                 create · categorize · path · persona (draft) → publish worklist
│
●  GATE 5 — LMS VERIFY           confirm the draft renders + tracks completion
│  ╰─ Segment E:  apply any fixes; stage the draft(s)
│
●  GATE 6 — APPROVE / PUBLISH    Submit → Approve → Publish → Confirm     ⟡ token
   ╰─ Segment F:  resolve published IDs → learner links → hand off to enrollment team
```

`⟡ = Intellum token, requested on demand (1-hr, never persisted).`

**The two Intellum touches.** Intellum is accessed in exactly two places: (1) an **optional
read-only peek at the very start** to make sure we aren't reusing names/slugs, and (2) **one
continuous session from upload through publish** (Segment D → Gate 6). The entire authoring half
in between — sources, decomposition, scripting, both content reviews — runs **offline**. The
token is a **just-in-time micro-gate**: the app halts and asks for a token whenever it reaches an
Intellum boundary, and never persists it.

**The two content-approval gates (the product's reason to exist).** There are **two** human
reviews of content, and they are different:
- **Gate 3 — the writing.** The SME approves the **full scripts and the course breakdown
  together**. Edits here can be large: add/remove microlearnings, restructure, rewrite.
- **Gate 4 — the built course.** After the courses are *built to template*, the SME approves the
  **finished course**. This is a final sign-off; **edits should be minor**.

Neither build nor upload runs on unapproved content. The app must make both gates explicit.

**Three artifacts hold the system together** — design to these and the segments stay decoupled:
1. **The Course Brief / Context Pack** (Gate 1 / §1) — the *why* and the *targets*. Grounds
   decomposition so the AI splits content toward leadership's objectives and the gaps the
   training must close, not just along document structure.
2. **The microlearning-draft markdown** (§8) — the **canonical** authoring artifact and the only
   thing the build consumes. SMEs never read raw `.md`; they review a `.docx` rendered *from* it.
3. **The Course IR JSON** (§9) — the machine contract inside the build; the canonical edit
   surface for post-draft and post-build tweaks.

---

# PART I — THE SPINE (walk the gates)

## 1. Gate 1 — Context Intake  →  Segment A

**Goal:** capture the *why* before touching content, so decomposition (Segment B) is driven by
business intent and measured need — not just by how the source docs happen to be organized.
Documents tell the AI **what exists**; the context pack tells it **what the training must achieve
and for whom**.

### Gate 1 — human inputs (from leadership / L&D, not from the source docs)
| Input | Purpose in the pipeline |
|---|---|
| **Training objectives** (from leadership) | The outcomes the program must produce. Become per-course objectives; bias what content is emphasized vs. cut. |
| **Gap-analysis results** | Current vs. desired competency. The *delta* is what the courses should close — high-gap topics get more depth/priority; already-strong areas get light coverage or are skipped. |
| **Target audience & personas** | Who the learner is (role, prior knowledge, system access). Sets reading level, examples, and which persona tracks the output maps to in Intellum. |
| **Success metrics / desired outcomes** | How "did it work" is measured. Shapes knowledge-check focus and lets §2's time-budget priorities track what's assessed. |
| **Constraints** | Compliance mandates, total seat-time ceiling, prerequisites, sequencing rules, deadlines. |
| **Existing-course inventory** | What's already published. **The one optional Intellum touch in the authoring half** — a read-only peek to avoid reusing names/slugs and to reuse/extend rather than rebuild. ⟡ |

### Segment A — output: Course Brief / Context Pack (JSON + 1-page human summary)
```jsonc
{
  "program": "Transfer Center Onboarding 2026",
  "objectives": [
    { "id": "obj-1", "text": "New TC users can create and route a transfer request unaided.",
      "priority": "high", "metric": "≥90% task completion in post-training sim" }
  ],
  "gaps": [
    { "topic": "Request routing rules", "current": "ad hoc", "desired": "policy-consistent",
      "severity": "high" }
  ],
  "audience": { "persona": "Transfer Center User", "prior_knowledge": "low",
                "intellum_track": "transfer_center_user" },
  "constraints": { "max_total_minutes": 90, "compliance": ["HIPAA basics"], "prereqs": [] },
  "existing_courses": ["Cases View Basics (published)"]
}
```

### Responsibilities
- Make the brief a **first-class, reviewable artifact** — leadership confirms it before any
  decomposition. A wrong brief wastes the whole downstream run.
- Carry the brief into Segment B as **grounding** alongside the source corpus.
- Convert relative dates/targets to absolute; record who supplied each input (provenance).
- If no formal gap analysis exists, still prompt for *objectives + audience* at minimum — never
  run decomposition with an empty context pack (log loudly if forced to).
- The existing-course peek is the **only** Intellum call before delivery, it is **read-only**, and
  it requires a token (⟡); if no token is offered, proceed with human-supplied inventory.

---

## 2. Gate 2 — Point to Sources  →  Segment B (ingest → decompose → draft full scripts)

**Gate 2 — human input:** the human points the system at the **source-documentation folder(s) or
references** for this program. Segment B then runs entirely offline to produce review-ready
scripts.

### B.1 — Ingest & normalize
**Goal:** turn a heterogeneous *folder of documentation* into a single **normalized source
corpus**: clean structured text + an extracted image set, with provenance.

| Format | Handler | Notes / status |
|---|---|---|
| `.txt`, `.md` | direct read | plain text; native, zero-dep. **Ready.** |
| `.docx` | structured text extract | done with **stdlib `zipfile`+`xml`** (no `python-docx` dependency — corrected 2026-06-09). **Ready.** |
| **`.doc` (legacy binary), `.rtf`, + any prose format not above** | **LLM-assisted read (CHOSEN 2026-06-09)** | feed the raw document to the model → clean structured text (heading hierarchy + prose). Format-flexible, no per-format parser to maintain. **Caveat: non-deterministic / not byte-reproducible — contained by the guardrail below.** |
| `.pdf` | text + image extract | prefer a deterministic lib (`pymupdf`/`pdfplumber`) when text is selectable; **LLM-assisted read** or OCR (`ocrmypdf`/Tesseract) fallback for scanned/image PDFs. |
| Rise / Evolve exports | structured course decode | Reuse `rise_import.py` (51/51 parse) / Evolve `course.json` (`reference_evolve_course_format`). Treat as *source to re-decompose*. |
| Confluence / web / Google Docs | API/HTML fetch | Confluence REST (`/content/{id}?expand=body.storage`) / Drive API export → strip nav/chrome. Needs the respective auth token. |

> **LLM-assisted ingestion — the chosen normalizer for heterogeneous/legacy docs (2026-06-09).**
> James's call: rather than maintain a parser per legacy format (`.doc`/`.rtf`/odd `.txt`/scanned PDF),
> feed the raw document to the model and have it emit the normalized-corpus JSON below. **Guardrail
> (because this step is non-deterministic):** the normalized corpus is **persisted and treated as a
> reviewable, frozen artifact** — re-runs don't silently change inputs; provenance (`origin`, page/section)
> is recorded; a human spot-checks it against the source before B.2. Determinism is recovered downstream
> (B.2/B.3 run from the frozen corpus; Gate 3 reviews the resulting scripts). **This is the one place the
> pipeline is intentionally non-deterministic — contained at the front and gated by review.**

Output — normalized corpus (JSON):
```jsonc
{
  "project": "transfer-center-basics",
  "sources": [
    { "id": "src-01", "origin": "AdminGuide.pdf", "kind": "pdf",
      "sections": [ { "heading": "Creating a Transfer Request", "level": 2,
                      "text": "…clean prose…", "page": 14 } ],
      "images": [ { "id": "img-01", "file": "assets/src-01-img-01.png",
                    "near_heading": "Creating a Transfer Request", "alt": "" } ] }
  ]
}
```
Responsibilities: **strip chrome** (nav, headers/footers, page numbers); **preserve heading
hierarchy** (B.2 chunks on it); **extract images** to an `assets/` pool keyed by the heading they
sit under; **record provenance** (`origin`, `page`). **One normalizer per format, one output
schema** — adding a format never touches downstream.

### B.2 — Decompose into courses & 10–15-minute microlearnings (context-guided)
Using the **Context Pack (§1)** + the **normalized corpus (B.1)**, decide the **course breakdown**
and segment each course into **10–15 minute microlearning units**, each with a clear objective
traceable to a leadership objective or a gap. This is the **core judgment step** and is
LLM-assisted — a *structured LLM call with deterministic guardrails*, grounded in **both** the
brief and the source segments.

How context drives the split:
- **Objectives** → course boundaries and per-unit objectives; content not serving an objective is deprioritized or cut.
- **Gaps** → set *depth and priority*: high-severity gaps get more units / more practice.
- **Audience** → reading level, example choice, the Intellum persona track.
- **Constraints** (e.g. `max_total_minutes`) → cap total unit count; force prioritization.
- **Existing inventory** → reuse/extend instead of re-authoring duplicates.

The 10–15 minute budget (the chunking rule):
```
unit_minutes ≈ (body_words / 130)          # adult reading ~130 wpm for instructional prose
             + 0.75 * knowledge_checks      # ~45s per interactive KC
             + 0.25 * images                 # ~15s visual processing per figure
```
Target **10–15 min** ⇒ roughly **900–1,500 body words + 2–4 KCs** per unit. Out-of-band units get
split/merged. Constants live in a config block — tune against real completion data.

### B.3 — Draft the full scripts
Decomposition and **full scripting happen in the same pass**: Segment B produces **complete
microlearning scripts already broken into 10–15-min units**, conforming exactly to the **§8
markdown contract** so they parse into the build with zero rework. (There is no separate
"approve the skeleton first" gate — the breakdown and the full scripts are reviewed together at
Gate 3.)

> **Authoring templates drive this step (`templates/`, added 2026-06-08).** Drafting is **not**
> freehand — the LLM reads `templates/AUTHORING_GUIDE.md` (the always-on voice / budget / §8-grammar
> contract) **plus one archetype** that matches the teaching job, then fills its slide-role plan:
> - `concept-explainer` — teach an idea (what → why → how → apply → recap → KC).
> - `software-procedure` — do a task in Nova (goal → steps → demo → mistakes → recap → KC).
> - `decision-scenario` — apply a rule (rule → criteria → scenario → decision KC → debrief).
> - `policy-acceptable-use` — compliance (core rule → why → do/don't → when unsure → KC).
>
> The templates **guarantee uniform, parser-conformant output** (verified: the skeleton round-trips
> through `md_import` with the author-meta correctly cut). In-slide visuals are **not** authored as
> markdown images — each is recorded as a **Visuals/Media plan** line under Build Notes (slug-named),
> which Segment C resolves into an IR `image`/`video`/`audio`/`embed` block. New teaching patterns =
> a new template file (no code change). This is the **front-half (authoring) template layer**; the
> §9.1 block model is the **back-half (build) template layer** they target.
>
> **Non-technical maintenance:** `templates/template-editor.html` is a zero-install, browser-based
> **guided form** for editing the archetypes (roles, headings, guidance). It generates the structural
> markers, so editors can't break the §8 format; **Export** produces a `.md` byte-identical to the
> files in `templates/`. This is how SMEs / L&D colleagues tune templates without touching VS Code.

Responsibilities:
- One `## Microlearning N: Title` per unit; each slide → a `**Slide K — Heading**` block, prose
  drawn **only** from the unit's source segments and shaped by the unit's objective. **No
  hallucinated product behavior** — this trains real software; fabrication is a correctness defect.
- Knowledge checks per §8.3 grammar (`*Question:*` / `- A)` / `*Correct Answer:*` / `*Feedback —*`),
  **unscored**, focused on the unit's success metric.
- **Author-meta block** at the end of each unit, opening with `**Articulate Build Notes:**` (the
  cut marker — see §8.4), carrying Subject / Estimated Length / Learning Objectives / Confidence /
  Build Notes / Sources + which objective/gap it serves. Auto-stripped at build; never reaches the
  learner; also becomes the reviewer's context box in the review `.docx`.
- **Lint before review:** run every generated `.md` through the *actual* `md_import` parser
  (dry-run) and block on unparseable slides, zero-option KCs, missing correct answer, or leaked
  author-meta (§11 guardrails).

**Segment B output:** the canonical `.md` script set + an image manifest, **plus** a review
`.docx` rendered from each `.md` (the SME's reading surface — see Gate 3).

---

## 3. Gate 3 — SME Script + Structure Approval  (⟲ revision loop)

**The first content gate.** The SME reviews **the full scripts and the course breakdown
together** and approves, or sends back edits. **This is where structure is decided** — the SME may
add or remove microlearnings, re-sequence, or rewrite. Edits here can be substantial; that's
expected and cheap relative to fixing built courses.

> **Design rule: `.md` is canonical; `.docx` is the readable face of it.** SMEs find raw markdown
> hard to read, so the app **renders each `.md` into a clean, branded `.docx`** for review. The
> markdown remains the single source of truth the build consumes — the Word doc is a *projection*,
> regenerated whenever the `.md` changes.

### The review document (.docx) — what it must contain
- Course/unit title and the **learning objective** at the top.
- Each slide as a Word **Heading 2** + its body (paragraphs, bullets, tables) — real Word
  formatting, not markdown symbols.
- Knowledge checks rendered legibly: question, lettered options, the **correct answer marked**,
  feedback — in a bordered/shaded box so reviewers see them as checks.
- A clearly-labeled **"Reviewer Notes — not shown to learners"** appendix carrying the author-meta
  (objective served, confidence, sources, build notes) so SMEs know provenance and where to scrutinize.
- TeleTracking-branded Word template (fonts/colors).

### The round-trip (the one part with a real failure mode)
The canonical artifact is `.md`, but SMEs edit in Word. Two supported modes — **start with A**:
- **Mode A — Comment/markup review (recommended initially).** SME uses Word **tracked changes /
  comments**; the change set is applied back to the canonical `.md` (by James or an assisted step),
  then the `.docx` is re-rendered. *No lossy parsing; the `.md` stays clean.*
- **Mode B — Edit-in-Word round-trip (graduate to once trusted).** SME edits the `.docx` body
  directly; a `docx → md` converter re-derives the canonical `.md`, which is **re-linted against
  the §8 grammar**. *Risk: structural drift — Word formatting that doesn't map cleanly to the
  contract. The lint is mandatory; a failing lint blocks downstream.*

**Tooling:** `pandoc` is the natural engine both ways; a branded reference `.docx` template drives
the look. (Pandoc is **not** in the current env — add it, or generate the review `.docx` with
`python-docx`.)

### Approval flow & state
1. App renders `.docx` from the canonical `.md`; presents to the SME.
2. Reviewer edits (Mode A or B); status moves `draft → in_review → changes_requested → approved`.
3. On approval, **freeze the exact `.md` bytes (content hash)**; only that frozen revision is
   eligible for build. The thing reviewed and the thing built are the *same* file — never a
   separate "approved copy" that can drift.

Track per script: `project · course · unit n · status · reviewer · revision history (the .md is
the diffable artifact) · approval timestamp · approver · content hash`.

---

## 4. Segment C — Create the Courses (templates + assets)   ⟵ *core build PROVEN 2026-06-09 (control course end-to-end); template-driven asset assembly being hardened*

**Goal:** turn the **approved, frozen scripts** into **built, branded courses** — uniform and to
company standard — ready for the final review at Gate 4. "Create the course" here means render to a
**reviewable branded course** (HTML preview); SCORM packaging happens *after* Gate 4 (Segment D),
so the thing reviewed is the thing shipped.

### Inputs
- The **approved `.md` scripts** (frozen, content-hashed from Gate 3).
- **Templates — two layers, the authoring layer now exists.** (1) **Authoring templates**
  (`templates/`, §2 B.3) scaffold the *script* — done. (2) **Build templates** = the §9.1 block
  primitives + parameter vocabulary that guarantee every *built course* is uniform/company-standard;
  the renderer-level enforcement spec (which params are mandatory, the brand-CSS map) is still being
  filled in. The authoring template's per-slot guidance already names which IR block each slot
  targets, so the two layers are wired together.
- The **asset library**: the **background image** for covers (we have it), **course icons** (made
  successfully in past sessions), and **premade in-slide images named by slot** (named for where
  they go / what they connect to). (Detailed asset-creation specs: §10, **deferred.**)

### What this segment does
1. **Build to template.** Parse each approved `.md` → **Course IR** (§9) → render a **self-contained
   branded HTML course** (no external CDN). The templates enforce layout/brand uniformity.
2. **Compose the cover image.** Each course cover = **the background image + its course icon,
   centered.** Deterministic code composites the two (the §10 Path-B compositor); the background is
   shared, the icon is per-course.
3. **Place in-slide images by slot-name.** In-slide images are **premade and named for their
   destination**; the renderer resolves them by name rather than parsing them out of the markdown.
   *(This is the intended answer to the "markdown can't carry in-slide images" limitation in §8.2 —
   resolve by slot-name, not by `![]()` parsing.)*
4. **Produce a reviewable preview** — the built course a human can open and read end-to-end.

### Reference tooling (today)
The back half already renders a course directory from an IR (`render.py`); keep that dir (do **not**
auto-package to SCORM yet). Post-edit tweaks go through `from-ir` (rebuild from edited IR) or
`repackage` (re-zip an edited course dir). The IR is the **edit surface** between Gate 4's minor
edits and Segment D's packaging.

> **Deferred (future session):** the concrete template definitions (Segment C) and the full asset
> pipeline (§10). This section states the *contract and intent*; the *how* is specified next.

---

## 5. Gate 4 — Final Course Approval

**The second content gate.** The SME reviews the **built courses** (not just the scripts) and gives
**final sign-off**. By design, **edits at this gate should be minor** — typos, a swapped image, a
spacing fix — because the substance was settled at Gate 3.

- Reviewer opens the built course preview from Segment C; flags minor changes.
- Minor edits are applied via the IR edit surface (`from-ir`) or a direct HTML tweak (`repackage`).
- On final approval, the course is **cleared for packaging + delivery** (Segment D).

If a Gate-4 review surfaces a *substantive* problem (not a minor edit), that's a signal the script
should go back to Gate 3 — log it; don't paper over a structural fix as a "minor edit."

---

## 6. Segment D — Package & Deliver to Intellum  ·  then Gates 5–6

This is the **delivery half** — one continuous Intellum session. The API can **set everything up
but cannot publish or enroll**; those stay human/other-team owned. Design to that line.

### Segment D — package & stage
1. **Apply the Gate-4 minor edits**, then **package as SCORM** (upload-ready `course.zip`).
2. **Host** the SCORM + images at **public HTTPS** URLs.
3. **Create + set up** the course in Intellum via the API (draft): create `CourseScorm`,
   categorize, build/attach Path, set persona (`custom_b`), locale, in-catalog.
4. **Emit a publish worklist** — which draft ids need Submit→Approve→Publish — since the app
   cannot publish itself.

> **SCORM target.** The packager emits a **SCORM 1.2 package** (`imsmanifest.xml` declares 1.2);
> the player also speaks the 2004 runtime API, but the *package/manifest is 1.2 only* — the
> broadly-accepted, Intellum-validated target.

### Upload channels — getting the `course.zip` into Intellum (SFTP **or** manual)
Two live ways (James, 2026-06-09); pick per job:
- **Manual UI upload** — upload the SCORM zip in the Intellum admin UI, per course. Default for one-off /
  net-new courses; pairs directly with the Gate-6 Submit→Approve→Publish flow.
- **Intellum SFTP dropbox** — `sftp.exceedlms.com` (validated in the Phase-2 migration: clean single-file
  uploads to **1.29 GB**, ~45–65 s each; `feedback_intellum_sftp_batch_tolerance`). Best for **batches**;
  Intellum ingests the dropped packages. Don't over-fragment.
> **Not to be confused with the retired item.** What was retired (2026-06-03) is using `sftp:///` as the
> **hosting URL in the CSV `Activity Resource URL` column** — host that file at **public HTTPS** instead.
> The SFTP **dropbox-to-Intellum upload channel** above is a *different thing* and remains available.

### Segment D.0 — SCORM package assembly: required internal structures + order of operations
**The contract for a valid, multi-media-capable SCO.** A built unit is packaged as a **single-SCO
SCORM 1.2** zip (one microlearning = one SCO; a multi-unit course is N SCORMs bundled in an Intellum
Path — see §12 #20). The package must contain **all** of the following internal structures, assembled
in this order:

1. **`index.html` at the SCO root** — the launch file (`href="index.html"`). Self-contained: no
   external CDN; brand + player are bundled in-package.
2. **`brand/`** — `tokens.css`, fonts, logo/favicon. The page links these relatively.
3. **`player/`** — `player.css` (block + media styling) and `player.js` (the SCORM runtime adapter +
   gate/KC/media completion logic).
4. **`assets/`** — every course medium referenced by the IR: images **and the new media** (`.mp4`
   self-hosted video, `.mp3`/audio, `.vtt` caption tracks, posters). Embedded/streamed media
   (`video embed`, `embed`) live at an external `https` URL and are **not** in `assets/`.
5. **`imsmanifest.xml`** — written **last** (it enumerates everything else). Required nodes:
   - `<manifest version="1.2">` + `<metadata>` (`ADL SCORM` / `1.2`).
   - one `<organizations default>` → one `<organization>` → one `<item identifierref>` (the SCO; title set).
   - one `<resource type="webcontent" adlcp:scormtype="sco" href="index.html">` containing a `<file>`
     entry for **every file under the course dir** — brand, player, and all bundled media.
   - **No `<adlcp:masteryscore>`** — the course is **completion-only / unscored**; a mastery score
     with no reported `cmi.core.score` strands some LMSs at `incomplete`. *(Fixed 2026-06-08 — was
     hardcoded `100`; §12 #25.)*

**Assembly order (deterministic):** render the IR → course dir (steps 1–4, `render.py`) → **then**
walk the finished dir and emit the manifest enumerating it (step 5, `scorm.py`) → zip with
`index.html` at the root. The manifest is regenerated on every package; an existing one is never
double-added.

**Completion & multi-media tracking (`player.js`).** The SCO reports `completed` (1.2
`cmi.core.lesson_status` / 2004 `cmi.completion_status`) when **all three** are satisfied: every
Continue gate passed · every knowledge check attempted · every **required** medium played to `ended`.
Required media = self-hosted `video file` / `audio` with `requireComplete:true` (the renderer tags
these `data-require="1"`). **Embedded/streamed media cannot be made required** — cross-origin iframes
don't expose playback state — so an `embed`/`video embed` never blocks completion (design limit, not a
bug; §12 #26).

> **Self-hosted vs. streamed — the packaging trade-off.** Self-hosted media is bundled in the zip:
> fully offline, reproducible, gateable on completion — but inflates package size (mp4 re-compressed by
> the zip's DEFLATE; consider `ZIP_STORED` for already-compressed media if size matters). Streamed
> media keeps the package tiny but depends on the host being reachable from the LMS and can't gate
> completion. Choose per course; both are first-class in the IR.

### Connection & auth (the JIT token)
- **Tenant:** `https://academy.teletracking.ai`. **v3 base** `/api/v3` (Bearer token) for
  create/categorize/path; **v2** `/api/v2` (`api_key`) for scalar field writes to the live master.
- **Tokens today are 1-hour test tokens.** Production auth (JWT signed with the app's RSA key,
  `iss` = app UID) is **not yet wired up** — open item. **Never persist tokens.** The app requests
  a token on demand at this boundary (⟡) and refreshes it on expiry within the same session.
- **Endpoint-discovery signal:** `401` = unknown route (catch-all, *not* an auth failure);
  `422` = route exists, body invalid. The only reliable probe.

### Two setup mechanisms (use both — they cover different jobs)

**A. Bulk CSV upload (admin UI) — stand up many courses at once.**
A **76-column CSV** defines each activity; **generate it programmatically** (we already produce
`Nova_Learning_Course_List.csv`), but the **upload action is UI-driven** — there is no `/imports`
or `/bulk` API endpoint. Key columns (full spec: `Internal Works/Intellum Bulk upload CSV column
description.docx`):

| CSV column | Field | Notes |
|---|---|---|
| Type | activity type | `scorm` (also path / collection / assessment / link / file / evolve…) |
| Activity Code | unique id | per-activity stable key |
| Name | course name | |
| Activity Resource URL | the SCORM file | **public HTTPS** (the column also accepts `sftp:///`, but team SFTP hosting was **retired 2026-06-03** — use HTTPS) |
| Cover Art URL / Hero Image URL / Mobile Hero Image URL | **the §10 assets** | public-readable HTTPS |
| Locale | `en` / `en-GB` / … | 50+ supported |
| In Catalog / Is Active / Is Restricted | visibility | booleans |
| Learning Objectives List | objectives | **pipe-separated** `\|` |
| Summary / Description (HTML) / URL Slug / SEO Title | catalog copy | |

**B. REST API (v3 + v2) — targeted per-course / taxonomy operations.**

| Operation | API-drivable? | How |
|---|---|---|
| Create a SCORM course | **YES** | `POST /api/v3/courses` with `type:"CourseScorm"` |
| Update scalar fields (persona `custom_b`, name, summary, `is_active`, `in_catalog`, `is_restricted`) | **YES (v2)** | `PUT /api/v2/courses/:id` (`api_key`). v3 PATCH writes only the draft. **Lands as a PENDING change — needs a UI publish.** |
| Attach / detach a Topic or Track category | **YES** | `PATCH /api/v3/courses/:id` `associated_categories:[{id}]`. No bulk endpoint — iterate GET→PATCH. |
| Create a category (Topic / Track) | **YES** | `POST /api/v3/categories` name + locale + `parent_category_id`. 7 hidden roots: Topics EN `44429` / UK `45466`, Tracks EN `44428` / UK `45501`. |
| Build a Path + populate its child list | **YES** | path create + child-list edits (net-new paths built in both locales during taxonomy remediation). |
| Create a locale translation (en-GB record) | **YES** | `POST /course_translations` (creates the locale record as a side effect; probe nearby ids to find it). |
| Read categories / paths / topics as a **collection** | **NO** | 401 catch-all. Only `GET /api/v3/categories/:id` single-fetch works; the 7 hidden roots `404`. |

> No bulk API endpoint anywhere — "tag N courses" = loop `GET /courses` → `PATCH` each.
> Mechanism A (CSV/UI) is the bulk path; Mechanism B (API) is the surgical path.

### Gate 5 — LMS Verify
**Human:** confirm the staged draft **renders correctly and tracks completion** in Intellum.
*(Whether a draft can be fully verified before publish, or needs a throwaway publish to preview, is
to be confirmed in the first end-to-end run.)* Any issues → **Segment E**: apply fixes, re-stage.

### Gate 6 — Approve / Publish (the hard line — stays manual)
Course versioning is on, so **every v2 PUT / v3 edit lands as a PENDING draft**. Going live requires
a human to walk each draft through the admin UI: **Submit → Approve → Publish → Confirm**
(~3 clicks/draft). James is currently the **sole editor / approver / publisher** — a real
serialization bottleneck. So the app must:
- **Emit a publish worklist** and **track confirmation**, because it cannot perform the action.
- Use the **published id (not the draft id)** for anything learner-facing.

**Segment F — handoff.** After publish: resolve **published ids**, build **learner links**
(`academy.teletracking.ai/courses/<published-id>`), and **hand off the structured catalog** to the
enrollment team.

### Auto-enrollment — explicitly NOT this system's job (different owner)
Getting a course *enrolled* to the right learners is a **separate rule object**
(`auto_enrollment_id`): **UI-managed, not API-readable**, owned by the **enrollment team
(Kristen)**. This system's responsibility ends at **structure** — created, categorized,
persona-tagged, pathed, in-catalog. **Auto-enroll rules are out of scope.** (Creating a new
top-level Topic *group* / hidden root is likewise admin-UI-only — roots `404` on the API.)

---

# PART II — CONTRACTS & REFERENCE

## 7. (reserved)

*Section intentionally omitted in the renumber; the spine is Part I, the locked contracts follow.*

## 8. THE CONTRACT — microlearning-draft markdown grammar

> The precise, machine-parsed format and **canonical** authoring artifact. It is locked. The front
> half **must emit exactly this**; the build (`md_import.py`) parses it with the regexes below; the
> Gate-3 review `.docx` is rendered *from* it. **Reproduce verbatim if rebuilding either half.**

### 8.1 Document structure
```markdown
# <Course / batch title>            ← preamble, ignored by parser (everything before first ##)

## Microlearning 1: <Unit Title>
**Slide 1 — <Heading>**
<body…>

**Slide 2 — <Heading>**
<body…>

**Slide 3 — Knowledge Check**
*Question:* <prompt>
- A) <option>
- B) <option>
- C) <option>
- D) <option>
*Correct Answer:* C
*Feedback — Correct:* <text>
*Feedback — Incorrect:* <text>

**Articulate Build Notes:**         ← author-meta CUT POINT (§8.4)
…anything from here down is dropped…

## Microlearning 2: <Unit Title>
…
```
- Units split on `^## Microlearning <N>`; `--which N` selects unit N; text before the first unit is
  preamble.

### 8.2 Slide & body grammar
| Element | Markdown | Parsed to (IR) |
|---|---|---|
| Slide heading | `**Slide K — Heading**` (em-, en-dash, or hyphen) | `heading` block, level 2, navy band |
| Paragraph | plain lines, blank-line separated | `paragraph` |
| Bulleted list | `- item` / `* item` | `list` (`ordered:false`) |
| Numbered list | `1. item` | `list` (`ordered:true`) |
| Table | GitHub pipe table (`\| … \|` + `\|---\|` row) | `table` |
| Bold/italic/code/link | `**b**` · `*i*` · `` `c` `` · `[text](https://…)` | inline HTML (sanitized) |

Parser anchors (from `md_import.py`, reproduce exactly):
```python
SLIDE_RE = re.compile(r'^\*\*Slide\s+\d+\s*[—–-]\s*(.+?)\*\*\s*$', re.M)
META_CUT = re.compile(r'^\*\*(Articulate Build Notes|Sources?(\s|&|$)).*', re.M | re.I)
```

> **In-slide images — the `*Visual:*` directive (added 2026-06-08).** The body grammar has no
> markdown-image element (`md_import` ignores `![]()`), so in-slide visuals use a **parser-supported
> slot directive** instead — parallel to `*Question:*`:
> ```
> *Visual:* <type> · <description/alt> · slot: `<asset-filename>`
> ```
> `md_import` emits an `image` block at that position, resolving `<slot>` against the labelled-asset
> folder (`--images`); unresolved slots keep `assets/<slot>` for later supply. `<type>` ∈
> `screenshot|graphic|diagram|photo|decorative` (decorative ⇒ no caption). This is the named-asset
> resolution intended in §10 — now wired into the grammar. The hero/cover remains separate (`--hero`).
> **Video/audio are not `*Visual:*`** — they build to `video`/`audio` IR blocks via the Media plan.
> **Standard: Slide 1 is always a Learning Objectives slide carrying a `*Visual:*`.**
>
> **Two body parser facts to know:** (1) only `*Feedback — Correct:*` is captured — a
> `*Feedback — Incorrect:*` line is written by authors but **dropped** by the importer
> (§12 #18); (2) any body text **before the first `**Slide 1 —**`** is silently discarded (§12 #19).

### 8.3 Knowledge check grammar
A slide is a KC if its heading contains "knowledge check" **or** its body contains `*Question:*`.
Options matched by `^\s*-\s*[A-D]\)\s*(.+)$`; the `*Correct Answer:*` letter → zero-based index. KCs
are **unscored** (completion-only). A KC with zero parsed options is dropped.

### 8.4 Author-meta (non-learner-facing)
Everything from the first `META_CUT` match onward is **excluded** from the build. The cut only fires
on a line starting `**Articulate Build Notes` or `**Sources`.
> **⚠ Ordering is load-bearing.** The cut keys on those two markers **only**. So the author-meta
> block **must open with `**Articulate Build Notes:**`** (the cut marker); any meta lines placed
> *above* it (`Subject`, `Estimated Length`, `Learning Objectives`, `Confidence Score`) are **not**
> stripped and **leak to the learner**. Put all meta *under* the marker. The §11 linter must assert
> no meta field appears before the first cut.

Conventional contents under the marker: `Subject`, `Estimated Length`, `Learning Objectives`,
`Confidence Score`, build notes, `**Sources & Further Reading:**`. Used for reviewer context (Gate-3
appendix) and provenance — invisible to learners by design.

---

## 9. The IR contract (inside the build)

`md_import.py` emits **Course IR** — `schema: "nova-course-ir/v1"` — the machine contract the
renderer + packager consume. Full block set + fields in [`schema/IR_SCHEMA.md`](schema/IR_SCHEMA.md),
validated by `schema/ir.schema.json`.
- One IR JSON + an `assets/` folder = a complete course.
- Blocks: `heading · paragraph · headingParagraph · image · imageText · **video · audio · embed** ·
  note · statement · list · table · divider · continue (gate) · knowledgeCheck`.
- **Multi-media blocks (added 2026-06-08):** `video` (`mode:"file"` self-hosted `<video>` bundled in
  the zip, optional `poster` + `.vtt` `captions`; or `mode:"embed"` streamed `<iframe>`), `audio`
  (`<audio>` + optional `transcript`), `embed` (generic interactive `<iframe>` — H5P / sim / widget).
  `requireComplete:true` folds the media into the completion tally (player marks it on `ended`) —
  **honored only for self-hosted `video file`/`audio`**; cross-origin embeds can't expose playback, so
  it's ignored there. Full field list: `schema/IR_SCHEMA.md`.
- IR is the **post-draft / post-build edit surface** — edit JSON in VS Code, then `from-ir`
  rebuilds. Don't hand-edit generated HTML except one-off via `repackage`.
- **Rise-parity expansion (design done 2026-06-08):** to emulate the visual + interactive variety of
  the 51 real Rise courses, a `band` section-background parameter + four interactive block types
  (`accordion`, `tabs`, `flashcard`, `process`) are fully mapped in
  [`schema/RISE_PARITY_BLOCKS.md`](schema/RISE_PARITY_BLOCKS.md) (Rise→IR shapes, renderer/player/a11y
  approach, §9.1 cost, build order, 51-course acceptance test). Implementation is next-session.

### 9.1 Block model — primitives + parameters (the template contract)
A "template" in this system **is a content block**, not a whole-page layout. A course is an
**ordered list of reusable blocks** the renderer composes **deterministically** — so authors mix
and match without bespoke design work. This is the mechanism the **Segment C course-creation
templates** rest on. One rule keeps it powerful *and* cheap to extend:

> **A small set of PRIMITIVE blocks + a PARAMETER vocabulary — not a proliferation of one-off block
> types.**

So *"text with an image in an outlined box, offset to the right"* is **not** a new block type — it's
the existing `imageText` primitive plus parameters:
```jsonc
{ "type": "imageText", "side": "right",
  "box": "outlined", "offset": "right", "emphasis": "normal", "density": "comfortable",
  "src": "assets/...", "html": "..." }
```
Proposed parameter vocabulary: `box` (none/outlined/filled/accent) · `offset` (none/left/right) ·
`align` (left/center) · `emphasis` (normal/strong/quiet) · `density` (compact/comfortable). Renderer
maps each to brand CSS; unknown params are ignored, so the contract degrades safely.

**Mapping-cost tiers (the scaling line, §11):**
- **New *instance*** (another paragraph, another `imageText`) → **no mapping**; just data.
- **New *parameter/variant*** of an existing primitive → **cheap**; one renderer branch.
- **New *block type*** → **costs a mapping**: a parser rule *and* a renderer rule. Reserve new types
  for genuinely new structures.

### 9.2 Block style sources (brand-native first; curated borrowing second)  ⟵ *proposed*
Block visuals come from the **TeleTracking brand tokens** by default. For richer treatments
(outlined cards, callouts, reveal/accordion patterns) the team *may* borrow from **MIT-licensed
open-source UI libraries — e.g. [uiverse.io](https://uiverse.io/)** (MIT, commercial-use OK, no
mandatory attribution). **Curated styling source, not a bulk import** — each borrowed component
must be: (1) **re-skinned to brand tokens**, (2) **self-contained for SCORM** (inline any CDN/font),
(3) **accessibility-vetted** (keyboard/ARIA/contrast for 508/WCAG), and (4) **mapped in as one block
variant** (it carries the new-type cost). Harvest only the few content-bearing treatments, and only
**after** the §9.1 taxonomy exists. *(Proposed — not yet implemented.)*

---

## 10. Visual asset generation — covers, in-slide images, LMS tiles   ⟵ *in-course art path BUILT 2026-06-09 (ChatGPT prompt generator); Figma catalog path specced*

**Goal:** produce the branded images every course needs **programmatically from templates**, so
imagery is brand-consistent and never requires manual click-and-export per asset.

### Art scope (clarified 2026-06-09 — James): CBS makes *in-course* art only
- **In-course art → the ChatGPT image-prompt generator (BUILT 2026-06-09). This is CBS's whole art job.**
  Illustrations, the Slide-1 **Learning Objectives** plate, the in-course hero image, and in-lesson visuals
  are generated from ChatGPT. The builder **emits the paste-ready prompt per asset** (`gen-prompts` CLI /
  `src/prompts.py`): constant TeleTracking style preamble + per-asset **color hierarchy** (primary/secondary
  interchangeable across TeleGreen #1EB16A / Teal #069696 / Deep Navy #0B2C37 / Blue #539BD2, **TeleGreen
  always present**) + **orientation** (objectives/aside→portrait, hero→landscape, full→landscape,
  spot→square) + the asset description. `type:screenshot` = a real capture (no prompt). Detail:
  `schema/ASSET_PIPELINE.md`.
- **Intellum catalog tile art (Cover/Hero/Mobile that show in the LMS catalog) → OUT OF CBS SCOPE.** James
  (2026-06-09): that's an **LMS-level concern, not part of creating a course or a SCORM package.** The Figma
  cover/hero "recipes" belong to the separate Intellum-catalog workflow, not CBS. CBS produces the SCORM and
  hands it off; catalog tile imagery is set elsewhere. (§6 CSV Cover/Hero/Mobile columns are filled by that
  separate LMS process, not by CBS.)

> **Rule of thumb: CBS makes the art *inside* the course (ChatGPT). The Intellum *catalog tile* is an LMS
> task outside CBS.**

### What we know now (the contract + the confirmed approach)
- **Course covers = background image + a centered course icon.** We **have the background image**;
  the **course icons have been made successfully in past sessions**. The composition is
  deterministic (background + icon centered → named output).
- **In-slide images are premade and named by slot** — named for where they go / what they connect
  to in the course. The renderer resolves them by name (this is the §8.2 answer to in-slide images).
- **Where images are consumed:** the course **cover/hero** (Segment C build + the §6 upload tile)
  and **in-slide images** (placed during Segment C).

### Two implementation paths (from the 2026-06-02 Figma capability audit)
- **Path A — Figma-native:** author templates in Figma; per item swap icon/background/text via a
  custom plugin, then **export via the Figma REST API** (token). **Constraint:** REST is
  **read + export only** — it cannot create/position nodes; composition runs in the Plugin API or Path B.
- **Path B — code compositor (recommended for "place icon centered, save as x").** A deterministic
  image library (**Pillow / ImageMagick / sharp / resvg**) composites layers in code from a JSON
  spec. Figma is the **design source for the plates**; per-course composition runs in code, **zero
  Figma-in-the-loop at runtime** — reproducible, testable, version-controlled. Best for the
  background+centered-icon cover pattern at volume.

**Naming convention** (so downstream resolves assets with no manual mapping): derive from the course
slug + asset role — `<slug>_cover.png`, `<slug>_hero.png`, `<slug>_tile.png`,
`<slug>_<n>_diagram.png`. Segment C and the §6 tile upload look these up.

> **Design spec written 2026-06-08 → [`schema/ASSET_PIPELINE.md`](schema/ASSET_PIPELINE.md):** asset
> taxonomy (Figma `.svg` element art · labelled screenshot/graphic folder · per-unit objectives plate ·
> Path-B LMS cover/hero/mobile), the `<slug>_<n>_<role>.<ext>` naming contract, the missing-asset lint,
> and a build order. The **consumption side is already built** — the `*Visual:* type · desc · slot:`
> directive (§8.2) + the `--images` slot resolver; this section's flows produce what fills that folder.

### Not in reach (from the audit — don't design against these)
- **Figma Make** (prompt-to-prototype): no public programmatic entry.
- **Live UI automation of the Figma desktop app:** anything requiring clicks in the running editor
  stays manual.

---

## 11. App architecture guidance (for the dev team)

### Separation of concerns
- **Deterministic code** owns: context-pack capture (Gate 1 forms), ingestion/normalization (B.1),
  the time-budget math + packing guardrails (B.2), markdown↔IR parsing (build), render/package,
  Intellum upload (Segment D), the **md↔docx rendering** for review (Gate 3), and the **§10 asset
  composition**.
- **LLM calls** own: the *judgment* in B.2 (context-guided segmentation) and B.3 (prose drafting).
  Wrap each as a **structured call with JSON-schema output**, fed the unit's own source segments
  **plus the context pack** (grounding — prevents fabrication, keeps the split on-objective).
  Prompt-cache the static system prompt + brand/voice guide.
- **The human** owns the gates: Gate 1 brief sign-off, **Gate 3 script+structure approval**, **Gate
  4 final course approval**, template/plate design in Figma (§10), the Gate-5 verify, and the Gate-6
  Submit→Approve→Publish.

### State model (minimum)
```
Program  ── has one  ─→ ContextPack (objectives, gaps, audience, constraints, inventory)
Program  ── has many ─→ Source (file/ref, normalized corpus)
Program  ── has many ─→ Course ── has many ─→ Unit (plan: title, objective, est_minutes, confidence, status)
Unit     ── has one  ─→ Script (.md canonical, review .docx, revisions, status, content hash)   ← Gate 3
Script   ── builds   ─→ Build (course dir/preview, IR snapshot, assets) ── final-approved ─→ ready  ← Gate 4
Build    ── packages ─→ SCORM (course.zip) ── lands as ─→ Intellum activity (draft id → published id;
                                                          publish_status; categories/path/persona)
Block    ── usage    ─→ BlockUsage (block type, variant/params, pedagogical_purpose, course, unit)
```

### Guardrails to bake in
- **Context required**: no decomposition without at least objectives + audience in the pack.
- **Time-budget validation**: flag any unit outside 10–15 min by the B.2 formula.
- **Contract validation**: lint generated/round-tripped `.md` through the *actual* `md_import` parser
  in a dry-run before review/build (unparseable slides, zero-option KCs, missing correct answer,
  leaked author-meta = blocking). **Assert no author-meta field appears before the first cut marker.**
- **Two-gate approval enforcement**: build only from a Gate-3 `approved` + frozen hash; package +
  deliver only after Gate-4 final approval.
- **Grounding/citation**: every slide traces to a source segment *and* an objective/gap; surface
  uncited claims to the reviewer.
- **No silent truncation**: unsupported format, oversized source, or dropped pre-slide body = log
  loudly, never drop silently.

### Build order if recreating from scratch
1. Stand up the **§8 markdown contract** + **§9 IR** + the existing `md_import → render → scorm` chain
   (back half). Verify one hand-written script → SCORM → Intellum.
2. Add **Gate 1** context-pack capture + the **Gate-3 md→docx review render** (highest SME value).
3. Add **Segment B.1** normalizers, format by format (`docx`/`md` first; then `pdf`; then Rise/Evolve
   via existing decoder; then Confluence/GDocs).
4. Add **Segment B.2/B.3** context-guided decomposition + full scripting (LLM + time-budget
   guardrails) → emits the §8 contract; gate behind the §8 linter.
5. Wrap **Gate 3** review (docx render + comment round-trip), approval state, freeze-on-approve.
6. Add **Segment C** course creation — render to a reviewable branded course **to template**; wrap
   **Gate 4** final approval. *(Template specs: future session.)*
7. Add **§10 visual assets** — Path-B compositor (background + centered icon) + slot-named in-slide
   images, slug-based naming. *(Asset specs: future session.)*
8. Add **Segment D + Gates 5–6** — package SCORM, host, v3/v2 API client (create `CourseScorm`,
   categorize, path, scalar fields), publish-worklist generator. Stop at the human publish gate;
   leave auto-enroll rules to the enrollment team.

### Expansion model — instances vs. variants vs. types (the scaling line)
| Add… | Mapping needed? | Cost | Examples |
|---|---|---|---|
| **A new instance** of an existing thing | None | Free — just data | another course/script, another `imageText`, another cover from a template |
| **A new variant/parameter** of an existing primitive | One renderer branch | Cheap | `box:outlined`, `offset:right`, a new accent treatment |
| **A new block type / layout / source format** | **Parser + renderer (or normalizer) mapping** | One bounded dev task, then reusable | a new IR block, a Tier-3 accordion, a borrowed §9.2 component, a new ingest format |

**Implication:** push expansion toward **instances and variants** and reserve new *types* for
genuinely new structure. That's what keeps the system mostly drag-and-drop while staying deterministic.

### Block-effectiveness feedback loop (advisory, not a gate)  ⟵ *proposed*
1. **Capture usage metadata now** — every block records `{type, variant/params, pedagogical_purpose}`
   (the `BlockUsage` record), even before the analytics exist.
2. **Join to a feedback signal** — SME review ratings (Gates 3/4) + Intellum completion data → a
   "block effectiveness" view.
3. **Keep it advisory.** Surface as a dashboard that *informs* authors and the B.3 generator — **do
   not** auto-prune the palette (monoculture / premature-convergence risk).
**Caveat:** needs real data volume — "capture now, analyze later."

---

## 12. Open decisions & risks (resolve before/while building)

| # | Item | Owner | Notes |
|---|---|---|---|
| 1 | **PDF text extraction** — not in current env | dev | Add PyMuPDF/pdfplumber + OCR fallback. |
| 2 | **Confluence / Google auth** | dev + IT | Service token / OAuth for the fetch handlers. |
| 3 | **docx tooling** — pandoc not installed | dev | Add `pandoc` (md↔docx) or build review docx with `python-docx` + a branded template. |
| 4 | **Review round-trip mode** | James + dev | Start **Mode A**; graduate to **Mode B** only once the converter+linter are trusted. |
| 5 | **Decomposition is LLM judgment** | James + dev | Gate 3 reviews scripts + breakdown together — keep until segmentation quality is trusted. |
| 6 | **Time constants** (130 wpm, KC/image seconds) | James | Tune against real Intellum completion data. |
| 7 | **Context-pack source** | James + leadership | Where do objectives/gap-analysis live, and in what format? |
| 8 | **Evolve write/clone** gated on JWS-signature test | James | Read/decompose fine; generating *into* Evolve unproven. |
| 9 | **mondrian custom blocks + interactives** (accordion, tabs, flashcard, process) | dev | **Design in `schema/RISE_PARITY_BLOCKS.md`.** 4 interactive types = straightforward (next-session). **Custom blocks (mondrian) = the hard one (CORRECTED 2026-06-08):** NOT empty — a free-form canvas in `course.mondrian.blockuments`/`items` (~1,981 nodes, tiptap text, template-based) carrying real content incl. **Learning Objectives (23 courses)**. Needs a tiptap→HTML + blockument decoder; start with a 1-block PoC. |
| 10 | **Figma image composition path** (§10) | James + dev | REST export-only; pick **Path B** for the background+centered-icon covers. |
| 11 | **Course-creation templates** (Segment C) | James + dev | **Authoring layer DONE (2026-06-08)** — `templates/` (guide + `_skeleton` + 4 archetypes), verified parser-conformant. **Remaining:** the build-side enforcement spec (which §9.1 params are mandatory per block, the brand-CSS map). |
| 12 | **Visual-asset specs** (§10) | James + dev | **Designed 2026-06-08** — `schema/ASSET_PIPELINE.md`: asset taxonomy (Figma SVG / screenshot folder / objectives plate / LMS cover-hero-mobile), slot-naming contract, Path-B compositor, missing-asset lint. Consumption side (`*Visual:*` + slot resolver) is **built**; production flows implement next-session. |
| 13 | **Intellum production auth** | dev | JWT/RSA-signed production tokens not yet wired — only 1-hour test tokens. Required before any automated/cron API run. |
| 14 | **Publish is human-serial** | James + LMO | Edits land as PENDING drafts; Submit→Approve→Publish→Confirm is UI-only, James sole approver — the bottleneck. Consider adding approvers. |
| 15 | **Path POST body shape** | dev | `POST /paths` route exists but body schema only partly documented — canary before bulk path creation. |
| 16 | **LMS verify vs. publish** (Gate 5/6) | James + dev | Confirm whether a draft can be fully verified pre-publish or needs a throwaway publish — settle in the first E2E run. |
| 17 | **In-slide images** (§8.2) | ✅ done | **Resolved 2026-06-08** — the `*Visual:* type · desc · slot:` directive is parsed by `md_import` into an `image` block, slot resolved via `--images`. Verified end-to-end. |
| 18 | **Incorrect-feedback dropped** (§8.3) | dev | Importer captures only `*Feedback — Correct:*`. Capture Incorrect too (cheap), or document that authors shouldn't write it. |
| 19 | **Pre-first-slide body dropped** (§8.1) | dev | Text between `## Microlearning N:` and `**Slide 1**` is silently discarded — violates "no silent truncation." Warn or keep. |
| 20 | **Course vs. unit granularity** | doc/dev | `from-md --which N` builds **one** unit → one `course.zip` → one Intellum activity. A "course" (group of units) = **many** SCORMs, bundled in an Intellum **Path**. |
| 21 | **md accent overrides brand default** | dev | `md_import` hardcodes accent `#069696` (Teal); documented + renderer default is TeleGreen `#1EB16A`. Reconcile (use default, or expose `--accent`). |
| 22 | **Mode B lint circularity** (Gate 3, with #4) | dev | The "re-lint for leaked author-meta" depends on the `**Articulate Build Notes**` marker — which a lossy `docx→md` could garble. Validate the marker survives the round-trip first. |
| 23 | **Borrowed UI components** (§9.2, uiverse.io) | dev | MIT/commercial-OK, but each needs re-skin to brand tokens + self-containment for SCORM + 508/WCAG a11y, and carries a new-type mapping. Curated harvest only, after the §9.1 taxonomy exists. |
| 24 | **Block-effectiveness loop** (§11) | James + dev | Needs data volume; instrument `BlockUsage` now, analyze later. Keep advisory, never auto-prune. |
| 25 | **`masteryscore` removed** (✅ 2026-06-08) | done | Manifest hardcoded `<adlcp:masteryscore>100>` but nothing reports a score → completion-only model contradiction (some LMSs hold `incomplete`). **Removed** from `scorm.py`. |
| 26 | **Embed completion not observable** (Seg D.0) | accepted limit | `video embed` / `embed` are cross-origin iframes → playback `ended` not observable → `requireComplete` ignored for them. Self-host (`video file`/`audio`) when completion must be gated on the media. |
| 27 | **Media in md grammar** (§8) | partial | **Images: done** — `*Visual:*` directive (#17). **Video/audio/embed:** still IR-only (author via the IR edit surface or the Build-Notes Media plan). A `*Video:*`/`*Audio:*` directive could be added on the same pattern if front-half authoring needs it. |
| 28 | **Streamed-media zip bloat** (Seg D.0) | dev | Self-hosted mp4/mp3 are re-DEFLATEd by the packager (wasteful on already-compressed media). Consider `ZIP_STORED` for `.mp4/.mp3/.png/.jpg` if package size becomes an issue. |

---

## 13. Provenance of this spec

- **OBSERVED** (read from code/disk this session): the §8 markdown grammar and §9 IR are extracted
  verbatim from `src/md_import.py`, `src/cli.py`, `schema/IR_SCHEMA.md`; the back-half chain from
  `cli.py._emit`; SCORM-1.2-manifest fact from `src/scorm.py`; the TeleGreen `#1EB16A` /
  md-hardcoded `#069696` accent discrepancy from `brand/tokens.css` + `md_import.py`.
- **RECALLED** (project memory): back half validated 51/51 Rise imports + 10 Responsible-AI SCORMs;
  Intellum upload + publish confirmed working; brand kit; Evolve/PDF gaps; **SFTP retired
  2026-06-03**. The **§10 Figma capability tiers** (REST export-only; plugin variant-generator;
  Make/desktop out of reach) are from the **2026-06-02 Figma Automation Briefing**. The **Segment D
  / Gates 5–6 Intellum facts** — v3/v2 endpoints, `CourseScorm` create, v2 scalar-write→PENDING,
  category PATCH, 7 hidden roots, the Submit→Approve→Publish gate, auto-enroll being a separate
  UI-managed/enrollment-team object — are OBSERVED/RECALLED from live API probing
  (`reference_intellum_api_v3`, `reference_intellum_groups_enrollments`) and the bulk-CSV column spec.
- **GENERATED** (proposed / design, not yet implemented): the **HitL-anchored spine** (§0) and its
  gate/segment framing; the Context Pack (§1), normalized-corpus + unit-plan schemas + time-budget
  formula (Segment B); the Gate-3 docx-review round-trip; the **two-gate approval model** (Gate 3
  scripts+structure, Gate 4 built course); **Segment C course-creation framing** and **§10 asset
  framing** (both with detailed specs **deferred to a future session**); the §9.1 primitives+
  parameters block model and §9.2 borrowed-styling source; the §11 expansion model + effectiveness
  loop + architecture/build order. Recommendations for the dev team. (uiverse.io facts — MIT,
  HTML/CSS/Tailwind — verified via web search.)
```
