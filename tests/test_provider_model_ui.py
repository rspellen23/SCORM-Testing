"""The AI account + model are an APP-WIDE setting in the top bar (set once, used by
every tab) — not a per-tab stage. These static drift guards over the dashboard
wiring fail if a future edit re-introduces a per-tab provider/model picker or drops
the global control's wiring.

Two invariants they protect:
  1. There is exactly ONE provider select (`ai_provider`) and ONE model select
     (`ai_model`), both in the top bar, both persisted to localStorage on change.
  2. The Haiku/Sonnet/Opus model picker is claude-specific — run_cli ignores
     `model` for codex — so a non-claude provider must DISABLE the picker rather
     than show a silently-ignored control (`syncModelCtl`).
"""
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()


def test_single_global_provider_and_model_selects():
    # exactly one of each, and they live in the top bar (the .aisel cluster)
    assert HTML.count('id="ai_provider"') == 1
    assert HTML.count('id="ai_model"') == 1
    aisel = HTML.split('class="aisel"', 1)[1].split("</div>", 1)[0]
    assert 'id="ai_provider"' in aisel and 'id="ai_model"' in aisel


def test_old_per_tab_controls_are_gone():
    # the dissolved per-tab stages must not creep back in
    for dead in ("gen_provider", "sl_provider", "gen_model_sel", "sl_model_sel",
                 "gen_model_row", "sl_model_row", "sl_ai_status"):
        assert dead not in HTML, dead


def test_both_global_selects_persist_on_change():
    for sel in ("ai_provider", "ai_model"):
        assert re.search(rf'id="{sel}"[^>]*onchange="onAiChange\(\)"', HTML), sel
    fn = HTML.split("function onAiChange(", 1)[1].split("\n}", 1)[0]
    assert "localStorage.setItem('cb_ai_provider'" in fn
    assert "localStorage.setItem('cb_ai_model'" in fn
    assert "syncModelCtl('ai_provider','ai_model_wrap')" in fn


def test_restore_reads_saved_prefs_and_syncs():
    fn = HTML.split("function restoreAiPrefs(", 1)[1].split("\n}", 1)[0]
    assert "getItem('cb_ai_provider')" in fn and "getItem('cb_ai_model')" in fn
    assert "syncModelCtl('ai_provider','ai_model_wrap')" in fn
    # a re-check (applyProviders) must re-apply the saved choice, not clobber it
    ap = HTML.split("function applyProviders(", 1)[1].split("\n}", 1)[0]
    assert "restoreAiPrefs()" in ap


def test_sync_disables_model_for_non_claude():
    assert "function syncModelCtl(" in HTML
    fn = HTML.split("function syncModelCtl(", 1)[1].split("\n}", 1)[0]
    assert "disabled" in fn and "ignored" in fn
    assert "prov.value==='claude'" in fn
