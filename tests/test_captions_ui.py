"""M3 — local captions, dashboard + CLI wiring (drift guard).

Guards the moving parts added for M3: the captions panel + controls in
dashboard/index.html, the genCaptions() function and its /api/captions call,
the do_captions server handler + route, and the CLI `captions` subcommand.
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()
SERVER = open(os.path.join(REPO, "dashboard", "server.py"), encoding="utf-8").read()
CLI = open(os.path.join(REPO, "src", "cli.py"), encoding="utf-8").read()


def _fn(name):
    return HTML.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


# ----- the captions panel + controls -----------------------------------------

def test_captions_panel_present():
    assert 'id="captions_box"' in HTML
    assert 'id="cap_lang"' in HTML
    assert 'id="cap_overwrite"' in HTML
    assert 'id="cap_results"' in HTML
    assert "genCaptions()" in HTML


def test_captions_box_revealed_with_script():
    # scriptStatus toggles the panel on whether a course script is loaded
    assert "captions_box" in _fn("scriptStatus")


def test_gen_captions_posts_to_api():
    fn = _fn("genCaptions")
    assert "/api/captions" in fn
    assert "CURRENT_SCRIPT" in fn
    assert "lang" in fn and "overwrite" in fn


# ----- server handler + route -------------------------------------------------

def test_server_has_captions_handler_and_route():
    assert "def do_captions(" in SERVER
    assert '"/api/captions"' in SERVER
    assert "do_captions(p)" in SERVER


def test_captions_snapshots_before_editing():
    body = SERVER.split("def do_captions(", 1)[1].split("\ndef ", 1)[0]
    assert "_auto_snapshot" in body               # script is edited in place → snapshot first
    assert "caption_markdown" in body


# ----- CLI subcommand ---------------------------------------------------------

def test_cli_has_captions_subcommand():
    assert 'add_parser("captions"' in CLI
    assert "def cmd_captions(" in CLI
    assert "--overwrite" in CLI
    assert "caption_markdown" in CLI
