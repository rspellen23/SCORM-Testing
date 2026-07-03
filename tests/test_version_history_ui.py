"""M16 — named version history, dashboard wiring (static drift guard).

Guards the moving parts in dashboard/index.html: the "Save version" control,
the version/checkpoint split in the history modal, the save/promote helpers, and
the server seam (rename handler + route).
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()
SERVER = open(os.path.join(REPO, "dashboard", "server.py"), encoding="utf-8").read()


def _fn(name):
    return HTML.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


# ----- UI controls -----------------------------------------------------------

def test_save_version_button_present():
    assert "saveVersion()" in HTML

def test_history_splits_versions_from_checkpoints():
    fn = _fn("paintHistory")
    assert "kind==='version'" in fn or 'kind==="version"' in fn
    assert "Versions" in fn and "Checkpoints" in fn


# ----- create / promote helpers ---------------------------------------------

def test_save_version_persists_then_snapshots_as_version():
    fn = _fn("saveVersion")
    assert "saveProject(true)" in fn                  # persist the in-memory deck first
    assert "/api/snapshot" in fn and "kind:'version'" in fn
    assert "prompt(" in fn                            # operator names the version

def test_name_version_promotes_via_rename_endpoint():
    fn = _fn("nameVersion")
    assert "/api/snapshot/rename" in fn
    assert "kind='version'" in fn or "body.kind" in fn  # promote sets kind=version


# ----- server seam -----------------------------------------------------------

def test_server_rename_route_and_handler():
    assert '"/api/snapshot/rename"' in SERVER
    assert "def do_rename_snapshot(" in SERVER
    assert "def rename_snapshot(" in SERVER
