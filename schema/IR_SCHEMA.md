# Course IR (Intermediate Representation) — schema

The IR is the **contract** between every stage. Importers (Rise, .docx) emit IR; the
renderer + packager consume it. One IR JSON file + an `assets/` folder = a complete course.

```jsonc
{
  "schema": "course-ir/v1",
  "id": "managing-bed-requests",        // slug; used for filenames + SCORM identifier
  "title": "Managing Bed Requests",
  "locale": "en",                        // "en" | "en-GB"
  "accent": "#1EB16A",                   // course accent (defaults to the brand accent)
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
| `video`       | `mode` (`file`/`embed`), `src`, `poster`, `captions`, `captionsLang`, `caption`, `aspect`, `title`, `requireComplete` | `file` = self-hosted `<video>` bundled in the zip (+ `<track>` captions); `embed` = streamed responsive `<iframe>` |
| `audio`       | `src`, `caption`, `transcript`, `requireComplete` | `<audio>` + optional collapsible transcript |
| `embed`       | `src`, `title`, `aspect`, `height`, `caption` | generic interactive `<iframe>` (H5P / sim / widget) |
| `note`        | `html` | callout box (accent left-border) |
| `statement`   | `html` | large centered emphasis line |
| `list`        | `ordered` (bool), `items` ([html,…]) | numbered/bulleted |
| `table`       | `html` | passthrough `<table>` HTML (sanitized) |
| `divider`     | — | spacer rule |
| `transition`  | `color` (green/gold/dark/blue/teal), `band` (top/bottom) | brand "ribbon" wave divider; reusable, color-swappable. Renders a pre-cropped band from `brand/transitions/<color>-<band>.png` (`green`=brand-accent default). Decorative (`aria-hidden`). md grammar: `*Transition:* <color> <band>` |
| `continue`    | `text` (default "CONTINUE") | gate; reveals the next gated run |
| `knowledgeCheck` | `prompt`, `multi` (bool), `options` [{`html`,`correct`}], `feedback`, `feedbackIncorrect` | interactive, **unscored** |
| `quote`       | `html` (quote text), `attribution`, `src` (optional bg image) | pull-quote; with `src` the image is a tinted full-bleed background. md: `*Quote:* <text> · by: <name> · slot:`bg`` |
| `accordion`   | `entries` [{`title`, `html`, `src?`}] | native `<details>` disclosure (a11y for free, no JS). md: `*Accordion:*` + `::: item` (title:/body:/slot:) groups, lone `:::` closes |
| `process`     | `entries` [{`title`, `html`, `src?`, `kind?`}] | numbered ordered-step list (static, accessible). md: `*Process:*` + `::: step` groups |
| `flashcard`   | `entries` [{`frontHtml`, `frontSrc?`, `backHtml`, `backSrc?`}] | CSS 3D-flip cards; click/Enter/Space toggles `aria-pressed`, both faces in DOM, reduced-motion safe. Non-gating. md: `*Flashcard:*` + `::: card` (front:/back:/frontslot:/backslot:) |
| `categorize`  | `buckets` [{`id`, `title`}], `pool` [{`html`, `target`}], `prompt?`, `feedback`, `feedbackIncorrect` | sort each pool item into its correct bucket. Accessible **select-to-place** base (a Check button validates + locks); drag is a future enhancement. **Gates completion** once checked. md: `*Categorize:*` + `bucket:`/`item: <text> -> <bucket>` lines, lone `:::` closes |
| `scenario`    | `scenes` [{`title`, `html`, `responses` [{`html`, `feedback`, `preferred?`}]}] | **linear fallback** for Rise branching scenarios — renders each scene's narrative + response options with their feedback (preferred path highlighted). True branching is a future track. Import-only (no authoring grammar yet) |

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
