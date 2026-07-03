"""M16 — named version history + restore (builds on M15's snapshot store).

A `version` is a named, deliberate, never-pruned snapshot — distinct from the
rolling auto/manual checkpoints. Versions can be created directly ("Save
version…") or by PROMOTING an existing checkpoint (rename + kind=version).
This guards:
  * the version kind survives auto-pruning (only `auto` is ever trimmed);
  * rename_snapshot edits the manifest in place (label and/or kind);
  * promoting an auto-checkpoint into a version keeps it out of prune scope;
  * the /api/snapshot/rename endpoint end-to-end + allowlist confinement;
  * versions restore through the same M15 restore path.

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


@pytest.fixture
def project():
    root = tempfile.mkdtemp(prefix="cb_ver_")
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

def test_version_kind_is_never_pruned(project):
    ver = server.make_snapshot(project, "Sent to SME", kind="version")
    for i in range(server.SNAP_AUTO_CAP + 5):
        server.make_snapshot(project, f"auto {i}", kind="auto")
    snaps = server.list_snapshots(project)
    assert [s for s in snaps if s["kind"] == "auto"].__len__() == server.SNAP_AUTO_CAP
    assert any(s["id"] == ver["id"] and s["kind"] == "version" for s in snaps)


def test_rename_snapshot_changes_label_only(project):
    m = server.make_snapshot(project, "Manual checkpoint", kind="manual")
    res = server.rename_snapshot(project, m["id"], label="Renamed")
    assert res["ok"] and res["snapshot"]["label"] == "Renamed"
    assert res["snapshot"]["kind"] == "manual"   # untouched when kind not passed
    # persisted to disk
    again = next(s for s in server.list_snapshots(project) if s["id"] == m["id"])
    assert again["label"] == "Renamed"


def test_promote_auto_to_version_survives_prune(project):
    promoted = server.make_snapshot(project, "Before regenerate deck", kind="auto")
    res = server.rename_snapshot(project, promoted["id"], label="Good draft", kind="version")
    assert res["ok"] and res["snapshot"]["kind"] == "version"
    # flood with autos; the promoted one must survive because it is no longer `auto`
    for i in range(server.SNAP_AUTO_CAP + 5):
        server.make_snapshot(project, f"auto {i}", kind="auto")
    snaps = server.list_snapshots(project)
    keep = next((s for s in snaps if s["id"] == promoted["id"]), None)
    assert keep and keep["kind"] == "version" and keep["label"] == "Good draft"


def test_rename_empty_label_keeps_existing(project):
    m = server.make_snapshot(project, "Keeper", kind="version")
    res = server.rename_snapshot(project, m["id"], label="")
    assert res["ok"] and res["snapshot"]["label"] == "Keeper"


def test_rename_unknown_id_errors(project):
    res = server.rename_snapshot(project, "nope", label="x")
    assert res["ok"] is False and "not found" in res["error"]


def test_version_restores_through_m15_path(project):
    ver = server.make_snapshot(project, "v1 milestone", kind="version")
    pj = _read_pj(project)
    pj["deck"][0]["content"]["title"] = "v2"
    json.dump(pj, open(os.path.join(project, "project.json"), "w", encoding="utf-8"))
    res = server.restore_snapshot(project, ver["id"])
    assert res["ok"]
    assert _read_pj(project)["deck"][0]["content"]["title"] == "v1"


# --------------------------------------------------------------- live endpoint

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


def test_endpoint_save_then_rename_version(port, project):
    # create a named version directly
    st, r = _post(port, "/api/snapshot", {"project": project, "label": "Sent to SME", "kind": "version"})
    assert st == 200 and r["ok"] and r["snapshot"]["kind"] == "version"
    vid = r["snapshot"]["id"]
    # promote an auto checkpoint into a version via /api/snapshot/rename
    st, r = _post(port, "/api/snapshot", {"project": project, "label": "auto", "kind": "auto"})
    aid = r["snapshot"]["id"]
    st, r = _post(port, "/api/snapshot/rename",
                  {"project": project, "id": aid, "label": "Promoted", "kind": "version"})
    assert st == 200 and r["ok"] and r["snapshot"]["kind"] == "version"
    assert any(s["id"] == aid and s["kind"] == "version" for s in r["snapshots"])
    assert any(s["id"] == vid for s in r["snapshots"])


def test_rename_endpoint_rejects_outside_allowlist(port):
    st, r = _post(port, "/api/snapshot/rename", {"project": "/etc", "id": "x", "label": "y"})
    assert st == 200 and r["ok"] is False and "not allowed" in r["error"]
