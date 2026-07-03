"""M13 — gate-completion toggle, dashboard wiring (drift guard).

Guards the moving parts M13 added to the dashboard: the "Gate completion on a
failing score" checkbox in the Output & publish step, its inclusion in BOTH the
preview and publish build payloads, and the server → CLI plumbing that turns an
unchecked box into `--no-gate`. The scoring/gating math itself is covered by
tests/test_final_quiz.py (Python) and tests/test_player.js (node).
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()
SERVER = open(os.path.join(REPO, "dashboard", "server.py"), encoding="utf-8").read()
CLI = open(os.path.join(REPO, "src", "cli.py"), encoding="utf-8").read()


def _fn(name):
    return HTML.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


def test_gate_checkbox_present():
    assert 'id="b_gate"' in HTML
    assert "Gate completion on a failing score" in HTML


def test_preview_build_payload_sends_gate():
    fn = _fn("generateCourses")
    assert "b_gate" in fn and "gate:" in fn


def test_publish_build_payload_sends_gate():
    fn = _fn("publishItems")
    assert "b_gate" in fn and "gate:" in fn


def test_server_build_jobs_threads_gate_to_no_gate_flag():
    jobs = SERVER.split("def build_jobs(", 1)[1].split("\ndef ", 1)[0]
    assert 'gate = p.get("gate", True)' in jobs
    assert "--no-gate" in jobs


def test_cli_has_no_gate_flag():
    assert "--no-gate" in CLI
    assert 'gate=(False if getattr(a, "no_gate", False) else None)' in CLI
