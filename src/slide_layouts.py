"""Standalone INFOGRAPHIC slides (.pptx) from a content file — brand-driven.

A reusable slide-template target, separate from course IR. Feed a JSON content
file describing the slide and it renders one editable, on-brand PowerPoint slide.
Colors come from the active brand profile (palette / defaultAccent), so the same
template renders client-branded or neutral depending on --brand.

Layouts:
  infographic  — header band (title + subtitle) | left "challenge" column
                 (heading + intro + bulleted items + callout box) | right
                 "framework" column (heading + sublabel + numbered cards) |
                 a goals row (label chip + cards) | footer band.
                 Every section is optional; omit a key to skip it.

Content schema (all sections optional):
{
  "title": "...", "subtitle": "...",
  "left":  {"heading": "...", "intro": "...",
            "items": [["bold lead", " rest of line"], "plain line", ...],
            "callout": "..."},
  "right": {"heading": "...", "sublabel": "...",
            "cards": [{"num": "1", "title": "...", "body": "...",
                       "accent": "primary|secondary|tertiary|dark"}, ...]},
  "goals": {"label": ["OUR", "GOALS"],
            "items": [{"title": "...", "body": "...", "accent": "primary"}, ...]},
  "footer": "..."
}
"""
import json
import layouts
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GREY  = RGBColor(0x44, 0x4B, 0x4F)
CARD  = RGBColor(0xF4, 0xF6, 0xF7)

W, H = Inches(13.333), Inches(7.5)


def _hex(s, fallback):
    s = (s or "").lstrip("#")
    try:
        return RGBColor(int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except Exception:
        return fallback


def _lighten(c, amt=0.88):
    """Blend a color toward white (amt = fraction of white)."""
    return RGBColor(int(c[0] + (255 - c[0]) * amt),
                    int(c[1] + (255 - c[1]) * amt),
                    int(c[2] + (255 - c[2]) * amt))


def palette(brand):
    """Resolve 4 brand roles (+ derived tint) with graceful fallbacks."""
    p = (brand.get("palette", {}) if brand else {}) or {}
    accent = (brand.get("defaultAccent") if brand else None) or "#3B82F6"
    primary   = _hex(p.get("green")  or p.get("accent")  or accent, RGBColor(0x1E, 0xB1, 0x6A))
    secondary = _hex(p.get("teal")   or p.get("accent2") or accent, RGBColor(0x06, 0x96, 0x96))
    tertiary  = _hex(p.get("blue")   or p.get("accent2") or accent, RGBColor(0x53, 0x9B, 0xD2))
    dark      = _hex(p.get("deepNavy") or p.get("navy") or p.get("heading") or "#1F2937",
                     RGBColor(0x0B, 0x2C, 0x37))
    return {"primary": primary, "secondary": secondary, "tertiary": tertiary,
            "dark": dark, "tint": _lighten(primary), "white": WHITE,
            "grey": GREY, "card": CARD}


def _accent(pal, name, default="primary"):
    return pal.get(name, pal.get(default, pal["primary"]))


LAYOUTS = ("infographic", "process", "comparison", "timeline", "divider", "chart")


def _drawkit(s):
    """Return (fill, rect, text) drawing helpers bound to one slide `s`."""
    def fill(sh, c):
        sh.fill.solid(); sh.fill.fore_color.rgb = c; sh.line.fill.background()

    def rect(x, y, w, h, color, rounded=False):
        shp = s.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE, x, y, w, h)
        fill(shp, color); return shp

    def text(x, y, w, h, runs, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
             space_after=2, line=1.0):
        tb = s.shapes.add_textbox(x, y, w, h); tf = tb.text_frame
        tf.word_wrap = True; tf.vertical_anchor = anchor
        for m in ("left", "right", "top", "bottom"):
            setattr(tf, f"margin_{m}", Pt(2))
        for i, para in enumerate(runs):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align; p.space_after = Pt(space_after)
            p.space_before = Pt(0); p.line_spacing = line
            for (txt, size, color, bold) in para:
                r = p.add_run(); r.text = txt
                r.font.size = Pt(size); r.font.bold = bold; r.font.color.rgb = color
        return tb
    return fill, rect, text


def _render_infographic(s, content, pal, fill, rect, text):
    """INFOGRAPHIC layout — header band | left challenge column | right numbered
    cards | goals row | footer. Every section is optional."""
    cycle = ["primary", "secondary", "tertiary", "dark"]
    # ---- header band (shared) ----
    _header(content, pal, rect, text)

    # ---- left column ----
    left = content.get("left") or {}
    LX, LW = Inches(0.55), Inches(6.35)
    if left.get("heading"):
        text(LX, Inches(1.45), LW, Inches(0.35), [[(left["heading"], 16, pal["primary"], True)]])
    if left.get("intro"):
        text(LX, Inches(1.88), LW, Inches(0.3), [[(left["intro"], 11.5, pal["grey"], False)]])
    cy, row_h = Inches(2.28), Inches(0.46)
    for item in left.get("items", []):
        dot = s.shapes.add_shape(MSO_SHAPE.OVAL, LX, cy + Emu(int(Inches(0.06))),
                                 Inches(0.13), Inches(0.13))
        fill(dot, pal["primary"])
        if isinstance(item, (list, tuple)) and len(item) == 2:
            runs = [[(item[0], 11.5, pal["dark"], True), (item[1], 11.5, pal["grey"], False)]]
        else:
            runs = [[(str(item), 11.5, pal["grey"], False)]]
        text(LX + Inches(0.28), cy, LW - Inches(0.28), row_h, runs)
        cy = cy + row_h
    if left.get("callout"):
        rect(LX, Inches(4.7), LW, Inches(1.0), pal["tint"], rounded=True)
        rect(LX, Inches(4.7), Inches(0.09), Inches(1.0), pal["primary"])
        text(LX + Inches(0.28), Inches(4.78), LW - Inches(0.45), Inches(0.85),
             [[(left["callout"], 12, pal["dark"], True)]], anchor=MSO_ANCHOR.MIDDLE, line=1.05)

    # ---- right column ----
    right = content.get("right") or {}
    RX, RW = Inches(7.15), Inches(5.65)
    if right.get("heading"):
        text(RX, Inches(1.45), RW, Inches(0.35), [[(right["heading"], 16, pal["secondary"], True)]])
    if right.get("sublabel"):
        text(RX, Inches(1.84), RW, Inches(0.3), [[(right["sublabel"], 10.5, pal["grey"], True)]])
    cards = right.get("cards", [])
    yy, ch, gap = Inches(2.24), Inches(0.78), Inches(0.12)
    cycle = ["primary", "secondary", "tertiary", "dark"]
    for i, c in enumerate(cards):
        accent = _accent(pal, c.get("accent", cycle[i % 4]))
        rect(RX, yy, RW, ch, pal["card"], rounded=True)
        rect(RX, yy, Inches(0.62), ch, accent, rounded=True)
        text(RX, yy, Inches(0.62), ch, [[(str(c.get("num", i + 1)), 24, pal["white"], True)]],
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        text(RX + Inches(0.78), yy + Inches(0.07), RW - Inches(0.9), ch,
             [[(c.get("title", ""), 12.5, pal["dark"], True)],
              [(c.get("body", ""), 10.5, pal["grey"], False)]], line=1.0, space_after=1)
        yy = yy + ch + gap

    # ---- goals row ----
    goals = content.get("goals") or {}
    GY = Inches(5.95)
    label = goals.get("label") or []
    if label:
        rect(Inches(0.55), GY, Inches(1.7), Inches(0.9), pal["dark"], rounded=True)
        runs = [[(label[0], 13, pal["white"], True)]]
        if len(label) > 1:
            runs.append([(label[1], 13, pal["primary"], True)])
        text(Inches(0.55), GY, Inches(1.7), Inches(0.9), runs,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, space_after=0)
    gitems = goals.get("items", [])
    gx = Inches(2.45) if label else Inches(0.55)
    gw = Inches(3.42); ggap = Inches(0.13)
    for i, g in enumerate(gitems):
        accent = _accent(pal, g.get("accent", cycle[i % 4]))
        rect(gx, GY, gw, Inches(0.9), pal["card"], rounded=True)
        rect(gx, GY, gw, Inches(0.08), accent, rounded=True)
        text(gx + Inches(0.2), GY + Inches(0.13), gw - Inches(0.35), Inches(0.8),
             [[(g.get("title", ""), 12, pal["dark"], True)],
              [(g.get("body", ""), 10, pal["grey"], False)]], line=1.0, space_after=1)
        gx = gx + gw + ggap

    # ---- footer ----
    footer = content.get("footer")
    if footer:
        rect(0, Inches(7.06), W, Inches(0.44), pal["primary"])
        text(0, Inches(7.06), W, Inches(0.44), [[(footer, 12, pal["white"], True)]],
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    return {"layout": "infographic", "cards": len(cards), "goals": len(gitems)}


def _palette_of(brand):
    return palette(brand if isinstance(brand, dict) else getattr(brand, "data", {}) or {})


def _apply_tx(s, transition, transition_dir, transition_speed):
    if transition and transition != "none":
        import pptx_transitions
        pptx_transitions.apply(s, transition, transition_speed, transition_dir)


def _new_presentation():
    prs = Presentation(); prs.slide_width = W; prs.slide_height = H
    return prs


def _add_slide(prs, content, pal, layout):
    """Render ONE slide of the given layout into `prs`; returns (slide, stats)."""
    if layout not in LAYOUTS:
        raise ValueError(f"unknown slide layout: {layout!r} (have: {', '.join(LAYOUTS)})")
    s = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    fill, rect, text = _drawkit(s)
    stats = RENDERERS[layout](s, content or {}, pal, fill, rect, text)
    return s, stats


def export_slide(content, out, brand=None, layout="infographic",
                 transition=None, transition_dir=None, transition_speed="med"):
    """Render ONE standalone, on-brand slide to a .pptx."""
    pal = _palette_of(brand)
    prs = _new_presentation()
    s, stats = _add_slide(prs, content, pal, layout)
    _apply_tx(s, transition, transition_dir, transition_speed)
    prs.save(out)
    return stats


def export_deck(slides, out, brand=None,
                transition=None, transition_dir=None, transition_speed="med"):
    """Assemble an ORDERED list of slides into ONE multi-slide .pptx deck.

    `slides` is a list of {"layout": <name>, "content": {...}}. The same
    transition (if any) is applied to every slide, like a real deck."""
    if not slides:
        raise ValueError("deck has no slides")
    pal = _palette_of(brand)
    prs = _new_presentation()
    used = []
    for spec in slides:
        layout = (spec or {}).get("layout", "infographic")
        s, _ = _add_slide(prs, (spec or {}).get("content"), pal, layout)
        _apply_tx(s, transition, transition_dir, transition_speed)
        used.append(layout)
    prs.save(out)
    return {"layout": "deck", "slides": len(used), "layouts": used}


def _render_process(s, content, pal, fill, rect, text):
    """PROCESS layout — a horizontal numbered-step poster.

    Header band (title + subtitle) | optional intro line | a row of 3-6
    connected step cards (top accent strip · numbered circle · title · body)
    joined by chevrons | optional footer band. Colors come from the brand.

    Content schema:
    {
      "title": "...", "subtitle": "...", "intro": "...",
      "steps": [{"num": "1", "title": "...", "body": "...",
                 "accent": "primary|secondary|tertiary|dark"}, ...],  # 3-6
      "footer": "..."
    }
    """
    cycle = ["primary", "secondary", "tertiary", "dark"]
    intro = content.get("intro", "")
    steps = (content.get("steps") or [])[:6]   # cap at 6 to stay on-slide
    footer = content.get("footer")

    # ---- header band (shared) ----
    _header(content, pal, rect, text)

    # ---- optional intro ----
    card_top = Inches(1.6)
    if intro:
        text(Inches(0.55), Inches(1.45), Inches(12.23), Inches(0.4),
             [[(intro, 12.5, pal["grey"], False)]])
        card_top = Inches(2.05)

    # ---- step cards row ----
    n = max(1, len(steps))
    margin, gap = Inches(0.55), Inches(0.34)
    avail = W - 2 * margin
    cw = int((avail - (n - 1) * gap) / n)
    card_bottom = Inches(6.85) if not footer else Inches(6.55)
    card_h = int(card_bottom - card_top)
    num_d = Inches(0.92)
    x = margin
    for i, st in enumerate(steps):
        accent = _accent(pal, st.get("accent", cycle[i % 4]))
        rect(x, card_top, cw, card_h, pal["card"], rounded=True)
        rect(x, card_top, cw, Inches(0.1), accent, rounded=True)  # top accent strip
        cx = x + int((cw - num_d) / 2)
        ny = card_top + Inches(0.4)
        circ = s.shapes.add_shape(MSO_SHAPE.OVAL, cx, ny, num_d, num_d)
        fill(circ, accent)
        text(cx, ny, num_d, num_d, [[(str(st.get("num", i + 1)), 30, pal["white"], True)]],
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        text(x + Inches(0.18), card_top + Inches(1.55), cw - Inches(0.36), Inches(0.8),
             [[(st.get("title", ""), 15, pal["dark"], True)]], align=PP_ALIGN.CENTER)
        text(x + Inches(0.18), card_top + Inches(2.35), cw - Inches(0.36),
             card_h - int(Inches(2.55)),
             [[(st.get("body", ""), 11.5, pal["grey"], False)]],
             align=PP_ALIGN.CENTER, line=1.05)
        if i < n - 1:  # connector chevron in the gap
            chd = Inches(0.3)
            chx = x + cw + int((gap - chd) / 2)
            chy = card_top + int(card_h / 2) - int(chd / 2)
            chev = s.shapes.add_shape(MSO_SHAPE.CHEVRON, chx, chy, chd, chd)
            fill(chev, pal["primary"])
        x = x + cw + gap

    # ---- footer band ----
    if footer:
        rect(0, Inches(7.06), W, Inches(0.44), pal["primary"])
        text(0, Inches(7.06), W, Inches(0.44), [[(footer, 12, pal["white"], True)]],
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

    return {"layout": "process", "steps": len(steps)}


def _header(content, pal, rect, text):
    """Shared dark header band (title + accent rule + subtitle). Returns the
    y-offset (EMU) where body content can begin."""
    rect(0, 0, W, Inches(1.18), pal["dark"])
    rect(0, Inches(1.18), W, Inches(0.06), pal["primary"])
    if content.get("title"):
        text(Inches(0.55), Inches(0.14), Inches(12.2), Inches(0.6),
             [[(content["title"], 28, pal["white"], True)]])
    if content.get("subtitle"):
        text(Inches(0.57), Inches(0.74), Inches(12.2), Inches(0.35),
             [[(content["subtitle"], 14, pal["primary"], False)]])
    return Inches(1.55)


def _footer(footer, pal, rect, text):
    if footer:
        rect(0, Inches(7.06), W, Inches(0.44), pal["primary"])
        text(0, Inches(7.06), W, Inches(0.44), [[(footer, 12, pal["white"], True)]],
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)


def _render_comparison(s, content, pal, fill, rect, text):
    """COMPARISON layout — 2 or 3 side-by-side panels.

    Header band | optional intro | 2-3 panels, each: accent header bar (heading)
    · optional sublabel · bulleted items · optional callout box | optional footer.
    Best for old-vs-new, option A/B/C. Colors come from the brand.

    Content schema:
    {
      "title","subtitle","intro",
      "columns": [                                   # 2 or 3
        {"heading":"...","sublabel":"...","accent":"primary|secondary|tertiary|dark",
         "items": [["bold lead"," rest"], "plain line", ...],   # up to 6
         "callout":"..."}, ...
      ],
      "footer":"..."
    }
    """
    # same accent order as the course block (render.py _ACCENT_CYCLE) so a panel
    # gets the same color on either surface.
    cycle = ["primary", "secondary", "tertiary", "dark"]
    content = layouts.normalize_comparison(content)   # accept course `panels` too
    top = _header(content, pal, rect, text)
    if content.get("intro"):
        text(Inches(0.55), Inches(1.45), Inches(12.23), Inches(0.4),
             [[(content["intro"], 12.5, pal["grey"], False)]])
        top = Inches(2.0)
    cols = (content.get("panels") or [])[:3]
    n = max(1, len(cols))
    footer = content.get("footer")
    margin, gap = Inches(0.55), Inches(0.4)
    avail = W - 2 * margin
    pw = int((avail - (n - 1) * gap) / n)
    p_bottom = Inches(6.85) if not footer else Inches(6.55)
    p_h = int(p_bottom - top)
    x = margin
    for i, col in enumerate(cols):
        accent = _accent(pal, col.get("accent", cycle[i % 4]))
        rect(x, top, pw, p_h, pal["card"], rounded=True)              # panel
        rect(x, top, pw, Inches(0.62), accent, rounded=True)          # header bar
        # tags stripped: a course panel may carry inline HTML (<strong> etc.) the
        # slide canvas can't render.
        text(x + Inches(0.1), top, pw - Inches(0.2), Inches(0.62),
             [[(layouts.strip_tags(col.get("heading", "")), 15, pal["white"], True)]],
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        iy = top + Inches(0.78)
        if col.get("sublabel"):
            text(x + Inches(0.22), iy, pw - Inches(0.44), Inches(0.3),
                 [[(layouts.strip_tags(col["sublabel"]), 10.5, pal["grey"], True)]])
            iy = iy + Inches(0.36)
        for item in (col.get("items") or [])[:6]:
            dot = s.shapes.add_shape(MSO_SHAPE.OVAL, x + Inches(0.22),
                                     iy + Inches(0.06), Inches(0.12), Inches(0.12))
            fill(dot, accent)
            if isinstance(item, (list, tuple)) and len(item) == 2:
                runs = [[(layouts.strip_tags(item[0]), 11, pal["dark"], True),
                         (layouts.strip_tags(item[1]), 11, pal["grey"], False)]]
            else:
                runs = [[(layouts.strip_tags(str(item)), 11, pal["grey"], False)]]
            text(x + Inches(0.46), iy, pw - Inches(0.6), Inches(0.5), runs, line=1.02)
            iy = iy + Inches(0.46)
        if col.get("callout"):
            cy = top + p_h - int(Inches(0.95))
            rect(x + Inches(0.18), cy, pw - Inches(0.36), Inches(0.8), pal["tint"], rounded=True)
            text(x + Inches(0.34), cy, pw - Inches(0.68), Inches(0.8),
                 [[(layouts.strip_tags(col["callout"]), 11, pal["dark"], True)]],
                 anchor=MSO_ANCHOR.MIDDLE, line=1.03)
        x = x + pw + gap
    _footer(footer, pal, rect, text)
    return {"layout": "comparison", "columns": len(cols)}


def _render_timeline(s, content, pal, fill, rect, text):
    """TIMELINE / ROADMAP layout — a horizontal axis with 3-6 milestones that
    alternate above and below the line.

    Header band | optional intro | axis line + numbered nodes; each milestone
    card shows a phase chip · title · body | optional footer.

    Content schema:
    {
      "title","subtitle","intro",
      "milestones": [                                # 3-6
        {"phase":"NOW / Q1","title":"...","body":"...",
         "accent":"primary|secondary|tertiary|dark"}, ...
      ],
      "footer":"..."
    }
    """
    cycle = ["primary", "secondary", "tertiary", "dark"]
    content = layouts.normalize_timeline(content)   # accept course `html` as well as slide `body`
    _header(content, pal, rect, text)
    if content.get("intro"):
        text(Inches(0.55), Inches(1.45), Inches(12.23), Inches(0.4),
             [[(content["intro"], 12.5, pal["grey"], False)]])
    ms = (content.get("milestones") or [])[:6]
    n = max(1, len(ms))
    footer = content.get("footer")
    axis_y = Inches(4.05)
    cardw = Inches(2.2)
    half = int(cardw / 2)
    pad = Inches(1.55)                       # keep extreme cards on-slide
    first, last = pad, W - pad
    span = int(last - first)
    node_d = Inches(0.34)
    # axis line
    rect(first, axis_y - Inches(0.015), span, Inches(0.05), pal["dark"])
    for i, m in enumerate(ms):
        cx = first if n == 1 else first + int(span * i / (n - 1))
        accent = _accent(pal, m.get("accent", cycle[i % 4]))
        above = (i % 2 == 0)
        # connector + node
        if above:
            rect(cx - Inches(0.015), Inches(3.55), Inches(0.03), int(axis_y - Inches(3.55)), accent)
        else:
            rect(cx - Inches(0.015), axis_y, Inches(0.03), Inches(0.5), accent)
        node = s.shapes.add_shape(MSO_SHAPE.OVAL, cx - int(node_d / 2),
                                  axis_y - int(node_d / 2), node_d, node_d)
        fill(node, accent)
        text(cx - int(node_d / 2), axis_y - int(node_d / 2), node_d, node_d,
             [[(str(i + 1), 13, pal["white"], True)]],
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        # card (clamped within margins)
        cardx = max(int(Inches(0.4)), min(cx - half, int(W - Inches(0.4) - cardw)))
        cardy = Inches(1.75) if above else Inches(4.6)
        card_h = Inches(1.75)
        rect(cardx, cardy, cardw, card_h, pal["card"], rounded=True)
        rect(cardx, cardy, cardw, Inches(0.08), accent, rounded=True)
        if m.get("phase"):
            text(cardx + Inches(0.16), cardy + Inches(0.14), cardw - Inches(0.32), Inches(0.3),
                 [[(layouts.strip_tags(m["phase"]), 10.5, accent, True)]])
        text(cardx + Inches(0.16), cardy + Inches(0.46), cardw - Inches(0.32), Inches(0.4),
             [[(layouts.strip_tags(m.get("title", "")), 13, pal["dark"], True)]])
        text(cardx + Inches(0.16), cardy + Inches(0.86), cardw - Inches(0.32), Inches(0.82),
             [[(layouts.strip_tags(m.get("body", "")), 10, pal["grey"], False)]], line=1.0)
    _footer(footer, pal, rect, text)
    return {"layout": "timeline", "milestones": len(ms)}


def _render_divider(s, content, pal, fill, rect, text):
    """DIVIDER / SECTION-TITLE layout — a full-bleed branded title screen.

    Full-bleed background (brand role) · optional kicker label + accent rule ·
    large centered title · optional subtitle · optional footer band. Use as a
    section break or a course/deck title slide.

    Content schema:
    {
      "kicker":"SECTION 2", "title":"...", "subtitle":"...",
      "bg":"dark|primary|secondary|tertiary",   # background role (default dark)
      "footer":"..."
    }
    """
    bg = _accent(pal, content.get("bg", "dark"), "dark")
    rect(0, 0, W, H, bg)                              # full bleed
    cx, cw = Inches(1.0), Inches(11.33)
    if content.get("kicker"):
        text(cx, Inches(2.55), cw, Inches(0.4),
             [[(content["kicker"], 16, pal["primary"], True)]], align=PP_ALIGN.CENTER)
        rect(int(W / 2) - Inches(0.6), Inches(3.05), Inches(1.2), Inches(0.05), pal["primary"])
    text(cx, Inches(3.25), cw, Inches(1.4),
         [[(content.get("title", ""), 44, pal["white"], True)]],
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    if content.get("subtitle"):
        text(cx, Inches(4.75), cw, Inches(0.8),
             [[(content["subtitle"], 18, pal["tint"], False)]],
             align=PP_ALIGN.CENTER, line=1.1)
    _footer(content.get("footer"), pal, rect, text)
    return {"layout": "divider"}


def _render_chart(s, content, pal, fill, rect, text):
    """CHART layout — header band (title + subtitle) | a NATIVE, editable PowerPoint
    chart (column / stacked / line / pie) brand-colored | optional source footnote.

    Unlike the other layouts (which draw shapes), this inserts a real PowerPoint
    chart object, so the figures stay editable in PowerPoint. Colors come from the
    brand palette (series = primary/secondary/tertiary/dark, cycling).

    Content schema:
    {
      "title": "...", "subtitle": "...",
      "chart": "bar|line|pie|stackedBar|groupedBar",
      "categories": ["Q1", "Q2", ...],
      "series": [{"name": "Admits", "data": [120, 145, ...]}, ...],
      "xLabel": "...", "yLabel": "...", "source": "..."
    }
    """
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION

    # ---- header band (shared) ----
    _header(content, pal, rect, text)

    ctype = content.get("chart", "bar")
    cats = content.get("categories") or []
    series = [sr for sr in (content.get("series") or []) if isinstance(sr, dict)]
    if not series:
        text(Inches(0.6), Inches(3.4), Inches(12.13), Inches(0.6),
             [[("No chart data provided.", 14, pal["grey"], False)]], align=PP_ALIGN.CENTER)
        return {"layout": "chart", "chart": ctype, "series": 0}

    cd = CategoryChartData()
    cd.categories = cats or [""]
    for i, sr in enumerate(series):
        data = list(sr.get("data") or [])
        if cats:                                  # align each series to the category count
            data = (data + [None] * len(cats))[:len(cats)]
        cd.add_series(sr.get("name") or f"Series {i + 1}", data)

    xl = {"bar": XL_CHART_TYPE.COLUMN_CLUSTERED,
          "groupedBar": XL_CHART_TYPE.COLUMN_CLUSTERED,
          "stackedBar": XL_CHART_TYPE.COLUMN_STACKED,
          "line": XL_CHART_TYPE.LINE_MARKERS,
          "pie": XL_CHART_TYPE.PIE}.get(ctype, XL_CHART_TYPE.COLUMN_CLUSTERED)

    gf = s.shapes.add_chart(xl, Inches(0.6), Inches(1.5), Inches(12.13), Inches(5.2), cd)
    chart = gf.chart
    chart.has_title = False
    order = [pal["primary"], pal["secondary"], pal["tertiary"], pal["dark"]]
    plot = chart.plots[0]

    if ctype == "pie":
        chart.has_legend = True
        chart.legend.position = XL_LEGEND_POSITION.RIGHT
        chart.legend.include_in_layout = False
        for i, pt in enumerate(plot.series[0].points):
            pt.format.fill.solid()
            pt.format.fill.fore_color.rgb = order[i % len(order)]
        plot.has_data_labels = True
        dl = plot.data_labels
        dl.show_percentage = True
        dl.show_value = False
        dl.number_format = "0%"
        dl.number_format_is_linked = False
        try:
            dl.position = XL_LABEL_POSITION.OUTSIDE_END
        except (ValueError, KeyError):
            pass
    else:
        chart.has_legend = len(series) > 1
        if chart.has_legend:
            chart.legend.position = XL_LEGEND_POSITION.BOTTOM
            chart.legend.include_in_layout = False
        for i, ser in enumerate(plot.series):
            c = order[i % len(order)]
            ser.format.fill.solid()
            ser.format.fill.fore_color.rgb = c
            try:                                  # line charts: also color the line
                ser.format.line.color.rgb = c
            except Exception:
                pass
        # axis titles
        try:
            if content.get("yLabel"):
                chart.value_axis.has_title = True
                chart.value_axis.axis_title.text_frame.text = content["yLabel"]
            if content.get("xLabel"):
                chart.category_axis.has_title = True
                chart.category_axis.axis_title.text_frame.text = content["xLabel"]
        except Exception:
            pass

    # ---- source footnote (the provenance line; carried through from the block) ----
    if content.get("source"):
        text(Inches(0.6), Inches(6.92), Inches(12.13), Inches(0.4),
             [[("Source: ", 10, pal["dark"], True), (content["source"], 10, pal["grey"], False)]])
    return {"layout": "chart", "chart": ctype, "series": len(series)}


RENDERERS = {
    "infographic": _render_infographic,
    "process": _render_process,
    "comparison": _render_comparison,
    "timeline": _render_timeline,
    "divider": _render_divider,
    "chart": _render_chart,
}


def export_slide_file(content_path, out, brand=None, layout="infographic", **kw):
    with open(content_path, encoding="utf-8") as fh:
        content = json.load(fh)
    return export_slide(content, out, brand=brand, layout=layout, **kw)


def export_deck_file(content_path, out, brand=None, **kw):
    """Build a deck from a JSON file shaped {"slides": [{"layout","content"}, ...]}
    (a bare list of slide specs is also accepted)."""
    with open(content_path, encoding="utf-8") as fh:
        data = json.load(fh)
    slides = data.get("slides") if isinstance(data, dict) else data
    return export_deck(slides or [], out, brand=brand, **kw)
