"""Course wizard: Generate preview comes BEFORE Output format, and publishing was
folded onto that final step. The preview is render-only HTML (no SCORM/cmi5 package
— that's reserved for publish); the package FORMAT is chosen at publish time, when
the chosen formats are built straight into the output folder.

Static drift guards over the dashboard wiring — they fail if a future edit re-orders
the steps, re-couples the preview to the format pickers, or reverts publish to the
old 'promote pre-staged files' model.
"""
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()


def _course_steps():
    line = re.search(r"const COURSE_STEPS=\[(.*?)\];", HTML).group(1)
    return [s.strip().strip("'\"") for s in line.split(",")]


def test_preview_step_precedes_output_and_publish():
    steps = _course_steps()
    assert "Generate preview" in steps and "Output & publish" in steps
    assert steps.index("Generate preview") < steps.index("Output & publish")
    # the dissolved standalone "Output format" / "Publish" steps are gone
    assert "Output format" not in steps and "Publish" not in steps


def test_scope_radio_machinery_removed():
    for dead in ("b_scope", "b_which", "syncScope"):
        assert dead not in HTML, dead


def test_preview_is_render_only_html():
    fn = HTML.split("async function generateCourses(", 1)[1].split("\n}", 1)[0]
    # preview renders HTML only — no SCORM/cmi5 package (that's reserved for publish)
    assert "formats:['html']" in fn and "stage:true" in fn
    assert "formats:['scorm']" not in fn
    # the preview must NOT read the format checkboxes — format is a publish-time choice
    assert ".b_fmt:checked" not in fn


def test_publish_builds_chosen_formats_to_output():
    fn = HTML.split("async function publishItems(", 1)[1].split("\n}", 1)[0]
    assert ".b_fmt:checked" in fn            # reads the operator's chosen formats
    assert "stage:false" in fn               # writes straight to the output folder
    assert "/api/build" in fn                # builds, rather than promoting staged files
    assert "/api/publish" not in fn          # the old promote endpoint is no longer used


def test_format_controls_and_publish_share_one_stage():
    s6 = HTML.split('id="s6"', 1)[1].split('<!--', 1)[0]
    assert 'class="b_fmt"' in s6 and 'id="b_publish"' in s6
