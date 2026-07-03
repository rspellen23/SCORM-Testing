"""M2 — WCAG conformance pass + AI alt text.

Two halves, both no-metered-API:
  1. `build_report.a11y_findings` — automated accessibility checks (alt text, heading
     order, brand-token contrast, knowledge-check labels) surfaced as a DISTINCT,
     NON-BLOCKING `a11y` section in the build report (James's fork 1).
  2. `authoring.heal_alt_text` — a generation-time redraft loop (James's fork 2) that
     re-prompts the provider to fill any informative image missing its description,
     reusing the M1 self-heal shape. `run_cli` is the stubbed seam.

A `*Visual:*` with no description falls back to alt = the bare type keyword, so the
gap the grammar actually produces is a NON-DESCRIPTIVE alt, not an empty one —
`alt_is_weak` is the shared oracle both halves agree on.
"""
import os
import build_report as BR
import authoring as A


# --------------------------------------------------------------------------- colors
def test_contrast_ratio_extremes_and_parse():
    assert round(BR.contrast_ratio("#FFFFFF", "#000000"), 1) == 21.0
    assert round(BR.contrast_ratio("#000", "#000"), 1) == 1.0        # 3-digit hex, identical
    assert BR.contrast_ratio("not-a-color", "#fff") is None


def test_parse_tokens_css_keeps_only_hex():
    css = """:root{
      --brand-ink: #1F2937;
      --brand-page-bg:#FFFFFF;
      --brand-accent: #abc;
      --brand-font-body: system-ui, sans-serif;   /* not a color -> dropped */
      --brand-radius: 14px;                         /* not a color -> dropped */
    }"""
    tk = BR.parse_tokens_css(css)
    assert tk["--brand-ink"] == "#1F2937"
    assert tk["--brand-page-bg"] == "#FFFFFF"
    assert tk["--brand-accent"] == "#abc"
    assert "--brand-font-body" not in tk and "--brand-radius" not in tk


# --------------------------------------------------------------------------- alt_is_weak
def test_alt_is_weak():
    assert BR.alt_is_weak("") and BR.alt_is_weak("   ") and BR.alt_is_weak(None)
    assert BR.alt_is_weak("screenshot") and BR.alt_is_weak("Diagram") and BR.alt_is_weak("photo")
    assert not BR.alt_is_weak("The export button in the toolbar")
    assert not BR.alt_is_weak("a labelled workflow diagram")     # phrase, not a bare token


# --------------------------------------------------------------------------- alt-text check
def test_alt_check_flags_weak_and_missing_but_not_good_or_decorative():
    ir = {"title": "T", "blocks": [
        {"type": "image", "src": "a.png", "alt": ""},                       # missing
        {"type": "image", "src": "b.png", "alt": "screenshot"},             # non-descriptive
        {"type": "imageText", "src": "c.png", "alt": "A clear labelled diagram of the flow"},  # good
        {"type": "image", "src": "d.png", "alt": "", "decorative": True},   # decorative -> skip
    ]}
    finds = [f for f in BR.a11y_findings(ir) if f["check"] == "alt-text"]
    where = {f["where"] for f in finds}
    assert where == {"image #1", "image #2"}            # exactly the two bad ones
    assert all(f["severity"] == "warn" for f in finds)


def test_alt_check_walks_nested_entry_images():
    ir = {"title": "T", "blocks": [
        {"type": "steps", "entries": [
            {"src": "s1.png", "alt": ""},                     # missing -> flagged
            {"src": "s2.png", "alt": "a filled progress bar"},
        ]},
    ]}
    finds = [f for f in BR.a11y_findings(ir) if f["check"] == "alt-text"]
    assert len(finds) == 1 and "entry" in finds[0]["where"]


# --------------------------------------------------------------------------- heading order
def test_heading_order_flags_skipped_level():
    ir = {"title": "T", "blocks": [                     # title = h1
        {"type": "heading", "level": 3, "html": "<p>Jumps to h3</p>"},
    ]}
    finds = [f for f in BR.a11y_findings(ir) if f["check"] == "heading-order"]
    assert any("h1" in f["where"] and "h3" in f["where"] for f in finds)


def test_heading_order_clean_scale_passes():
    ir = {"title": "T", "blocks": [                     # h1 -> h2 -> h2 : conformant
        {"type": "heading", "level": 2, "html": "<p>Section</p>"},
        {"type": "headingParagraph", "level": 2, "headingHtml": "<p>Another</p>", "html": "body"},
    ]}
    assert [f for f in BR.a11y_findings(ir) if f["check"] == "heading-order"] == []


def test_heading_order_flags_empty_heading_text():
    ir = {"title": "T", "blocks": [{"type": "heading", "level": 2, "html": "<p></p>"}]}
    finds = [f for f in BR.a11y_findings(ir) if f["check"] == "heading-order"]
    assert any("no text" in f["message"] for f in finds)


# --------------------------------------------------------------------------- contrast
def test_contrast_flags_failing_pair_only():
    tokens = {
        "--brand-ink": "#1F2937", "--brand-page-bg": "#FFFFFF",     # ~13:1 pass
        "--brand-accent-ink": "#BBBBBB",                            # grey on white -> fail AA
    }
    finds = [f for f in BR.a11y_findings({"title": "T", "blocks": []}, brand_tokens=tokens)
             if f["check"] == "contrast"]
    assert len(finds) == 1
    assert "--brand-accent-ink" in finds[0]["where"] and "below WCAG AA" in finds[0]["message"]


def test_contrast_skipped_without_tokens():
    finds = [f for f in BR.a11y_findings({"title": "T", "blocks": []}) if f["check"] == "contrast"]
    assert finds == []


# --------------------------------------------------------------------------- KC labels
def test_kc_labels_flags_empty_prompt_and_option():
    ir = {"title": "T", "blocks": [
        {"type": "knowledgeCheck", "prompt": "", "options": [{"html": "A"}, {"html": ""}]},
        {"type": "knowledgeCheck", "prompt": "<p>Good?</p>", "options": [{"html": "Yes"}, {"html": "No"}]},
    ]}
    finds = [f for f in BR.a11y_findings(ir) if f["check"] == "kc-labels"]
    msgs = " ".join(f["message"] for f in finds)
    assert "no question prompt" in msgs and "no text label" in msgs
    assert all("#1" in f["where"] for f in finds)      # only the first KC has faults


# --------------------------------------------------------------------------- assemble integration
def test_assemble_carries_a11y_non_blocking():
    ir = {"title": "T", "_stats": {"blocks": 1, "assets": 0},
          "blocks": [{"type": "image", "src": "a.png", "alt": ""}]}
    rep = BR.assemble(ir)
    assert rep["ok"] is True                           # a11y never flips ok
    assert isinstance(rep["a11y"], list) and rep["a11y"]
    assert rep["a11y"][0]["check"] == "alt-text"
    assert "not full WCAG conformance" in rep["a11y_note"]


def test_assemble_a11y_empty_when_clean():
    ir = {"title": "T", "_stats": {"blocks": 0}, "blocks": []}
    rep = BR.assemble(ir)
    assert rep["a11y"] == [] and rep["ok"] is True


# --------------------------------------------------------------------------- alt_gaps oracle
WEAK = """# Course

## Microlearning 1: One

**Slide 1 — Learning Objectives**
*Visual:* graphic · a clear overview of the topic · slot: `obj.png`
*Objectives:* After this lesson, you will be able to:
- Do the thing

**Slide 2 — Detail**
*Visual:* screenshot · slot: `screen.png`
Body text explaining the export button.
"""
# the FIXED variant supplies the missing description on the Slide-2 visual
FIXED = WEAK.replace(
    "*Visual:* screenshot · slot: `screen.png`",
    "*Visual:* screenshot · The toolbar with the export button highlighted · slot: `screen.png`")


def test_alt_gaps_finds_weak_visual():
    gaps = A.alt_gaps(WEAK)
    assert len(gaps) == 1 and gaps[0]["slot"] == "screen.png" and gaps[0]["unit"] == 1


def test_alt_gaps_empty_when_all_described():
    assert A.alt_gaps(FIXED) == []


def test_alt_gaps_ignores_decorative():
    md = WEAK.replace("*Visual:* screenshot · slot: `screen.png`",
                      "*Visual:* decorative · slot: `screen.png`")
    assert A.alt_gaps(md) == []                         # decorative empty alt is intentional


def test_alt_gaps_non_course_is_empty():
    assert A.alt_gaps("not a course at all") == []


# --------------------------------------------------------------------------- heal_alt_text loop
def _alt_stub(fixed=FIXED, calls=None):
    """Provider returning `fixed` for any alt-repair prompt (carries the banner)."""
    def run(prov, prompt, **k):
        is_repair = "VISUALS MISSING ALT TEXT" in prompt
        if calls is not None:
            calls.append("repair" if is_repair else "draft")
        return (True, fixed if is_repair else WEAK, "")
    return run


def test_heal_alt_already_complete_needs_no_rounds(monkeypatch):
    monkeypatch.setattr(A, "run_cli", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no repair")))
    res = A.heal_alt_text("claude", FIXED)
    assert res["rounds"] == 0 and res["gaps"] == [] and res["history"] == [] and res["md"] == FIXED


def test_heal_alt_weak_then_fixed_in_one_round(monkeypatch):
    calls = []
    monkeypatch.setattr(A, "run_cli", _alt_stub(calls=calls))
    res = A.heal_alt_text("claude", WEAK)
    assert res["rounds"] == 1 and res["gaps"] == [] and res["md"] == FIXED
    assert calls == ["repair"]
    assert res["history"][0]["before"] == 1 and res["history"][0]["ok"] is True


def test_heal_alt_stalls_keeps_best(monkeypatch):
    # a provider that never actually fixes anything (echoes the weak draft) must not loop
    # forever or ship something worse — it stops after one non-improving pass.
    monkeypatch.setattr(A, "run_cli", lambda prov, prompt, **k: (True, WEAK, ""))
    res = A.heal_alt_text("claude", WEAK)
    assert res["rounds"] == 1 and len(res["gaps"]) == 1 and res["md"] == WEAK


def test_heal_alt_provider_error_ends_gracefully(monkeypatch):
    monkeypatch.setattr(A, "run_cli", lambda prov, prompt, **k: (False, "", "provider exploded"))
    res = A.heal_alt_text("claude", WEAK)
    assert res["rounds"] == 1 and len(res["gaps"]) == 1 and res["md"] == WEAK
    assert res["history"][0]["ok"] is False and "failed" in res["history"][0]["after"]


def test_heal_alt_respects_round_cap(monkeypatch):
    # every repair reduces gaps by making one more visual weak->described would need many
    # rounds; cap at max_rounds and return residuals rather than looping past the cap.
    monkeypatch.setattr(A, "run_cli", lambda prov, prompt, **k: (True, WEAK, ""))  # never improves
    res = A.heal_alt_text("claude", WEAK, max_rounds=2)
    assert res["rounds"] <= 2


# --------------------------------------------------------------------------- prompts
def test_build_alt_repair_prompt_lists_gaps_and_rules():
    p = A.build_alt_repair_prompt(WEAK, [{"unit": 1, "src": "assets/screen.png", "slot": "screen.png"}])
    assert "VISUALS MISSING ALT TEXT" in p and "screen.png" in p
    assert "alt-text" in p.lower() and "Change NOTHING else" in p
    assert "## Microlearning 1:" in p


def test_build_prompt_teaches_alt_text_rule():
    # the generator is told every informative *Visual:* must carry its description
    assert "ALT TEXT" in A.MEDIA_RULES and "description / alt text" in A.MEDIA_RULES


# --------------------------------------------------------------------------- generate() end-to-end
def test_generate_fills_alt_and_reports_residuals(tmp_path, monkeypatch):
    src = tmp_path / "src"; src.mkdir()
    (src / "s.txt").write_text("Source about the export workflow.", encoding="utf-8")
    out = tmp_path / "out" / "course.md"

    def run(prov, prompt, **k):
        if "VISUALS MISSING ALT TEXT" in prompt:
            return (True, FIXED, "")               # alt redraft -> describes the visual
        if "LINT VIOLATIONS TO FIX" in prompt:
            return (True, WEAK, "")                # lint self-heal (WEAK already lints clean)
        return (True, WEAK, "")                    # first draft
    monkeypatch.setattr(A, "run_cli", run)

    res = A.generate("claude", str(src), "Teach export", "Operators",
                     "concept-explainer", 1, str(out))
    assert res["ok"] is True
    written = out.read_text(encoding="utf-8")
    assert "The toolbar with the export button highlighted" in written   # alt got filled
    assert res["alt_rounds"] == 1 and res["alt_gaps"] == []
    assert "alt_history" in res
