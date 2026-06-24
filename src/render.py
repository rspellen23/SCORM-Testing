"""Course IR -> a self-contained HTML course directory (brand + player bundled)."""
import os, re, shutil, html
import brand as brandlib
import chart_svg
import layouts

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


# Brand accent roles -> the tokens.css variables they map to (same 4 roles the
# slide layouts use). Omit a role to auto-cycle, matching the slide renderer.
_ACCENT_VAR = {"primary": "var(--brand-accent)", "secondary": "var(--brand-accent2)",
               "tertiary": "var(--brand-accent-ink)", "dark": "var(--brand-heading)"}
_ACCENT_CYCLE = ("primary", "secondary", "tertiary", "dark")


def _accent_var(role, i=0):
    role = role or _ACCENT_CYCLE[i % 4]
    return _ACCENT_VAR.get(role, "var(--brand-accent)")


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
        if b.get("variant") == "overlay":
            # full-width image with text overlaid (Rise "text overlay") — inline, not promoted to course hero
            cap = f'<div class="nv-hero-cap"><div class="nv-overlay-text">{b.get("html","")}</div></div>' if b.get("html") else ""
            return (f'<figure class="nv-block nv-hero nv-overlay"><img src="{_esc(b["src"])}" '
                    f'alt="{_esc(b.get("alt"))}">{cap}</figure>')
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
        # Skipped when the active brand ships no transitions/ art (sections still get a CSS band).
        if ctx is not None and not ctx.get("transitions", True):
            return ""
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
                f'<div class="nv-kc-fb" role="status" aria-live="polite" data-fb-correct="{_esc(fb_ok)}" data-fb-incorrect="{_esc(fb_no)}"></div>'
                f'</div>')
    if t == "quote":
        attr = f'<figcaption class="nv-quote-by">{_unwrap_p(b.get("attribution"))}</figcaption>' if b.get("attribution") else ""
        cls, style = "nv-block nv-quote", ""
        if b.get("src"):
            cls += " nv-quote--bg"
            style = f' style="--nv-quote-bg:url(&quot;{_esc(b["src"])}&quot;)"'
        return (f'<figure class="{cls}"{style}><blockquote class="nv-quote-text">'
                f'{b.get("html","")}</blockquote>{attr}</figure>')
    if t == "accordion":
        rows = []
        for e in b.get("entries", []):
            img = (f'<img class="nv-acc-media" src="{_esc(e["src"])}" alt="{_esc(e.get("alt"))}">'
                   if e.get("src") else "")
            rows.append(f'<details class="nv-acc-item"><summary>{_unwrap_p(e.get("title"))}</summary>'
                        f'<div class="nv-acc-body">{img}{e.get("html","")}</div></details>')
        return f'<div class="nv-block nv-accordion">{"".join(rows)}</div>'
    if t == "process":
        steps = []
        for e in b.get("entries", []):
            if e.get("kind") == "intro" and not (e.get("title") or e.get("html")):
                continue
            img = (f'<img class="nv-step-media" src="{_esc(e["src"])}" alt="{_esc(e.get("alt"))}">'
                   if e.get("src") else "")
            title = f'<h4 class="nv-step-title">{_unwrap_p(e.get("title"))}</h4>' if e.get("title") else ""
            steps.append(f'<li class="nv-step">{title}{img}<div class="nv-p">{e.get("html","")}</div></li>')
        return f'<ol class="nv-block nv-process">{"".join(steps)}</ol>'
    if t == "flashcard":
        cards = []
        for e in b.get("entries", []):
            fimg = (f'<img class="nv-flip-media" src="{_esc(e["frontSrc"])}" alt="">'
                    if e.get("frontSrc") else "")
            bimg = (f'<img class="nv-flip-media" src="{_esc(e["backSrc"])}" alt="">'
                    if e.get("backSrc") else "")
            cards.append(
                '<button class="nv-flip" type="button" aria-pressed="false">'
                '<span class="nv-sr-only nv-flip-hint">Flashcard — activate to flip.</span>'
                '<span class="nv-flip-inner">'
                f'<span class="nv-flip-face nv-flip-front">{fimg}<span class="nv-flip-text">{e.get("frontHtml","")}</span></span>'
                f'<span class="nv-flip-face nv-flip-back" aria-hidden="true">{bimg}<span class="nv-flip-text">{e.get("backHtml","")}</span></span>'
                '</span></button>')
        return f'<div class="nv-block nv-flashgrid">{"".join(cards)}</div>'
    if t == "categorize":
        buckets = b.get("buckets", [])
        opts = "".join(f'<option value="{_esc(bk.get("id"))}">{_unwrap_p(bk.get("title"))}</option>'
                       for bk in buckets)
        rows = []
        for it in b.get("pool", []):
            rows.append(
                f'<li class="nv-sort-item" data-target="{_esc(it.get("target"))}">'
                f'<span class="nv-sort-label">{_unwrap_p(it.get("html"))}</span>'
                f'<select class="nv-sort-pick" aria-label="Choose a category">'
                f'<option value="">Choose…</option>{opts}</select></li>')
        prompt = f'<div class="nv-sort-prompt">{_unwrap_p(b.get("prompt"))}</div>' if b.get("prompt") else ""
        fb_ok = b.get("feedback", "")
        fb_no = b.get("feedbackIncorrect", "") or fb_ok
        return (f'<div class="nv-block nv-sort" data-sort><div class="nv-sort-instr">Match each item to its category.</div>'
                f'{prompt}<ul class="nv-sort-items">{"".join(rows)}</ul>'
                f'<button class="nv-btn nv-sort-check" type="button">Check</button>'
                f'<div class="nv-sort-fb" role="status" aria-live="polite" data-fb-correct="{_esc(fb_ok)}" data-fb-incorrect="{_esc(fb_no)}"></div></div>')
    if t == "scenario":
        scenes = []
        for sc in b.get("scenes", []):
            head = f'<h3 class="nv-h3">{_unwrap_p(sc.get("title"))}</h3>' if sc.get("title") else ""
            narr = f'<div class="nv-p">{sc.get("html","")}</div>' if sc.get("html") else ""
            resp = []
            for r in sc.get("responses", []):
                pref = " is-preferred" if r.get("preferred") else ""
                fb = f'<div class="nv-scn-fb">{r.get("feedback","")}</div>' if r.get("feedback") else ""
                resp.append(f'<li class="nv-scn-resp{pref}"><div class="nv-scn-choice">{r.get("html","")}</div>{fb}</li>')
            rlist = f'<ul class="nv-scn-responses">{"".join(resp)}</ul>' if resp else ""
            scenes.append(f'<div class="nv-scn-scene">{head}{narr}{rlist}</div>')
        return f'<section class="nv-block nv-scenario">{"".join(scenes)}</section>'
    if t == "timeline":
        # vertical roadmap: a brand axis with milestone cards (HTML parity with the timeline slide layout)
        tl = layouts.normalize_timeline(b)     # accept slide `body` as well as course `html`
        block_accent = b.get("accent")
        items = []
        for i, m in enumerate(tl["milestones"]):
            av = _accent_var(m.get("accent") or block_accent, i)
            phase = f'<span class="nv-tl-phase">{_esc(m.get("phase"))}</span>' if m.get("phase") else ""
            title = f'<h4 class="nv-tl-title">{_unwrap_p(m.get("title"))}</h4>' if m.get("title") else ""
            body = f'<div class="nv-p">{m.get("html","")}</div>' if m.get("html") else ""
            items.append(f'<li class="nv-tl-item" style="--nv-accent:{av}">'
                         f'<span class="nv-tl-node" aria-hidden="true"></span>'
                         f'<div class="nv-tl-card">{phase}{title}{body}</div></li>')
        return f'<ol class="nv-block nv-timeline">{"".join(items)}</ol>'
    if t == "comparison":
        # 2-3 side-by-side panels (old-vs-new / option A/B/C); HTML parity with the comparison slide layout
        cmp = layouts.normalize_comparison(b)  # accept slide `columns` as well as course `panels`
        block_accent = b.get("accent")
        panels = []
        for i, p in enumerate(cmp["panels"]):
            av = _accent_var(p.get("accent") or block_accent, i)
            head = f'<div class="nv-cmp-head">{_unwrap_p(p.get("heading"))}</div>' if p.get("heading") else ""
            sub = f'<div class="nv-cmp-sub">{_esc(p.get("sublabel"))}</div>' if p.get("sublabel") else ""
            lis = "".join(f'<li>{_pair_or_text(x)}</li>' for x in (p.get("items") or []))
            ul = f'<ul class="nv-cmp-list">{lis}</ul>' if lis else ""
            callout = (f'<div class="nv-cmp-callout">{_unwrap_p(p.get("callout"))}</div>'
                       if p.get("callout") else "")
            panels.append(f'<div class="nv-cmp-panel" style="--nv-accent:{av}">{head}{sub}{ul}{callout}</div>')
        cols = max(1, len(panels))
        return f'<div class="nv-block nv-comparison" style="--nv-cmp-cols:{cols}">{"".join(panels)}</div>'
    if t == "chart":
        # engine-generated inline SVG (bar/line/pie/stacked/grouped) — no JS, brand-colored,
        # with a screen-reader data-table fallback. See src/chart_svg.py.
        return chart_svg.render_chart(b)
    if t == "infographic":
        # poster-style overview as a flowing HTML section. Consumes the SAME content object as
        # the 'infographic' slide layout (b["infographic"] == slide content) — one schema, two renderers.
        return _render_infographic_block(b.get("infographic") or {})
    return ""


def _pair_or_text(x):
    """A comparison/list item that is either inline-HTML text OR a [bold, rest]
    pair (the slide-schema shape). Returns the inner HTML (caller wraps it)."""
    if isinstance(x, (list, tuple)):
        bold = _unwrap_p(str(x[0])) if len(x) > 0 else ""
        rest = _unwrap_p(str(x[1])) if len(x) > 1 else ""
        return f'<strong>{bold}</strong>{rest}'
    return _unwrap_p(x)


def _ig_item_li(item):
    """A left-column bullet: a [bold, detail] pair (slide schema) OR a plain string."""
    if isinstance(item, (list, tuple)):
        bold = _unwrap_p(str(item[0])) if len(item) > 0 else ""
        detail = _unwrap_p(str(item[1])) if len(item) > 1 else ""
        return f'<li><strong>{bold}</strong>{detail}</li>'
    return f'<li>{_unwrap_p(item)}</li>'


def _render_infographic_block(c):
    title = f'<h3 class="nv-ig-title">{_unwrap_p(c.get("title"))}</h3>' if c.get("title") else ""
    sub = f'<p class="nv-ig-subtitle">{_unwrap_p(c.get("subtitle"))}</p>' if c.get("subtitle") else ""
    header = f'<header class="nv-ig-header">{title}{sub}</header>' if (title or sub) else ""

    left = c.get("left") or {}
    lh = f'<h4 class="nv-ig-heading">{_esc(left.get("heading"))}</h4>' if left.get("heading") else ""
    li_ = f'<p class="nv-ig-intro">{_unwrap_p(left.get("intro"))}</p>' if left.get("intro") else ""
    litems = "".join(_ig_item_li(it) for it in (left.get("items") or []))
    lul = f'<ul class="nv-ig-items">{litems}</ul>' if litems else ""
    lcall = f'<div class="nv-ig-callout">{_unwrap_p(left.get("callout"))}</div>' if left.get("callout") else ""
    left_html = f'<div class="nv-ig-left">{lh}{li_}{lul}{lcall}</div>' if (lh or li_ or lul or lcall) else ""

    right = c.get("right") or {}
    rh = f'<h4 class="nv-ig-heading">{_esc(right.get("heading"))}</h4>' if right.get("heading") else ""
    rs = f'<div class="nv-ig-sublabel">{_esc(right.get("sublabel"))}</div>' if right.get("sublabel") else ""
    cards = []
    for i, cd in enumerate(right.get("cards") or []):
        av = _accent_var(cd.get("accent"), i)
        num = _esc(str(cd.get("num", i + 1)))
        ct = f'<div class="nv-ig-card-title">{_unwrap_p(cd.get("title"))}</div>' if cd.get("title") else ""
        cb = f'<div class="nv-ig-card-body">{_unwrap_p(cd.get("body"))}</div>' if cd.get("body") else ""
        cards.append(f'<li class="nv-ig-card" style="--nv-accent:{av}">'
                     f'<span class="nv-ig-num" aria-hidden="true">{num}</span>'
                     f'<div class="nv-ig-card-text">{ct}{cb}</div></li>')
    rcards = f'<ul class="nv-ig-cards">{"".join(cards)}</ul>' if cards else ""
    right_html = f'<div class="nv-ig-right">{rh}{rs}{rcards}</div>' if (rh or rs or rcards) else ""

    cols = f'<div class="nv-ig-cols">{left_html}{right_html}</div>' if (left_html or right_html) else ""

    goals = c.get("goals") or {}
    glabel_raw = goals.get("label")
    glabel_txt = " ".join(glabel_raw) if isinstance(glabel_raw, (list, tuple)) else (glabel_raw or "")
    glabel = f'<div class="nv-ig-goals-label">{_esc(glabel_txt)}</div>' if glabel_txt else ""
    gitems = []
    for i, g in enumerate(goals.get("items") or []):
        av = _accent_var(g.get("accent"), i)
        gt = f'<div class="nv-ig-goal-title">{_unwrap_p(g.get("title"))}</div>' if g.get("title") else ""
        gb = f'<div class="nv-ig-goal-body">{_unwrap_p(g.get("body"))}</div>' if g.get("body") else ""
        gitems.append(f'<li class="nv-ig-goal" style="--nv-accent:{av}">{gt}{gb}</li>')
    glist = f'<ul class="nv-ig-goal-list">{"".join(gitems)}</ul>' if gitems else ""
    goals_html = f'<div class="nv-ig-goals">{glabel}{glist}</div>' if (glabel or glist) else ""

    footer = f'<p class="nv-ig-footer">{_unwrap_p(c.get("footer"))}</p>' if c.get("footer") else ""

    return f'<section class="nv-block nv-infographic">{header}{cols}{goals_html}{footer}</section>'


def _section_wave(color, role, ab="", have=True):
    """Lead-in (top of the colored section) uses the <color>-top band; lead-out (bottom) the <color>-bottom.
    Returns nothing when the active brand ships no transition art."""
    if not have:
        return ""
    band = "top" if role == "lead" else "bottom"
    cls = "is-section-lead" if role == "lead" else "is-section-tail"
    return (f'<div class="nv-transition {cls}" aria-hidden="true">'
            f'<img src="{ab}brand/transitions/{color}-{band}.png" alt=""></div>')


def _body(blocks, asset_base="", have_transitions=True):
    """Return (body_html, modals_html). Modal overlays are collected during the walk
    (button/cardGrid register them via ctx) and injected once near the end of <main>."""
    ctx = {"modals": [], "n": [0], "ab": asset_base, "transitions": have_transitions}
    parts, i, n = [], 0, len(blocks)
    sec_color = None
    while i < n:
        b = blocks[i]
        if b.get("type") == "sectionStart":
            sec_color = (b.get("color") or "green").lower()
            parts.append(_section_wave(sec_color, "lead", asset_base, have_transitions))
            parts.append(f'<section class="nv-section nv-section--{sec_color}">')
            i += 1; continue
        if b.get("type") == "sectionEnd":
            parts.append('</section>')
            parts.append(_section_wave(sec_color or "green", "tail", asset_base, have_transitions))
            sec_color = None
            i += 1; continue
        if b.get("type") == "continue":
            parts.append(render_block(b, ctx))
            j = i + 1
            run = []
            while j < n and blocks[j].get("gated"):
                run.append(blocks[j]); j += 1
            if run:
                parts.append('<div class="nv-gated" tabindex="-1" role="region" aria-label="Continued content">')
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
<link rel="icon" href="{ab}brand/{favicon}">
<link rel="stylesheet" href="{ab}brand/tokens.css">
<link rel="stylesheet" href="{ab}player/player.css">
<style>:root{{ --brand-accent: {accent}; }}</style>
<noscript><style>.nv-gated{{ display: block !important; }}</style></noscript>
</head>
<body{body_attrs}>
<a class="nv-skip" href="#nv-main">Skip to content</a>
<header class="nv-topbar">
  <img src="{ab}brand/{logo}" alt="{logo_alt}">
  <span class="nv-title">{title}</span>
  <div class="nv-progress" role="progressbar" aria-label="Course progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><span></span></div>
</header>
<main class="nv-main" id="nv-main" tabindex="-1">
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


def copy_shared(dest_dir, brand=None):
    """Copy the active BRAND profile's assets into dest/brand + bundle player/.
    Only course-needed brand files travel (tokens.css, logo, favicon, fonts/, transitions/);
    brand.json + backgrounds/ + icons/ stay out of the shipped course."""
    b = brand or brandlib.load_brand()
    bdest = os.path.join(dest_dir, "brand")
    os.makedirs(bdest, exist_ok=True)
    tk = b.asset("tokens.css")
    if tk:
        shutil.copy(tk, os.path.join(bdest, "tokens.css"))
    for key in ("logo", "favicon"):
        fn = b.get(key)
        src = b.asset(fn) if fn else None
        if src:
            shutil.copy(src, os.path.join(bdest, os.path.basename(fn)))
    for sub in ("fonts", "transitions"):
        s = b.asset(sub)
        if s and os.path.isdir(s):
            shutil.copytree(s, os.path.join(bdest, sub), dirs_exist_ok=True)
    shutil.copytree(os.path.join(ROOT, "player"), os.path.join(dest_dir, "player"))


def render_course(ir, out_dir, asset_blobs=None, asset_base="", bundle_brand_player=True,
                  lesson_index=1, lesson_count=1, brand=None, animate=True):
    """Write a complete course dir: index.html + (brand/ + player/) + assets/.

    asset_blobs: dict {out_rel_path: bytes} for course media (from a Rise zip or
    a .docx image folder). Brand fonts/logo come from the bundled brand/ dir.
    asset_base: prefix for shared brand/ + player/ refs (e.g. "../" for a SCO in a
    multi-SCO package whose shared assets live at the package root).
    bundle_brand_player: when False, the caller has placed brand/ + player/ at a
    shared location (multi-SCO); only index.html + local assets/ are written here.
    """
    b = brand or brandlib.load_brand()
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    if bundle_brand_player:
        copy_shared(out_dir, b)
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
    body_html, modals_html = _body(ir.get("blocks", []), asset_base, b.has_transitions())
    attrs = f' data-lesson="{int(lesson_index)}" data-lessons="{int(lesson_count)}"'
    if ir.get("graded"):
        attrs += f' data-graded="1" data-pass="{int(ir.get("passingScore", 80))}"'
    if ir.get("retry"):
        attrs += f' data-retry="{int(ir["retry"])}"'
    if not animate:                          # default on; player.js gates on data-anim="0"
        attrs += ' data-anim="0"'
    exit_label = "Next lesson →" if (lesson_count > 1 and lesson_index < lesson_count) else "Finish course"
    page = PAGE.format(lang=ir.get("locale", "en"), title=_esc(ir.get("title")),
                       accent=ir.get("accent") or b.accent, hero=hero_html,
                       body=body_html, modals=modals_html, ab=asset_base,
                       body_attrs=attrs, exit_label=exit_label,
                       favicon=_esc(os.path.basename(b.get("favicon") or "favicon.svg")),
                       logo=_esc(os.path.basename(b.get("logo") or "logo.svg")),
                       logo_alt=_esc(b.get("logoAlt") or ""))
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    return out_dir
