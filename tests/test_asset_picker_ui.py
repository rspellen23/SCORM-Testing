"""Icon picker — dashboard + server wiring (static drift guards).

The slide controls gained an "Icon" button that opens a modal of on-brand library
icons; picking one sets the slide's `image`. The server serves the library at
/api/assets with a recolored preview SVG per icon.
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()
SERVER = open(os.path.join(REPO, "dashboard", "server.py"), encoding="utf-8").read()


def _fn(name):
    return HTML.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


def test_controls_have_icon_button():
    ctl = _fn("slideControlsHtml")
    assert "openAssetPicker(${i})" in ctl


def test_picker_modal_present():
    assert 'id="asset_picker"' in HTML and 'id="asset_grid"' in HTML
    assert "openAssetPicker" in HTML and "closeAssetPicker" in HTML
    assert "clearAsset()" in HTML            # the remove-icon affordance


def test_picker_fetches_library_and_sets_image():
    op = _fn("openAssetPicker")
    assert "/api/assets" in op and "_assetCache" in op
    si = _fn("_setSlideImage")
    assert "o.image=name" in si and "delete o.image" in si
    assert "renderDeck()" in si              # repaint after the pick


def test_server_serves_asset_library():
    assert '"/api/assets"' in SERVER
    assert "import assets" in SERVER
    assert "icon_preview_svg" in SERVER and "list_icons" in SERVER


def test_resvg_declared_optional_dep():
    pp = open(os.path.join(REPO, "pyproject.toml"), encoding="utf-8").read()
    assert "resvg-py" in pp


def test_icon_license_bundled():
    assert os.path.isfile(os.path.join(REPO, "assets", "icons", "LICENSE.md"))
