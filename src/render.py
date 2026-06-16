"""Course IR -> a self-contained HTML course directory (brand + player bundled)."""
import os, re, shutil, html

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _unwrap_p(s):
    s = (s or "").strip()
    m = re.match(r"^<p>(.*)</p>$", s, re.S)
    return m.group(1).strip() if m and "<p>" not in m.group(1) else s


def _esc(s):
    return html.escape(s or "", quote=True)


def _aspect(s):
    """'16:9' | '16/9' -> a CSS aspect-ratio value; default 16/9."""
    s = (s or "16:9").replace(":", "/").replace(" ", "")
    return s if "/" in s else "16/9"


def _modal_media(m):
    """Render the single bounded media slot inside a modal (image | video | embed)."""
    m = m or {}
    mt, src = m.get("type"), m.get("src")
    if not src:
        return ""
    if mt == "image":
        return f'<img class="nv-modal-media" src="{_esc(src)}" alt="{_esc(m.get("alt"))}">'
    if mt == "video":
        if m.get("mode") == "embed":
            return (f'<div class="nv-embed-frame" style="--nv-aspect:{_aspect(m.get("aspect"))}">'
                    f'<iframe src="{_esc(src)}" title="{_esc(m.get("alt") or "Video")}" loading="lazy" '
                    f'allow="fullscreen; encrypted-media; picture-in-picture" allowfullscreen></iframe></div>')
        poster = f' poster="{_esc(m["poster"])}"' if m.get("poster") else ""
        return (f'<video class="nv-modal-media" controls preload="metadata"{poster}>'
                f'<source src="{_esc(src)}"></video>')
    if mt == "embed":
        return (f'<div class="nv-embed-frame" style="--nv-aspect:{_aspect(m.get("aspect"))}">'
                f'<iframe src="{_esc(src)}" title="{_esc(m.get("alt") or "Interactive content")}" loading="lazy" '
                f'allow="fullscreen; encrypted-media; picture-in-picture" allowfullscreen></iframe></div>')
    return ""


def _modal_panel(mid, modal, title_fallback=""):
    """A hidden dialog overlay holding the bounded payload; the player toggles [hidden]."""
    modal = modal or {}
    heading = _esc(modal.get("heading") or title_fallback)
    media = _modal_media(modal.get("media"))
    body = f'<div class="nv-p nv-modal-body">{modal.get("html","")}</div>' if modal.get("html") else ""
    link = ""
    lk = modal.get("link") or {}
    if lk.get("href"):
        link = (f'<a class="nv-cta nv-cta--primary nv-cta--arrow" href="{_esc(lk["href"])}" '
                f'target="_blank" rel="noopener">{_esc(lk.get("label") or "Open")}'
                f'<span class="nv-cta-arrow" aria-hidden="true">→</span></a>')
    return (f'<div class="nv-modal" id="{mid}" role="dialog" aria-modal="true" '
            f'aria-labelledby="{mid}-t" hidden><div class="nv-modal-card">'
            f'<button class="nv-modal-close" type="button" aria-label="Close">×</button>'
            f'<h2 class="nv-modal-title" id="{mid}-t">{heading}</h2>'
            f'{media}{body}{link}</div></div>')


def _cta_classes(b):
    variant = "secondary" if b.get("buttonVariant") == "secondary" else "primary"
    return "nv-cta nv-cta--" + variant + (" nv-cta--arrow" if b.get("arrow") else "")


def render_block(b, ctx=None):
    t = b.get("type")
    if t == "button":
        label = _esc(b.get("label") or "Learn more")
        arrow = '<span class="nv-cta-arrow" aria-hidden="true">→</span>' if b.get("arrow") else ""
        cls = _cta_classes(b)
        if b.get("action") == "modal" and b.get("modal") and ctx is not None:
            ctx["n"][0] += 1
            mid = f'nv-m{ctx["n"][0]}'
            ctx["modals"].append(_modal_panel(mid, b["modal"], b.get("label")))
            return (f'<div class="nv-block nv-cta-wrap"><button class="{cls}" type="button" '
                    f'data-modal="{mid}">{label}{arrow}</button></div>')
        href = _esc(b.get("href") or "#")
        return (f'<div class="nv-block nv-cta-wrap"><a class="{cls}" href="{href}" '
                f'target="_blank" rel="noopener">{label}{arrow}</a></div>')
    if t == "cardGrid":
        require = b.get("requireOpen")
        cols = b.get("columns")
        style = f' style="--nv-cols:{int(cols)}"' if cols else ""
        cards = []
        for c in b.get("cards", []):
            icon = f'<div class="nv-card-icon" aria-hidden="true">{c.get("icon")}</div>' if c.get("icon") else ""
            teaser = f'<p class="nv-card-teaser">{_esc(c.get("teaser"))}</p>' if c.get("teaser") else ""
            inner = f'{icon}<h3 class="nv-card-title">{_esc(c.get("title"))}</h3>{teaser}'
            if c.get("modal") and ctx is not None:
                ctx["n"][0] += 1
                mid = f'nv-m{ctx["n"][0]}'
                ctx["modals"].append(_modal_panel(mid, c["modal"], c.get("title")))
                req = ' data-require-open="1"' if require else ""
                cue = '<span class="nv-card-cue" aria-hidden="true">+</span>'
                cards.append(f'<button class="nv-card nv-card--interactive" type="button" '
                             f'data-modal="{mid}"{req}>{inner}{cue}</button>')
            elif c.get("href"):
                cards.append(f'<a class="nv-card nv-card--link" href="{_esc(c["href"])}" '
                             f'target="_blank" rel="noopener">{inner}</a>')
            else:
                cards.append(f'<div class="nv-card">{inner}</div>')
        return f'<div class="nv-block nv-cardgrid"{style}>{"".join(cards)}</div>'
    if t == "heading":
        inner = _unwrap_p(b.get("html"))
        if b.get("level", 2) <= 2:
            return f'<div class="nv-block nv-band"><div class="nv-h2">{inner}</div></div>'
        return f'<h3 class="nv-block nv-h3">{inner}</h3>'
    if t == "headingParagraph":
        head = _unwrap_p(b.get("headingHtml"))
        band = f'<div class="nv-band"><div class="nv-h2">{head}</div></div>' if b.get("level",2)<=2 \
               else f'<h3 class="nv-h3">{head}</h3>'
        return f'<div class="nv-block">{band}<div class="nv-p">{b.get("html","")}</div></div>'
    if t == "paragraph":
        return f'<div class="nv-block nv-p">{b.get("html","")}</div>'
    if t == "image":
        if not b.get("src"):
            return ""
        if b.get("variant") == "hero":
            cap = f'<div class="nv-hero-cap"><h1>{_unwrap_p(b.get("html"))}</h1></div>' if b.get("html") else ""
            return f'<div class="nv-hero"><img src="{_esc(b["src"])}" alt="{_esc(b.get("alt"))}">{cap}</div>'
        cap = f'<figcaption>{_esc(b.get("caption"))}</figcaption>' if b.get("caption") else ""
        return f'<figure class="nv-block nv-figure"><img src="{_esc(b["src"])}" alt="{_esc(b.get("alt"))}">{cap}</figure>'
    if t == "imageText":
        if not b.get("src"):
            return f'<div class="nv-block nv-p">{b.get("html","")}</div>'
        side = "right" if b.get("side") == "right" else ""
        return (f'<div class="nv-block nv-aside {side}">'
                f'<img src="{_esc(b["src"])}" alt="{_esc(b.get("alt"))}">'
                f'<div class="nv-p">{b.get("html","")}</div></div>')
    if t == "video":
        if not b.get("src"):
            return ""
        cap = f'<figcaption>{_esc(b.get("caption"))}</figcaption>' if b.get("caption") else ""
        if b.get("mode") == "embed":
            # streamed/hosted video — cross-origin, completion NOT observable (requireComplete ignored)
            return (f'<figure class="nv-block nv-embed" style="--nv-aspect:{_aspect(b.get("aspect"))}">'
                    f'<div class="nv-embed-frame"><iframe src="{_esc(b["src"])}" '
                    f'title="{_esc(b.get("title") or b.get("caption") or "Video")}" loading="lazy" '
                    f'allow="fullscreen; encrypted-media; picture-in-picture" allowfullscreen></iframe></div>'
                    f'{cap}</figure>')
        # self-hosted file — bundled in the SCORM zip; 'ended' is observable
        poster = f' poster="{_esc(b["poster"])}"' if b.get("poster") else ""
        req = ' data-require="1"' if b.get("requireComplete") else ""
        track = (f'<track kind="captions" src="{_esc(b["captions"])}" '
                 f'srclang="{_esc(b.get("captionsLang") or "en")}" label="Captions" default>') \
                if b.get("captions") else ""
        return (f'<figure class="nv-block nv-video"><video controls preload="metadata"{poster}{req}>'
                f'<source src="{_esc(b["src"])}">{track}</video>{cap}</figure>')
    if t == "audio":
        if not b.get("src"):
            return ""
        cap = f'<figcaption>{_esc(b.get("caption"))}</figcaption>' if b.get("caption") else ""
        req = ' data-require="1"' if b.get("requireComplete") else ""
        tr = (f'<details class="nv-transcript"><summary>Transcript</summary>'
              f'<div class="nv-p">{_esc(b.get("transcript"))}</div></details>') if b.get("transcript") else ""
        return (f'<figure class="nv-block nv-audio">'
                f'<audio controls preload="metadata"{req} src="{_esc(b["src"])}"></audio>'
                f'{cap}{tr}</figure>')
    if t == "embed":
        if not b.get("src"):
            return ""
        cap = f'<figcaption>{_esc(b.get("caption"))}</figcaption>' if b.get("caption") else ""
        frame_style = f' style="height:{int(b["height"])}px"' if b.get("height") else ""
        return (f'<figure class="nv-block nv-embed" style="--nv-aspect:{_aspect(b.get("aspect"))}">'
                f'<div class="nv-embed-frame"{frame_style}><iframe src="{_esc(b["src"])}" '
                f'title="{_esc(b.get("title") or b.get("caption") or "Interactive content")}" loading="lazy" '
                f'allow="fullscreen; encrypted-media; picture-in-picture" allowfullscreen></iframe></div>'
                f'{cap}</figure>')
    if t == "note":
        return f'<div class="nv-block nv-note">{b.get("html","")}</div>'
    if t == "statement":
        return f'<div class="nv-block nv-statement">{_unwrap_p(b.get("html"))}</div>'
    if t == "list":
        tag = "ol" if b.get("ordered") else "ul"
        lis = "".join(f"<li>{_unwrap_p(x)}</li>" for x in b.get("items", []))
        return f'<{tag} class="nv-block nv-list">{lis}</{tag}>'
    if t == "table":
        return f'<div class="nv-block nv-table-wrap">{b.get("html","")}</div>'
    if t == "divider":
        return '<hr class="nv-divider">'
    if t == "transition":
        # reusable brand "ribbon" wave divider; color-swappable, band = top|bottom.
        # Pre-cropped canonical bands live in brand/transitions/<color>-<band>.png.
        color = (b.get("color") or "green").lower()
        band = "bottom" if b.get("band") == "bottom" else "top"
        ab = (ctx or {}).get("ab", "")
        src = f"{ab}brand/transitions/{color}-{band}.png"
        return f'<div class="nv-transition" aria-hidden="true"><img src="{_esc(src)}" alt=""></div>'
    if t == "continue":
        txt = _esc(b.get("text") or "CONTINUE")
        return f'<div class="nv-continue" data-passed="0"><button class="nv-btn">{txt}</button></div>'
    if t == "knowledgeCheck":
        opts = "".join(
            f'<button class="nv-kc-opt" data-correct="{1 if o.get("correct") else 0}">{_unwrap_p(o.get("html"))}</button>'
            for o in b.get("options", []))
        # both feedback paths ride as data-* attrs; the player shows the one matching the choice
        fb_ok = b.get("feedback", "")
        fb_no = b.get("feedbackIncorrect", "") or fb_ok
        kcid = f' data-kc-id="{_esc(b.get("id"))}"' if b.get("id") else ""
        return (f'<div class="nv-block nv-kc"{kcid}><div class="nv-kc-prompt">{_unwrap_p(b.get("prompt"))}</div>'
                f'{opts}'
                f'<div class="nv-kc-fb" data-fb-correct="{_esc(fb_ok)}" data-fb-incorrect="{_esc(fb_no)}"></div>'
                f'</div>')
    return ""


def _section_wave(color, role, ab=""):
    """Lead-in (top of the colored section) uses the <color>-top band; lead-out (bottom) the <color>-bottom."""
    band = "top" if role == "lead" else "bottom"
    cls = "is-section-lead" if role == "lead" else "is-section-tail"
    return (f'<div class="nv-transition {cls}" aria-hidden="true">'
            f'<img src="{ab}brand/transitions/{color}-{band}.png" alt=""></div>')


def _body(blocks, asset_base=""):
    """Return (body_html, modals_html). Modal overlays are collected during the walk
    (button/cardGrid register them via ctx) and injected once near the end of <main>."""
    ctx = {"modals": [], "n": [0], "ab": asset_base}
    parts, i, n = [], 0, len(blocks)
    sec_color = None
    while i < n:
        b = blocks[i]
        if b.get("type") == "sectionStart":
            sec_color = (b.get("color") or "green").lower()
            parts.append(_section_wave(sec_color, "lead", asset_base))
            parts.append(f'<section class="nv-section nv-section--{sec_color}">')
            i += 1; continue
        if b.get("type") == "sectionEnd":
            parts.append('</section>')
            parts.append(_section_wave(sec_color or "green", "tail", asset_base))
            sec_color = None
            i += 1; continue
        if b.get("type") == "continue":
            parts.append(render_block(b, ctx))
            j = i + 1
            run = []
            while j < n and blocks[j].get("gated"):
                run.append(blocks[j]); j += 1
            if run:
                parts.append('<div class="nv-gated">')
                parts.extend(render_block(x, ctx) for x in run)
                parts.append('</div>')
            i = j
        else:
            parts.append(render_block(b, ctx)); i += 1
    body_html = "\n".join(p for p in parts if p)
    return body_html, "\n".join(ctx["modals"])


PAGE = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="icon" href="{ab}brand/Favicon.png">
<link rel="stylesheet" href="{ab}brand/tokens.css">
<link rel="stylesheet" href="{ab}player/player.css">
<style>:root{{ --tt-accent: {accent}; }}</style>
</head>
<body{body_attrs}>
<header class="nv-topbar">
  <img src="{ab}brand/Logo.png" alt="TeleTracking">
  <span class="nv-title">{title}</span>
  <div class="nv-progress"><span></span></div>
</header>
<main class="nv-main">
{hero}
{body}
<div class="nv-course-end">
  <p class="nv-course-end-msg">You've reached the end of this microlearning.</p>
  <button class="nv-btn nv-exit" type="button" disabled>{exit_label}</button>
</div>
{modals}
</main>
<script src="{ab}player/player.js"></script>
</body>
</html>
"""


def copy_shared(dest_dir):
    """Copy the bundled brand/ + player/ once (used at the package root for multi-SCO)."""
    shutil.copytree(os.path.join(ROOT, "brand"), os.path.join(dest_dir, "brand"))
    shutil.copytree(os.path.join(ROOT, "player"), os.path.join(dest_dir, "player"))


def render_course(ir, out_dir, asset_blobs=None, asset_base="", bundle_brand_player=True,
                  lesson_index=1, lesson_count=1):
    """Write a complete course dir: index.html + (brand/ + player/) + assets/.

    asset_blobs: dict {out_rel_path: bytes} for course media (from a Rise zip or
    a .docx image folder). Brand fonts/logo come from the bundled brand/ dir.
    asset_base: prefix for shared brand/ + player/ refs (e.g. "../" for a SCO in a
    multi-SCO package whose shared assets live at the package root).
    bundle_brand_player: when False, the caller has placed brand/ + player/ at a
    shared location (multi-SCO); only index.html + local assets/ are written here.
    """
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    if bundle_brand_player:
        copy_shared(out_dir)
    # course media (always local to this dir)
    os.makedirs(os.path.join(out_dir, "assets"), exist_ok=True)
    for rel, blob in (asset_blobs or {}).items():
        dest = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as out:
            out.write(blob)
    hero_html = ""
    if ir.get("hero") and ir["hero"].get("image"):
        h = ir["hero"]
        sub = f'<p>{_esc(h.get("subtitle"))}</p>' if h.get("subtitle") else ""
        hero_html = (f'<div class="nv-hero"><img src="{_esc(h["image"])}" alt="{_esc(h.get("title"))}">'
                     f'<div class="nv-hero-cap"><h1>{_esc(h.get("title"))}</h1>{sub}</div></div>')
    body_html, modals_html = _body(ir.get("blocks", []), asset_base)
    attrs = f' data-lesson="{int(lesson_index)}" data-lessons="{int(lesson_count)}"'
    if ir.get("graded"):
        attrs += f' data-graded="1" data-pass="{int(ir.get("passingScore", 80))}"'
    if ir.get("retry"):
        attrs += f' data-retry="{int(ir["retry"])}"'
    exit_label = "Next lesson →" if (lesson_count > 1 and lesson_index < lesson_count) else "Finish course"
    page = PAGE.format(lang=ir.get("locale", "en"), title=_esc(ir.get("title")),
                       accent=ir.get("accent", "#1EB16A"), hero=hero_html,
                       body=body_html, modals=modals_html, ab=asset_base,
                       body_attrs=attrs, exit_label=exit_label)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    return out_dir
