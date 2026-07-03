"""M1 — self-healing generation loop.

After a course is drafted, `heal_course_md` re-lints and, while there are BLOCKING
violations, re-prompts the provider to fix ONLY those, re-lints, and keeps the BEST
(fewest-error) draft — up to a small cap. `generate()` runs it before writing, so a
lint-broken draft is auto-fixed within N rounds or the residuals are RETURNED (never
silently shipped). No metered calls — `run_cli` is the stubbed seam.
"""
import authoring as A


G = {"preferred": [], "banned": []}

# A one-unit §8 course whose only knowledge check has a SINGLE option — a blocking lint
# fault ("fewer than 2 options"). The FIXED variant adds a second option and lints clean.
BROKEN = """# Course

## Microlearning 1: One

**Slide 1 — Learning Objectives**
*Visual:* graphic · overview
*Objectives:* After this lesson, you will be able to:
- Do the thing

**Slide 2 — Knowledge Check**
*Question:* Only one option?
- A) The only choice
*Correct Answer:* A
*Feedback — Correct:* Yes.
*Feedback — Incorrect:* No.
"""
FIXED = BROKEN.replace("- A) The only choice",
                       "- A) The only choice\n- B) A second choice")


def _mk_source(tmp_path):
    d = tmp_path / "src"
    d.mkdir()
    (d / "src.txt").write_text("Some source material about the topic.", encoding="utf-8")
    return str(d)


def _stub(broken=BROKEN, fixed=FIXED, calls=None):
    """A provider that returns `broken` for the initial draft and `fixed` for any repair
    pass (repair prompts carry the 'LINT VIOLATIONS TO FIX' banner)."""
    def run(prov, prompt, **k):
        if calls is not None:
            calls.append("repair" if "LINT VIOLATIONS TO FIX" in prompt else "draft")
        return (True, fixed if "LINT VIOLATIONS TO FIX" in prompt else broken, "")
    return run


# ---- the primitive ------------------------------------------------------------

def test_clean_draft_needs_no_rounds(monkeypatch):
    monkeypatch.setattr(A, "run_cli", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no repair")))
    res = A.heal_course_md("claude", FIXED, glossary=G)
    assert res["lint_ok"] and res["rounds"] == 0 and res["history"] == []
    assert res["md"] == FIXED and res["units"] == 1


def test_broken_then_fixed_in_one_round(monkeypatch):
    calls = []
    monkeypatch.setattr(A, "run_cli", _stub(calls=calls))
    res = A.heal_course_md("claude", BROKEN, glossary=G)
    assert res["lint_ok"] and res["rounds"] == 1
    assert res["md"] == FIXED and res["lint_errors"] == []
    assert calls == ["repair"]                      # exactly one repair pass
    assert res["history"][0]["before"] and res["history"][0]["ok"]


def test_stops_at_cap_and_reports_residuals(monkeypatch):
    # every repair pass returns a DIFFERENT still-broken draft (more errors → not adopted;
    # here each stays 1 error so it's a stall) → loop halts, residuals survive.
    monkeypatch.setattr(A, "run_cli", _stub(fixed=BROKEN))   # repair also returns broken
    res = A.heal_course_md("claude", BROKEN, glossary=G, max_rounds=2)
    assert not res["lint_ok"]
    assert res["lint_errors"]                        # residuals RETURNED, not dropped
    assert res["md"] == BROKEN                        # never shipped something worse
    assert res["rounds"] == 1                         # a stall stops early (no wasted 2nd pass)


def test_provider_error_keeps_best_draft(monkeypatch):
    monkeypatch.setattr(A, "run_cli", lambda *a, **k: (False, "", "boom"))
    res = A.heal_course_md("claude", BROKEN, glossary=G)
    assert not res["lint_ok"] and res["md"] == BROKEN
    assert res["rounds"] == 1 and res["history"][0]["ok"] is False
    assert any("boom" in a for a in res["history"][0]["after"])


def test_max_rounds_zero_is_a_noop(monkeypatch):
    monkeypatch.setattr(A, "run_cli", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no call")))
    res = A.heal_course_md("claude", BROKEN, glossary=G, max_rounds=0)
    assert not res["lint_ok"] and res["rounds"] == 0 and res["md"] == BROKEN


def test_on_round_callback_fires(monkeypatch):
    monkeypatch.setattr(A, "run_cli", _stub())
    seen = []
    A.heal_course_md("claude", BROKEN, glossary=G, on_round=lambda n, ok, errs: seen.append((n, ok)))
    assert seen == [(1, True)]


# ---- generate() integration ---------------------------------------------------

def test_generate_auto_heals_before_write(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "run_cli", _stub())
    monkeypatch.setattr(A, "load_glossary", lambda b=None: G)
    out = tmp_path / "out" / "course.md"
    res = A.generate("claude", _mk_source(tmp_path), "obj", "aud", "concept-explainer",
                     None, str(out))
    assert res["ok"] and res["lint_ok"] and res["heal_rounds"] == 1
    # the WRITTEN file is the healed draft, not the broken first pass
    written = out.read_text(encoding="utf-8")
    assert "B) A second choice" in written
    assert res["heal_history"][0]["ok"]


def test_generate_reports_residuals_when_unfixable(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "run_cli", _stub(fixed=BROKEN))    # repairs never clear lint
    monkeypatch.setattr(A, "load_glossary", lambda b=None: G)
    out = tmp_path / "out" / "course.md"
    res = A.generate("claude", _mk_source(tmp_path), "obj", "aud", "concept-explainer",
                     None, str(out))
    assert res["ok"] and not res["lint_ok"]              # generation succeeds, lint flagged
    assert res["lint_errors"] and res["heal_rounds"] >= 1  # residuals surfaced, never silent


def test_build_repair_prompt_lists_issues():
    p = A.build_repair_prompt("## Microlearning 1: X\n", ["unit 1: bad thing", "unit 1: other"])
    assert "LINT VIOLATIONS TO FIX" in p
    assert "- unit 1: bad thing" in p and "- unit 1: other" in p
    assert "## Microlearning 1:" in p                    # the current script is embedded
