"""C17 — translation memory, dashboard + CLI wiring (drift guard).

Guards the moving parts added for C17: the TM reuse line + approve button in the
translate result, the approveTranslation() function and its /api/tm-approve call, the
do_tm_approve server handler + route, the translate_course TM integration, and the CLI
`tm` subcommand + `--no-tm` flag.
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()
SERVER = open(os.path.join(REPO, "dashboard", "server.py"), encoding="utf-8").read()
CLI = open(os.path.join(REPO, "src", "cli.py"), encoding="utf-8").read()
AUTHORING = open(os.path.join(REPO, "src", "authoring.py"), encoding="utf-8").read()


def _fn(name):
    return HTML.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


# ----- translate result surfaces reuse + approval -----------------------------

def test_translate_result_shows_tm_reuse_and_approve():
    fn = _fn("translateCourse")
    assert "tm_reused" in fn
    assert "pending_approval" in fn
    assert "approveTranslation(" in fn


def test_approve_translation_posts_to_api():
    fn = _fn("approveTranslation")
    assert "/api/tm-approve" in fn
    assert "CURRENT_SCRIPT" in fn
    assert "target" in fn


# ----- server handler + route -------------------------------------------------

def test_server_has_tm_approve_handler_and_route():
    assert "def do_tm_approve(" in SERVER
    assert '"/api/tm-approve"' in SERVER
    assert "do_tm_approve(p)" in SERVER


def test_server_tm_approve_is_store_only():
    body = SERVER.split("def do_tm_approve(", 1)[1].split("\ndef ", 1)[0]
    assert "tm.approve" in body
    assert 'open(script, "w"' not in body           # never edits the course file


# ----- CLI subcommand + flag --------------------------------------------------

def test_cli_has_tm_subcommand_and_no_tm_flag():
    assert 'add_parser("tm"' in CLI
    assert "def cmd_tm(" in CLI
    assert '"--no-tm"' in CLI or "'--no-tm'" in CLI


# ----- engine integration -----------------------------------------------------

def test_translate_course_consults_tm():
    body = AUTHORING.split("def translate_course(", 1)[1].split("\ndef ", 1)[0]
    assert "import tm" in body
    assert ".lookup(" in body
    assert ".remember(" in body
    assert "use_tm" in body
