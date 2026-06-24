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
