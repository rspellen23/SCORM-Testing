# Nova Course Builder — Complete Spec, How-To & Source

> Self-contained guide. Everything needed to run, understand, and iterate on the
> pipeline that turns a content doc (`.docx`/`.md`) or a Rise export into a
> TeleTracking-branded HTML microlearning packaged as **SCORM 1.2/2004** that tracks
> completion in Intellum. Built & validated end-to-end 2026-06-04.

> **To rebuild from this doc alone:** recreate the file tree below, paste each file's
> contents from the SOURCE section, then `pip install python-docx` and run the CLI.
> Brand fonts/logos/images are binary — get them from the TeleTracking Branding Resources
> + Articulate Assets folders (paths noted), or use the accompanying project zip.


---


# === README.md ===

# Nova Course Builder

Turns course content into **TeleTracking-branded HTML microlearnings packaged as SCORM**
that track completion in Intellum. Built 2026-06-04.

Two front doors into the same pipeline:

```
[.docx + image folder] ─┐
                        ├─→ Course IR ─→ branded HTML ─→ SCORM 1.2/2004 zip
[Rise -raw- export]   ─┘
```

- **Architecture:** our own static template (Option A), styled from the TeleTracking
  brand kit — not Rise's runtime. (Option B = emit Rise JSON, deferred research thread.)
- **Brand:** Open Sans / Open Sans Condensed fonts + the official color palette, both
  bundled in `brand/`. Accents snap to the nearest official brand hex.
- **Knowledge checks:** interactive multiple-choice with feedback, **unscored**
  (completion-only to the LMS).

## Usage

```bash
# Author a new course from Word + a folder of named images
python3 src/cli.py from-docx course.docx --images ./images --out build/course.zip

# Re-skin an existing Rise export into our branded SCORM
python3 src/cli.py from-rise rise-raw.zip --out build/course.zip

# Just inspect the IR an importer produces
python3 src/cli.py import-rise rise-raw.zip --out build/course.ir.json
```

Then upload `build/course.zip` to Intellum as a `CourseScorm`.

## Authoring grammar (.docx)

See the header of [`src/docx_import.py`](src/docx_import.py). Heading 1/2/3 map to
title/section/subheading; normal paragraphs and lists pass through; line markers add
structure: `[HERO: file | title | subtitle]`, `[IMG: file | alt | caption]`,
`[IMG-LEFT/RIGHT: file | alt]`, `[NOTE] …`, `[STATEMENT] …`, `[CONTINUE]`, and a
`[KC] … [/KC]` block (`Q:` prompt, `*` correct option, `-` wrong option, `FB:` feedback).

## Layout

```
brand/      tokens.css (palette + @font-face), fonts/, Logo.png, Favicon.png
player/     player.css (block styles), player.js (nav + KC + SCORM 1.2/2004 API)
schema/     IR_SCHEMA.md
src/        common.py, rise_import.py, docx_import.py, render.py, scorm.py, cli.py
examples/   sample_course.docx + sample_images/
build/      output
```

## Validated (2026-06-04)
- **51/51** Rise courses (EN+UK) import with **0 failures**, 713 blocks, **0 unresolved images**.
- Full round-trip `Managing Bed Requests`: Rise → IR → branded HTML → 22 MB SCORM,
  valid `imsmanifest.xml`, sanitized HTML (0 editor cages, 0 stranded white-on-navy text).
- `.docx` authoring path: hero, bands, note, list, continue-gating, KC all render.

## Known gaps / next steps
- **`mondrian` blocks are skipped** (188 across the library). They store content by
  reference (`blockumentId`/`globalBlockId`) outside the inline tree; some are decorative,
  some may carry primary copy. Importer logs the count per course so content-heavy ones
  are visible. Recovering them = the deferred Option-B research thread.
- **Tier-3 blocks** (accordion, tabs, flashcard, fullscreen process) skipped in v1.
- **Not yet uploaded to Intellum** — needs James's manual upload + completion-tracking test.
- **SCORM schema `.xsd` files** are referenced, not bundled (matches the working v6 packages);
  add them if any target LMS rejects the manifest.


# === schema/IR_SCHEMA.md ===

# Course IR (Intermediate Representation) — schema

The IR is the **contract** between every stage. Importers (Rise, .docx) emit IR; the
renderer + packager consume it. One IR JSON file + an `assets/` folder = a complete course.

```jsonc
{
  "schema": "nova-course-ir/v1",
  "id": "managing-bed-requests",        // slug; used for filenames + SCORM identifier
  "title": "Managing Bed Requests",
  "locale": "en",                        // "en" | "en-GB"
  "accent": "#1EB16A",                   // course accent (defaults to TeleGreen)
  "hero": {                              // optional cover
    "image": "assets/hero.jpg",
    "title": "Managing Bed Requests",
    "subtitle": ""
  },
  "blocks": [ /* ordered list, see below */ ]
}
```

## Block types (Tier 1 + Tier 2)

Every block is `{ "type": "...", ...fields, "gated": false }`.
`gated: true` means the block is hidden until the preceding `continue` block is clicked
(the renderer wraps gated runs in a reveal container).

| type | fields | notes |
|---|---|---|
| `heading`     | `level` (1–3), `html` | section title; `level:1/2` render as a navy band |
| `paragraph`   | `html` | body copy (sanitized inline HTML: strong/em/a/ul/li kept) |
| `headingParagraph` | `level`, `headingHtml`, `html` | combined |
| `image`       | `src`, `alt`, `caption`, `variant` (`full`/`hero`) | full-width figure |
| `imageText`   | `src`, `alt`, `html`, `side` (`left`/`right`) | image beside text |
| `note`        | `html` | callout box (accent left-border) |
| `statement`   | `html` | large centered emphasis line |
| `list`        | `ordered` (bool), `items` ([html,…]) | numbered/bulleted |
| `table`       | `html` | passthrough `<table>` HTML (sanitized) |
| `divider`     | — | spacer rule |
| `continue`    | `text` (default "CONTINUE") | gate; reveals the next gated run |
| `knowledgeCheck` | `prompt`, `multi` (bool), `options` [{`html`,`correct`}], `feedback` | interactive, **unscored** |

## Importer responsibilities
- Resolve Rise media references → a real filename copied into `assets/`.
- Sanitize block HTML: drop `data-editor-id`, unwrap the editor `<div>`, strip
  Rise-theme-coupled inline `color`/`font-size` styles (our brand CSS owns those),
  keep semantic tags (`strong`, `em`, `a`, `ul`/`ol`/`li`, `table`, `br`).
- Carry the course accent from the Rise `theme.colorAccent` if present (else TeleGreen).

## Renderer responsibilities
- Emit one self-contained HTML page (no external CDN), link `brand/tokens.css`,
  `player/player.css`, `player/player.js`.
- Wrap each run of blocks after a `continue` (until the next `continue`) in a
  `.nv-gated` container so the player can reveal it.

## Packager responsibilities
- Wrap the rendered course dir in a SCORM 1.2 `imsmanifest.xml` (+ 2004 supported at runtime).
- Zip with `index.html` at the SCO root.


---
# === FILE TREE ===
```
README.md
brand/Favicon.png
brand/Logo.png
brand/tokens.css
brand/fonts/OpenSans-Bold.ttf
brand/fonts/OpenSans-ExtraBold.ttf
brand/fonts/OpenSans-Italic.ttf
brand/fonts/OpenSans-Regular.ttf
brand/fonts/OpenSans-SemiBold.ttf
brand/fonts/OpenSansCondensed-Bold.ttf
brand/fonts/OpenSansCondensed-Light.ttf
schema/IR_SCHEMA.md
schema/ir.schema.json
examples/sample_course.docx
examples/sample_images/screen1.png
.vscode/extensions.json
.vscode/settings.json
player/player.css
player/player.js
src/cli.py
src/common.py
src/docx_import.py
src/md_import.py
src/render.py
src/rise_import.py
src/scorm.py
```

---
# === SOURCE (paste these back into the matching paths) ===


## `brand/tokens.css`

```css
/* TeleTracking brand tokens — sourced from TeleTracking_BrandingColors.png + TeleFonts (2026-06-04).
   Single source of truth for the course look. Players reference var(--tt-*) only. */

@font-face { font-family: "Open Sans"; font-weight: 400; font-style: normal;
  src: url("fonts/OpenSans-Regular.ttf") format("truetype"); font-display: swap; }
@font-face { font-family: "Open Sans"; font-weight: 400; font-style: italic;
  src: url("fonts/OpenSans-Italic.ttf") format("truetype"); font-display: swap; }
@font-face { font-family: "Open Sans"; font-weight: 600; font-style: normal;
  src: url("fonts/OpenSans-SemiBold.ttf") format("truetype"); font-display: swap; }
@font-face { font-family: "Open Sans"; font-weight: 700; font-style: normal;
  src: url("fonts/OpenSans-Bold.ttf") format("truetype"); font-display: swap; }
@font-face { font-family: "Open Sans"; font-weight: 800; font-style: normal;
  src: url("fonts/OpenSans-ExtraBold.ttf") format("truetype"); font-display: swap; }
@font-face { font-family: "Open Sans Condensed"; font-weight: 700; font-style: normal;
  src: url("fonts/OpenSansCondensed-Bold.ttf") format("truetype"); font-display: swap; }
@font-face { font-family: "Open Sans Condensed"; font-weight: 300; font-style: normal;
  src: url("fonts/OpenSansCondensed-Light.ttf") format("truetype"); font-display: swap; }

:root {
  /* --- Brand palette (exact hex from the brand sheet) --- */
  --tt-telegreen:    #1EB16A;  /* primary */
  --tt-teal:         #069696;
  --tt-blue:         #539BD2;
  --tt-navy:         #003E51;
  --tt-deep-navy:    #0B2C37;
  --tt-yellow:       #ECBD00;
  --tt-orange:       #F27D05;
  --tt-red:          #BD362F;  /* used for incorrect-answer state */
  --tt-accent-green: #4EE89E;
  --tt-mint:         #ABF7BC;
  --tt-black:        #0C0E0F;
  --tt-charcoal:     #394047;
  --tt-slate:        #6C7782;
  --tt-light-gray:   #C7CFD6;
  --tt-gray:         #EDF0F0;
  --tt-white:        #FFFFFF;

  /* --- Semantic roles (themeable per course via --tt-accent) --- */
  --tt-accent:        var(--tt-telegreen);
  --tt-accent-ink:    #0d5e39;          /* darker accent for text-on-light */
  --tt-band-bg:       var(--tt-navy);   /* heading band / KC card background */
  --tt-band-ink:      var(--tt-white);
  --tt-page-bg:       var(--tt-white);
  --tt-surface:       var(--tt-gray);   /* tinted block background */
  --tt-ink:           #1b2127;          /* body text */
  --tt-ink-soft:      var(--tt-slate);
  --tt-note-bg:       #eaf7f0;          /* callout tint (telegreen-derived) */
  --tt-note-border:   var(--tt-telegreen);
  --tt-correct:       var(--tt-telegreen);
  --tt-incorrect:     var(--tt-red);

  /* --- Type --- */
  --tt-font-body:    "Open Sans", system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
  --tt-font-head:    "Open Sans Condensed", "Open Sans", system-ui, sans-serif;

  /* --- Shape / rhythm --- */
  --tt-radius:        14px;
  --tt-radius-lg:     22px;
  --tt-content-width: 820px;
  --tt-gap:           1.6rem;
}
```

## `player/player.css`

```css
/* Nova Course Player — block + layout styles. Brand values come only from ../brand/tokens.css. */

* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: var(--tt-font-body);
  color: var(--tt-ink);
  background: var(--tt-page-bg);
  line-height: 1.6;
  font-size: 18px;
  -webkit-font-smoothing: antialiased;
}
img { max-width: 100%; height: auto; display: block; }

/* ---- App chrome ---- */
.nv-topbar {
  display: flex; align-items: center; gap: 14px;
  padding: 12px 22px; background: var(--tt-deep-navy); color: var(--tt-white);
  position: sticky; top: 0; z-index: 20;
}
.nv-topbar img { height: 26px; }
.nv-topbar .nv-title { font-family: var(--tt-font-head); font-weight: 700; font-size: 1.15rem; letter-spacing: .3px; }
.nv-progress { flex: 1; height: 6px; background: rgba(255,255,255,.18); border-radius: 99px; overflow: hidden; }
.nv-progress > span { display: block; height: 100%; width: 0; background: var(--tt-accent); transition: width .35s ease; }

.nv-main { max-width: var(--tt-content-width); margin: 0 auto; padding: 0 22px 120px; }

/* ---- Cover / hero ---- */
.nv-hero { position: relative; margin: 0 -22px 2rem; }
.nv-hero img { width: 100%; max-height: 360px; object-fit: cover; }
.nv-hero .nv-hero-cap {
  position: absolute; inset: auto 0 0 0; padding: 28px 22px;
  background: linear-gradient(transparent, rgba(11,44,55,.82));
  color: var(--tt-white);
}
.nv-hero .nv-hero-cap h1 { font-family: var(--tt-font-head); margin: 0; font-size: 2.4rem; }

/* ---- Blocks (generic) ---- */
.nv-block { margin: var(--tt-gap) 0; }
.nv-block--tint { background: var(--tt-surface); border-radius: var(--tt-radius); padding: 1.4rem 1.6rem; }

.nv-h1, .nv-h2, .nv-h3 { font-family: var(--tt-font-head); color: var(--tt-navy); line-height: 1.2; margin: .4em 0; }
.nv-h1 { font-size: 2.3rem; font-weight: 700; }
.nv-h2 { font-size: 1.8rem; font-weight: 700; }
.nv-h3 { font-size: 1.35rem; font-weight: 700; color: var(--tt-accent-ink); }

/* heading "band" (Rise put headings on a navy bar) */
.nv-band {
  background: var(--tt-band-bg); color: var(--tt-band-ink);
  border-radius: var(--tt-radius); padding: 1.1rem 1.4rem; margin: var(--tt-gap) 0;
}
.nv-band .nv-h1, .nv-band .nv-h2, .nv-band .nv-h3 { color: var(--tt-band-ink); margin: 0; }

.nv-p { margin: .6rem 0; }
.nv-p a { color: var(--tt-accent-ink); }

/* image variants */
.nv-figure { margin: var(--tt-gap) 0; }
.nv-figure img { border-radius: var(--tt-radius); width: 100%; }
.nv-figure figcaption { color: var(--tt-ink-soft); font-size: .9rem; margin-top: .5rem; text-align: center; }
.nv-aside { display: grid; grid-template-columns: 1fr 1fr; gap: 1.6rem; align-items: center; margin: var(--tt-gap) 0; }
.nv-aside.right { direction: rtl; } .nv-aside.right > * { direction: ltr; }
.nv-aside img { border-radius: var(--tt-radius); }
@media (max-width: 680px){ .nv-aside { grid-template-columns: 1fr; } }

/* impact: note (callout) + statement */
.nv-note {
  background: var(--tt-note-bg); border-left: 6px solid var(--tt-note-border);
  border-radius: 10px; padding: 1.1rem 1.3rem; margin: var(--tt-gap) 0;
}
.nv-statement {
  text-align: center; font-family: var(--tt-font-head); font-weight: 700;
  font-size: 1.6rem; color: var(--tt-navy); padding: 1.2rem 1rem; margin: var(--tt-gap) 0;
}

/* lists / tables */
.nv-list { margin: var(--tt-gap) 0; padding-left: 1.4rem; }
.nv-list li { margin: .4rem 0; }
.nv-table-wrap { overflow-x: auto; margin: var(--tt-gap) 0; }
.nv-table-wrap table { border-collapse: collapse; width: 100%; }
.nv-table-wrap th, .nv-table-wrap td { border: 1px solid var(--tt-light-gray); padding: .6rem .8rem; text-align: left; }
.nv-table-wrap th { background: var(--tt-navy); color: var(--tt-white); font-family: var(--tt-font-head); }
.nv-table-wrap tr:nth-child(even) td { background: var(--tt-gray); }
.nv-divider { height: 1px; background: var(--tt-light-gray); border: 0; margin: 2rem 0; }

/* ---- Continue gate ---- */
.nv-continue { text-align: center; margin: 2.2rem 0; }
.nv-btn {
  font-family: var(--tt-font-head); font-weight: 700; letter-spacing: .5px;
  background: var(--tt-accent); color: var(--tt-white); border: 0; cursor: pointer;
  padding: .85rem 2.2rem; border-radius: 99px; font-size: 1.05rem;
}
.nv-btn:disabled { opacity: .45; cursor: not-allowed; }
.nv-gated { display: none; }
.nv-gated.revealed { display: block; animation: nv-fade .4s ease; }
@keyframes nv-fade { from { opacity:0; transform: translateY(8px);} to {opacity:1; transform:none;} }

/* ---- Knowledge check ---- */
.nv-kc { background: var(--tt-band-bg); color: var(--tt-band-ink); border-radius: var(--tt-radius-lg); padding: 1.6rem; margin: var(--tt-gap) 0; }
.nv-kc .nv-kc-prompt { font-family: var(--tt-font-head); font-weight: 700; font-size: 1.3rem; margin-bottom: 1rem; }
.nv-kc-opt {
  display: block; width: 100%; text-align: left; background: var(--tt-white); color: var(--tt-ink);
  border: 2px solid transparent; border-radius: 12px; padding: .8rem 1rem; margin: .5rem 0; cursor: pointer; font-size: 1rem;
}
.nv-kc-opt:hover { border-color: var(--tt-accent); }
.nv-kc-opt.correct { border-color: var(--tt-correct); background: #e9faf1; }
.nv-kc-opt.incorrect { border-color: var(--tt-incorrect); background: #fbeceb; }
.nv-kc-opt.is-disabled { pointer-events: none; opacity: .85; }
.nv-kc-fb { margin-top: 1rem; padding: .9rem 1.1rem; border-radius: 10px; background: rgba(255,255,255,.12); display: none; }
.nv-kc-fb.show { display: block; }
.nv-kc-fb.ok { border-left: 5px solid var(--tt-correct); }
.nv-kc-fb.no { border-left: 5px solid var(--tt-incorrect); }

/* utility: strip leftover Rise inline white text that would vanish on white bg is handled at import,
   but as a guard, force readable ink inside light blocks */
.nv-block :where(span,strong,em,p)[style*="color: rgb(255, 255, 255)"] { color: inherit !important; }
```

## `player/player.js`

```javascript
/* Nova Course Player runtime.
   - Reveals content gated behind Continue buttons.
   - Handles knowledge-check interactivity (interactive + feedback, UNSCORED).
   - Reports completion to the LMS via SCORM 1.2 (API) or 2004 (API_1484_11).
   Completion fires when every Continue gate is passed and every KC has been attempted. */
(function () {
  "use strict";

  /* ---------------- SCORM adapter (1.2 + 2004, with graceful no-LMS fallback) ---------------- */
  var SCORM = (function () {
    var api = null, ver = null;
    function find(win) {
      var n = 0;
      while (win && n++ < 12) {
        if (win.API_1484_11) { ver = "2004"; return win.API_1484_11; }
        if (win.API)        { ver = "1.2";  return win.API; }
        if (win.parent && win.parent !== win) { win = win.parent; continue; }
        break;
      }
      return null;
    }
    function locate() {
      api = find(window);
      if (!api && window.opener) api = find(window.opener);
      return api;
    }
    function get(k){ return ver==="2004" ? api.GetValue(k) : api.LMSGetValue(k); }
    function set(k,v){ return ver==="2004" ? api.SetValue(k,v) : api.LMSSetValue(k,v); }
    function commit(){ try { ver==="2004" ? api.Commit("") : api.LMSCommit(""); } catch(e){} }
    return {
      init: function () {
        if (!locate()) { console.info("[nova] no SCORM LMS — running standalone"); return false; }
        try {
          ver==="2004" ? api.Initialize("") : api.LMSInitialize("");
          set(ver==="2004" ? "cmi.completion_status" : "cmi.core.lesson_status",
              ver==="2004" ? "incomplete" : "incomplete");
          commit();
        } catch(e){ console.warn("[nova] SCORM init error", e); }
        return true;
      },
      complete: function () {
        if (!api) return;
        try {
          if (ver==="2004") { set("cmi.completion_status","completed"); set("cmi.success_status","passed"); }
          else { set("cmi.core.lesson_status","completed"); }
          commit();
        } catch(e){ console.warn("[nova] SCORM complete error", e); }
      },
      quit: function () {
        if (!api) return;
        try { ver==="2004" ? api.Terminate("") : api.LMSFinish(""); } catch(e){}
      }
    };
  })();

  /* ---------------- Course flow ---------------- */
  function ready(fn){ document.readyState!=="loading" ? fn() : document.addEventListener("DOMContentLoaded", fn); }

  ready(function () {
    SCORM.init();

    var gates = Array.prototype.slice.call(document.querySelectorAll(".nv-continue"));
    var kcs   = Array.prototype.slice.call(document.querySelectorAll(".nv-kc"));
    var bar   = document.querySelector(".nv-progress > span");
    var kcSeen = {};

    function updateProgress() {
      var totalSteps = gates.length + kcs.length || 1;
      var done = gates.filter(function(g){ return g.dataset.passed === "1"; }).length
               + Object.keys(kcSeen).length;
      if (bar) bar.style.width = Math.min(100, Math.round(done/totalSteps*100)) + "%";
      maybeComplete();
    }

    var completed = false;
    function maybeComplete() {
      if (completed) return;
      var gatesOk = gates.every(function(g){ return g.dataset.passed === "1"; });
      var kcsOk   = kcs.length === Object.keys(kcSeen).length;
      if (gatesOk && kcsOk) { completed = true; SCORM.complete(); if (bar) bar.style.width = "100%"; }
    }

    /* Continue gates: reveal the next gated region and mark passed */
    gates.forEach(function (gate) {
      var btn = gate.querySelector(".nv-btn");
      if (!btn) return;
      btn.addEventListener("click", function () {
        gate.dataset.passed = "1";
        btn.disabled = true;
        var region = gate.nextElementSibling;
        while (region) {
          if (region.classList && region.classList.contains("nv-gated")) { region.classList.add("revealed"); break; }
          region = region.nextElementSibling;
        }
        updateProgress();
        var tgt = (region || gate);
        tgt.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });

    /* Knowledge checks */
    kcs.forEach(function (kc, i) {
      var opts = Array.prototype.slice.call(kc.querySelectorAll(".nv-kc-opt"));
      var fb   = kc.querySelector(".nv-kc-fb");
      opts.forEach(function (opt) {
        opt.addEventListener("click", function () {
          var isCorrect = opt.dataset.correct === "1";
          opt.classList.add(isCorrect ? "correct" : "incorrect");
          if (!isCorrect) {
            // also highlight the correct one
            opts.forEach(function(o){ if (o.dataset.correct==="1") o.classList.add("correct"); });
          }
          opts.forEach(function(o){ o.classList.add("is-disabled"); });
          if (fb) {
            fb.classList.add("show", isCorrect ? "ok" : "no");
          }
          kcSeen["kc"+i] = true;
          updateProgress();
        });
      });
    });

    updateProgress();
    window.addEventListener("pagehide", SCORM.quit);
    window.addEventListener("beforeunload", SCORM.quit);
  });
})();
```

## `schema/ir.schema.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://teletracking.local/nova-course-ir/v1",
  "title": "Nova Course IR",
  "type": "object",
  "required": ["title", "blocks"],
  "properties": {
    "schema": { "const": "nova-course-ir/v1" },
    "id": { "type": "string" },
    "title": { "type": "string" },
    "locale": { "enum": ["en", "en-GB"] },
    "accent": {
      "type": "string",
      "description": "Official TeleTracking accent hex",
      "enum": ["#1EB16A", "#069696", "#539BD2", "#003E51", "#0B2C37", "#ECBD00", "#F27D05", "#BD362F", "#4EE89E"]
    },
    "hero": {
      "type": ["object", "null"],
      "properties": {
        "image": { "type": "string" },
        "title": { "type": "string" },
        "subtitle": { "type": "string" }
      }
    },
    "blocks": { "type": "array", "items": { "$ref": "#/definitions/block" } },
    "_stats": { "type": "object" }
  },
  "definitions": {
    "block": {
      "type": "object",
      "required": ["type"],
      "properties": {
        "type": {
          "enum": ["heading", "paragraph", "headingParagraph", "image", "imageText",
                   "note", "statement", "list", "table", "divider", "continue", "knowledgeCheck"]
        },
        "gated": { "type": "boolean", "description": "Hidden until the preceding continue gate is clicked" },
        "level": { "type": "integer", "minimum": 1, "maximum": 3 },
        "html": { "type": "string", "description": "Inline HTML (strong/em/a/ul/li kept)" },
        "headingHtml": { "type": "string" },
        "variant": { "enum": ["full", "hero"] },
        "src": { "type": "string", "description": "assets/<file> path" },
        "alt": { "type": "string" },
        "caption": { "type": "string" },
        "side": { "enum": ["left", "right"] },
        "ordered": { "type": "boolean" },
        "items": { "type": "array", "items": { "type": "string" } },
        "text": { "type": "string", "description": "Continue button label" },
        "prompt": { "type": "string" },
        "multi": { "type": "boolean" },
        "feedback": { "type": "string" },
        "options": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["html", "correct"],
            "properties": {
              "html": { "type": "string" },
              "correct": { "type": "boolean" }
            }
          }
        }
      }
    }
  }
}
```

## `src/common.py`

```python
"""Shared helpers: HTML sanitation + slug + asset-name normalisation."""
import re, unicodedata
from html.parser import HTMLParser

# Tags we keep verbatim (no attributes unless whitelisted below).
_KEEP = {"p","br","strong","b","em","i","u","s","sub","sup",
         "ul","ol","li","h1","h2","h3","h4",
         "table","thead","tbody","tfoot","tr","th","td","caption","a"}
# Tags whose wrapper we drop but whose children we keep (Rise's editor cages).
_UNWRAP = {"div","span","font","section","article"}
_ATTR_OK = {"a": {"href"}, "th": {"colspan","rowspan"}, "td": {"colspan","rowspan"}}
_VOID = {"br"}


class _Clean(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
    def handle_starttag(self, tag, attrs):
        if tag in _UNWRAP:
            return
        if tag in _KEEP:
            ok = _ATTR_OK.get(tag, set())
            kept = "".join(
                ' %s="%s"' % (k, _esc(v)) for k, v in attrs
                if k in ok and v is not None
            )
            self.out.append("<%s%s>" % (tag, kept))
    def handle_endtag(self, tag):
        if tag in _KEEP and tag not in _VOID:
            self.out.append("</%s>" % tag)
    def handle_startendtag(self, tag, attrs):
        if tag in _KEEP:
            self.out.append("<%s>" % tag)
    def handle_data(self, data):
        self.out.append(_esc(data, text=True))


def _esc(s, text=False):
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    if not text:
        s = s.replace('"', "&quot;")
    return s


def clean_html(fragment):
    """Strip Rise editor cages + theme-coupled inline styling; keep semantic HTML."""
    if not fragment:
        return ""
    p = _Clean()
    p.feed(fragment)
    p.close()
    html = "".join(p.out)
    # collapse empty paragraphs / whitespace runs
    html = re.sub(r"<p>\s*</p>", "", html)
    html = re.sub(r"[ \t]+\n", "\n", html).strip()
    return html


def plain_text(fragment):
    """Readable text only — for titles, alt text, slugs."""
    txt = re.sub(r"<[^>]+>", " ", fragment or "")
    txt = re.sub(r"&nbsp;|&#160;", " ", txt)
    txt = re.sub(r"&amp;", "&", txt)
    return re.sub(r"\s+", " ", txt).strip()


def slugify(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "course"


def norm_name(s):
    """Normalise an asset filename for fuzzy matching (unicode spaces, case)."""
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace(" ", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip().lower()
```

## `src/rise_import.py`

```python
"""Rise published-HTML export (-raw- zip) -> Course IR + extracted assets.

Extends the runtime-data.js decoder. Maps the Rise block taxonomy onto the IR
block set (see schema/IR_SCHEMA.md). mondrian/flashcard/interactive blocks are
skipped in v1 (counted + reported), per the 2026-06-04 scope decision.
"""
import re, base64, json, zipfile, os, posixpath
from collections import Counter
from common import clean_html, plain_text, slugify, norm_name

DEFAULT_ACCENT = "#1EB16A"  # TeleGreen

# Official TeleTracking accent-eligible hexes (vivid palette only, no greys).
BRAND_ACCENTS = ["#1EB16A", "#069696", "#539BD2", "#003E51", "#0B2C37",
                 "#ECBD00", "#F27D05", "#BD362F", "#4EE89E"]


def snap_accent(hexstr):
    """Snap an arbitrary Rise accent to the nearest official TeleTracking color."""
    try:
        h = (hexstr or "").lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:
        return DEFAULT_ACCENT
    def dist(c):
        c = c.lstrip("#")
        return (int(c[0:2],16)-r)**2 + (int(c[2:4],16)-g)**2 + (int(c[4:6],16)-b)**2
    return min(BRAND_ACCENTS, key=dist)


def _decode(zf):
    name = [n for n in zf.namelist() if n.endswith("runtime-data.js")][0]
    raw = zf.read(name).decode("utf-8", "replace")
    b64 = re.search(r'__jsonp\("runtime-data\.js","([A-Za-z0-9+/=]+)"', raw).group(1)
    return json.loads(base64.b64decode(b64))


def _asset_index(zf):
    """Map normalised basename -> in-zip path for everything under content/assets/."""
    idx = {}
    for n in zf.namelist():
        if "/assets/" in n and not n.endswith("/"):
            idx[norm_name(posixpath.basename(n))] = n
    return idx


def _resolve_image(media, idx):
    img = (media or {}).get("image") or {}
    cands = []
    for k in ("crushedKey", "originalUrl", "key"):
        if img.get(k):
            cands.append(img[k])
    oi = img.get("originalImage") or {}
    for k in ("crushedKey", "originalUrl", "key"):
        if oi.get(k):
            cands.append(oi[k])
    for c in cands:
        base = norm_name(posixpath.basename(c))
        if base in idx:
            return idx[base]
    return None


def _items(block):
    return block.get("items") or []


def _walk(items, out):
    for it in items or []:
        out.append(it)
        for k in ("items", "children"):
            if isinstance(it.get(k), list) and it.get("family") == "mondrian":
                _walk(it[k], out)  # flatten mondrian children only


def block_to_ir(b, idx, used, stats):
    fam, var = b.get("family"), b.get("variant")
    it0 = _items(b)[0] if _items(b) else {}

    def img(rec):
        path = _resolve_image(rec.get("media"), idx)
        if path:
            used.add(path)
            return "assets/" + posixpath.basename(path)
        return None

    if fam == "text" and var in ("heading", "subheading"):
        return {"type": "heading", "level": 2 if var == "heading" else 3,
                "html": clean_html(it0.get("heading"))}
    if fam == "text" and var in ("heading paragraph", "subheading paragraph"):
        return {"type": "headingParagraph",
                "level": 2 if var.startswith("heading") else 3,
                "headingHtml": clean_html(it0.get("heading")),
                "html": clean_html(it0.get("paragraph"))}
    if fam == "text" and var == "paragraph":
        return {"type": "paragraph", "html": clean_html(it0.get("paragraph"))}
    if fam == "text" and var == "table":
        return {"type": "table", "html": clean_html(it0.get("paragraph"))}
    if fam == "text" and var == "two column":
        return {"type": "paragraph", "html": clean_html(it0.get("paragraph") or it0.get("heading"))}

    if fam == "image" and var == "hero":
        return {"type": "image", "variant": "hero", "src": img(it0),
                "alt": plain_text(it0.get("caption")) or "",
                "html": clean_html(it0.get("paragraph"))}
    if fam == "image" and var == "full":
        return {"type": "image", "variant": "full", "src": img(it0),
                "alt": plain_text(it0.get("caption")) or "",
                "caption": plain_text(it0.get("caption"))}
    if fam == "image" and var == "text aside":
        return {"type": "imageText", "src": img(it0), "side": "left",
                "alt": plain_text(it0.get("caption")) or "",
                "html": clean_html(it0.get("paragraph"))}

    if fam == "impact" and var == "note":
        return {"type": "note", "html": clean_html(it0.get("paragraph"))}
    if fam == "impact":  # 'd' statement (and any other impact variant)
        return {"type": "statement", "html": clean_html(it0.get("paragraph"))}

    if fam == "list":
        items = [clean_html(x.get("paragraph")) for x in _items(b) if x.get("paragraph")]
        return {"type": "list", "ordered": var != "bulleted", "items": items}

    if fam == "divider":
        return {"type": "divider"}

    if fam == "continue":
        return {"type": "continue", "text": plain_text(it0.get("title")) or "CONTINUE"}

    if fam == "knowledgeCheck":
        answers = it0.get("answers") or []
        return {"type": "knowledgeCheck",
                "multi": it0.get("type") == "MULTIPLE_RESPONSE",
                "prompt": clean_html(it0.get("title")),
                "options": [{"html": clean_html(a.get("title")), "correct": bool(a.get("correct"))}
                            for a in answers],
                "feedback": clean_html(it0.get("feedback"))}

    stats["skipped"][f"{fam}/{var}"] += 1
    return None


def import_rise(zip_path):
    """Return (ir_dict, {in_zip_path: out_rel_path}) for assets to copy."""
    with zipfile.ZipFile(zip_path) as zf:
        data = _decode(zf)
        idx = _asset_index(zf)
        asset_paths = {p: zf.getinfo(p) for p in zf.namelist()}  # noqa: keep handle scope
        course = data.get("course", {})
        title = plain_text(course.get("title")) or "Course"
        accent = snap_accent(((course.get("theme") or {}).get("colorAccent")) or DEFAULT_ACCENT)

        flat = []
        for les in course.get("lessons", []):
            _walk(les.get("items", []), flat)

        used = set()
        stats = {"skipped": Counter()}
        blocks = []
        for b in flat:
            ir = block_to_ir(b, idx, used, stats)
            if ir:
                blocks.append(ir)

        # gating: everything after a `continue` (until the next one) is gated
        gated = False
        for blk in blocks:
            if blk["type"] == "continue":
                gated = True
                blk["gated"] = False
                continue
            blk["gated"] = gated

        # hero promotion: if the first visual block is a hero image, lift it to course.hero
        hero = None
        for blk in blocks:
            if blk["type"] == "image" and blk.get("variant") == "hero" and blk.get("src"):
                hero = {"image": blk["src"], "title": title,
                        "subtitle": plain_text(blk.get("html"))}
                blocks.remove(blk)
                break

        ir = {
            "schema": "nova-course-ir/v1",
            "id": slugify(title),
            "title": title,
            "locale": course.get("exportLocale") or "en",
            "accent": accent,
            "hero": hero,
            "blocks": blocks,
        }
        copy_map = {p: "assets/" + posixpath.basename(p) for p in used}
        ir["_stats"] = {"blocks": len(blocks), "assets": len(used),
                        "skipped": dict(stats["skipped"])}
        return ir, copy_map, zip_path
```

## `src/md_import.py`

```python
"""Markdown microlearning drafts -> Course IR.

Tuned to the TeleTracking microlearning draft format:

  ## Microlearning N: Title
  **Slide K — Heading**
  body paragraphs / markdown tables / - bullet or 1. numbered lists
  ...
  **Slide K — Knowledge Check**
  *Question:* ...
  - A) option
  *Correct Answer:* C
  *Feedback — Correct:* ...
  *Feedback — Incorrect:* ...
  **Articulate Build Notes:**  <- author meta; everything from here is dropped
  **Sources & Further Reading:**

Author meta (Subject, Estimated Length, Learning Objectives, Confidence Score,
Build Notes, Sources) is NOT learner-facing and is excluded. Markdown is a clean
authoring surface — edit the .md, re-run, done.
"""
import re, html
from common import slugify

SLIDE_RE = re.compile(r'^\*\*Slide\s+\d+\s*[—–-]\s*(.+?)\*\*\s*$', re.M)
META_CUT = re.compile(r'^\*\*(Articulate Build Notes|Sources?(\s|&|$)).*', re.M | re.I)


def _inline(s):
    s = html.escape(s.strip())
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?![\*\w])', r'<em>\1</em>', s)
    s = re.sub(r'`(.+?)`', r'<code>\1</code>', s)
    s = re.sub(r'\[(.+?)\]\((https?://[^)]+)\)', r'<a href="\2">\1</a>', s)
    return s


def _table(rows):
    cells = [[c.strip() for c in r.strip().strip('|').split('|')] for r in rows]
    header, body = cells[0], cells[2:]  # row 1 is the |---| separator
    out = ['<table><thead><tr>']
    out += [f'<th>{_inline(h)}</th>' for h in header]
    out.append('</tr></thead><tbody>')
    for row in body:
        out.append('<tr>' + ''.join(f'<td>{_inline(c)}</td>' for c in row) + '</tr>')
    out.append('</tbody></table>')
    return ''.join(out)


def _body_blocks(text):
    lines = text.split('\n')
    blocks, para, tbl, lst, lst_ord = [], [], [], [], False

    def flush_para():
        nonlocal para
        if para:
            blocks.append({"type": "paragraph", "html": "<p>" + _inline(" ".join(para)) + "</p>"})
            para = []

    def flush_tbl():
        nonlocal tbl
        if tbl:
            blocks.append({"type": "table", "html": _table(tbl)})
            tbl = []

    def flush_lst():
        nonlocal lst
        if lst:
            blocks.append({"type": "list", "ordered": lst_ord, "items": [_inline(x) for x in lst]})
            lst = []

    for ln in lines:
        s = ln.strip()
        if not s:
            flush_para(); flush_tbl(); flush_lst(); continue
        if s.startswith('|'):
            flush_para(); flush_lst(); tbl.append(s); continue
        flush_tbl()
        mnum = re.match(r'^\d+\.\s+(.*)', s)
        mbul = re.match(r'^[-*]\s+(.*)', s)
        if mnum:
            flush_para()
            if lst and not lst_ord: flush_lst()
            lst_ord = True; lst.append(mnum.group(1)); continue
        if mbul:
            flush_para()
            if lst and lst_ord: flush_lst()
            lst_ord = False; lst.append(mbul.group(1)); continue
        flush_lst()
        para.append(s)
    flush_para(); flush_tbl(); flush_lst()
    return blocks


def _knowledge_check(body):
    q = re.search(r'\*Question:\*\s*(.+)', body)
    opts = re.findall(r'^\s*-\s*[A-D]\)\s*(.+)$', body, re.M)
    ans = re.search(r'\*Correct Answer:\*\s*([A-D])', body)
    fb = re.search(r'\*Feedback\s*[—–-]\s*Correct:\*\s*(.+)', body)
    correct_idx = "ABCD".index(ans.group(1)) if ans else -1
    return {
        "type": "knowledgeCheck", "multi": False,
        "prompt": _inline(q.group(1)) if q else "",
        "options": [{"html": _inline(o), "correct": i == correct_idx} for i, o in enumerate(opts)],
        "feedback": _inline(fb.group(1)) if fb else "",
    }


def import_md(md_path, which=1, hero=None, image_dir=None):
    text = open(md_path, encoding="utf-8").read()
    secs = re.split(r'^##\s+Microlearning\s+', text, flags=re.M)
    # secs[0] = preamble; module k lives at secs[k] starting "k: Title\n..."
    if which < 1 or which >= len(secs):
        raise ValueError(f"Microlearning {which} not found (file has {len(secs)-1})")
    sec = secs[which]
    head, _nl, rest = sec.partition('\n')
    m = re.match(r'\d+:\s*(.+)', head.strip())
    title = (m.group(1) if m else head).strip()
    # drop a trailing "(101)" / "— Workshop" qualifier noise but keep meaningful suffix
    rest = META_CUT.split(rest)[0]

    parts = SLIDE_RE.split(rest)  # [pre, title1, body1, title2, body2, ...]
    blocks = []
    for i in range(1, len(parts), 2):
        s_title = parts[i].strip()
        s_body = META_CUT.split(parts[i + 1])[0].strip() if i + 1 < len(parts) else ""
        if "knowledge check" in s_title.lower() or re.search(r'\*Question:\*', s_body):
            kc = _knowledge_check(s_body)
            if kc["options"]:
                blocks.append({"type": "heading", "level": 2, "html": "<p>Check Your Understanding</p>"})
                blocks.append(kc)
            continue
        blocks.append({"type": "heading", "level": 2, "html": f"<p>{_inline(s_title)}</p>"})
        blocks.extend(_body_blocks(s_body))

    for b in blocks:
        b["gated"] = False

    hero_block = None
    used = {}
    if hero and image_dir:
        import os
        cand = {n.lower(): n for n in os.listdir(image_dir)}
        actual = cand.get(hero.lower())
        if actual:
            used["assets/" + actual] = os.path.join(image_dir, actual)
            hero_block = {"image": "assets/" + actual, "title": title, "subtitle": ""}

    ir = {"schema": "nova-course-ir/v1", "id": slugify(title), "title": title,
          "locale": "en", "accent": "#069696", "hero": hero_block, "blocks": blocks}
    ir["_stats"] = {"blocks": len(blocks), "assets": len(used)}
    return ir, used
```

## `src/docx_import.py`

```python
"""Author a course in Word (.docx) + a folder of named images -> Course IR.

Authoring grammar (builds on the microlearning-template/storyboard format):

  Heading 1            -> course title  (also the hero title if a [HERO] is present)
  Heading 2            -> section heading (navy band)
  Heading 3            -> subheading
  normal paragraph     -> body paragraph (bold/italic/underline preserved)
  numbered/bullet list -> list block

  Line markers (each on its own paragraph):
    [HERO: file.jpg | Title | Subtitle]      -> cover hero
    [IMG: file.png | alt text | caption]     -> full-width image (alt/caption optional)
    [IMG-LEFT: file.png | alt]  / [IMG-RIGHT: ...]  -> image beside the NEXT paragraph
    [NOTE] text...                           -> callout box
    [STATEMENT] text...                      -> centered emphasis line
    [CONTINUE]                               -> gate (reveals following content)
    [KC] ... [/KC]                           -> knowledge check (see below)

  Knowledge check:
    [KC]
    Q: Who can edit a note?
    * Only the user who created it      (a leading * marks the correct answer)
    - Any associated user
    - Only Transfer Center Users
    FB: Notes are private to their author.
    [/KC]

Images are resolved by filename against the supplied image folder.
"""
import os, re, html
from common import slugify, plain_text

MARK = re.compile(r"^\[(HERO|IMG|IMG-LEFT|IMG-RIGHT|NOTE|STATEMENT|CONTINUE|KC|/KC)\b\s*:?\s*(.*?)\]?\s*$", re.I)


def _runs_to_html(para):
    out = []
    for r in para.runs:
        t = html.escape(r.text or "")
        if not t:
            continue
        if r.bold: t = f"<strong>{t}</strong>"
        if r.italic: t = f"<em>{t}</em>"
        if r.underline: t = f"<u>{t}</u>"
        out.append(t)
    return "".join(out).strip()


def _is_list(para):
    s = (para.style.name or "").lower()
    if "list number" in s or "list bullet" in s:
        return "ol" if "number" in s else "ul"
    # fallback: numPr in the paragraph properties
    pPr = para._p.pPr
    if pPr is not None and pPr.numPr is not None:
        return "ol"
    return None


def import_docx(docx_path, image_dir=None):
    from docx import Document  # python-docx
    doc = Document(docx_path)
    image_dir = image_dir or os.path.dirname(os.path.abspath(docx_path))
    available = {n.lower(): n for n in os.listdir(image_dir)} if os.path.isdir(image_dir) else {}

    title = None
    hero = None
    blocks = []
    used = {}          # out_rel -> source path on disk
    pending_list = None  # (tag, [items])
    pending_aside = None  # (side, src, alt) waiting for the next paragraph
    kc = None           # active KC accumulator

    def flush_list():
        nonlocal pending_list
        if pending_list:
            tag, items = pending_list
            blocks.append({"type": "list", "ordered": tag == "ol", "items": items})
            pending_list = None

    def resolve(fname):
        fname = (fname or "").strip()
        actual = available.get(fname.lower())
        if actual:
            rel = "assets/" + actual
            used[rel] = os.path.join(image_dir, actual)
            return rel
        return None

    paras = doc.paragraphs
    for para in paras:
        text = (para.text or "").strip()
        style = (para.style.name or "")

        # --- inside a KC block ---
        if kc is not None:
            if text.upper().startswith("[/KC"):
                blocks.append(kc); kc = None
                continue
            if text.lower().startswith("q:"):
                kc["prompt"] = html.escape(text[2:].strip())
            elif text.startswith("*"):
                kc["options"].append({"html": html.escape(text[1:].strip()), "correct": True})
            elif text.startswith("-"):
                kc["options"].append({"html": html.escape(text[1:].strip()), "correct": False})
            elif text.lower().startswith("fb:"):
                kc["feedback"] = html.escape(text[3:].strip())
            continue

        m = MARK.match(text) if text.startswith("[") else None
        if m:
            flush_list()
            tag = m.group(1).upper()
            arg = m.group(2).strip()
            parts = [p.strip() for p in arg.split("|")]
            if tag == "HERO":
                src = resolve(parts[0]) if parts else None
                hero = {"image": src, "title": parts[1] if len(parts) > 1 else (title or ""),
                        "subtitle": parts[2] if len(parts) > 2 else ""}
            elif tag == "IMG":
                src = resolve(parts[0]) if parts else None
                blocks.append({"type": "image", "variant": "full", "src": src,
                               "alt": parts[1] if len(parts) > 1 else "",
                               "caption": parts[2] if len(parts) > 2 else ""})
            elif tag in ("IMG-LEFT", "IMG-RIGHT"):
                src = resolve(parts[0]) if parts else None
                pending_aside = ("right" if tag == "IMG-RIGHT" else "left", src,
                                 parts[1] if len(parts) > 1 else "")
            elif tag == "NOTE":
                blocks.append({"type": "note", "html": f"<p>{html.escape(arg)}</p>" if arg else ""})
            elif tag == "STATEMENT":
                blocks.append({"type": "statement", "html": html.escape(arg)})
            elif tag == "CONTINUE":
                blocks.append({"type": "continue", "text": arg or "CONTINUE"})
            elif tag == "KC":
                kc = {"type": "knowledgeCheck", "multi": False, "prompt": "", "options": [], "feedback": ""}
            continue

        if not text:
            continue

        # headings
        if style.startswith("Heading 1") or style == "Title":
            flush_list()
            if not title:
                title = text
            else:
                blocks.append({"type": "heading", "level": 2, "html": _runs_to_html(para) or html.escape(text)})
            continue
        if style.startswith("Heading 2"):
            flush_list()
            blocks.append({"type": "heading", "level": 2, "html": _runs_to_html(para) or html.escape(text)})
            continue
        if style.startswith("Heading 3"):
            flush_list()
            blocks.append({"type": "heading", "level": 3, "html": _runs_to_html(para) or html.escape(text)})
            continue

        # lists
        listtag = _is_list(para)
        if listtag:
            if pending_list and pending_list[0] != listtag:
                flush_list()
            if not pending_list:
                pending_list = (listtag, [])
            pending_list[1].append(_runs_to_html(para) or html.escape(text))
            continue
        flush_list()

        # paragraph — possibly the text half of a pending image-aside
        html_frag = f"<p>{_runs_to_html(para) or html.escape(text)}</p>"
        if pending_aside:
            side, src, alt = pending_aside
            blocks.append({"type": "imageText", "src": src, "side": side, "alt": alt, "html": html_frag})
            pending_aside = None
        else:
            blocks.append({"type": "paragraph", "html": html_frag})

    flush_list()
    if kc is not None:
        blocks.append(kc)

    # gating
    gated = False
    for b in blocks:
        if b["type"] == "continue":
            gated = True; b["gated"] = False; continue
        b["gated"] = gated

    title = title or os.path.splitext(os.path.basename(docx_path))[0]
    ir = {"schema": "nova-course-ir/v1", "id": slugify(title), "title": title,
          "locale": "en", "accent": "#1EB16A", "hero": hero, "blocks": blocks}
    ir["_stats"] = {"blocks": len(blocks), "assets": len(used)}
    return ir, used
```

## `src/render.py`

```python
"""Course IR -> a self-contained HTML course directory (brand + player bundled)."""
import os, re, shutil, html

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _unwrap_p(s):
    s = (s or "").strip()
    m = re.match(r"^<p>(.*)</p>$", s, re.S)
    return m.group(1).strip() if m and "<p>" not in m.group(1) else s


def _esc(s):
    return html.escape(s or "", quote=True)


def render_block(b):
    t = b.get("type")
    if t == "heading":
        inner = _unwrap_p(b.get("html"))
        if b.get("level", 2) <= 2:
            return f'<div class="nv-block nv-band"><div class="nv-h2">{inner}</div></div>'
        return f'<h3 class="nv-block nv-h3">{inner}</h3>'
    if t == "headingParagraph":
        head = _unwrap_p(b.get("headingHtml"))
        band = f'<div class="nv-band"><div class="nv-h2">{head}</div></div>' if b.get("level",2)<=2 \
               else f'<h3 class="nv-h3">{head}</h3>'
        return f'<div class="nv-block">{band}<div class="nv-p">{b.get("html","")}</div></div>'
    if t == "paragraph":
        return f'<div class="nv-block nv-p">{b.get("html","")}</div>'
    if t == "image":
        if not b.get("src"):
            return ""
        if b.get("variant") == "hero":
            cap = f'<div class="nv-hero-cap"><h1>{_unwrap_p(b.get("html"))}</h1></div>' if b.get("html") else ""
            return f'<div class="nv-hero"><img src="{_esc(b["src"])}" alt="{_esc(b.get("alt"))}">{cap}</div>'
        cap = f'<figcaption>{_esc(b.get("caption"))}</figcaption>' if b.get("caption") else ""
        return f'<figure class="nv-block nv-figure"><img src="{_esc(b["src"])}" alt="{_esc(b.get("alt"))}">{cap}</figure>'
    if t == "imageText":
        if not b.get("src"):
            return f'<div class="nv-block nv-p">{b.get("html","")}</div>'
        side = "right" if b.get("side") == "right" else ""
        return (f'<div class="nv-block nv-aside {side}">'
                f'<img src="{_esc(b["src"])}" alt="{_esc(b.get("alt"))}">'
                f'<div class="nv-p">{b.get("html","")}</div></div>')
    if t == "note":
        return f'<div class="nv-block nv-note">{b.get("html","")}</div>'
    if t == "statement":
        return f'<div class="nv-block nv-statement">{_unwrap_p(b.get("html"))}</div>'
    if t == "list":
        tag = "ol" if b.get("ordered") else "ul"
        lis = "".join(f"<li>{_unwrap_p(x)}</li>" for x in b.get("items", []))
        return f'<{tag} class="nv-block nv-list">{lis}</{tag}>'
    if t == "table":
        return f'<div class="nv-block nv-table-wrap">{b.get("html","")}</div>'
    if t == "divider":
        return '<hr class="nv-divider">'
    if t == "continue":
        txt = _esc(b.get("text") or "CONTINUE")
        return f'<div class="nv-continue" data-passed="0"><button class="nv-btn">{txt}</button></div>'
    if t == "knowledgeCheck":
        opts = "".join(
            f'<button class="nv-kc-opt" data-correct="{1 if o.get("correct") else 0}">{_unwrap_p(o.get("html"))}</button>'
            for o in b.get("options", []))
        fb = f'<div class="nv-kc-fb">{b.get("feedback","")}</div>' if b.get("feedback") else \
             '<div class="nv-kc-fb"></div>'
        return (f'<div class="nv-block nv-kc"><div class="nv-kc-prompt">{_unwrap_p(b.get("prompt"))}</div>'
                f'{opts}{fb}</div>')
    return ""


def _body(blocks):
    parts, i, n = [], 0, len(blocks)
    while i < n:
        b = blocks[i]
        if b.get("type") == "continue":
            parts.append(render_block(b))
            j = i + 1
            run = []
            while j < n and blocks[j].get("gated"):
                run.append(blocks[j]); j += 1
            if run:
                parts.append('<div class="nv-gated">')
                parts.extend(render_block(x) for x in run)
                parts.append('</div>')
            i = j
        else:
            parts.append(render_block(b)); i += 1
    return "\n".join(p for p in parts if p)


PAGE = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="icon" href="brand/Favicon.png">
<link rel="stylesheet" href="brand/tokens.css">
<link rel="stylesheet" href="player/player.css">
<style>:root{{ --tt-accent: {accent}; }}</style>
</head>
<body>
<header class="nv-topbar">
  <img src="brand/Logo.png" alt="TeleTracking">
  <span class="nv-title">{title}</span>
  <div class="nv-progress"><span></span></div>
</header>
<main class="nv-main">
{hero}
{body}
</main>
<script src="player/player.js"></script>
</body>
</html>
"""


def render_course(ir, out_dir, asset_blobs=None):
    """Write a complete course dir: index.html + brand/ + player/ + assets/.

    asset_blobs: dict {out_rel_path: bytes} for course media (from a Rise zip or
    a .docx image folder). Brand fonts/logo come from the bundled brand/ dir.
    """
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    # bundle brand + player
    shutil.copytree(os.path.join(ROOT, "brand"), os.path.join(out_dir, "brand"))
    shutil.copytree(os.path.join(ROOT, "player"), os.path.join(out_dir, "player"))
    # course media
    os.makedirs(os.path.join(out_dir, "assets"), exist_ok=True)
    for rel, blob in (asset_blobs or {}).items():
        dest = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as out:
            out.write(blob)
    hero_html = ""
    if ir.get("hero") and ir["hero"].get("image"):
        h = ir["hero"]
        sub = f'<p>{_esc(h.get("subtitle"))}</p>' if h.get("subtitle") else ""
        hero_html = (f'<div class="nv-hero"><img src="{_esc(h["image"])}" alt="{_esc(h.get("title"))}">'
                     f'<div class="nv-hero-cap"><h1>{_esc(h.get("title"))}</h1>{sub}</div></div>')
    page = PAGE.format(lang=ir.get("locale", "en"), title=_esc(ir.get("title")),
                       accent=ir.get("accent", "#1EB16A"), hero=hero_html,
                       body=_body(ir.get("blocks", [])))
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    return out_dir
```

## `src/scorm.py`

```python
"""Wrap a rendered course directory into a SCORM 1.2 package (.zip).

Runtime supports both SCORM 1.2 and 2004 (player.js detects API/API_1484_11);
the manifest declares 1.2, which is the broadly-accepted, Intellum-validated target.
"""
import os, zipfile
from xml.sax.saxutils import escape

MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="MANIFEST-{id}" version="1.2"
  xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.imsproject.org/xsd/imscp_rootv1p1p2 imscp_rootv1p1p2.xsd
                      http://www.adlnet.org/xsd/adlcp_rootv1p2 adlcp_rootv1p2.xsd">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>1.2</schemaversion>
  </metadata>
  <organizations default="ORG-{id}">
    <organization identifier="ORG-{id}">
      <title>{title}</title>
      <item identifier="ITEM-{id}" identifierref="RES-{id}" isvisible="true">
        <title>{title}</title>
        <adlcp:masteryscore>100</adlcp:masteryscore>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="RES-{id}" type="webcontent" adlcp:scormtype="sco" href="index.html">
{files}
    </resource>
  </resources>
</manifest>
"""


def _all_files(course_dir):
    for base, _dirs, names in os.walk(course_dir):
        for n in names:
            full = os.path.join(base, n)
            rel = os.path.relpath(full, course_dir).replace(os.sep, "/")
            if rel == "imsmanifest.xml":   # we (re)write our own; never double-add
                continue
            yield full, rel


def package(course_dir, out_zip, course_id, title):
    files = list(_all_files(course_dir))
    file_tags = "\n".join('      <file href="%s"/>' % escape(rel) for _f, rel in files)
    manifest = MANIFEST.format(id=escape(course_id), title=escape(title), files=file_tags)
    with open(os.path.join(course_dir, "imsmanifest.xml"), "w", encoding="utf-8") as f:
        f.write(manifest)
    os.makedirs(os.path.dirname(os.path.abspath(out_zip)), exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(course_dir, "imsmanifest.xml"), "imsmanifest.xml")
        for full, rel in files:
            z.write(full, rel)
    return out_zip
```

## `src/cli.py`

```python
#!/usr/bin/env python3
"""Nova Course Builder — CLI.

  python src/cli.py from-rise  <rise-raw.zip>           --out build/course.zip
  python src/cli.py from-docx  <course.docx> --images <dir>  --out build/course.zip
  python src/cli.py import-rise <rise-raw.zip>          --out build/course.ir.json
"""
import os, sys, json, argparse, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render, scorm  # noqa: E402


def _emit(ir, asset_blobs, out_zip, keep_dir=False):
    course_dir = os.path.splitext(out_zip)[0] + ".course"
    render.render_course(ir, course_dir, asset_blobs)
    scorm.package(course_dir, out_zip, ir["id"], ir["title"])
    if not keep_dir:
        import shutil; shutil.rmtree(course_dir, ignore_errors=True)
    st = ir.get("_stats", {})
    print(f"✓ {ir['title']}")
    print(f"  blocks={st.get('blocks')} assets={st.get('assets')} "
          f"skipped={st.get('skipped', {})}")
    print(f"  SCORM → {out_zip} ({os.path.getsize(out_zip)//1024} KB)")


def cmd_from_rise(a):
    from rise_import import import_rise
    ir, copy_map, src_zip = import_rise(a.zip)
    blobs = {}
    with zipfile.ZipFile(src_zip) as zf:
        for in_path, rel in copy_map.items():
            blobs[rel] = zf.read(in_path)
    _emit(ir, blobs, a.out, a.keep_dir)


def cmd_from_docx(a):
    from docx_import import import_docx
    ir, used = import_docx(a.docx, a.images)
    blobs = {rel: open(src, "rb").read() for rel, src in used.items()}
    _emit(ir, blobs, a.out, a.keep_dir)


def cmd_from_md(a):
    from md_import import import_md
    ir, used = import_md(a.md, which=a.which, hero=a.hero, image_dir=a.images)
    blobs = {rel: open(src, "rb").read() for rel, src in used.items()}
    _emit(ir, blobs, a.out, a.keep_dir)


def cmd_import_rise(a):
    from rise_import import import_rise
    ir, _copy, _src = import_rise(a.zip)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(ir, f, indent=2, ensure_ascii=False)
    print(f"✓ IR → {a.out}  (blocks={ir['_stats']['blocks']}, "
          f"skipped={ir['_stats'].get('skipped')})")


def cmd_from_ir(a):
    """Rebuild a SCORM from an (edited) IR JSON + a folder of its assets."""
    ir = json.load(open(a.ir, encoding="utf-8"))
    blobs = {}
    if a.images and os.path.isdir(a.images):
        for n in os.listdir(a.images):
            fp = os.path.join(a.images, n)
            if os.path.isfile(fp):
                blobs["assets/" + n] = open(fp, "rb").read()
    _emit(ir, blobs, a.out, a.keep_dir)


def cmd_repackage(a):
    """Re-zip an (edited) course directory into SCORM — for direct HTML tweaks."""
    cid = a.id or os.path.splitext(os.path.basename(a.dir))[0]
    title = a.title or cid
    scorm.package(a.dir, a.out, cid, title)
    print(f"✓ repackaged {a.dir} → {a.out} ({os.path.getsize(a.out)//1024} KB)")


def main():
    p = argparse.ArgumentParser(prog="nova-course-builder")
    sub = p.add_subparsers(required=True)

    r = sub.add_parser("from-rise"); r.add_argument("zip")
    r.add_argument("--out", required=True); r.add_argument("--keep-dir", action="store_true")
    r.set_defaults(fn=cmd_from_rise)

    d = sub.add_parser("from-docx"); d.add_argument("docx")
    d.add_argument("--images", required=True); d.add_argument("--out", required=True)
    d.add_argument("--keep-dir", action="store_true"); d.set_defaults(fn=cmd_from_docx)

    md = sub.add_parser("from-md"); md.add_argument("md")
    md.add_argument("--which", type=int, default=1); md.add_argument("--images", default=None)
    md.add_argument("--hero", default=None); md.add_argument("--out", required=True)
    md.add_argument("--keep-dir", action="store_true"); md.set_defaults(fn=cmd_from_md)

    i = sub.add_parser("import-rise"); i.add_argument("zip")
    i.add_argument("--out", required=True); i.set_defaults(fn=cmd_import_rise)

    fi = sub.add_parser("from-ir"); fi.add_argument("ir")
    fi.add_argument("--images", default=None); fi.add_argument("--out", required=True)
    fi.add_argument("--keep-dir", action="store_true"); fi.set_defaults(fn=cmd_from_ir)

    rp = sub.add_parser("repackage"); rp.add_argument("dir")
    rp.add_argument("--out", required=True); rp.add_argument("--id", default=None)
    rp.add_argument("--title", default=None); rp.set_defaults(fn=cmd_repackage)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
```

## `.vscode/settings.json`

```json
{
  "json.schemas": [
    {
      "fileMatch": ["*.ir.json", "**/build/*.ir.json"],
      "url": "./schema/ir.schema.json"
    }
  ],
  "files.associations": { "*.ir.json": "json" }
}
```

## `.vscode/extensions.json`

```json
{
  "recommendations": [
    "ms-vscode.live-server"
  ]
}
```

---
# === BRAND ASSETS (binary — fetch separately) ===

Fonts: `…/Branding Resources/TeleFonts/Open_Sans/*.ttf` + `Open_Sans_Condensed/*.ttf` → `brand/fonts/`
Logo (white, for dark topbar): `…/Branding Resources/OneDrive_1_*/TeleTracking Logo - All White - Registered.png` → `brand/Logo.png`
Favicon: `…/Branding Resources/T Only Logos/Tmark Registered Green.png` → `brand/Favicon.png`
Course images: `…/2026 Courses/Articulate Assets/` (102 healthcare/AI illustrations + brand transition banners)
Palette source: `…/Branding Resources/TeleTracking_BrandingColors.png` (exact hexes are in brand/tokens.css)