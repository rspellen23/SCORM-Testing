"""M9 — multi-candidate slide regeneration.

`regenerate_slide(..., n>1)` drafts N distinct treatments, ranks them best-first
(deterministically, no AI), and returns a `candidates` list while still hoisting the
top pick for backward compatibility. n<=1 stays single-shot and byte-identical.
"""
import authoring as A


CUR = {"title": "X", "steps": [{"num": "1", "title": "a", "body": "b"}]}


def _sources(monkeypatch):
    monkeypatch.setattr(A, "read_sources", lambda f, urls=None: ("source text", ["a.md"], []))


# ---- prompt-level: variation nudge is opt-in (byte-identical when variants<=1) ----

def test_prompt_byte_identical_when_single_variant():
    base = A.build_regen_slide_prompt("process", CUR, [], 1, 3, "", "", "", "SRC", "")
    explicit = A.build_regen_slide_prompt("process", CUR, [], 1, 3, "", "", "", "SRC", "",
                                          variant=0, variants=1)
    assert base == explicit
    assert "TREATMENT VARIANT" not in base


def test_prompt_adds_variation_line_when_multiple():
    p = A.build_regen_slide_prompt("process", CUR, [], 1, 3, "", "", "", "SRC", "",
                                   variant=2, variants=3)
    assert "TREATMENT VARIANT 2 OF 3" in p


# ---- single path unchanged ----

def test_single_path_returns_one_slide_no_candidates(monkeypatch):
    _sources(monkeypatch)
    monkeypatch.setattr(A, "run_cli",
                        lambda *a, **k: (True, '{"layout":"process","content":{"title":"Y","steps":[]}}', ""))
    res = A.regenerate_slide("claude", "/src", "process", CUR, [], 1, 3)
    assert res["ok"] and res["layout"] == "process"
    assert "candidates" not in res


# ---- multi-candidate path ----

def test_multi_returns_n_candidates(monkeypatch):
    _sources(monkeypatch)
    calls = {"n": 0}
    outs = [
        '{"layout":"process","content":{"title":"A","steps":[{"num":"1","title":"a","body":"b"}]}}',
        '{"layout":"process","content":{"title":"B","steps":[{"num":"1","title":"c","body":"d"}]}}',
        '{"layout":"process","content":{"title":"C","steps":[{"num":"1","title":"e","body":"f"}]}}',
    ]

    def fake_cli(*a, **k):
        i = calls["n"]; calls["n"] += 1
        return (True, outs[i], "")

    monkeypatch.setattr(A, "run_cli", fake_cli)
    res = A.regenerate_slide("claude", "/src", "process", CUR, [], 1, 3, n=3)
    assert res["ok"]
    assert len(res["candidates"]) == 3
    # top pick is hoisted for backward-compat
    assert res["content"] == res["candidates"][0]["content"]
    assert calls["n"] == 3                      # one AI pass per candidate


def test_multi_drops_unparseable_candidates_but_keeps_good_ones(monkeypatch):
    _sources(monkeypatch)
    seq = iter([
        (True, "not json at all", ""),
        (True, '{"layout":"process","content":{"title":"OK","steps":[{"num":"1","title":"a","body":"b"}]}}', ""),
        (True, "}{ also broken", ""),
    ])
    monkeypatch.setattr(A, "run_cli", lambda *a, **k: next(seq))
    res = A.regenerate_slide("claude", "/src", "process", CUR, [], 1, 3, n=3)
    assert res["ok"]
    assert len(res["candidates"]) == 1
    assert res["candidates"][0]["content"]["title"] == "OK"


def test_multi_all_fail_returns_error(monkeypatch):
    _sources(monkeypatch)
    monkeypatch.setattr(A, "run_cli", lambda *a, **k: (True, "garbage", ""))
    res = A.regenerate_slide("claude", "/src", "process", CUR, [], 1, 3, n=2)
    assert res["ok"] is False
    assert res["error"]


def test_n_capped_at_five(monkeypatch):
    _sources(monkeypatch)
    calls = {"n": 0}

    def fake_cli(*a, **k):
        calls["n"] += 1
        return (True, '{"layout":"process","content":{"title":"Y","steps":[]}}', "")

    monkeypatch.setattr(A, "run_cli", fake_cli)
    A.regenerate_slide("claude", "/src", "process", CUR, [], 1, 3, n=99)
    assert calls["n"] == 5


# ---- ranking ----

def test_rank_puts_lint_ok_first():
    bad = {"layout": "process", "content": {}, "lint_ok": False, "lint_errors": ["x"]}
    good = {"layout": "process",
            "content": {"title": "Y", "steps": [{"num": "1", "title": "a", "body": "b"}]},
            "lint_ok": True, "lint_errors": []}
    ranked = A.rank_slide_candidates([bad, good])
    assert ranked[0]["lint_ok"] is True
    assert ranked[0]["score"] > ranked[1]["score"]


def test_rank_is_stable_on_ties():
    a = {"layout": "process", "content": {"title": "one", "steps": [{"num": "1", "title": "a", "body": "bb cc"}]},
         "lint_ok": True, "lint_errors": []}
    b = {"layout": "process", "content": {"title": "two", "steps": [{"num": "1", "title": "a", "body": "bb cc"}]},
         "lint_ok": True, "lint_errors": []}
    ranked = A.rank_slide_candidates([a, b])
    # identical density/validity -> generation order preserved
    assert [c["content"]["title"] for c in ranked] == ["one", "two"]


def test_text_volume_counts_string_leaves():
    assert A._slide_text_volume({"title": "two words", "items": ["a b", "c"]}) == 5
