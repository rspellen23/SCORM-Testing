"""Structured build report (C1) — make the engine's silent drops visible.

The engine never crashes: malformed input drops to empty and keeps going. The
build report folds those scattered, stderr-only signals (IR import warnings, the
§8 lint pass, the PowerPoint flatten's dropped set, SCORM conformance lint) into
one JSON beside each artifact so the dashboard can tell the operator a build
degraded — not just stderr. These tests pin: the pure assembler, the on-disk
round-trip, and the real seam (md_import recording a dropped image).
"""
import os
import tempfile

import build_report
import md_import


# ---- pure assembler -------------------------------------------------------

def _ir(blocks=3, assets=1, warnings=None, title="T"):
    return {"title": title, "_stats": {"blocks": blocks, "assets": assets,
                                       "warnings": warnings or []}}


def test_clean_build_is_ok():
    rep = build_report.assemble(_ir())
    assert rep["ok"] is True
    assert rep["errors"] == [] and rep["warnings"] == []
    assert rep["blocks"] == 3 and rep["assets"] == 1 and rep["title"] == "T"


def test_import_warnings_surface_as_warnings_not_errors():
    rep = build_report.assemble(_ir(warnings=["visual slot “x.png” has no matching file"]))
    assert rep["ok"] is True                       # a dropped image doesn't make the build "wrong"
    assert any("x.png" in w for w in rep["warnings"])
    assert rep["errors"] == []


def test_lint_errors_make_the_build_not_ok():
    rep = build_report.assemble(_ir(), lint_errors=["unit 1: a knowledge check ..."])
    assert rep["ok"] is False                      # correctness problem — flag the build
    assert any("knowledge check" in e for e in rep["errors"])


def test_dropped_blocks_become_warnings_and_are_counted():
    rep = build_report.assemble(_ir(), dropped={"accordion": 2, "video": 1, "x": 0})
    assert rep["dropped"] == {"accordion": 2, "video": 1}   # zero-count entries pruned
    joined = " ".join(rep["warnings"])
    assert "accordion" in joined and "2" in joined


def test_conformance_errors_and_warnings_split_correctly():
    rep = build_report.assemble(_ir(), conformance_errors=["bad manifest"],
                                conformance_warnings=["odd resource"])
    assert rep["ok"] is False
    assert any("bad manifest" in e for e in rep["errors"])
    assert any("odd resource" in w for w in rep["warnings"])


def test_rise_skipped_variants_surface_as_warnings():
    ir = {"title": "T", "_stats": {"blocks": 5, "assets": 2, "skipped": {"interaction/hotspot": 3}}}
    rep = build_report.assemble(ir)
    assert rep["ok"] is True
    assert any("hotspot" in w and "3" in w for w in rep["warnings"])


def test_assemble_tolerates_a_minimal_ir():
    rep = build_report.assemble({})                # no _stats at all
    assert rep["ok"] is True and rep["blocks"] is None and rep["warnings"] == []


# ---- on-disk persistence (crosses the subprocess boundary) ----------------

def test_report_path_sits_beside_the_artifact():
    assert build_report.report_path("/out/course_m1_scorm12.zip") == \
        "/out/course_m1_scorm12.report.json"
    assert build_report.report_path("/out/deck.pptx") == "/out/deck.report.json"


def test_write_then_read_round_trips():
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "course.zip")
        rep = build_report.assemble(_ir(warnings=["w1"]), lint_errors=["e1"])
        p = build_report.write(rep, out)
        assert p and os.path.exists(p)
        back = build_report.read(out)
        assert back["warnings"] == ["w1"] and back["errors"] == ["e1"] and back["ok"] is False


def test_read_missing_report_is_none():
    with tempfile.TemporaryDirectory() as d:
        assert build_report.read(os.path.join(d, "nope.zip")) is None


# ---- the real seam: a dropped image is recorded, not swallowed ------------

_MD = """# Course

## Microlearning 1: Intro

**Slide 1 — A slide**

Some body text.

*Visual:* graphic · a chart · slot: `missing.png`
"""


def test_missing_visual_asset_is_recorded_in_stats_warnings():
    with tempfile.TemporaryDirectory() as d:
        md = os.path.join(d, "c.md")
        open(md, "w", encoding="utf-8").write(_MD)
        imgs = os.path.join(d, "images")           # provided, but EMPTY → slot can't resolve
        os.makedirs(imgs)
        ir, _used = md_import.import_md(md, which=1, image_dir=imgs)
        warns = ir["_stats"]["warnings"]
        assert any("missing.png" in w for w in warns), warns
        # and the report folds it through as an operator warning (build still ok)
        rep = build_report.assemble(ir)
        assert rep["ok"] is True and any("missing.png" in w for w in rep["warnings"])


def test_cli_write_report_folds_build_time_lint():
    # the cli wiring: a hand-authored md with the A1 KC bug must surface as a
    # build-time ERROR in the persisted report (not just at generation).
    import cli
    bad = _MD + ("\n**Slide 2 — Knowledge Check**\n\n*Question:* Q?\n"
                 "- A) one\n- B) two\n- C) three\n*Correct Answer:* A, C and also B\n")
    with tempfile.TemporaryDirectory() as d:
        md = os.path.join(d, "c.md")
        open(md, "w", encoding="utf-8").write(bad)
        out = os.path.join(d, "course.zip")
        ir, _ = md_import.import_md(md, which=1)
        cli._write_report(ir, out, lint_md=md)
        rep = build_report.read(out)
        assert rep is not None and rep["ok"] is False
        assert any("Correct Answer" in e for e in rep["errors"])


def test_resolved_visual_asset_produces_no_warning():
    with tempfile.TemporaryDirectory() as d:
        md = os.path.join(d, "c.md")
        open(md, "w", encoding="utf-8").write(_MD.replace("missing.png", "there.png"))
        imgs = os.path.join(d, "images")
        os.makedirs(imgs)
        open(os.path.join(imgs, "there.png"), "wb").write(b"\x89PNG\r\n\x1a\n")
        ir, _used = md_import.import_md(md, which=1, image_dir=imgs)
        assert ir["_stats"]["warnings"] == []
