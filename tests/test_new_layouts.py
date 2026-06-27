"""Section Header + Cycles layouts — the two template layouts generalized into
the token-driven generative engine (2026-06-26).

Covers: both are registered + offered to the deck generator; both render to SVG
(preview parity) and into a real .pptx deck; the Cycles ring adapts to step
count; Cycles overflow paginates onto a continuation slide; and the design
tokens come from the brand blueprint (engine stays agnostic without one).
"""
import os
import tempfile

import authoring
import brand as brandmod
import slide_layouts as SL
import slide_svg

SH = {"number": "02", "kicker": "Section",
      "title": "Operationalizing the Cycle",
      "subtitle": "How the loop runs in practice.", "footer": "TeleTracking"}
CY = {"title": "Continuous Improvement Cycle", "subtitle": "A repeating loop.",
      "center": "Improve",
      "steps": [{"title": "Plan", "body": "Define the change."},
                {"title": "Do", "body": "Pilot it small."},
                {"title": "Check", "body": "Measure vs target."},
                {"title": "Act", "body": "Standardize, repeat."}],
      "footer": "Repeat each cycle."}


def _brand():
    return brandmod.load_brand("teletracking")


def test_both_layouts_registered():
    for lay in ("sectionheader", "cycles"):
        assert lay in SL.LAYOUTS
        assert lay in SL.RENDERERS


def test_both_offered_to_deck_generator():
    assert "sectionheader" in authoring._LAYOUT_ORDER
    assert "cycles" in authoring._LAYOUT_ORDER
    for lay in ("sectionheader", "cycles"):
        assert authoring.LAYOUT_PURPOSE.get(lay)              # has a purpose hint
    tmpls = authoring.load_slide_templates()
    assert "sectionheader" in tmpls and "cycles" in tmpls     # example schema loads


def test_sectionheader_svg_renders():
    svg = slide_svg.render_slide_svg("sectionheader", SH, _brand())
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    # the mock splits text into per-word tspans, so check single tokens
    assert "02" in svg and "Operationalizing" in svg


def test_cycles_svg_renders_nodes_and_legend():
    svg = slide_svg.render_slide_svg("cycles", CY, _brand())
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    # one numbered node per step on the ring (ellipses) + the step titles in the legend
    assert svg.count("<ellipse") >= len(CY["steps"])
    for st in CY["steps"]:
        assert st["title"] in svg


def test_cycles_ring_adapts_to_count():
    # the ring must place a node for any 3..6 steps without error
    for k in (3, 5, 6):
        c = {"title": "C", "steps": [{"title": f"S{i}", "body": "x"} for i in range(k)]}
        svg = slide_svg.render_slide_svg("cycles", c, _brand())
        assert svg.count("<ellipse") >= k


def test_cycles_is_never_paginated():
    # a cycle is ONE visualization (a loop) — it must NEVER split across slides,
    # even when the step count is large. The model is steered to pick process/
    # timeline for a too-long sequence instead.
    design = SL._load_blueprint(_brand()).get("design")
    spec = {"layout": "cycles",
            "content": {"title": "Big", "steps": [{"title": str(i)} for i in range(8)]}}
    pages = SL._paginate(spec, design)
    assert len(pages) == 1                                    # the wheel stays whole
    assert len(pages[0]["content"]["steps"]) == 8


def test_new_layouts_build_into_a_real_pptx_deck():
    out = os.path.join(tempfile.mkdtemp(), "newlayouts.pptx")
    stats = SL.export_deck(
        [{"layout": "sectionheader", "content": SH},
         {"layout": "cycles", "content": CY}],
        out, brand=_brand())
    assert os.path.getsize(out) > 0
    assert stats["layouts"] == ["sectionheader", "cycles"]


def test_engine_agnostic_without_blueprint():
    # no blueprint (_default brand) -> tokens absent, but both still render
    for lay, content in (("sectionheader", SH), ("cycles", CY)):
        svg = slide_svg.render_slide_svg(lay, content, "_default")
        assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
