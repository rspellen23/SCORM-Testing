"""M5 — translate/localize course, dashboard + CLI wiring (drift guard).

Guards the moving parts added for M5: the translate panel + target input + button
in dashboard/index.html, the translateCourse() function and its /api/translate
call, scriptStatus toggling the panel, the do_translate server handler + route,
and the CLI `translate` subcommand.
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()
SERVER = open(os.path.join(REPO, "dashboard", "server.py"), encoding="utf-8").read()
CLI = open(os.path.join(REPO, "src", "cli.py"), encoding="utf-8").read()


def _fn(name):
    return HTML.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


# ----- the translate panel + control ------------------------------------------

def test_translate_panel_present():
    assert 'id="translate_box"' in HTML
    assert 'id="tr_target"' in HTML
    assert 'onclick="translateCourse()"' in HTML
    assert 'id="tr_results"' in HTML


def test_script_status_toggles_translate_box():
    body = _fn("scriptStatus")
    assert "translate_box" in body and "CURRENT_SCRIPT" in body


# ----- translateCourse() posts the right payload ------------------------------

def test_translate_course_fn_posts_target_and_script():
    body = _fn("translateCourse")
    assert "/api/translate" in body
    assert "script:CURRENT_SCRIPT" in body
    assert "target" in body and "brand:brand()" in body
    # surfaces the structure-verify + lint outcomes
    assert "structure_ok" in body and "lint_ok" in body


# ----- server seam ------------------------------------------------------------

def test_server_route_and_handler():
    assert '"/api/translate"' in SERVER
    assert "do_translate(p)" in SERVER
    assert "def do_translate(p):" in SERVER
    # reuses the structure-preserving translate seam
    assert "translate_course(" in SERVER


# ----- CLI subcommand ---------------------------------------------------------

def test_cli_translate_subcommand():
    assert 'add_parser("translate"' in CLI
    assert "def cmd_translate(a):" in CLI
    assert "--target" in CLI
    assert "translate_course(" in CLI
