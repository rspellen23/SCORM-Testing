"""Image-prompt generator — emit ready-to-use ChatGPT image prompts per course asset.

Leadership generates course art (covers, Learning Objectives plates, in-lesson illustrations)
with ChatGPT using a fixed brand style preamble + a per-asset description. This module
turns each asset a course needs into a complete, paste-ready prompt with the correct ORIENTATION
(portrait art sits beside a text column; landscape art is a banner/cover).

    Constant  = STYLE preamble (style + full palette + "one clear idea" + avoid-list).
    Variables = color hierarchy (per module section) · orientation (per asset role) · asset description.

----------------------------------------------------------------------------------------------------
DECK-WIDE COHESION (harvested from ppt-master, MIT — hugohe3/ppt-master, references/image-generator.md)
----------------------------------------------------------------------------------------------------
ppt-master's insight: lock the *deck-wide* dimensions ONCE so every image in a deck coheres, then vary
only the per-image specifics. Three orthogonal dimensions, locked in order:

    Rendering (deck-wide) → Palette usage (deck-wide) → Type/role (per image)

For us the mapping is:

  * Rendering  → the STYLE preamble (our calm professional vector look — already deck-wide).
  * Palette    → DEFAULT_HIERARCHY *plus* PALETTE_BEHAVIOR (NEW): not just *which* colors, but *how*
                 they are distributed (proportion / role / temperament). A usage contract, not a list.
  * Type/role  → ROLE_DEFAULT_ORIENT + ROLE_CONCEPT (per asset — cover / objectives / aside / …).

Two more harvests, applied as closing GLOBAL_RULES on every prompt:

  * HEX-as-text guard (ppt-master §5.1): image models sometimes paint "#1A2B3C" as visible text and
    ruin the asset. We pass HEX codes in the prompt, so this is a live failure mode for us — guarded.
  * Simplified figures (ppt-master §5.2): humans as calm stylized figures, no photorealistic faces.

  * text_policy (ppt-master §5.3): default "none" — for instructional design this is the strong default
    because baked-in text can't be localized (en-GB!) or reworded without regenerating the image. A cover
    *may* opt into "embedded" designed lettering, accepting that localization cost. The toggle is explicit.

A CourseImageLock bundles the deck-wide choices so a whole course's assets are generated from one lock.
"""

from collections import namedtuple

# --- The constant style preamble (verbatim from leadership's working prompt) ---------------------
# Neutral default style preamble — the active brand's `promptStyle` overrides this at runtime.
STYLE = (
    "Use a clean, calm, professional illustration style with soft vector shapes, rounded edges, "
    "gentle gradients, minimal shadows, and plenty of whitespace. Use the brand accent as the dominant "
    "color with one or two neutral supporting tones; small bright accents only. {hierarchy} "
    "Show one clear idea related to the topic, using simple workflow, people, or learning elements only "
    "if they support the main idea. Keep the image simple, centered, spacious, and easy to understand. "
    "Avoid clutter, busy backgrounds, too many icons, complex screens, readable text, photorealism, "
    "anime, glossy 3D, and childish mascots."
)

# Default color hierarchy — the active brand's `promptHierarchy` overrides this at runtime.
DEFAULT_HIERARCHY = ("Use the brand accent as the dominant color with one or two neutral supporting "
                     "tones; the accent should always be present in some capacity.")

# --- Palette USAGE behavior (NEW — ppt-master harvest) --------------------------------------------
# DEFAULT_HIERARCHY says *which* colors; PALETTE_BEHAVIOR says *how they are distributed*. Giving the
# model proportion + role guidance is what makes a set of images read as one cohesive course rather
# than a stack of unrelated illustrations. Deck-wide: the same behavior applies to every asset.
PALETTE_BEHAVIOR = (
    "Color usage: one color dominates the main shapes, a second carries supporting elements, and "
    "white provides generous breathing space (roughly 50–60% of the canvas). Accents appear in only "
    "one or two small emphasis points — never spread evenly across the image."
)

# --- Orientation guidance (the bit leadership wished they'd specified) ---------------------------
ORIENTATION = {
    "portrait":  "Orientation: portrait / vertical (about 2:3 or 3:4, e.g. 1024x1536), composed to sit "
                 "alongside a single column of text.",
    "landscape": "Orientation: landscape / horizontal (about 16:9, e.g. 1536x1024), composed as a wide "
                 "full-width banner.",
    "square":    "Orientation: square (1:1, e.g. 1024x1024).",
}

# --- Text policy (NEW — ppt-master §5.3 harvest) --------------------------------------------------
# Default "none": no text baked into the artwork. This is the strong default for instructional design
# because any text inside a raster can't be localized or reworded without regenerating the image — all
# editable course copy lives in the HTML/SCORM layer, not the picture. "embedded" is an explicit opt-in
# for a designed cover title that is stable and part of the artwork.
TEXT_POLICY = {
    "none": ("No text of any kind anywhere in the image — no letters, numbers, signs, labels, "
             "captions, or watermarks."),
    "embedded": ("Any in-image text is part of the artwork (a designed title or single keyword) and "
                 "must be stable — do not bake in body copy, dates, or anything that may be reworded "
                 "or localized; that belongs in the course HTML, not the image."),
}

# --- Global hard rules appended as closing sentences to EVERY prompt (ppt-master §5.1 / §5.2) ------
GLOBAL_RULES = (
    "Color values (HEX codes) and color names are rendering guidance only — do NOT draw "
    "HEX codes, color names, or palette labels as visible text anywhere in the image. "
    "Any people appear as simplified, stylized figures conveying role and tone through posture and "
    "gesture — no photorealistic faces, no detailed anatomy, no celebrity likeness."
)

# --- Asset roles → default orientation + a description scaffold ----------------------------------
# role is inferred from the *Visual:*/hero context; description comes from the directive.
ROLE_DEFAULT_ORIENT = {
    "cover":      "landscape",   # course cover / hero banner
    "objectives": "portrait",    # Learning Objectives plate beside the objectives list
    "aside":      "portrait",    # any image-beside-text (2-column) illustration
    "full":       "landscape",   # full-width in-lesson illustration
    "spot":       "square",      # small spot/icon illustration
}


# Strong default concepts for the standard roles, so a terse/blank authored description still yields
# a good prompt. {desc}/{title} are filled when present; otherwise the concept stands on its own.
ROLE_CONCEPT = {
    "objectives": ("An in-lesson illustration representing the learning objectives for this module — a "
                   "single calm person looking toward a small set of simple goal or "
                   "checklist markers (circles / checkmarks, no readable text), conveying focus, growth, "
                   "and readiness to learn."),
    "cover": ("Course cover illustration for '{title}' — one clear, welcoming idea that represents the "
              "module's topic, with a person or workflow element as the focal point."),
}

# Authored descriptions this generic are treated as "no real description" → use the role concept.
_GENERIC = {"", "learning objectives", "learning objectives for this microlearning",
            "objectives", "cover", "course cover", "hero"}


# --- Deck-wide lock (NEW — ppt-master harvest) ----------------------------------------------------
# Bundle the deck-wide dimensions for one course so every asset is generated from a single source of
# truth. Built once per course (make_lock), then build_prompt reads from it. Defaults reproduce the
# legacy behavior exactly, so callers that pass nothing get identical output to before.
CourseImageLock = namedtuple("CourseImageLock", ["hierarchy", "palette_behavior", "title"])


def make_lock(hierarchy=None, palette_behavior=None, title=""):
    """Create the deck-wide image lock for a course (rendering is the module-level STYLE constant)."""
    return CourseImageLock(
        hierarchy=hierarchy or DEFAULT_HIERARCHY,
        palette_behavior=palette_behavior if palette_behavior is not None else PALETTE_BEHAVIOR,
        title=title,
    )


def asset_description(role, description, title=""):
    """Pick the best Asset-type text: a specific authored description wins; else the role concept."""
    d = (description or "").strip()
    if d.lower().rstrip(".") in _GENERIC and role in ROLE_CONCEPT:
        return ROLE_CONCEPT[role].format(title=title or "this course")
    if d:
        return d
    return ROLE_CONCEPT.get(role, "In-lesson illustration supporting the topic.").format(title=title or "this course")


def build_prompt(description, role="full", orientation=None, hierarchy=None, title="",
                 text_policy="none", palette_behavior=None):
    """Assemble one complete image prompt.

    orientation overrides the role default when given. text_policy defaults to "none" (no baked-in
    text — the localization-safe default for course art). palette_behavior defaults to PALETTE_BEHAVIOR;
    pass "" to suppress it. The signature is backward-compatible: the original four kwargs still work
    and, left at their defaults, the new clauses only ADD the global guards (HEX-as-text, simplified
    figures) and a stronger no-text instruction — never removing prior behavior.
    """
    orient = orientation or ROLE_DEFAULT_ORIENT.get(role, "landscape")
    behavior = palette_behavior if palette_behavior is not None else PALETTE_BEHAVIOR
    parts = [
        STYLE.format(hierarchy=hierarchy or DEFAULT_HIERARCHY),
        behavior,
        ORIENTATION.get(orient, ORIENTATION["landscape"]),
        "Asset type: " + asset_description(role, description, title).rstrip(".") + ".",
        TEXT_POLICY.get(text_policy, TEXT_POLICY["none"]),
        GLOBAL_RULES,
    ]
    return " ".join(p for p in parts if p)


def build_prompt_locked(lock, description, role="full", orientation=None, text_policy="none"):
    """Convenience: build a prompt from a CourseImageLock so every asset shares the deck-wide choices."""
    return build_prompt(description, role=role, orientation=orientation,
                         hierarchy=lock.hierarchy, title=lock.title,
                         text_policy=text_policy, palette_behavior=lock.palette_behavior)


# --- Manifest (NEW — ppt-master §6 harvest) -------------------------------------------------------
# A trackable, re-rollable record of a course's image set: the deck-wide lock at the top, one item per
# asset with a status the author updates as art is produced. Pairs with schema/ASSET_PIPELINE.md's
# missing-asset lint. Status enum mirrors ppt-master: Pending → Generated | Needs-Manual.
def manifest_item(slot, role, orientation, prompt, generatable=True, text_policy="none"):
    """One image_prompts.json item."""
    return {
        "slot": slot,
        "role": role,
        "orientation": orientation,
        "text_policy": text_policy,
        "prompt": prompt if generatable else None,
        # screenshots are captured from the live app, not generated — flagged so the lint can tell them apart
        "source": "generate" if generatable else "screenshot",
        "status": "Pending" if generatable else "Capture",
    }


def build_manifest(title, items, lock):
    """Assemble the image_prompts.json structure for a course (deck-wide lock + per-asset items)."""
    return {
        "course": title,
        "rendering": "calm-vector",   # the deck-wide STYLE family
        "palette_hierarchy": lock.hierarchy,
        "palette_behavior": lock.palette_behavior,
        "items": items,
    }
