"""Dashboard server security regression tests (C2).

`dashboard/server.py` had ZERO tests, so the hardening from the 2026-06-23 audit
(CSRF/same-origin/JSON-only POST guard, the `_within_roots` allowlist on the file
endpoints, `_safe_brand`/`_safe_path_arg` argument confinement) was unguarded — a
future edit could silently re-open the file-read hole or the CSRF gap with the
suite still green.

Two layers:
  * live-server tests spin up the REAL `ThreadingHTTPServer` on a free port and hit
    it with crafted headers, exercising `_csrf_ok`/`_same_origin` end-to-end and the
    GET file endpoints (`/api/readjson`, `/preview`);
  * unit tests pin the security primitives (`_within_roots`, `_safe_brand`,
    `_safe_path_arg`) directly.

server.py lives in dashboard/, not on the pyproject `pythonpath=src`, so we add it.
"""
import http.client
import json
import os
import sys
import threading
from http.server import ThreadingHTTPServer

import pytest

_DASH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard")
if _DASH not in sys.path:
    sys.path.insert(0, _DASH)
import server  # noqa: E402


# --------------------------------------------------------------- live server

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


def _post(port, path, body=None, *, origin="self", ctype="application/json",
          token="valid"):
    """POST helper. origin='self' → the server's own origin; token='valid' → the
    real CSRF token. Pass origin=None / ctype=None / token=None to omit a header,
    or any string to send a bogus value."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {}
    if ctype is not None:
        headers["Content-Type"] = ctype
    if origin == "self":
        headers["Origin"] = f"http://127.0.0.1:{port}"
    elif origin is not None:
        headers["Origin"] = origin
    if token == "valid":
        headers["X-CSRF-Token"] = server.CSRF_TOKEN
    elif token is not None:
        headers["X-CSRF-Token"] = token
    conn.request("POST", path, json.dumps(body or {}), headers)
    resp = conn.getresponse()
    out = (resp.status, resp.read())
    conn.close()
    return out


def _get(port, path):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    out = (resp.status, resp.read())
    conn.close()
    return out


# --------------------------------------------------------------- POST guard (CSRF / same-origin / JSON-only)

def test_post_without_csrf_token_is_403(port):
    status, _ = _post(port, "/api/build", token=None)
    assert status == 403


def test_post_with_wrong_csrf_token_is_403(port):
    status, _ = _post(port, "/api/build", token="not-the-token")
    assert status == 403


def test_post_from_evil_origin_is_403(port):
    # valid token, but a cross-origin attacker page → blocked
    status, _ = _post(port, "/api/build", origin="http://evil.example")
    assert status == 403


def test_post_non_json_content_type_is_403(port):
    # a CSRF-able form POST (text/plain dodges the JSON preflight) → blocked
    status, _ = _post(port, "/api/build", ctype="text/plain")
    assert status == 403


def test_valid_request_passes_the_csrf_guard(port):
    # correct origin + content-type + token → the guard lets it through; an unknown
    # path then 404s (NOT 403), proving the request cleared the guard, not the gate.
    status, _ = _post(port, "/api/__no_such_endpoint__")
    assert status == 404


# --------------------------------------------------------------- GET file endpoints (allowlist)

def test_readjson_system_path_blocked(port):
    status, body = _get(port, "/api/readjson?path=/etc/passwd")
    assert status == 200                      # endpoint answers, but refuses the read
    data = json.loads(body)
    assert data["ok"] is False
    assert "not allowed" in data["error"].lower()


def test_preview_outside_roots_is_404(port):
    status, _ = _get(port, "/preview/etc/passwd")
    assert status == 404


def test_preview_traversal_is_404(port):
    # ../ escape collapses via realpath to a system path outside the allowlist
    status, _ = _get(port, "/preview/../../../../../../etc/passwd")
    assert status == 404


def test_bogus_brand_rejected(port):
    # a non-empty slide list reaches _safe_brand; a traversal brand raises → 500,
    # never silently builds against an attacker-chosen directory.
    body = {"slides": [{"layout": "statement", "content": {"title": "x"}}],
            "brand": "../../etc"}
    status, out = _post(port, "/api/deck-svg", body)
    assert status == 500
    assert b"unknown brand" in out


# --------------------------------------------------------------- security primitives (direct)

def test_within_roots_rejects_system_and_empty_paths():
    assert server._within_roots("/etc") is False
    assert server._within_roots("/etc/passwd") is False
    assert server._within_roots("/") is False
    assert server._within_roots("") is False


def test_within_roots_accepts_home_and_repo():
    assert server._within_roots(os.path.expanduser("~")) is True
    assert server._within_roots(server.ROOT) is True
    assert server._within_roots(os.path.abspath(__file__)) is True   # under the repo


def test_safe_brand_confines_to_real_brands():
    assert server._safe_brand("_default") == "_default"
    assert server._safe_brand(None) == "_default"
    for bad in ("../../etc", "../brands", "no-such-brand", "/etc"):
        with pytest.raises(ValueError):
            server._safe_brand(bad)


def test_safe_path_arg_rejects_flag_like_values():
    assert server._safe_path_arg("course.md", "source") == "course.md"
    for bad in ("-rf", "--out", "-"):
        with pytest.raises(ValueError):
            server._safe_path_arg(bad, "source")
