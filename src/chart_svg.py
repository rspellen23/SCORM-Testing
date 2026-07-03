"""chart_svg — engine-generated inline SVG charts for the HTML course player.

Pure standard library: every chart is static SVG computed here, with NO JavaScript
and NO external charting library, so it renders inside a self-contained SCORM package
and survives an air-gapped LMS. Series colors are brand CSS variables, so a chart
re-skins automatically with the active brand (same mechanism as comparison/timeline).

Accessibility (508/WCAG): the <svg> is aria-hidden (decorative presentation) and the
real data is carried by a visually-hidden <table> that screen readers read, captioned
with the chart title + source. Print and no-CSS fall back to that table too.

Public entry point: render_chart(block) -> HTML string (a <figure>).
"""
import math
import html as _html

# series palette = the brand accent roles, in a stable order (cycles if more series)
_SERIES = ("var(--brand-accent)", "var(--brand-accent2)",
           "var(--brand-accent-ink)", "var(--brand-heading)")

# internal coordinate space; the SVG scales to 100% width via CSS
_W, _H = 680.0, 420.0
_ML, _MR, _MT, _MB = 64.0, 22.0, 28.0, 74.0   # plot margins (left/right/top/bottom)


def _esc(s):
    return _html.escape(str(s if s is not None else ""), quote=True)


def _color(i):
    return _SERIES[i % len(_SERIES)]


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        if isinstance(v, float) and not v.is_integer():
            return f"{v:g}"
        return str(int(v))
    # Non-numeric cell (LLMs emit "N/A"/null for missing data). Show it verbatim in
    # the SR/print data table rather than crashing the whole chart on int("N/A").
    return str(v)


def _nice(x, round_down):
    if x == 0:
        return 0.0
    exp = math.floor(math.log10(abs(x)))
    f = abs(x) / 10 ** exp
    if round_down:
        nf = 1 if f <= 1 else 2 if f <= 2 else 5 if f <= 5 else 10
    else:
        nf = 1 if f < 1.5 else 2 if f < 3 else 5 if f < 7 else 10
    return nf * 10 ** exp * (1 if x >= 0 else -1)


def _ticks(vmin, vmax, n=4):
    """A short list of 'nice' axis tick values spanning [vmin, vmax]."""
    if vmax == vmin:
        vmax = vmin + 1
    step = _nice((vmax - vmin) / max(1, n), True) or 1
    lo = math.floor(vmin / step) * step
    hi = math.ceil(vmax / step) * step
    out, v = [], lo
    while v <= hi + step * 0.5 and len(out) < 12:
        out.append(round(v, 6))
        v += step
    return out


def _series(block):
    return [s for s in (block.get("series") or []) if isinstance(s, dict)]


def _all_values(block):
    vals = []
    for s in _series(block):
        vals += [v for v in (s.get("data") or []) if isinstance(v, (int, float))]
    return vals


# ---------------------------------------------------------------- axis scaffold

def _axes(cats, vmin, vmax):
    """Return (svg_fragment, x0, y0, x1, y1, scale_fn) for a value-vs-category plot."""
    x0, x1 = _ML, _W - _MR
    y0, y1 = _MT, _H - _MB
    ticks = _ticks(vmin, vmax)
    tmin, tmax = ticks[0], ticks[-1]
    span = (tmax - tmin) or 1

    def sy(v):
        return y1 - (v - tmin) / span * (y1 - y0)

    frag = []
    # horizontal gridlines + y tick labels
    for t in ticks:
        gy = sy(t)
        frag.append(f'<line x1="{x0:.1f}" y1="{gy:.1f}" x2="{x1:.1f}" y2="{gy:.1f}" '
                    f'stroke="var(--brand-line)" stroke-width="1"/>')
        frag.append(f'<text x="{x0 - 8:.1f}" y="{gy + 4:.1f}" text-anchor="end" '
                    f'font-size="12" fill="var(--brand-ink-soft)">{_esc(_fmt(t))}</text>')
    # baseline (zero or axis floor) emphasized
    by = sy(max(tmin, min(0, tmax)) if tmin <= 0 <= tmax else tmin)
    frag.append(f'<line x1="{x0:.1f}" y1="{by:.1f}" x2="{x1:.1f}" y2="{by:.1f}" '
                f'stroke="var(--brand-ink-soft)" stroke-width="1.5"/>')
    return "".join(frag), x0, y0, x1, y1, sy, by


def _cat_labels(cats, x0, x1):
    """Evenly spaced category labels along the x axis; returns (fragment, band_centers)."""
    n = max(1, len(cats))
    band = (x1 - x0) / n
    centers = [x0 + band * (k + 0.5) for k in range(n)]
    frag = [f'<text x="{centers[k]:.1f}" y="{_H - _MB + 20:.1f}" text-anchor="middle" '
            f'font-size="12" fill="var(--brand-ink)">{_esc(cats[k])}</text>'
            for k in range(len(cats))]
    return "".join(frag), centers, band


def _axis_titles(block, x0, x1, y0, y1):
    frag = []
    if block.get("xLabel"):
        frag.append(f'<text x="{(x0 + x1) / 2:.1f}" y="{_H - 8:.1f}" text-anchor="middle" '
                    f'font-size="12.5" font-weight="600" fill="var(--brand-ink-soft)">'
                    f'{_esc(block["xLabel"])}</text>')
    if block.get("yLabel"):
        cy = (y0 + y1) / 2
        frag.append(f'<text x="16" y="{cy:.1f}" text-anchor="middle" font-size="12.5" '
                    f'font-weight="600" fill="var(--brand-ink-soft)" '
                    f'transform="rotate(-90 16 {cy:.1f})">{_esc(block["yLabel"])}</text>')
    return "".join(frag)


# ----------------------------------------------------------------- chart bodies

def _svg_open(label):
    return (f'<svg class="nv-chart-svg" viewBox="0 0 {int(_W)} {int(_H)}" '
            f'role="img" aria-label="{_esc(label)}" preserveAspectRatio="xMidYMid meet">')


def _bar(block, stacked=False):
    cats = block.get("categories") or []
    series = _series(block)
    if stacked:
        vmax = max([sum(v for v in (s.get("data") or []) if isinstance(v, (int, float)))
                    for s in series] or [1])
        vmin = 0
    else:
        vals = _all_values(block)
        vmin = min(0, min(vals)) if vals else 0
        vmax = max(vals) if vals else 1
    axfrag, x0, y0, x1, y1, sy, by = _axes(cats, vmin, vmax)
    catfrag, centers, band = _cat_labels(cats, x0, x1)
    bars = []
    ns = max(1, len(series))
    for ci in range(len(cats)):
        cx = x0 + band * ci
        if stacked:
            acc = 0.0
            for si, s in enumerate(series):
                v = (s.get("data") or [None] * len(cats))[ci] if ci < len(s.get("data") or []) else None
                if not isinstance(v, (int, float)):
                    continue
                top, bot = sy(acc + v), sy(acc)
                bars.append(f'<rect x="{cx + band * 0.18:.1f}" y="{top:.1f}" '
                            f'width="{band * 0.64:.1f}" height="{max(0, bot - top):.1f}" '
                            f'fill="{_color(si)}"><title>{_esc(s.get("name"))}: {_esc(_fmt(v))}</title></rect>')
                acc += v
        else:
            gw = band * 0.7 / ns
            for si, s in enumerate(series):
                data = s.get("data") or []
                v = data[ci] if ci < len(data) else None
                if not isinstance(v, (int, float)):
                    continue
                bx = cx + band * 0.15 + gw * si
                top, bot = sy(v), by
                y, h = (top, bot - top) if v >= 0 else (bot, top - bot)
                bars.append(f'<rect x="{bx:.1f}" y="{y:.1f}" width="{gw * 0.86:.1f}" '
                            f'height="{max(0, h):.1f}" fill="{_color(si)}" rx="2">'
                            f'<title>{_esc(s.get("name"))}: {_esc(_fmt(v))}</title></rect>')
                if ns == 1:
                    bars.append(f'<text x="{bx + gw * 0.43:.1f}" y="{top - 5:.1f}" '
                                f'text-anchor="middle" font-size="11.5" '
                                f'fill="var(--brand-ink)">{_esc(_fmt(v))}</text>')
    return (_svg_open(_aria_summary(block)) + axfrag + "".join(bars) + catfrag
            + _axis_titles(block, x0, x1, y0, y1) + "</svg>")


def _line(block, area=False):
    cats = block.get("categories") or []
    series = _series(block)
    vals = _all_values(block)
    vmin = min(0, min(vals)) if vals else 0
    vmax = max(vals) if vals else 1
    axfrag, x0, y0, x1, y1, sy, by = _axes(cats, vmin, vmax)
    catfrag, centers, band = _cat_labels(cats, x0, x1)
    fills, body = [], []
    for si, s in enumerate(series):
        data = s.get("data") or []
        pts = [(centers[ci], sy(data[ci])) for ci in range(min(len(cats), len(data)))
               if isinstance(data[ci], (int, float))]
        if not pts:
            continue
        line = " L".join(f"{px:.1f} {py:.1f}" for px, py in pts)
        if area:                              # translucent region under the line, down to baseline
            fills.append(f'<path d="M{pts[0][0]:.1f} {by:.1f} L{line} '
                         f'L{pts[-1][0]:.1f} {by:.1f} Z" fill="{_color(si)}" '
                         f'fill-opacity="0.16" stroke="none"/>')
        body.append(f'<path d="M{line}" fill="none" stroke="{_color(si)}" stroke-width="2.5" '
                    f'stroke-linejoin="round" stroke-linecap="round"/>')
        for px, py in pts:
            body.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="{_color(si)}"/>')
    return (_svg_open(_aria_summary(block)) + axfrag + "".join(fills) + "".join(body) + catfrag
            + _axis_titles(block, x0, x1, y0, y1) + "</svg>")


# -- horizontal bar: value axis runs along X, categories stack down the Y axis --
_MLH = 118.0                                   # wider left margin: category labels sit here


def _barh(block, stacked=False):
    cats = block.get("categories") or []
    series = _series(block)
    if stacked:
        vmax = max([sum(v for v in (s.get("data") or []) if isinstance(v, (int, float)))
                    for s in series] or [1])
        vmin = 0
    else:
        vals = _all_values(block)
        vmin = min(0, min(vals)) if vals else 0
        vmax = max(vals) if vals else 1
    x0, x1 = _MLH, _W - _MR
    y0, y1 = _MT, _H - 52.0
    ticks = _ticks(vmin, vmax)
    tmin, tmax = ticks[0], ticks[-1]
    span = (tmax - tmin) or 1

    def sx(v):
        return x0 + (v - tmin) / span * (x1 - x0)

    frag = []
    for t in ticks:                            # vertical gridlines + value labels at the bottom
        gx = sx(t)
        frag.append(f'<line x1="{gx:.1f}" y1="{y0:.1f}" x2="{gx:.1f}" y2="{y1:.1f}" '
                    f'stroke="var(--brand-line)" stroke-width="1"/>')
        frag.append(f'<text x="{gx:.1f}" y="{y1 + 18:.1f}" text-anchor="middle" '
                    f'font-size="12" fill="var(--brand-ink-soft)">{_esc(_fmt(t))}</text>')
    bx = sx(max(tmin, min(0, tmax)) if tmin <= 0 <= tmax else tmin)
    frag.append(f'<line x1="{bx:.1f}" y1="{y0:.1f}" x2="{bx:.1f}" y2="{y1:.1f}" '
                f'stroke="var(--brand-ink-soft)" stroke-width="1.5"/>')
    n = max(1, len(cats))
    band = (y1 - y0) / n
    ns = max(1, len(series))
    bars = []
    for ci in range(len(cats)):
        cyt = y0 + band * ci
        bars.append(f'<text x="{x0 - 8:.1f}" y="{cyt + band / 2 + 4:.1f}" text-anchor="end" '
                    f'font-size="12" fill="var(--brand-ink)">{_esc(cats[ci])}</text>')
        if stacked:
            acc = 0.0
            for si, s in enumerate(series):
                data = s.get("data") or []
                v = data[ci] if ci < len(data) else None
                if not isinstance(v, (int, float)):
                    continue
                left, right = sx(acc), sx(acc + v)
                bars.append(f'<rect x="{min(left, right):.1f}" y="{cyt + band * 0.18:.1f}" '
                            f'width="{abs(right - left):.1f}" height="{band * 0.64:.1f}" '
                            f'fill="{_color(si)}"><title>{_esc(s.get("name"))}: {_esc(_fmt(v))}</title></rect>')
                acc += v
        else:
            bh = band * 0.7 / ns
            for si, s in enumerate(series):
                data = s.get("data") or []
                v = data[ci] if ci < len(data) else None
                if not isinstance(v, (int, float)):
                    continue
                yt = cyt + band * 0.15 + bh * si
                xv = sx(v)
                bars.append(f'<rect x="{min(bx, xv):.1f}" y="{yt:.1f}" width="{abs(xv - bx):.1f}" '
                            f'height="{bh * 0.86:.1f}" fill="{_color(si)}" rx="2">'
                            f'<title>{_esc(s.get("name"))}: {_esc(_fmt(v))}</title></rect>')
                if ns == 1:
                    bars.append(f'<text x="{xv + 5:.1f}" y="{yt + bh * 0.43 + 4:.1f}" '
                                f'font-size="11.5" fill="var(--brand-ink)">{_esc(_fmt(v))}</text>')
    return (_svg_open(_aria_summary(block)) + "".join(frag) + "".join(bars)
            + _axis_titles(block, x0, x1, y0, y1) + "</svg>")


def _pie(block, donut=False):
    cats = block.get("categories") or []
    series = _series(block)
    data = (series[0].get("data") if series else []) or []
    pairs = [(cats[i] if i < len(cats) else f"#{i + 1}", data[i])
             for i in range(len(data)) if isinstance(data[i], (int, float)) and data[i] > 0]
    total = sum(v for _, v in pairs) or 1
    cx, cy, r = _W * 0.36, _H / 2, 150.0
    body, ang = [], -math.pi / 2
    for i, (label, v) in enumerate(pairs):
        frac = v / total
        a2 = ang + frac * 2 * math.pi
        x1, y1 = cx + r * math.cos(ang), cy + r * math.sin(ang)
        x2, y2 = cx + r * math.cos(a2), cy + r * math.sin(a2)
        large = 1 if frac > 0.5 else 0
        if frac >= 0.999:                       # single full-circle slice
            body.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{_color(i)}"/>')
        else:
            body.append(f'<path d="M{cx:.1f} {cy:.1f} L{x1:.1f} {y1:.1f} '
                        f'A{r:.1f} {r:.1f} 0 {large} 1 {x2:.1f} {y2:.1f} Z" fill="{_color(i)}">'
                        f'<title>{_esc(label)}: {_esc(_fmt(v))} ({frac * 100:.0f}%)</title></path>')
        ang = a2
    # legend column on the right
    lx, ly = cx + r + 40, cy - len(pairs) * 12
    leg = []
    for i, (label, v) in enumerate(pairs):
        yy = ly + i * 26
        leg.append(f'<rect x="{lx:.1f}" y="{yy:.1f}" width="14" height="14" rx="2" fill="{_color(i)}"/>')
        leg.append(f'<text x="{lx + 22:.1f}" y="{yy + 12:.1f}" font-size="12.5" '
                   f'fill="var(--brand-ink)">{_esc(label)} — {_esc(_fmt(v))} '
                   f'({v / total * 100:.0f}%)</text>')
    # donut = the same wedges with a punched-out center (fills with the frame bg) + a total
    hole = ""
    if donut:
        ri = r * 0.58
        hole = (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{ri:.1f}" fill="var(--brand-light)"/>'
                f'<text x="{cx:.1f}" y="{cy - 4:.1f}" text-anchor="middle" font-size="26" '
                f'font-weight="700" fill="var(--brand-ink)">{_esc(_fmt(total))}</text>'
                f'<text x="{cx:.1f}" y="{cy + 18:.1f}" text-anchor="middle" font-size="12.5" '
                f'fill="var(--brand-ink-soft)">Total</text>')
    return _svg_open(_aria_summary(block)) + "".join(body) + hole + "".join(leg) + "</svg>"


# ------------------------------------------------------------- accessibility text

def _aria_summary(block):
    kind = {"bar": "Bar", "groupedBar": "Grouped bar", "stackedBar": "Stacked bar",
            "horizontalBar": "Horizontal bar", "horizontalStackedBar": "Horizontal stacked bar",
            "line": "Line", "area": "Area", "pie": "Pie", "donut": "Donut"}.get(block.get("chart"), "")
    bits = [f"{kind} chart"]
    if block.get("title"):
        bits.append(_strip(block["title"]))
    return ": ".join(bits) if len(bits) > 1 else bits[0]


def _strip(s):
    return _html.unescape(__import__("re").sub(r"<[^>]+>", "", str(s or ""))).strip()


def _data_table(block):
    """Visually-hidden data table — the screen-reader / print / no-CSS equivalent."""
    cats = block.get("categories") or []
    series = _series(block)
    cap = _strip(block.get("title")) or _aria_summary(block)
    if block.get("source"):
        cap += f" (source: {_strip(block['source'])})"
    head = "".join(f"<th scope=\"col\">{_esc(s.get('name') or f'Series {i + 1}')}</th>"
                   for i, s in enumerate(series))
    rows = []
    for ci in range(len(cats)):
        cells = "".join(
            f"<td>{_esc(_fmt(s.get('data')[ci]))}</td>"
            if ci < len(s.get("data") or []) else "<td></td>" for s in series)
        rows.append(f"<tr><th scope=\"row\">{_esc(cats[ci])}</th>{cells}</tr>")
    return (f'<table class="nv-sr-only"><caption>{_esc(cap)}</caption>'
            f'<thead><tr><th scope="col"></th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def _legend(block):
    series = _series(block)
    if len(series) < 2:
        return ""
    items = "".join(
        f'<li class="nv-chart-key"><span class="nv-chart-swatch" style="background:{_color(i)}"></span>'
        f'{_esc(s.get("name") or f"Series {i + 1}")}</li>' for i, s in enumerate(series))
    return f'<ul class="nv-chart-legend" aria-hidden="true">{items}</ul>'


# --------------------------------------------------------------------- assembly

_BODY = {"bar": _bar, "groupedBar": _bar, "line": _line, "pie": _pie}


def render_chart(block):
    ctype = block.get("chart") or "bar"
    if ctype == "stackedBar":
        svg = _bar(block, stacked=True)
    elif ctype == "groupedBar":
        svg = _bar(block, stacked=False)
    elif ctype == "horizontalBar":
        svg = _barh(block, stacked=False)
    elif ctype == "horizontalStackedBar":
        svg = _barh(block, stacked=True)
    elif ctype == "area":
        svg = _line(block, area=True)
    elif ctype == "donut":
        svg = _pie(block, donut=True)
    else:
        svg = _BODY.get(ctype, _bar)(block)
    title = (f'<figcaption class="nv-chart-title">{block["title"]}</figcaption>'
             if block.get("title") else "")
    legend = "" if ctype in ("pie", "donut") else _legend(block)
    takeaway = (f'<p class="nv-chart-takeaway">{block["takeaway"]}</p>'
                if block.get("takeaway") else "")
    source = (f'<p class="nv-chart-source"><span class="nv-chart-src-label">Source:</span> '
              f'{block["source"]}</p>' if block.get("source") else "")
    return (f'<figure class="nv-block nv-chart" role="group" aria-label="{_esc(_aria_summary(block))}">'
            f'{title}{legend}<div class="nv-chart-frame" aria-hidden="true">{svg}</div>'
            f'{takeaway}{_data_table(block)}{source}</figure>')


# --------------------------------------------------------- CSV / paste -> data

def _csv_num(cell):
    """A pasted cell -> number, or None when blank/non-numeric. Tolerates thousands
    commas, a leading $, and a trailing % (so `1,200`, `$45`, `12%` all parse)."""
    s = str(cell or "").strip().replace(",", "").replace("$", "").rstrip("%").strip()
    if not s:
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return int(f) if f.is_integer() else f


def parse_chart_csv(text, *, max_series=8):
    """Turn pasted CSV/TSV into a chart block's `{categories, series}` — so an operator
    can paste a spreadsheet table straight into the chart editor.

    Convention: first column = category labels, remaining columns = series (their header
    cell = the series name). A first row whose value cells are ALL numeric is treated as
    header-less (unnamed `Series N`). A single column of numbers becomes one series with
    1-based category labels. Blank/non-numeric value cells become `null`. Unknown extra
    columns past `max_series` are dropped. NEVER raises — bad input yields empty data.
    """
    import csv as _csv
    import io as _io
    text = (text or "").lstrip("﻿").strip("\n")
    if not text.strip():
        return {"categories": [], "series": []}
    head = text.split("\n", 1)[0]
    delim = "\t" if "\t" in head else (";" if (";" in head and "," not in head) else ",")
    try:
        rows = [r for r in _csv.reader(_io.StringIO(text), delimiter=delim)
                if any(str(c or "").strip() for c in r)]
    except Exception:
        return {"categories": [], "series": []}
    if not rows:
        return {"categories": [], "series": []}
    ncols = max(len(r) for r in rows)

    if ncols == 1:                             # a single pasted column of values
        nums = [_csv_num(r[0]) for r in rows]
        name = "Series 1"
        if nums and nums[0] is None:           # first cell is a header label, not a value
            name = str(rows[0][0]).strip() or "Series 1"
            nums = nums[1:]
        return {"categories": [str(k + 1) for k in range(len(nums))],
                "series": [{"name": name, "data": nums}]}

    first = rows[0]
    value_cells = first[1:]
    headerless = bool(value_cells) and all(_csv_num(c) is not None for c in value_cells)
    if headerless:
        names = [f"Series {i + 1}" for i in range(ncols - 1)] or ["Series 1"]
        data_rows = rows
    else:
        names = [str(c or "").strip() or f"Series {i + 1}" for i, c in enumerate(first[1:])]
        names = names or ["Series 1"]
        data_rows = rows[1:]
    names = names[:max_series]
    cats, cols = [], [[] for _ in names]
    for r in data_rows:
        cats.append(str(r[0] if r else "").strip())
        for si in range(len(names)):
            cols[si].append(_csv_num(r[si + 1]) if si + 1 < len(r) else None)
    return {"categories": cats,
            "series": [{"name": names[si], "data": cols[si]} for si in range(len(names))]}
