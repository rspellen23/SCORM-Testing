"""Scoped slide regeneration — the Step-2 'what to regenerate' checkboxes
(Content / Layout) narrow what the AI may change. Color is a client-side local
reshuffle and never reaches the model, so it isn't exercised here.

These assert the prompt carries the right directives and that a layout-locked
regen ignores any layout the model returns.
"""
import authoring as A


CUR = {"title": "X", "steps": [{"num": "1", "title": "a", "body": "b"}]}


def _prompt(**kw):
    return A.build_regen_slide_prompt("process", CUR, [], 1, 3, "", "", "", "SRC", "", **kw)


def test_content_only_rewords_and_locks_layout():
    p = _prompt(scope_content=True, scope_layout=False)
    assert "Re-word" in p
    assert 'MUST stay "process"' in p
    assert "must be one of:" not in p   # layout choice not offered


def test_layout_only_keeps_wording():
    p = _prompt(scope_content=False, scope_layout=True)
    assert "Keep the existing wording" in p
    assert "must be one of:" in p        # layout choice IS offered


def test_both_is_full_redraft():
    p = _prompt(scope_content=True, scope_layout=True)
    assert "Full re-draft" in p


def test_layout_lock_ignores_model_layout(monkeypatch):
    # when layout is locked, a model that returns a different layout is overridden
    monkeypatch.setattr(A, "read_sources", lambda f: ("source text", ["a.md"], []))
    monkeypatch.setattr(A, "run_cli",
                        lambda *a, **k: (True, '{"layout":"timeline","content":{"title":"Y"}}', ""))
    res = A.regenerate_slide("claude", "/src", "process", CUR, [], 1, 3,
                             scope_content=True, scope_layout=False)
    assert res["ok"] and res["layout"] == "process"   # NOT timeline


def test_layout_unlocked_accepts_model_layout(monkeypatch):
    monkeypatch.setattr(A, "read_sources", lambda f: ("source text", ["a.md"], []))
    monkeypatch.setattr(A, "run_cli",
                        lambda *a, **k: (True, '{"layout":"timeline","content":{"title":"Y","milestones":[]}}', ""))
    res = A.regenerate_slide("claude", "/src", "process", CUR, [], 1, 3,
                             scope_content=True, scope_layout=True)
    assert res["ok"] and res["layout"] == "timeline"
