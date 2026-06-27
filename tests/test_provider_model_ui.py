"""P2 — the Haiku/Sonnet/Opus model picker is claude-specific. run_cli ignores
`model` for codex (ChatGPT/Codex picks its own model via its subscription login),
so the dashboard must disable that control when a non-claude provider is chosen
rather than show a silently-ignored picker.

These are static drift guards over the dashboard wiring (the behavior itself is
exercised by a node logic check during development); they fail if a future edit
removes the sync wiring and re-opens the silent no-op.
"""
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()


def test_sync_function_defined():
    assert "function syncModelCtl(" in HTML
    # codex/non-claude path must disable the select + say the control is ignored
    fn = HTML.split("function syncModelCtl(", 1)[1].split("\n}", 1)[0]
    assert "disabled" in fn and "ignored" in fn
    assert "prov.value==='claude'" in fn


def test_both_provider_selects_wire_the_sync():
    for prov, row in (("gen_provider", "gen_model_row"), ("sl_provider", "sl_model_row")):
        assert re.search(rf'id="{prov}"[^>]*onchange="syncModelCtl\(\'{prov}\',\'{row}\'\)"', HTML), prov
        assert f'id="{row}"' in HTML                       # the row the sync dims exists


def test_applyproviders_calls_sync_for_both_tabs():
    ap = HTML.split("function applyProviders(", 1)[1].split("\n}", 1)[0]
    assert "syncModelCtl('gen_provider','gen_model_row')" in ap
    assert "syncModelCtl('sl_provider','sl_model_row')" in ap


def test_model_hints_have_restorable_default():
    # the claude-restore path reads data-default, so both hints must carry it
    assert HTML.count('data-default="') >= 2
