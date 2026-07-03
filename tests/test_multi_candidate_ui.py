"""M9 — multi-candidate slide picker, dashboard wiring (static drift guard).

The slide builder lets the operator ask for N treatments and pick one. This guards
the four moving parts in dashboard/index.html: the count selector on each slide row,
the regen payload carrying `n` + `brand`, the candidate picker modal, and the
openCandidates/applyCandidate/useCandidate plumbing that renders previews and applies
the chosen treatment.
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()


def _fn(name):
    return HTML.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


def test_count_selector_present_per_row():
    assert 'id="sl_regen_n_${i}"' in HTML


def test_regen_payload_carries_n_and_brand():
    fn = _fn("regenSlide")
    assert "n:nWant" in fn
    assert "brand:brand()" in fn
    assert "openCandidates(" in fn                  # branches to the picker on candidates


def test_candidate_modal_exists():
    assert 'id="cand_modal"' in HTML
    assert 'id="cand_grid"' in HTML


def test_picker_functions_defined():
    assert "function openCandidates(" in HTML
    assert "function applyCandidate(" in HTML
    assert "function useCandidate(" in HTML
    assert "function closeCand(" in HTML


def test_previews_use_deterministic_slide_svg():
    fn = _fn("renderCandPreview")
    assert "/api/slide-svg" in fn                   # cheap, exact, no AI


def test_use_candidate_applies_chosen_treatment():
    fn = _fn("useCandidate")
    # X1: the chosen candidate now routes through the diff/accept-reject review step
    # (reviewThenApply) instead of a wholesale applyCandidate — the picker closes first.
    assert "reviewThenApply(i, c, wantColor" in fn
    assert "closeCand()" in fn
