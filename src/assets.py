"""Vector asset library — brand-recolor + rasterize SVG icons/shapes (and, later,
illustrations/characters) so they render on every surface.

SVG is the source of truth. The slide preview and the course HTML can embed SVG
natively; the built .pptx can't (python-pptx needs a raster, and PowerPoint wants a
PNG fallback the library won't generate). So for the .pptx we recolor the SVG to a
brand color and rasterize it to a cached PNG with resvg-py (a self-contained binary
wheel — no system libraries). If resvg-py isn't installed, `svg_asset_to_png` returns
None and the caller falls back to its existing labeled placeholder.

The shared image placer (`slide_layouts._place_image`, which also drives the preview)
calls `svg_asset_to_png`, so preview == .pptx — both place the identical recolored PNG.
"""
import os
import re
import hashlib
import tempfile

# repo_root/assets/icons — the shared, brand-agnostic icon library (recolored on use,
# so the source color is irrelevant). Kept OUT of the brand photo folder so course/deck
# generation still draws hero imagery only from the brand's own photography.
ICON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "assets", "icons")

_COMMENT = re.compile(r"<!--.*?-->", re.S)
_HEX6 = re.compile(r"[0-9a-fA-F]{6}")
_HEX3 = re.compile(r"[0-9a-fA-F]{3}")
_SIZE_ATTR = re.compile(r'(<svg\b[^>]*?)\swidth="[^"]*"([^>]*?)\sheight="[^"]*"', re.S)


def norm_hex(color, default="#000000"):
    """Coerce a color into '#RRGGBB'. Accepts '#rrggbb', 'rrggbb', a 3-digit hex, or a
    python-pptx RGBColor (whose str() is six hex digits). Falls back to `default`."""
    if color is None:
        return default
    s = str(color).strip().lstrip("#")
    if _HEX6.fullmatch(s):
        return "#" + s.upper()
    if _HEX3.fullmatch(s):
        return "#" + "".join(c * 2 for c in s).upper()
    return default


def recolor_svg(svg, color):
    """Recolor a monochrome SVG to `color`: strip comments, swap `currentColor`, and
    repaint explicit fills/strokes (never 'none'/'transparent'). Handles both stroke-
    based icons (Tabler: fill=none stroke=currentColor) and fill-based glyphs."""
    hexc = norm_hex(color)
    s = _COMMENT.sub("", svg).strip()
    s = re.sub(r"currentColor", hexc, s, flags=re.I)

    def _swap(m):
        if m.group(2).strip().lower() in ("none", "transparent"):
            return m.group(0)
        return '%s="%s"' % (m.group(1), hexc)

    return re.sub(r'(fill|stroke)="([^"]*)"', _swap, s)


def _resize_svg(svg, px):
    """Set the root <svg> width/height to `px` (keeps the viewBox, so the art scales)
    so a 24px icon rasterizes crisp at slide size. Injects the attrs if absent."""
    if _SIZE_ATTR.search(svg):
        return _SIZE_ATTR.sub(r'\1 width="%d"\2 height="%d"' % (px, px), svg, count=1)
    return re.sub(r"<svg\b", '<svg width="%d" height="%d"' % (px, px), svg, count=1)


def rasterize_svg(svg, px=512):
    """Recolored SVG text -> PNG bytes via resvg-py, or None if it isn't installed."""
    try:
        import resvg_py
    except Exception:
        return None
    try:
        out = resvg_py.svg_to_bytes(svg_string=_resize_svg(svg, px))
        return bytes(out)
    except Exception:
        return None


_CACHE = {}
_TMPDIR = None


def _tmpdir():
    global _TMPDIR
    if _TMPDIR is None:
        _TMPDIR = tempfile.mkdtemp(prefix="cb_assets_")
    return _TMPDIR


def svg_asset_to_png(svg_path, color, px=512):
    """Recolor an SVG asset to `color` and rasterize to a cached PNG file; return its
    path, or None when rasterization isn't available (caller falls back to a
    placeholder). Cached by (path, mtime, color, size) so re-renders are cheap."""
    try:
        mtime = os.path.getmtime(svg_path)
    except OSError:
        return None
    key = hashlib.md5(("%s|%s|%s|%d" % (svg_path, mtime, norm_hex(color), px)).encode()).hexdigest()
    hit = _CACHE.get(key)
    if hit and os.path.isfile(hit):
        return hit
    try:
        with open(svg_path, encoding="utf-8") as fh:
            svg = fh.read()
    except OSError:
        return None
    png = rasterize_svg(recolor_svg(svg, color), px)
    if not png:
        return None
    out = os.path.join(_tmpdir(), key + ".png")
    with open(out, "wb") as fh:
        fh.write(png)
    _CACHE[key] = out
    return out


def icon_path(name):
    """Resolve a bare icon filename to the shared library, or None. basename-confined
    so a slide's `image` value can never escape the library."""
    if not name or not isinstance(name, str):
        return None
    p = os.path.join(ICON_DIR, os.path.basename(name))
    return p if os.path.isfile(p) else None


def list_icons():
    """Filenames of the bundled library icons (for the picker)."""
    if not os.path.isdir(ICON_DIR):
        return []
    return sorted(n for n in os.listdir(ICON_DIR)
                  if n.lower().endswith(".svg") and not n.startswith("."))


def icon_preview_svg(name, color="#0B2C37"):
    """A recolored, size-normalized SVG string for the picker thumbnail, or '' if the
    icon is missing. Confined to the library."""
    p = icon_path(name)
    if not p:
        return ""
    try:
        with open(p, encoding="utf-8") as fh:
            return _resize_svg(recolor_svg(fh.read(), color), 48)
    except OSError:
        return ""
