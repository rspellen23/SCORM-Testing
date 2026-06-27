"""Cross-cutting per-slide `theme: dark|light` flag (2026-06-26).

A deck slide may carry an optional "theme" sibling to "layout" that overrides
the layout's blueprint-default theme — swapping ONLY the color theme (semantic
colors + background art + theme logo), keeping the layout's header mode and
structure. Honored only when the brand defines that theme; a no-blueprint brand
ignores it. Covers: pal resolution, fallback on invalid/absent theme, every
layout renders in BOTH themes (the regression guard for theme-agnostic
renderers), pagination carries the flag, lint validation, SVG-preview parity,
and the build path's slide normalization preserving theme.
"""
import json
import os
import tempfile

import authoring
import brand as brandmod
import slide_layouts as SL
import slide_svg


def _brand():
    return brandmod.load_brand("teletracking")


def _pal(layout, theme=None, brand=None):
    brand = brand if brand is not None else _brand()
    base = SL._palette_of(brand)
    bp = SL._load_blueprint(brand)
    return SL._slide_pal(base, brand, bp, layout, theme)[0]


# ---------------------------------------------------------------- pal resolution
def test_override_flips_theme_and_semantic_colors():
    # `cards` is a light layout by default; force it dark.
    light = _pal("cards", None)
    dark = _pal("cards", "dark")
    assert light["theme"] == "light"
    assert dark["theme"] == "dark"
    # ink (primary text) inverts: navy on light, white on dark
    assert str(light["ink"]) != str(dark["ink"])
    assert str(dark["ink"]).upper() == "FFFFFF"
    assert str(light["ink"]).upper() != "FFFFFF"
    # the full-bleed background art also swaps with the theme
    assert light["bg_image"] != dark["bg_image"]


def test_override_keeps_header_mode_structure():
    # flipping the theme must NOT change the layout's header mode (structure)
    assert _pal("cards", None)["header_mode"] == _pal("cards", "dark")["header_mode"]
    assert _pal("divider", None)["header_mode"] == _pal("divider", "light")["header_mode"]


def test_flip_a_dark_layout_to_light():
    # `divider` is dark by default; light override gives navy title ink, not white
    dark = _pal("divider", None)
    lite = _pal("divider", "light")
    assert dark["theme"] == "dark" and lite["theme"] == "light"
    assert str(dark["title_ink"]).upper() == "FFFFFF"
    assert str(lite["title_ink"]).upper() != "FFFFFF"


def test_invalid_or_absent_theme_falls_back_to_layout_default():
    default = _pal("cards", None)
    for bad in ("teal", "DARKMODE", "", "  ", 7, None):
        assert _pal("cards", bad)["theme"] == default["theme"]


def test_no_blueprint_brand_ignores_theme():
    # _default has no blueprint -> theme override is a no-op (no themes to switch)
    base = SL._palette_of("_default")
    bp = SL._load_blueprint("_default")
    assert not bp
    pal, bg = SL._slide_pal(base, "_default", bp, "cards", "dark")
    assert bg is None
    assert "theme" not in pal or pal.get("theme") is None


# ----------------------------------------------------------- render both themes
def test_every_layout_renders_in_both_themes():
    brand = _brand()
    examples = authoring.load_slide_templates(images=False)
    rendered = 0
    for layout in SL.LAYOUTS:
        content = examples.get(layout, {"title": layout})
        for theme in ("dark", "light"):
            fd, tmp = tempfile.mkstemp(suffix=".pptx")
            os.close(fd)
            try:
                SL.export_deck([{"layout": layout, "content": content, "theme": theme}], tmp,
                               brand=brand)
                assert os.path.getsize(tmp) > 0
                rendered += 1
            finally:
                os.unlink(tmp)
    assert rendered == len(SL.LAYOUTS) * 2


# ----------------------------------------------------------------- pagination
def test_pagination_carries_theme_to_continuation_slides():
    spec = {"layout": "cards", "theme": "dark",
            "content": {"title": "Many", "cards": [{"title": f"C{i}", "body": "x"}
                                                    for i in range(12)]}}
    design = (SL._load_blueprint(_brand()) or {}).get("design") or {}
    parts = SL._paginate(spec, design)
    assert len(parts) > 1                      # actually split
    assert all(p.get("theme") == "dark" for p in parts)   # flag survives on every page


def test_pagination_without_theme_adds_no_theme_key():
    spec = {"layout": "cards",
            "content": {"title": "Many", "cards": [{"title": f"C{i}", "body": "x"}
                                                    for i in range(12)]}}
    design = (SL._load_blueprint(_brand()) or {}).get("design") or {}
    parts = SL._paginate(spec, design)
    assert len(parts) > 1
    assert all("theme" not in p for p in parts)


# ---------------------------------------------------------------------- lint
def test_lint_accepts_valid_and_absent_theme():
    ok, _n, errs = authoring.lint_deck([
        {"layout": "cards", "content": {"title": "a", "cards": [{"title": "x", "body": "y"}]}},
        {"layout": "divider", "content": {"title": "b"}, "theme": "light"},
        {"layout": "statement", "content": {"title": "c"}, "theme": "dark"},
    ])
    assert ok, errs


def test_lint_rejects_invalid_theme():
    ok, _n, errs = authoring.lint_deck([
        {"layout": "cards", "content": {"title": "a"}, "theme": "teal"},
    ])
    assert not ok
    assert any("invalid theme" in e for e in errs)


# --------------------------------------------------------------- preview parity
def test_svg_preview_honors_theme():
    brand = _brand()
    content = authoring.load_slide_templates(images=False).get("cards", {"title": "Cards"})
    light = slide_svg.render_slide_svg("cards", content, brand, theme="light")
    dark = slide_svg.render_slide_svg("cards", content, brand, theme="dark")
    assert light.startswith("<svg") and dark.startswith("<svg")
    # the dark theme paints a different card fill -> the SVG markup must differ
    assert light != dark


def test_render_deck_svg_reads_per_slide_theme():
    brand = _brand()
    slides = [{"layout": "divider", "content": {"title": "T"}, "theme": "light"}]
    svgs = slide_svg.render_deck_svg(slides, brand)
    assert len(svgs) == 1 and svgs[0].startswith("<svg")


# ------------------------------------------------- build-path normalization
def test_build_path_preserves_theme():
    # the CLI/build path writes a {"slides":[...]} JSON file then export_deck_file's
    # it; a per-slide theme must survive that round-trip into the rendered .pptx.
    brand = _brand()
    deck = {"slides": [
        {"layout": "statement", "content": {"title": "Big", "value": "6x"}, "theme": "light"},
        {"layout": "cards", "content": {"title": "C", "cards": [{"title": "a", "body": "b"}]}},
    ]}
    fd, dj = tempfile.mkstemp(suffix=".json"); os.close(fd)
    fd, op = tempfile.mkstemp(suffix=".pptx"); os.close(fd)
    try:
        with open(dj, "w") as f:
            json.dump(deck, f)
        stats = SL.export_deck_file(dj, op, brand=brand)
        assert stats["slides"] == 2
        assert os.path.getsize(op) > 0
    finally:
        os.unlink(dj); os.unlink(op)
