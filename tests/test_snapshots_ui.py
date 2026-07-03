"""M15 — checkpoint / rewind, dashboard wiring (static drift guard).

Guards the moving parts in dashboard/index.html: the History controls on both
project bars, the snapshotBefore() helper fired before each deck/slide AI edit,
the history modal + restore flow, and the server seam (snapshot/restore handlers
+ routes).
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()
SERVER = open(os.path.join(REPO, "dashboard", "server.py"), encoding="utf-8").read()


def _fn(name):
    return HTML.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


# ----- UI controls -----------------------------------------------------------

def test_history_button_on_both_project_bars():
    assert HTML.count("openHistory()") >= 2          # course bar + deck bar

def test_history_modal_present():
    assert 'id="hist_modal"' in HTML
    assert 'id="hist_list"' in HTML
    assert "manualSnapshot()" in HTML and "closeHistory()" in HTML


# ----- snapshot-before-AI-edit wiring ---------------------------------------

def test_snapshot_before_helper_persists_then_snapshots():
    fn = _fn("snapshotBefore")
    assert "saveProject(true)" in fn                  # persist the in-memory deck first
    assert "/api/snapshot" in fn and "kind:'auto'" in fn

def test_deck_ai_edits_snapshot_first():
    assert "await snapshotBefore(" in _fn("regenSlide")
    assert "await snapshotBefore(" in _fn("genDeck")
    assert "await snapshotBefore(" in _fn("genNotes")


# ----- restore flow ----------------------------------------------------------

def test_restore_confirms_and_reopens_project():
    fn = _fn("restoreSnapshot")
    assert "/api/restore" in fn
    assert "confirm(" in fn                           # undoable-but-confirm
    assert "loadProject(" in fn                       # restored IR loads back into the UI


# ----- server seam -----------------------------------------------------------

def test_server_routes_and_handlers():
    assert '"/api/snapshot"' in SERVER and '"/api/restore"' in SERVER
    assert '"/api/snapshots"' in SERVER
    assert "def do_snapshot(" in SERVER and "def do_restore(" in SERVER
