"""C17 — translation memory: reuse previously-approved translations across courses.

An APPROVED source→target unit is reused verbatim on the next translate (no LLM call,
no re-review). A LOCALIZE unit (en-GB) is approved on write; a TRANSLATE unit (a real
language) is stored PENDING until an explicit approval step promotes it. The store is a
per-target JSON file under the config dir — isolated to a temp dir by the autouse
conftest fixture, so these tests never touch the real ~/.course-builder.
"""
import re

import authoring as A
import tm

from test_translate import SRC, _echo_cli


# ---- the pure store ----------------------------------------------------------

def test_normalize_drops_unit_number_but_keeps_title():
    a = tm._normalize_unit("## Microlearning 3: Intake\n\nBody here.")
    b = tm._normalize_unit("## Microlearning 7: Intake\n\nBody here.")
    assert a == b                                   # position-independent
    assert "Intake" in a                            # title kept


def test_hash_stable_and_position_independent():
    assert tm.unit_hash("## Microlearning 1: X\n\nHi.") == tm.unit_hash("## Microlearning 9: X\n\nHi.")
    assert tm.unit_hash("## Microlearning 1: X\n\nHi.") != tm.unit_hash("## Microlearning 1: Y\n\nHi.")


def test_lookup_miss_is_none():
    assert tm.lookup("Spanish", "## Microlearning 1: X\n\nHi.") is None


def test_localize_is_approved_and_reusable_immediately():
    src = "## Microlearning 1: Greeting\n\nHello."
    approved = tm.remember("en-GB", src, "## Microlearning 1: Greeting\n\nHello (UK).", mode="localize")
    assert approved is True
    assert tm.lookup("en-GB", src) == "## Microlearning 1: Greeting\n\nHello (UK)."


def test_translate_is_pending_until_approved():
    src = "## Microlearning 1: Greeting\n\nHello."
    approved = tm.remember("Spanish", src, "## Microlearning 1: Greeting\n\nHola.", mode="translate")
    assert approved is False
    assert tm.lookup("Spanish", src) is None                        # not reusable yet
    assert tm.lookup("Spanish", src, approved_only=False) == "## Microlearning 1: Greeting\n\nHola."


def test_approve_promotes_pending_units():
    md = SRC
    for _n, unit in tm._iter_units(md):
        tm.remember("Spanish", unit, unit + "\n(es)", mode="translate")
    assert tm.pending_count("Spanish", md) == 2
    promoted = tm.approve("Spanish", md)
    assert promoted == 2
    assert tm.pending_count("Spanish", md) == 0
    # now reusable
    first = next(u for _n, u in tm._iter_units(md))
    assert tm.lookup("Spanish", first) is not None


def test_remember_never_downgrades_an_approved_entry():
    src = "## Microlearning 1: X\n\nBody."
    tm.remember("Spanish", src, "APPROVED", mode="translate")
    tm.approve("Spanish", src)
    tm.remember("Spanish", src, "NEW MT", mode="translate")         # pending write over approved
    assert tm.lookup("Spanish", src) == "APPROVED"                  # kept the blessed one


# ---- translate_course integration -------------------------------------------

def _counting_cli(counter):
    def stub(prov, prompt, **k):
        counter[0] += 1
        return _echo_cli(prompt)
    return stub


def _no_glossary(monkeypatch):
    monkeypatch.setattr(A, "load_glossary", lambda b=None: {"preferred": [], "banned": []})


def test_localize_stores_then_reuses(monkeypatch):
    _no_glossary(monkeypatch)
    c = [0]
    monkeypatch.setattr(A, "run_cli", _counting_cli(c))
    r1 = A.translate_course("claude", SRC, "en-GB")
    assert r1["tm_stored"] == 2 and r1["tm_reused"] == 0
    assert r1["pending_approval"] is False          # localize needs no approval
    calls_first = c[0]                              # preamble + 2 units = 3
    # second run: both units reused verbatim, only the preamble hits run_cli
    r2 = A.translate_course("claude", SRC, "en-GB")
    assert r2["tm_reused"] == 2 and r2["tm_stored"] == 0
    assert c[0] - calls_first == 1                  # only the preamble re-ran


def test_translate_pending_is_not_reused_until_approved(monkeypatch):
    _no_glossary(monkeypatch)
    c = [0]
    monkeypatch.setattr(A, "run_cli", _counting_cli(c))
    r1 = A.translate_course("claude", SRC, "Spanish")
    assert r1["tm_stored"] == 2 and r1["pending_approval"] is True
    # second run: still pending → NOT reused (units re-run through the CLI)
    c[0] = 0
    r2 = A.translate_course("claude", SRC, "Spanish")
    assert r2["tm_reused"] == 0
    assert c[0] == 3                                # preamble + both units again
    # approve, then a third run reuses
    tm.approve("Spanish", SRC)
    c[0] = 0
    r3 = A.translate_course("claude", SRC, "Spanish")
    assert r3["tm_reused"] == 2
    assert c[0] == 1                                # only the preamble


def test_no_tm_flag_bypasses_the_store(monkeypatch):
    _no_glossary(monkeypatch)
    monkeypatch.setattr(A, "run_cli", lambda prov, prompt, **k: _echo_cli(prompt))
    r = A.translate_course("claude", SRC, "en-GB", use_tm=False)
    assert r["tm_stored"] == 0 and r["tm_reused"] == 0
    assert tm.load("en-GB") == {}                   # nothing written


def test_reused_unit_number_is_repinned(monkeypatch):
    """A unit remembered under one number is reused verbatim under a DIFFERENT number
    (the memory key ignores the number; the output re-pins to the current header)."""
    _no_glossary(monkeypatch)
    monkeypatch.setattr(A, "run_cli", lambda prov, prompt, **k: _echo_cli(prompt))
    A.translate_course("claude", SRC, "en-GB")      # stores unit "Intake" (as #1) approved
    # the same Intake unit, now numbered 5, in a one-unit course
    intake = next(u for _n, u in tm._iter_units(SRC))
    renumbered = re.sub(r"^##\s+Microlearning\s+\d+:", "## Microlearning 5:", intake, count=1)
    course = renumbered + "\n"                       # no preamble → a pure-reuse run
    c = [0]
    monkeypatch.setattr(A, "run_cli", _counting_cli(c))
    r = A.translate_course("claude", course, "en-GB")
    assert r["tm_reused"] == 1 and c[0] == 0        # reused verbatim, no CLI call at all
    assert re.search(r"(?m)^##\s+Microlearning\s+5:", r["out"])  # re-pinned to the new number


# ---- CLI ---------------------------------------------------------------------

def test_cli_tm_approve_and_list(tmp_path, capsys, monkeypatch):
    import cli
    _no_glossary(monkeypatch)
    monkeypatch.setattr(A, "run_cli", lambda prov, prompt, **k: _echo_cli(prompt))
    A.translate_course("claude", SRC, "Spanish")    # stores 2 pending
    src_md = tmp_path / "src.md"
    src_md.write_text(SRC, encoding="utf-8")
    cli.cmd_tm(type("A", (), {"action": "approve", "src": str(src_md), "target": "Spanish"})())
    assert "approved 2" in capsys.readouterr().out
    cli.cmd_tm(type("A", (), {"action": "list", "src": None, "target": "Spanish"})())
    out = capsys.readouterr().out
    assert "2 unit(s) in memory" in out and "2 approved" in out
