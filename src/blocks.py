"""Central block-type registry — the single source of truth for the IR block
vocabulary.

Every block type the engine understands is declared here exactly once, with its
authoring status and its course->deck (PPTX) disposition. The drift test
(`tests/test_block_registry.py`) asserts this registry agrees with the four real
sites where a block type has to be wired up:

    1. the JSON-schema enum            schema/ir.schema.json
    2. the markdown authoring parser   src/md_import.py
    3. the HTML renderer               src/render.py
    4. the PPTX exporter               src/pptx_export.py  (the `_DROP` set)

Add a type to one site without the others and CI fails. This closes the audit
finding that there was no registry, so a block could be (and was) schema'd +
rendered but have no parser — degrading silently.

Pure stdlib, no imports of the renderer/parser/exporter: the registry is a flat
declaration so it stays importable in the air-gapped build and cannot itself
drift by side effect.
"""

# ----------------------------------------------------------------- status
# "stable"      fully wired: markdown-authorable, HTML-rendered, schema'd.
# "coming-soon" schema + HTML renderer exist, but there is NO markdown authoring
#               grammar yet. These types are produced today only by the Rise /
#               docx importers (e.g. branching scenarios, gated reveals). They
#               are deliberately NOT offered to the AI author and NOT given a
#               `*Marker:*` grammar, so the author path can't emit a half-baked
#               one. Stubbed-and-flagged, never silently orphaned.
STABLE = "stable"
COMING_SOON = "coming-soon"

# -------------------------------------------------------- PPTX disposition
# The course->deck flatten is lossy by design (use `./build slide --layout ...`
# for a rich, native slide). Every type declares how the flatten treats it:
# "render"      represented on the static slide (textflow / table / image path).
# "drop"        intentionally logged as dropped (rich block; no faithful static
#               form) — surfaced to the user, never swallowed.
# "structural"  section/divider/transition markers: not content, dropped without
#               a "lost content" warning (they carry no learner-facing payload).
RENDER = "render"
DROP = "drop"
STRUCTURAL = "structural"


def _b(status, md, pptx, summary):
    return {"status": status, "md": md, "pptx": pptx, "summary": summary}


BLOCKS = {
    # --- text / structure -------------------------------------------------
    "heading":          _b(STABLE, True,  RENDER,     "section title / subheading"),
    "paragraph":        _b(STABLE, True,  RENDER,     "body copy"),
    "headingParagraph": _b(COMING_SOON, False, RENDER, "combined heading+body (importer-only)"),
    "note":             _b(STABLE, True,  RENDER,     "callout box"),
    "statement":        _b(STABLE, True,  RENDER,     "large centered emphasis line"),
    "list":             _b(STABLE, True,  RENDER,     "ordered / unordered list"),
    "table":            _b(STABLE, True,  RENDER,     "tabular data"),
    "divider":          _b(STABLE, True,  STRUCTURAL, "spacer rule"),
    "transition":       _b(STABLE, True,  STRUCTURAL, "brand ribbon/wave band (decorative)"),
    "sectionStart":     _b(STABLE, True,  STRUCTURAL, "colored-section open marker"),
    "sectionEnd":       _b(STABLE, True,  STRUCTURAL, "colored-section close marker"),
    "continue":         _b(STABLE, True,  DROP,       "gate that reveals the next gated run (progressive reveal)"),
    "objectives":       _b(STABLE, True,  RENDER,     "learning-objectives list ('you will be able to…')"),

    # --- media ------------------------------------------------------------
    "image":            _b(STABLE, True,  RENDER,     "full-width / hero figure"),
    "imageText":        _b(STABLE, True,  RENDER,     "image beside text"),
    "video":            _b(STABLE, True,  DROP,       "self-hosted or embedded video"),
    "audio":            _b(STABLE, True,  DROP,       "audio + optional transcript"),
    "embed":            _b(STABLE, True,  DROP,       "generic interactive iframe"),

    # --- interactive / rich blocks ---------------------------------------
    "knowledgeCheck":   _b(STABLE, True,  RENDER,     "interactive check (unscored)"),
    "button":           _b(STABLE, True,  DROP,       "CTA link / modal trigger"),
    "cardGrid":         _b(STABLE, True,  RENDER,     "card grid (optional modals)"),
    "quote":            _b(STABLE, True,  DROP,       "pull-quote (optional bg image)"),
    "accordion":        _b(STABLE, True,  DROP,       "native <details> disclosure"),
    "process":          _b(STABLE, True,  DROP,       "numbered ordered-step list"),
    "flashcard":        _b(STABLE, True,  DROP,       "CSS flip cards"),
    "categorize":       _b(STABLE, True,  DROP,       "sort-into-buckets (gates completion)"),
    "scenario":         _b(STABLE, True,  DROP,       "decision walk-through (situation + choices + feedback; linear)"),
    "timeline":         _b(STABLE, True,  DROP,       "vertical milestone axis"),
    "comparison":       _b(STABLE, True,  DROP,       "2-3 panel comparison"),
    "chart":            _b(STABLE, True,  DROP,       "bar/line/pie/stacked/grouped (native slide via ./build slide)"),
    "infographic":      _b(STABLE, True,  DROP,       "poster-style overview section"),
}


# --------------------------------------------------------------- accessors

def all_types():
    """The full block vocabulary (set of type names)."""
    return set(BLOCKS)


def coming_soon_types():
    """Types that are schema'd + rendered but not yet markdown-authorable.

    These are stubbed: produced only by importers, never offered to the AI
    author. Surfaced in the authoring docs as 'Coming soon'."""
    return {t for t, info in BLOCKS.items() if info["status"] == COMING_SOON}


def authorable_types():
    """Types an author / the AI may emit via markdown grammar."""
    return {t for t, info in BLOCKS.items() if info["md"]}


def pptx_drop_types():
    """Types the course->deck flatten drops (logged 'drop' + silent 'structural').

    Must equal `pptx_export._DROP`; the drift test enforces it."""
    return {t for t, info in BLOCKS.items() if info["pptx"] in (DROP, STRUCTURAL)}


def pptx_render_types():
    """Types the flatten represents on a static slide."""
    return {t for t, info in BLOCKS.items() if info["pptx"] == RENDER}
