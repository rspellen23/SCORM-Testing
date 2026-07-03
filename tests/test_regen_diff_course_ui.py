"""X1 — diff + accept/reject on regenerate (course side): wiring + merge round-trip.

A regenerated microlearning previously overwrote the unit on disk immediately. X1
makes it reviewable: the server hands back the OLD and NEW unit markdown without
writing (review flag), the client aligns them block-by-block (blank-line delimited)
and lets the operator keep the new intro but reject a reworked knowledge check, then
posts the merged unit to /api/apply-unit-merge to land it.

Guards the moving parts in dashboard/index.html + dashboard/server.py, plus the pure
engine helpers (extract_unit, apply-merge splice) that the endpoints stand on.
"""
import json
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()
SERVER = open(os.path.join(REPO, "dashboard", "server.py"), encoding="utf-8").read()
sys.path.insert(0, os.path.join(REPO, "dashboard"))
sys.path.insert(0, os.path.join(REPO, "src"))


def _fn(name):
    marker = "function " + name + "("
    assert marker in HTML, f"{name} missing from index.html"
    return HTML.split(marker, 1)[1].split("\n}", 1)[0]


# ===== 1. review modal + client wiring =====

def test_course_diff_modal_present():
    assert 'id="udiff_modal"' in HTML and 'id="udiff_list"' in HTML
    assert 'onclick="applyUnitDiff()"' in HTML and 'onclick="closeUnitDiff()"' in HTML
    assert "unitSetAll(true)" in HTML and "unitSetAll(false)" in HTML


def test_regen_module_requests_review_and_opens_diff():
    fn = _fn("regenModule")
    assert "review:true" in fn                        # ask for old+new, don't write yet
    assert "openUnitDiff(which" in fn                  # route into the block diff
    assert "val('mod_guide_'+which)" in fn             # guidance steer preserved (Q5)


def test_block_split_and_positional_alignment():
    fn = _fn("openUnitDiff")
    assert "splitBlocks(oldMd)" in fn and "splitBlocks(newMd)" in fn
    assert "Math.max(UDIFF_OLD.length, UDIFF_NEW.length)" in fn   # align by position
    sb = _fn("splitBlocks")
    assert "split(" in sb                              # blank-line delimiter


def test_apply_unit_diff_reconstructs_and_posts_merge():
    fn = _fn("applyUnitDiff")
    assert "take?r.nw:r.o" in fn                       # take-new default, keep-mine rejects
    assert "parts.join('\\n\\n')" in fn                # rebuild the unit markdown
    assert "/api/apply-unit-merge" in fn
    assert "scanScript()" in fn                        # refresh after landing


# ===== 2. server routing =====

def test_apply_merge_endpoint_routed():
    assert '"/api/apply-unit-merge"' in SERVER
    assert "do_apply_unit_merge(p)" in SERVER


def test_regenerate_unit_review_branch_returns_without_writing():
    body = SERVER.split("def do_regenerate_unit(", 1)[1].split("\ndef ", 1)[0]
    assert 'p.get("review")' in body
    assert '"old_md"' in body and '"new_md"' in body
    assert "extract_unit(" in body
    # the shared write path is factored out and reused by both landing routes
    assert "_apply_unit_markdown(" in body
    assert "def _apply_unit_markdown(" in SERVER


# ===== 3. engine helpers (the endpoints stand on these) =====

def test_extract_unit_round_trips():
    import authoring as A
    md = ("# C\n\n## Microlearning 1: Alpha\n\nOne.\n\n"
          "## Microlearning 2: Beta\n\nTwo.\n\n### H\n\nBody.\n")
    u2 = A.extract_unit(md, 2)
    assert u2.startswith("## Microlearning 2: Beta")
    assert "Body." in u2 and "Alpha" not in u2        # only unit 2, not its neighbor
    assert A.extract_unit(md, 9) == ""                 # missing unit → empty


def test_apply_unit_merge_splices_the_chosen_blocks():
    import server
    root = tempfile.mkdtemp(prefix="cb_x1_")
    try:
        script = os.path.join(root, "course.md")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write("# C\n\n## Microlearning 1: Alpha\n\nKeep me.\n\n"
                     "## Microlearning 2: Beta\n\nOld intro.\n\n### H\n\nOld body.\n")
        json.dump({"name": "D", "script": script},
                  open(os.path.join(root, "project.json"), "w", encoding="utf-8"))
        # operator kept the new intro but dropped the reworked body (merged omits it)
        merged = "## Microlearning 2: Beta\n\nNew intro.\n\n### H"
        res = server.do_apply_unit_merge(
            {"project": root, "script": script, "which": 2, "merged_md": merged})
        assert res["ok"] is True
        out = open(script, encoding="utf-8").read()
        assert "New intro." in out and "Old body." not in out
        assert "## Microlearning 1: Alpha" in out and "Keep me." in out   # neighbor untouched
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_apply_unit_merge_rejects_empty():
    import server
    root = tempfile.mkdtemp(prefix="cb_x1_")
    try:
        script = os.path.join(root, "course.md")
        open(script, "w").write("# C\n\n## Microlearning 1: A\n\nx.\n")
        res = server.do_apply_unit_merge(
            {"project": root, "script": script, "which": 1, "merged_md": "   "})
        assert res["ok"] is False
    finally:
        shutil.rmtree(root, ignore_errors=True)
