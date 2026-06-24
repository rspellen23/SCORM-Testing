"""(c) Renderer HTML snapshot.

Renders the showcase IR to the course index.html (neutral brand, deterministic)
and compares to the committed snapshot. Catches unintended changes to the HTML
the learner actually sees. Regenerate intentional changes with UPDATE_GOLDENS=1.
"""
import os
import tempfile

import brand
import render
from conftest import assert_golden


def _render_index(ir, animate=True):
    b = brand.load_brand("_default")
    d = tempfile.mkdtemp()
    render.render_course(ir, d, {}, brand=b, animate=animate)
    with open(os.path.join(d, "index.html"), encoding="utf-8") as fh:
        return fh.read()


def test_showcase_html_snapshot(showcase_ir):
    html = _render_index(showcase_ir)
    assert_golden("showcase.index.html", html)


def test_render_is_deterministic(showcase_ir):
    # Same IR -> byte-identical HTML on repeat renders.
    assert _render_index(showcase_ir) == _render_index(showcase_ir)
