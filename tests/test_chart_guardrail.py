"""(e) The no-fabricated-metrics chart guardrail.

Every chart must cite a `source:` line. authoring.lint() must reject a
sourceless chart (the no-invented-metrics rule) and accept a sourced one.
"""
import authoring

_UNIT = """## Microlearning 1: Chart Test

**Slide 1 — Overview**
Some teaching prose about admissions trends over the past year.

**Slide 2 — The numbers**
*Chart:* bar
title: Quarterly admits
categories: Q1, Q2, Q3
series: Admits = 120, 145, 130
yLabel: Patients
xLabel: Quarter
"""

_SOURCE = "source: Q2 operations report, table 3\n"


def test_sourceless_chart_rejected():
    ok, n, errors = authoring.lint(_UNIT)
    assert ok is False
    assert any("source" in e.lower() for e in errors), errors


def test_sourced_chart_accepted():
    ok, n, errors = authoring.lint(_UNIT + _SOURCE)
    assert ok is True, errors
    assert errors == []


# --- B3: a chart with a non-numeric cell ("N/A"/null) must not crash --------
# LLMs emit "N/A"/null for missing data; the SR/print data table did int("N/A").

def test_chart_with_non_numeric_cell_does_not_crash():
    import chart_svg
    block = {"chart": "bar", "categories": ["Q1", "Q2", "Q3"],
             "series": [{"name": "Admits", "data": [120, "N/A", 130]}],
             "source": "ops report"}
    svg = chart_svg.render_chart(block)        # must not raise
    assert svg and "N/A" in svg                # the bad cell shows verbatim in the data table
    assert "120" in svg and "130" in svg       # the numeric cells still render


def test_chart_with_null_cell_renders_blank_not_crash():
    import chart_svg
    block = {"chart": "line", "categories": ["A", "B"],
             "series": [{"name": "X", "data": [5, None]}], "source": "s"}
    assert chart_svg.render_chart(block)        # None → "" in _fmt, no crash


# --- Q1: chart auto-narrative (takeaway line) -------------------------------
# A chart carries an optional one-line takeaway/insight: the generation prompt
# asks the model to write it, the parser preserves it, and both the course
# (SVG) and deck (PPTX) renderers show it.

def test_chart_prompt_injects_takeaway_instruction():
    # CHART_RULE is the shared rule injected into the course generation prompt.
    assert "takeaway" in authoring.CHART_RULE.lower()
    prompt = authoring.build_prompt("obj", "aud", "concept-explainer", 2, "some source text")
    assert "takeaway" in prompt.lower()


def test_chart_parser_preserves_takeaway():
    import md_import, tempfile, os
    md = ("## Microlearning 1: Chart Test\n\n"
          "**Slide 1 — The numbers**\n"
          "*Chart:* bar\n"
          "title: Quarterly admits\n"
          "categories: Q1, Q2, Q3\n"
          "series: Admits = 120, 145, 130\n"
          "source: Q2 operations report, table 3\n"
          "takeaway: Admissions rose steadily across the year.\n")
    fd, tmp = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    open(tmp, "w", encoding="utf-8").write(md)
    try:
        ir, _ = md_import.import_md(tmp, which=1)
    finally:
        os.unlink(tmp)
    charts = [b for b in ir["blocks"] if b.get("type") == "chart"]
    assert charts, "no chart block parsed"
    assert charts[0].get("takeaway") == "Admissions rose steadily across the year."


def test_chart_renderer_shows_takeaway():
    import chart_svg
    block = {"chart": "bar", "categories": ["Q1", "Q2"],
             "series": [{"name": "Admits", "data": [120, 145]}],
             "source": "ops report",
             "takeaway": "Admits climbed 21% from Q1 to Q2."}
    svg = chart_svg.render_chart(block)
    assert "nv-chart-takeaway" in svg
    assert "Admits climbed 21% from Q1 to Q2." in svg


def test_chart_renderer_omits_takeaway_when_absent():
    import chart_svg
    block = {"chart": "bar", "categories": ["Q1"],
             "series": [{"name": "X", "data": [1]}], "source": "s"}
    assert "nv-chart-takeaway" not in chart_svg.render_chart(block)


def test_deck_chart_renders_with_takeaway():
    # the deck-side chart layout carries the same takeaway into the .pptx.
    import slide_layouts, tempfile, os
    slides = [{"layout": "chart", "content": {
        "title": "Quarterly admits", "chart": "bar",
        "categories": ["Q1", "Q2"],
        "series": [{"name": "Admits", "data": [120, 145]}],
        "source": "ops report",
        "takeaway": "Admits climbed 21% from Q1 to Q2."}}]
    fd, tmp = tempfile.mkstemp(suffix=".pptx")
    os.close(fd)
    try:
        slide_layouts.export_deck(slides, tmp)   # must not raise
        assert os.path.getsize(tmp) > 0
    finally:
        os.unlink(tmp)
