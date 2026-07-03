"""M7 UI drift guard — chart-type dropdown + CSV-paste box in the slide editor.

The deck slide editor (editFields / slideEditorHtml) already edits a chart's
categories + series generically; M7 adds (1) a chart-type <select> in place of the
free-text `chart` field and (2) a "Paste CSV/TSV" box that POSTs to /api/chart-csv
and fills categories + series. These are static assertions over the wiring; the
CSV core is exercised behaviorally in tests/test_charts.py.
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()
SERVER = open(os.path.join(REPO, "dashboard", "server.py"), encoding="utf-8").read()


def _fn(name):
    return HTML.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


def test_chart_types_constant_lists_new_types():
    assert "const CHART_TYPES=[" in HTML
    for t in ("horizontalBar", "horizontalStackedBar", "area", "donut"):
        assert f"'{t}'" in HTML


def test_editfields_renders_chart_type_as_dropdown():
    body = _fn("editFields")
    assert "k==='chart'" in body
    assert "<select" in body and "CHART_TYPES" in body


def test_slide_editor_shows_csv_box_for_charts():
    body = _fn("slideEditorHtml")
    assert "chartCsvBox(i)" in body
    assert "'chart' in o || 'series' in o" in body


def test_csv_box_and_fill_wired():
    box = _fn("chartCsvBox")
    assert "chart_csv_" in box and "fillChartFromCsv(" in box
    fill = _fn("fillChartFromCsv")
    assert "/api/chart-csv" in fill
    assert "o.categories=res.categories" in fill and "o.series=res.series" in fill
    assert "_editCommit(i,o)" in fill and "renderEditor(i)" in fill


def test_chart_guide_mentions_new_types_and_csv():
    # the layout help text operators read
    assert "donut" in HTML and "horizontalBar" in HTML
    assert "paste a CSV" in HTML or "Paste a CSV" in HTML


def test_server_has_chart_csv_route_and_handler():
    assert '/api/chart-csv' in SERVER
    assert "def do_chart_csv(" in SERVER
    assert "chart_svg.parse_chart_csv(" in SERVER
