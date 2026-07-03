"""M15 — checkpoint / rewind: per-project snapshot store + endpoints.

The dashboard auto-snapshots the project IR (project.json carrying the deck, plus
the referenced course script .md) before each AI edit, and offers one-click restore.
This guards:
  * the snapshot store (make/list/restore/prune + capture targets);
  * snapshot-then-restore (a restore captures current state first, so it's undoable);
  * the HTTP endpoints (/api/snapshot, /api/snapshots, /api/restore) end-to-end;
  * the allowlist confinement and the auto-snapshot wiring in the AI-edit handlers.

server.py lives in dashboard/, not on the pyproject pythonpath, so we add it.
"""
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer

import pytest

_DASH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard")
if _DASH not in sys.path:
    sys.path.insert(0, _DASH)
import server  # noqa: E402


# --------------------------------------------------------------- fixtures

@pytest.fixture
def project():
    """A temp project under the system temp dir (inside the server allowlist),
    with a project.json carrying a deck + a referenced course script .md."""
    root = tempfile.mkdtemp(prefix="cb_snap_")
    script = os.path.join(root, "course.md")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write("# Course\n\n## Microlearning 1\nOriginal body.\n")
    meta = {"name": "Demo", "deck": [{"layout": "infographic", "content": {"title": "v1"}}],
            "script": script}
    with open(os.path.join(root, "project.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _read_pj(root):
    return json.load(open(os.path.join(root, "project.json"), encoding="utf-8"))


# --------------------------------------------------------------- store unit tests

def test_make_snapshot_captures_project_and_script(project):
    m = server.make_snapshot(project, "first", kind="manual")
    assert m and m["label"] == "first" and m["kind"] == "manual"
    names = {f["name"] for f in m["files"]}
    assert names == {"project.json", "course.md"}
    sdir = os.path.join(server._snap_root(project), m["id"])
    assert os.path.isfile(os.path.join(sdir, "project.json"))
    assert os.path.isfile(os.path.join(sdir, "course.md"))
    # the captured copy reflects the pre-edit content
    saved = json.load(open(os.path.join(sdir, "project.json"), encoding="utf-8"))
    assert saved["deck"][0]["content"]["title"] == "v1"


def test_snapshot_without_script_captures_project_only(project):
    pj = _read_pj(project)
    pj.pop("script")
    json.dump(pj, open(os.path.join(project, "project.json"), "w", encoding="utf-8"))
    m = server.make_snapshot(project, "deck only")
    assert {f["name"] for f in m["files"]} == {"project.json"}


def test_make_snapshot_none_when_nothing_to_capture():
    empty = tempfile.mkdtemp(prefix="cb_empty_")
    try:
        assert server.make_snapshot(empty, "x") is None
        assert server.list_snapshots(empty) == []
    finally:
        shutil.rmtree(empty, ignore_errors=True)


def test_list_snapshots_newest_first(project):
    a = server.make_snapshot(project, "a")
    b = server.make_snapshot(project, "b")
    c = server.make_snapshot(project, "c")
    ids = [s["id"] for s in server.list_snapshots(project)]
    assert ids == [c["id"], b["id"], a["id"]]   # microsecond ids sort newest-first


def test_restore_rolls_back_and_snapshots_current_first(project):
    snap = server.make_snapshot(project, "v1 state")          # captures title=v1, "Original body."
    # mutate both files (simulate an AI edit)
    pj = _read_pj(project)
    pj["deck"][0]["content"]["title"] = "v2"
    json.dump(pj, open(os.path.join(project, "project.json"), "w", encoding="utf-8"))
    with open(os.path.join(project, "course.md"), "w", encoding="utf-8") as fh:
        fh.write("# Course\n\n## Microlearning 1\nEdited body.\n")

    res = server.restore_snapshot(project, snap["id"])
    assert res["ok"]
    # rolled back
    assert _read_pj(project)["deck"][0]["content"]["title"] == "v1"
    assert "Original body." in open(os.path.join(project, "course.md"), encoding="utf-8").read()
    # snapshot-then-restore: a restore-point capturing the v2/edited state exists
    assert res["safety"] and res["safety"]["kind"] == "restore-point"
    sdir = os.path.join(server._snap_root(project), res["safety"]["id"])
    assert json.load(open(os.path.join(sdir, "project.json"), encoding="utf-8"))[
        "deck"][0]["content"]["title"] == "v2"
    # ...so the restore is itself undoable
    server.restore_snapshot(project, res["safety"]["id"])
    assert _read_pj(project)["deck"][0]["content"]["title"] == "v2"


def test_restore_unknown_id_errors(project):
    res = server.restore_snapshot(project, "nope")
    assert res["ok"] is False and "not found" in res["error"]


def test_prune_keeps_manual_and_restore_points_drops_old_auto(project):
    keep_manual = server.make_snapshot(project, "pinned", kind="manual")
    for i in range(server.SNAP_AUTO_CAP + 6):
        server.make_snapshot(project, f"auto {i}", kind="auto")
    snaps = server.list_snapshots(project)
    autos = [s for s in snaps if s["kind"] == "auto"]
    assert len(autos) == server.SNAP_AUTO_CAP                  # trimmed to the cap
    assert any(s["id"] == keep_manual["id"] for s in snaps)    # manual never trimmed
    # the surviving autos are the most-recent ones
    assert autos[0]["label"] == f"auto {server.SNAP_AUTO_CAP + 5}"


def test_auto_snapshot_respects_allowlist(project, tmp_path, monkeypatch):
    # valid, allowlisted project -> snapshots
    assert server._auto_snapshot({"project": project}, "edit") is not None
    # no project key -> no-op
    assert server._auto_snapshot({}, "edit") is None
    # project outside the allowed roots -> refused, nothing written
    outside = "/etc/cb_should_never"
    assert server._auto_snapshot({"project": outside}, "edit") is None


def test_handlers_wire_auto_snapshot():
    """The three on-disk AI-edit handlers must capture before they overwrite."""
    src = open(os.path.join(_DASH, "server.py"), encoding="utf-8").read()
    for fn in ("do_regenerate_unit", "do_save_course", "do_revise"):
        body = src.split(f"def {fn}(", 1)[1].split("\ndef ", 1)[0]
        assert "_auto_snapshot(" in body, f"{fn} does not auto-snapshot"


# --------------------------------------------------------------- live endpoints

@pytest.fixture(scope="module")
def port():
    p = server.free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", p), server.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield p
    finally:
        httpd.shutdown()
        httpd.server_close()
        t.join(timeout=2)


def _post(port, path, body):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", path, json.dumps(body),
                 {"Content-Type": "application/json",
                  "Origin": f"http://127.0.0.1:{port}",
                  "X-CSRF-Token": server.CSRF_TOKEN})
    resp = conn.getresponse()
    out = json.loads(resp.read() or b"{}")
    conn.close()
    return resp.status, out


def _get(port, path):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    out = json.loads(resp.read() or b"{}")
    conn.close()
    return resp.status, out


def test_endpoints_snapshot_list_restore(port, project):
    # create
    st, r = _post(port, "/api/snapshot", {"project": project, "label": "manual one"})
    assert st == 200 and r["ok"] and r["snapshot"]["label"] == "manual one"
    sid = r["snapshot"]["id"]
    # list (GET, read-only)
    st, r = _get(port, "/api/snapshots?project=" + project)
    assert st == 200 and any(s["id"] == sid for s in r["snapshots"])
    # mutate, then restore via endpoint
    pj = _read_pj(project)
    pj["deck"][0]["content"]["title"] = "changed"
    json.dump(pj, open(os.path.join(project, "project.json"), "w", encoding="utf-8"))
    st, r = _post(port, "/api/restore", {"project": project, "id": sid})
    assert st == 200 and r["ok"] and r["restored"]
    assert _read_pj(project)["deck"][0]["content"]["title"] == "v1"
    assert r["snapshots"]                                   # list returned for the UI


def test_endpoint_rejects_outside_allowlist(port):
    st, r = _post(port, "/api/snapshot", {"project": "/etc", "label": "x"})
    assert st == 200 and r["ok"] is False and "not allowed" in r["error"]
    st, r = _get(port, "/api/snapshots?project=/etc")
    assert st == 200 and r["snapshots"] == []


# --- sid path-traversal hardening (parity with the M17 template store) --------

def test_restore_rejects_traversal_sid(project):
    """A crafted snapshot id must not escape the snapshot dir (mirrors the
    M17 template store's _safe_store_id guard)."""
    for bad in ("", "..", "../x", "a/b", "/etc/passwd"):
        res = server.restore_snapshot(project, bad)
        assert res["ok"] is False and res["error"] == "snapshot not found"


def test_rename_rejects_traversal_sid(project):
    server.make_snapshot(project, "v1", kind="manual")       # a real snapshot exists
    for bad in ("..", "../x", "a/b"):
        res = server.rename_snapshot(project, bad, label="x")
        assert res["ok"] is False and res["error"] == "snapshot not found"


def test_restore_endpoint_rejects_traversal_sid(port, project):
    server.make_snapshot(project, "v1", kind="manual")
    st, r = _post(port, "/api/restore", {"project": project, "id": "../../escape"})
    assert st == 200 and r["ok"] is False
