"""Audit item 2.4 — the course->deck flatten must not silently swallow blocks.

quote + infographic used to fall through `_render_textflow` with no branch and
no `_DROP` entry, vanishing with no signal. They are now logged-dropped, and any
*unregistered* type is reported (and warned) instead of disappearing.
"""
import tempfile
import os

import md_import
import pptx_export


def _ir():
    ir, _ = md_import.import_md(
        os.path.join(os.path.dirname(__file__), "fixtures", "showcase.md"), which=1)
    return ir


def test_quote_and_infographic_are_reported_dropped():
    ir = _ir()
    types = {b.get("type") for b in ir["blocks"]}
    assert {"quote", "infographic"} <= types, "fixture should exercise both"
    out = tempfile.mktemp(suffix=".pptx")
    try:
        stats = pptx_export.export_pptx(ir, {}, out)
    finally:
        if os.path.exists(out):
            os.unlink(out)
    assert stats["dropped"].get("quote"), stats["dropped"]
    assert stats["dropped"].get("infographic"), stats["dropped"]


def test_unregistered_type_is_reported_not_swallowed():
    ir = _ir()
    ir = dict(ir)
    ir["blocks"] = list(ir["blocks"]) + [
        {"type": "heading", "level": 2, "html": "<p>Section</p>"},
        {"type": "frobnicate", "html": "<p>unknown block</p>"},
    ]
    out = tempfile.mktemp(suffix=".pptx")
    try:
        stats = pptx_export.export_pptx(ir, {}, out)
    finally:
        if os.path.exists(out):
            os.unlink(out)
    assert stats["dropped"].get("frobnicate") == 1, stats["dropped"]
