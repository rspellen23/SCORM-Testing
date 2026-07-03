"""C20 — consistency check, dashboard + CLI wiring (drift guard).

Guards the moving parts added for C20: the consistency panel + controls in
dashboard/index.html, the checkConsistency() function and its /api/consistency
call, the do_consistency server handler + route, and the CLI `consistency`
subcommand.
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()
SERVER = open(os.path.join(REPO, "dashboard", "server.py"), encoding="utf-8").read()
CLI = open(os.path.join(REPO, "src", "cli.py"), encoding="utf-8").read()


def _fn(name):
    return HTML.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


# ----- the consistency panel + controls --------------------------------------

def test_consistency_panel_present():
    assert 'id="consistency_box"' in HTML
    assert 'id="cons_which"' in HTML
    assert 'id="cons_results"' in HTML
    assert "checkConsistency()" in HTML


def test_consistency_box_revealed_with_script():
    assert "consistency_box" in _fn("scriptStatus")


def test_check_consistency_posts_to_api():
    fn = _fn("checkConsistency")
    assert "/api/consistency" in fn
    assert "CURRENT_SCRIPT" in fn
    assert "which" in fn


# ----- server handler + route -------------------------------------------------

def test_server_has_consistency_handler_and_route():
    assert "def do_consistency(" in SERVER
    assert '"/api/consistency"' in SERVER
    assert "do_consistency(p)" in SERVER


def test_server_consistency_is_read_only():
    body = SERVER.split("def do_consistency(", 1)[1].split("\ndef ", 1)[0]
    assert "consistency_findings" in body
    assert "_auto_snapshot" not in body           # read-only: it never edits the script
    assert 'open(script, "w"' not in body


# ----- CLI subcommand ---------------------------------------------------------

def test_cli_has_consistency_subcommand():
    assert 'add_parser("consistency"' in CLI
    assert "def cmd_consistency(" in CLI
    assert "consistency_findings" in CLI


# ----- multi-unit build wires the sweep into the report -----------------------

def test_course_build_computes_consistency():
    body = CLI.split("def cmd_from_md_course(", 1)[1].split("\ndef ", 1)[0]
    assert "consistency_findings_course" in body
    assert "unit_irs" in body
