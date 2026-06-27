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
