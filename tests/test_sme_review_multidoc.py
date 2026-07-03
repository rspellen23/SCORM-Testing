"""Apply-SME-review across multiple reviewed docs (course stage 3).

Parallel generation writes one review .docx per module, so an SME hands back
several. The stage accepted a single file; now it accepts a FOLDER (or one file).
`do_revise` expands a folder to its .docx files (skipping Word ~$ lock files) and
`authoring.revise` merges every reviewed body + comments into one revise pass,
labeling each section by its module number when the filename carries one.
"""
import os
import sys

import authoring as A

_DASH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard")
if _DASH not in sys.path:
    sys.path.insert(0, _DASH)
import server  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()


# --------------------------------------------------------------- authoring.revise

def _stub_cli(monkeypatch):
    cap = {}
    def fake(provider, prompt, model=None):
        cap["prompt"] = prompt
        return (True, "## Microlearning 1: A\n\nx", "")
    monkeypatch.setattr(A, "run_cli", fake)
    return cap


def test_revise_merges_multiple_reviewed_docs(monkeypatch, tmp_path):
    script = tmp_path / "course.md"; script.write_text("## Microlearning 1: A\n\nx", encoding="utf-8")
    bodies = {"course_m1_review.docx": "EDIT ONE", "course_m2_review.docx": "EDIT TWO"}
    monkeypatch.setattr(A, "_read_one", lambda d: bodies.get(os.path.basename(str(d)), ""))
    monkeypatch.setattr(A, "_docx_comments", lambda d: (["fix the intro"] if "m2" in str(d) else []))
    cap = _stub_cli(monkeypatch)
    res = A.revise("claude", str(script),
                   [str(tmp_path / "course_m1_review.docx"), str(tmp_path / "course_m2_review.docx")],
                   str(tmp_path / "out.md"))
    p = cap["prompt"]
    assert "----- Microlearning 1 -----" in p and "EDIT ONE" in p
    assert "----- Microlearning 2 -----" in p and "EDIT TWO" in p
    assert "fix the intro" in p                 # comments merged across docs
    assert res["comments_found"] == 1


def test_revise_single_doc_is_unlabeled(monkeypatch, tmp_path):
    script = tmp_path / "course.md"; script.write_text("## Microlearning 1: A\n\nx", encoding="utf-8")
    monkeypatch.setattr(A, "_read_one", lambda d: "SOLO EDIT")
    monkeypatch.setattr(A, "_docx_comments", lambda d: [])
    cap = _stub_cli(monkeypatch)
    A.revise("claude", str(script), str(tmp_path / "course_m1_review.docx"), str(tmp_path / "out.md"))
    p = cap["prompt"]
    assert "SOLO EDIT" in p
    assert "----- Microlearning" not in p       # one doc => no section wrapper


def test_revise_no_readable_docs_errors(monkeypatch, tmp_path):
    script = tmp_path / "course.md"; script.write_text("## Microlearning 1: A\n\nx", encoding="utf-8")
    monkeypatch.setattr(A, "_read_one", lambda d: "")
    monkeypatch.setattr(A, "_docx_comments", lambda d: [])
    res = A.revise("claude", str(script),
                   [str(tmp_path / "a.docx"), str(tmp_path / "b.docx")], str(tmp_path / "out.md"))
    assert res["ok"] is False and "no readable" in res["error"].lower()


# --------------------------------------------------------------- do_revise folder expansion

def test_do_revise_expands_a_folder(monkeypatch, tmp_path):
    folder = tmp_path / "reviews"; folder.mkdir()
    (folder / "course_m1_review.docx").write_bytes(b"x")
    (folder / "course_m2_review.docx").write_bytes(b"x")
    (folder / "~$course_m1_review.docx").write_bytes(b"lock")   # Word lock file -> skipped
    script = tmp_path / "course.md"; script.write_text("## Microlearning 1: A", encoding="utf-8")
    cap = {}
    monkeypatch.setattr(A, "revise",
                        lambda **kw: (cap.update(reviewed=kw["reviewed_docx"]) or
                                      {"ok": True, "lint_ok": False, "units": 0}))
    server.do_revise({"script": str(script), "approved_dir": str(tmp_path), "reviewed": str(folder)})
    rev = cap["reviewed"]
    assert isinstance(rev, list) and len(rev) == 2
    assert all(r.endswith(".docx") for r in rev)
    assert not any("~$" in os.path.basename(r) for r in rev)


def test_do_revise_empty_folder_errors(monkeypatch, tmp_path):
    folder = tmp_path / "empty"; folder.mkdir()
    script = tmp_path / "course.md"; script.write_text("## Microlearning 1: A", encoding="utf-8")
    res = server.do_revise({"script": str(script), "approved_dir": str(tmp_path), "reviewed": str(folder)})
    assert res["ok"] is False and "no .docx" in res["error"].lower()


# --------------------------------------------------------------- UI drift guards

def test_review_picker_accepts_folder_or_file():
    assert "pick('both','rev_doc',null,['docx'])" in HTML
    assert "a folder of reviewed .docx files, or a single .docx" in HTML
    assert "one review doc per module" in HTML
