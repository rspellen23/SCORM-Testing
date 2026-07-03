"""M17 — saved templates / starters: a GLOBAL, cross-project template store.

An operator can save the current project (its deck IR + course script) OR a single
slide as a reusable starter, then start a new deck/course from it ("New from
template"), duplicate-and-edit. This is distinct from the per-project snapshot store
(M15/M16): templates live under the user config dir and INSTANTIATE into the current
session rather than restoring in place.

This guards:
  * the store (save project/slide, list, instantiate, delete) round-tripping the IR;
  * byte-clean capture (location/identity fields are stripped from a project template);
  * the course-script capture + placement into an open project's source folder;
  * the HTTP endpoints (/api/template/save, /api/templates, /api/template/new,
    /api/template/delete) end-to-end, including path-traversal + allowlist confinement.

server.py lives in dashboard/, not on the pyproject pythonpath, so we add it. The store
is global (under CONFIG_DIR), so every test repoints CONFIG_DIR at a temp dir.
"""
import http.client
import json
import os
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
def store(tmp_path, monkeypatch):
    """Repoint the global template store (and config dir) at a temp dir."""
    cfg = tmp_path / "config"
    cfg.mkdir()
    monkeypatch.setattr(server, "CONFIG_DIR", str(cfg))
    return cfg


@pytest.fixture
def project(tmp_path):
    """A temp project under the system temp dir (inside the server allowlist), with a
    project.json carrying a deck + definition fields + a referenced course script."""
    root = tempfile.mkdtemp(prefix="cb_tpl_")
    src = os.path.join(root, server.PROJECT_FOLDERS["source"])
    os.makedirs(src, exist_ok=True)
    script = os.path.join(src, "course.md")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write("# Course\n\n## Microlearning 1\nOriginal body.\n")
    meta = {"name": "Demo Project", "title": "Demo Course", "objective": "Do the thing",
            "audience": "Nurses", "sl_title": "Demo Deck", "brand": "teletracking",
            "deck": [{"layout": "infographic", "content": "{\"title\": \"v1\"}"},
                     {"layout": "cards", "content": "{\"title\": \"two\"}"}],
            "script": script, "created": "2026-01-01T00:00:00", "updated": "2026-01-02T00:00:00"}
    server.write_project(root, meta)
    return root


# --------------------------------------------------------------- store units

def test_save_project_template_captures_deck_and_script(store, project):
    res = server.save_project_template(project, "My Starter")
    assert res["ok"]
    m = res["template"]
    assert m["kind"] == "project" and m["name"] == "My Starter"
    assert m["n_slides"] == 2 and m["script_name"] == "course.md"
    # the payload + script live under the store
    tdir = os.path.join(server._tpl_root(), m["id"])
    assert os.path.isfile(os.path.join(tdir, "payload.json"))
    assert os.path.isfile(os.path.join(tdir, "script.md"))


def test_project_template_strips_identity_fields(store, project):
    tid = server.save_project_template(project, "S")["template"]["id"]
    payload = json.load(open(os.path.join(server._tpl_root(), tid, "payload.json")))
    # location/identity fields must not leak into a new session
    for k in ("name", "script", "created", "updated"):
        assert k not in payload
    # content fields survive
    assert payload["title"] == "Demo Course" and len(payload["deck"]) == 2


def test_instantiate_project_returns_meta_and_script_text(store, project):
    tid = server.save_project_template(project, "S")["template"]["id"]
    inst = server.instantiate_template(tid)
    assert inst["ok"] and inst["kind"] == "project"
    assert inst["meta"]["title"] == "Demo Course"
    assert len(inst["meta"]["deck"]) == 2
    assert "Original body." in inst["script_text"]
    assert inst["script_name"] == "course.md"


def test_save_and_instantiate_slide_template(store):
    res = server.save_slide_template("Hero", "cards", "{\"title\": \"Hi\"}")
    assert res["ok"] and res["template"]["kind"] == "slide"
    tid = res["template"]["id"]
    inst = server.instantiate_template(tid)
    assert inst["ok"] and inst["kind"] == "slide"
    assert inst["layout"] == "cards" and json.loads(inst["content"])["title"] == "Hi"


def test_slide_template_coerces_dict_content_to_json(store):
    tid = server.save_slide_template("H", "infographic", {"title": "x"})["template"]["id"]
    inst = server.instantiate_template(tid)
    assert isinstance(inst["content"], str) and json.loads(inst["content"])["title"] == "x"


def test_list_templates_newest_first_and_filterable(store, project):
    p = server.save_project_template(project, "P")["template"]["id"]
    s = server.save_slide_template("S", "cards", "{}")["template"]["id"]
    ids = [m["id"] for m in server.list_templates()]
    assert set(ids) == {p, s}
    assert ids == sorted(ids, reverse=True)          # newest-first
    assert [m["id"] for m in server.list_templates(kind="slide")] == [s]
    assert [m["id"] for m in server.list_templates(kind="project")] == [p]


def test_delete_template(store):
    tid = server.save_slide_template("S", "cards", "{}")["template"]["id"]
    assert server.delete_template(tid)["ok"]
    assert server.list_templates() == []
    assert server.delete_template(tid)["ok"] is False        # already gone


def test_place_template_script_writes_into_source_folder(store, project):
    dest = server.place_template_script(project, "starter.md", "# New\n\nbody\n")
    assert os.path.isfile(dest)
    assert server.PROJECT_FOLDERS["source"] in dest
    # recorded on the project so the session picks it up as the current script
    assert server._project_meta(project)["script"] == dest


def test_place_template_script_dedupes(store, project):
    a = server.place_template_script(project, "dup.md", "a")
    b = server.place_template_script(project, "dup.md", "b")
    assert a != b and os.path.isfile(a) and os.path.isfile(b)


def test_safe_store_id_rejects_traversal(store):
    for bad in ("", "..", "../x", "a/b", "/etc/passwd"):
        assert server._safe_store_id(bad) is False
        assert server._tpl_manifest(bad) is None
    assert server._safe_store_id("project-20260101T000000000000") is True


def test_instantiate_missing_template(store):
    assert server.instantiate_template("project-does-not-exist")["ok"] is False


# --------------------------------------------------------------- HTTP end-to-end

@pytest.fixture
def http_server(store):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield httpd.server_address
    finally:
        httpd.shutdown()


def _post(addr, path, body):
    c = http.client.HTTPConnection(*addr)
    c.request("POST", path, json.dumps(body),
              {"Content-Type": "application/json", "Origin": f"http://{addr[0]}:{addr[1]}",
               "X-CSRF-Token": server.CSRF_TOKEN})
    r = c.getresponse()
    return json.loads(r.read())


def _get(addr, path):
    c = http.client.HTTPConnection(*addr)
    c.request("GET", path)
    return json.loads(c.getresponse().read())


def test_http_save_list_instantiate_project(http_server, project):
    saved = _post(http_server, "/api/template/save",
                  {"kind": "project", "project": project, "name": "Via HTTP"})
    assert saved["ok"]
    tid = saved["template"]["id"]
    listed = _get(http_server, "/api/templates")["templates"]
    assert any(m["id"] == tid for m in listed)
    inst = _post(http_server, "/api/template/new", {"id": tid, "project": project})
    assert inst["ok"] and inst["kind"] == "project"
    # the carried course script was placed into the open project's source folder
    assert inst.get("script") and os.path.isfile(inst["script"])


def test_http_save_slide_and_delete(http_server):
    saved = _post(http_server, "/api/template/save",
                  {"kind": "slide", "name": "S", "layout": "cards", "content": "{}"})
    assert saved["ok"]
    tid = saved["template"]["id"]
    assert any(m["id"] == tid for m in saved["templates"])
    gone = _post(http_server, "/api/template/delete", {"id": tid})
    assert gone["ok"] and all(m["id"] != tid for m in gone["templates"])


def test_http_save_project_rejects_outside_allowlist(http_server):
    res = _post(http_server, "/api/template/save",
                {"kind": "project", "project": "/etc", "name": "nope"})
    assert res["ok"] is False


def test_http_bad_template_id_rejected(http_server):
    assert _post(http_server, "/api/template/new", {"id": "../escape"})["ok"] is False
