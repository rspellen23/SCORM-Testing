"""M6 — CSV manifest -> bulk generate, dashboard + CLI wiring (drift guard).

Guards the moving parts added for M6: the batch panel + csv/out pickers +
validate/generate buttons in dashboard/index.html, the batchGenerate() function
and its /api/batch-generate call, the do_batch_generate server handler + route,
and the CLI `from-csv` subcommand with --validate.
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()
SERVER = open(os.path.join(REPO, "dashboard", "server.py"), encoding="utf-8").read()
CLI = open(os.path.join(REPO, "src", "cli.py"), encoding="utf-8").read()


def _fn(name):
    return HTML.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


# ----- the batch panel + controls ---------------------------------------------

def test_batch_panel_present():
    assert 'id="batch_box"' in HTML
    assert 'id="batch_csv"' in HTML
    assert 'id="batch_out"' in HTML
    assert 'id="batch_results"' in HTML
    assert "batchGenerate(true)" in HTML     # validate
    assert "batchGenerate(false)" in HTML    # generate


# ----- batchGenerate() posts the right payload --------------------------------

def test_batch_generate_fn_posts_manifest():
    body = _fn("batchGenerate")
    assert "/api/batch-generate" in body
    assert "csv" in body and "out" in body
    assert "validate" in body
    assert "brand:brand()" in body


# ----- server seam ------------------------------------------------------------

def test_server_route_and_handler():
    assert '"/api/batch-generate"' in SERVER
    assert "do_batch_generate(p)" in SERVER
    assert "def do_batch_generate(p):" in SERVER
    assert "parse_manifest(" in SERVER
    assert "validate_manifest(" in SERVER
    assert "generate_batch(" in SERVER


# ----- CLI subcommand ---------------------------------------------------------

def test_cli_from_csv_subcommand():
    assert 'add_parser("from-csv"' in CLI
    assert "def cmd_from_csv(a):" in CLI
    assert "--validate" in CLI
    assert "generate_batch(" in CLI
    assert "validate_manifest(" in CLI
