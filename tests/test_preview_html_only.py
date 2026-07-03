"""Course preview renders HTML only — no SCORM package (stage 4).

The preview step built a SCORM zip into a hidden .preview area just to show the
HTML, so previewing littered packages. Now preview renders only the learner-facing
.course dir (via `from-md --no-package`); packaging is reserved for publish. The
build report is keyed off the course dir since there's no zip beside it.
"""
import os
import sys

import cli
from md_import import import_md

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOWCASE = os.path.join(REPO, "tests", "fixtures", "showcase.md")

_DASH = os.path.join(REPO, "dashboard")
if _DASH not in sys.path:
    sys.path.insert(0, _DASH)
import server  # noqa: E402

HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()


# --------------------------------------------------------------- _emit functional

def test_emit_no_package_renders_html_only(tmp_path):
    ir, used = import_md(SHOWCASE, which=1, image_dir=None)
    blobs = {rel: open(src, "rb").read() for rel, src in used.items()}
    out_zip = tmp_path / "c_m1_preview.zip"
    cli._emit(ir, blobs, str(out_zip), brand_name="teletracking",
              package=False, lint_md=SHOWCASE)
    course = tmp_path / "c_m1_preview.course"
    assert (course / "index.html").exists()                 # learner-facing HTML rendered
    assert (tmp_path / "c_m1_preview.report.json").exists()  # report keyed off the course dir
    assert not out_zip.exists()                              # NO SCORM zip


def test_emit_packages_by_default(tmp_path):
    ir, used = import_md(SHOWCASE, which=1, image_dir=None)
    blobs = {rel: open(src, "rb").read() for rel, src in used.items()}
    out_zip = tmp_path / "c_m1.zip"
    cli._emit(ir, blobs, str(out_zip), brand_name="teletracking", keep_dir=True)
    assert out_zip.exists()                                  # default still packages SCORM


# --------------------------------------------------------------- build_jobs routing

def test_html_format_is_preview_job_without_zip(monkeypatch):
    monkeypatch.setattr(server, "_safe_path_arg", lambda v, label: v)
    monkeypatch.setattr(server, "microlearnings", lambda md: [{"which": 1}])
    jobs = server.build_jobs({"md": "/x/course.md", "images": "/x/img", "out": "/x/out",
                              "brand": "teletracking", "formats": ["html"],
                              "scope": "single", "which": 1})
    assert len(jobs) == 1
    j = jobs[0]
    assert j["fmt"] == "html"
    assert "--no-package" in j["args"] and "from-md" in j["args"]
    assert j["out"].endswith(".course")
    assert j["preview"].endswith("index.html")
    assert "scorm" not in j["args"] and "cmi5" not in j["args"]   # no packaging requested


def test_scorm_format_still_packages(monkeypatch):
    monkeypatch.setattr(server, "_safe_path_arg", lambda v, label: v)
    monkeypatch.setattr(server, "microlearnings", lambda md: [{"which": 1}])
    jobs = server.build_jobs({"md": "/x/course.md", "images": "/x/img", "out": "/x/out",
                              "brand": "teletracking", "formats": ["scorm"],
                              "scope": "single", "which": 1})
    j = jobs[0]
    assert j["out"].endswith(".zip") and "--keep-dir" in j["args"]


# --------------------------------------------------------------- UI drift

def test_generate_preview_requests_html_format():
    fn = HTML.split("async function generateCourses(", 1)[1].split("\n}", 1)[0]
    assert "formats:['html']" in fn
    assert "formats:['scorm']" not in fn
