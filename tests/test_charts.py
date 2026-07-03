"""M7 — editable chart data + more chart types.

Adds four new chart types on top of the existing bar/groupedBar/stackedBar/line/pie:
horizontal bar, horizontal stacked bar, area (filled line), and donut (pie with a
punched-out center). Each renders in the inline SVG engine AND the native PPTX deck.
Plus a CSV/TSV -> {categories, series} helper so an operator can paste a spreadsheet
table straight into the chart editor.

Guarantees under test:
  * each new type renders distinct, non-crashing SVG;
  * the ADDITIVE flags leave the original render byte-identical when off;
  * author-friendly spellings alias to the canonical enum in the md parser;
  * the IR schema accepts the new enum values;
  * every new type exports a native .pptx without raising;
  * the CSV parser handles headered/headerless/single-column/blank-cell/TSV input
    and never raises;
  * one new type raster-verifies to a real PNG (when resvg-py is present).
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import chart_svg  # noqa: E402

_MULTI = {"categories": ["Q1", "Q2", "Q3"],
          "series": [{"name": "Admits", "data": [120, 145, 130]},
                     {"name": "Discharges", "data": [110, 132, 140]}],
          "source": "ops report"}


def _blk(chart, **over):
    b = dict(_MULTI, chart=chart)
    b.update(over)
    return b


# ---- new SVG chart types render, distinctly and without crashing --------------

@pytest.mark.parametrize("ctype", ["horizontalBar", "horizontalStackedBar", "area", "donut"])
def test_new_type_renders_svg(ctype):
    svg = chart_svg.render_chart(_blk(ctype))
    assert svg and "<svg" in svg and "</svg>" in svg
    # the data table (SR/print fallback) still carries the numbers
    assert "120" in svg and "145" in svg


def test_new_types_are_distinct_from_the_old_ones():
    seen = {t: chart_svg.render_chart(_blk(t))
            for t in ("bar", "line", "pie", "horizontalBar", "horizontalStackedBar", "area", "donut")}
    assert len(set(seen.values())) == len(seen)     # every variant produced different SVG


def test_donut_punches_a_center_hole_using_the_frame_background():
    svg = chart_svg.render_chart(_blk("donut"))
    assert "var(--brand-light)" in svg              # the hole fills with the frame bg (theme-safe)
    assert "Total" in svg


def test_area_fills_under_the_line():
    svg = chart_svg.render_chart(_blk("area"))
    assert 'fill-opacity="0.16"' in svg
    # still a line on top
    assert 'stroke-width="2.5"' in svg


def test_horizontal_bar_labels_categories_on_the_left_axis():
    svg = chart_svg.render_chart(_blk("horizontalBar"))
    assert 'text-anchor="end"' in svg               # category labels sit right-aligned at the left


def test_aria_summary_names_each_new_type():
    for ctype, word in [("horizontalBar", "Horizontal bar"), ("area", "Area"),
                        ("donut", "Donut"), ("horizontalStackedBar", "Horizontal stacked bar")]:
        svg = chart_svg.render_chart(_blk(ctype, title="X"))
        assert word in svg


# ---- additive: the new flags leave the old render byte-identical when off -----

def test_line_area_off_is_byte_identical_to_before():
    b = _blk("line")
    assert chart_svg._line(dict(b)) == chart_svg._line(dict(b), area=False)


def test_pie_donut_off_is_byte_identical_to_before():
    b = _blk("pie")
    assert chart_svg._pie(dict(b)) == chart_svg._pie(dict(b), donut=False)


# ---- md parser: author-friendly spellings alias to the canonical enum ---------

def _parse_chart_type(kind):
    import md_import
    md = ("## Microlearning 1: T\n\n**Slide 1 — N**\n"
          f"*Chart:* {kind}\ncategories: Q1, Q2\nseries: A = 1, 2\nsource: s\n")
    fd, tmp = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    open(tmp, "w", encoding="utf-8").write(md)
    try:
        ir, _ = md_import.import_md(tmp, which=1)
    finally:
        os.unlink(tmp)
    return [b for b in ir["blocks"] if b.get("type") == "chart"][0]["chart"]


@pytest.mark.parametrize("raw,canon", [
    ("donut", "donut"), ("doughnut", "donut"),
    ("area", "area"), ("areachart", "area"),
    ("horizontal", "horizontalBar"), ("hbar", "horizontalBar"), ("barh", "horizontalBar"),
    ("horizontal-stacked", "horizontalStackedBar"), ("hstacked", "horizontalStackedBar"),
    ("bar", "bar"), ("pie", "pie"),
])
def test_chart_type_aliases(raw, canon):
    assert _parse_chart_type(raw) == canon


def test_donut_is_no_longer_aliased_to_pie():
    # regression: donut used to collapse onto pie; it is now its own render.
    assert _parse_chart_type("donut") == "donut"


def test_schema_accepts_new_chart_enum_values():
    import json
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    schema = json.load(open(os.path.join(root, "schema", "ir.schema.json"), encoding="utf-8"))
    enum = _find_chart_enum(schema)
    for t in ("area", "donut", "horizontalBar", "horizontalStackedBar"):
        assert t in enum


def _find_chart_enum(node):
    # tolerant walk in case the schema nesting differs
    found = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("enum") and "bar" in n["enum"] and "pie" in n["enum"]:
                found.append(n["enum"])
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    walk(node)
    assert found, "chart enum not found in schema"
    return found[0]


# ---- native PPTX: every new type exports without raising ----------------------

@pytest.mark.parametrize("ctype", ["horizontalBar", "horizontalStackedBar", "area", "donut"])
def test_new_type_exports_native_pptx(ctype):
    import slide_layouts
    slides = [{"layout": "chart", "content": {
        "title": "T", "chart": ctype, "categories": ["Q1", "Q2"],
        "series": [{"name": "A", "data": [1, 2]}, {"name": "B", "data": [3, 4]}],
        "source": "s"}}]
    fd, tmp = tempfile.mkstemp(suffix=".pptx")
    os.close(fd)
    try:
        slide_layouts.export_deck(slides, tmp)
        assert os.path.getsize(tmp) > 0
    finally:
        os.unlink(tmp)


# ---- CSV / paste -> chart data ------------------------------------------------

def test_csv_headered_table():
    out = chart_svg.parse_chart_csv("Quarter,Admits,Discharges\nQ1,120,110\nQ2,145,132")
    assert out["categories"] == ["Q1", "Q2"]
    assert out["series"] == [{"name": "Admits", "data": [120, 145]},
                             {"name": "Discharges", "data": [110, 132]}]


def test_csv_headerless_is_unnamed_series():
    out = chart_svg.parse_chart_csv("Q1,5,9\nQ2,6,8")
    assert out["categories"] == ["Q1", "Q2"]
    assert [s["name"] for s in out["series"]] == ["Series 1", "Series 2"]
    assert out["series"][0]["data"] == [5, 6]


def test_csv_single_column_of_values():
    out = chart_svg.parse_chart_csv("10\n20\n30")
    assert out["categories"] == ["1", "2", "3"]
    assert out["series"] == [{"name": "Series 1", "data": [10, 20, 30]}]


def test_csv_single_column_with_header():
    out = chart_svg.parse_chart_csv("Admits\n10\n20")
    assert out["series"][0]["name"] == "Admits"
    assert out["series"][0]["data"] == [10, 20]


def test_csv_tab_separated():
    out = chart_svg.parse_chart_csv("Quarter\tAdmits\nQ1\t120\nQ2\t145")
    assert out["categories"] == ["Q1", "Q2"]
    assert out["series"] == [{"name": "Admits", "data": [120, 145]}]


def test_csv_blank_and_non_numeric_cells_become_null():
    out = chart_svg.parse_chart_csv("Quarter,Admits\nQ1,120\nQ2,\nQ3,N/A")
    assert out["series"][0]["data"] == [120, None, None]


def test_csv_tolerates_thousands_commas_and_symbols():
    out = chart_svg.parse_chart_csv('Region\tRevenue\nEast\t"1,200"\nWest\t$980\nNorth\t12%')
    assert out["series"][0]["data"] == [1200, 980, 12]


def test_csv_empty_input_is_empty_data():
    assert chart_svg.parse_chart_csv("") == {"categories": [], "series": []}
    assert chart_svg.parse_chart_csv("   \n  ") == {"categories": [], "series": []}


def test_csv_never_raises_on_garbage():
    for junk in ["\x00\x01", ",,,\n,,,", "a\nb\nc"]:
        chart_svg.parse_chart_csv(junk)          # must not raise


def test_csv_output_feeds_the_renderer():
    out = chart_svg.parse_chart_csv("Quarter,Admits\nQ1,120\nQ2,145")
    svg = chart_svg.render_chart(dict(out, chart="bar", source="s"))
    assert "120" in svg and "145" in svg


# ---- raster verify one new type (resvg-py) ------------------------------------

def _has_raster():
    try:
        import assets
        return bool(assets.rasterize_svg(
            '<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8"/></svg>'))
    except Exception:
        return False


@pytest.mark.skipif(not _has_raster(), reason="resvg-py not installed")
@pytest.mark.parametrize("brand_css", ["_default", "teletracking"])
def test_new_chart_type_rasterizes_each_theme(brand_css):
    import assets
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tokens = open(os.path.join(root, "brands", brand_css, "tokens.css"), encoding="utf-8").read()
    svg = chart_svg.render_chart(_blk("area"))
    # pull the raw <svg>…</svg> and inject the brand tokens so var() fills resolve to hex
    inner = svg[svg.index("<svg"):svg.index("</svg>") + 6]
    styled = inner.replace("<svg ", f'<svg xmlns="http://www.w3.org/2000/svg" ', 1)
    styled = styled.replace(">", f"><style>:root{{{tokens}}}</style>", 1)
    png = assets.rasterize_svg(styled)
    assert png and len(png) > 200
