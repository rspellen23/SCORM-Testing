"""X1 — diff + accept/reject on regenerate (deck side): dashboard wiring drift guard.

When a slide is regenerated the operator should be able to keep the new title but
reject the new body — a per-field merge, not a wholesale swap. This is pure
client-side JS over the two slide content objects (no server route), so the guard
asserts the moving parts in dashboard/index.html: the review modal, the
reviewThenApply router that replaces the old wholesale-apply call sites, and the
merge semantics in applyDiff.
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()


def _fn(name):
    """Slice one JS function body out of index.html for focused assertions."""
    marker = "function " + name + "("
    assert marker in HTML, f"{name} missing from index.html"
    return HTML.split(marker, 1)[1].split("\n}", 1)[0]


# ===== 1. the review modal exists =====

def test_diff_modal_present():
    assert 'id="diff_modal"' in HTML
    assert 'id="diff_list"' in HTML
    assert 'onclick="applyDiff()"' in HTML
    assert 'onclick="closeDiff()"' in HTML
    # bulk shortcuts for the two common intents
    assert "diffSetAll(true)" in HTML and "diffSetAll(false)" in HTML


# ===== 2. regen routes through the review step, not straight to wholesale apply =====

def test_regen_paths_route_through_review():
    # both the single-candidate regen and the multi-candidate picker go via reviewThenApply
    assert "reviewThenApply(i, res, wantColor, wantContent, wantLayout)" in _fn("regenSlide")
    assert "reviewThenApply(i, c, wantColor" in _fn("useCandidate")


def test_review_falls_back_to_wholesale_when_not_field_comparable():
    body = _fn("reviewThenApply")
    # a layout change or a content-less regen can't be field-merged → apply whole
    assert "newLayout!==oldLayout" in body
    assert "applyCandidate(i, c, wantColor, wantContent, wantLayout)" in body
    # only the genuinely-changed top-level keys become diff rows
    assert "_diffEq(oldC[k], newC[k])" in body


# ===== 3. merge semantics: default-to-new, keep-mine rejects, removals honored =====

def test_apply_diff_merges_field_by_field():
    body = _fn("applyDiff")
    assert "Object.assign({}, DIFF_OLD)" in body          # start from the current slide
    assert "merged[k]=DIFF_NEW[k]" in body                # take-new copies the new field
    assert "delete merged[k]" in body                     # take-new honors an AI removal
    # the merged slide is applied through the existing single apply path
    assert "applyCandidate(i, { layout:DIFF_LAYOUT, content:merged" in body


def test_rows_default_to_take_new():
    body = _fn("renderDiff")
    assert 'type="checkbox"' in body and "checked" in body  # every changed field pre-set to new
    assert "your current" in body and "new draft" in body    # both sides are shown
