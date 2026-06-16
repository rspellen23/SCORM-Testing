"""Markdown microlearning drafts -> Course IR.

Tuned to the TeleTracking microlearning draft format:

  ## Microlearning N: Title
  **Slide K — Heading**
  body paragraphs / markdown tables / - bullet or 1. numbered lists
  ...
  **Slide K — Knowledge Check**
  *Question:* ...
  - A) option
  *Correct Answer:* C
  *Feedback — Correct:* ...
  *Feedback — Incorrect:* ...
  **Articulate Build Notes:**  <- author meta; everything from here is dropped
  **Sources & Further Reading:**

Author meta (Subject, Estimated Length, Learning Objectives, Confidence Score,
Build Notes, Sources) is NOT learner-facing and is excluded. Markdown is a clean
authoring surface — edit the .md, re-run, done.
"""
import re, html
from common import slugify

SLIDE_RE = re.compile(r'^\*\*Slide\s+\d+\s*[—–-]\s*(.+?)\*\*\s*$', re.M)
META_CUT = re.compile(r'^\*\*(Articulate Build Notes|Sources?(\s|&|$)).*', re.M | re.I)


def _inline(s):
    s = html.escape(s.strip())
    s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'(?<![\*\w])\*(?!\s)(.+?)(?<!\s)\*(?![\*\w])', r'<em>\1</em>', s)
    s = re.sub(r'`(.+?)`', r'<code>\1</code>', s)
    s = re.sub(r'\[(.+?)\]\((https?://[^)]+)\)', r'<a href="\2">\1</a>', s)
    return s


def _table(rows):
    cells = [[c.strip() for c in r.strip().strip('|').split('|')] for r in rows]
    header, body = cells[0], cells[2:]  # row 1 is the |---| separator
    out = ['<table><thead><tr>']
    out += [f'<th>{_inline(h)}</th>' for h in header]
    out.append('</tr></thead><tbody>')
    for row in body:
        out.append('<tr>' + ''.join(f'<td>{_inline(c)}</td>' for c in row) + '</tr>')
    out.append('</tbody></table>')
    return ''.join(out)


VISUAL_RE = re.compile(r'^\*Visual:\*\s*(.+)$', re.I)
TRANSITION_RE = re.compile(r'^\*Transition:\*\s*(.+)$', re.I)
SECTION_RE = re.compile(r'^\*Section:\*\s*(.+)$', re.I | re.M)
CARDS_RE = re.compile(r'^\*Cards:\*\s*(.*)$', re.I)
BUTTON_RE = re.compile(r'^\*Button:\*\s*(.+)$', re.I)
FENCE_RE = re.compile(r'^:::\s*(\w+)?\s*$')   # "::: card" / "::: modal" / lone ":::"
NOTE_RE = re.compile(r'^\*Note:\*\s*(.+)$', re.I)
STATEMENT_RE = re.compile(r'^\*Statement:\*\s*(.+)$', re.I)
VIDEO_RE = re.compile(r'^\*Video:\*\s*(.+)$', re.I)
AUDIO_RE = re.compile(r'^\*Audio:\*\s*(.+)$', re.I)
EMBED_RE = re.compile(r'^\*Embed:\*\s*(.+)$', re.I)
DIVIDER_RE = re.compile(r'^(-{3,}|\*{3,}|(?:\*\s){2,}\*)$')


def _kv_opt(segs, key):
    """Pull a `key: value` value out of a list of `·`-separated segments (case-insensitive)."""
    for s in segs:
        m = re.match(key + r'\s*:\s*(.+)$', s, re.I)
        if m:
            return m.group(1).strip()
    return None


def _video_block(spec):
    """`*Video:* file|embed · <src> [· poster: x] [· aspect: 16:9] [· require]`."""
    segs = _segs(spec)
    mode = "embed" if any(s.lower() == "embed" for s in segs) else "file"
    require = any(s.lower() == "require" for s in segs)
    src = next((s for s in segs if s.lower() not in ("file", "embed", "require")
                and (":" not in s or s.lower().startswith("http"))), "")
    b = {"type": "video", "src": src}
    if mode == "embed":
        b["mode"] = "embed"
        asp = _kv_opt(segs, "aspect")
        if asp:
            b["aspect"] = asp
    else:
        poster = _kv_opt(segs, "poster")
        if poster:
            b["poster"] = poster
        if require:
            b["requireComplete"] = True
    return b


def _audio_block(spec):
    """`*Audio:* <src> [· transcript: ...] [· require]`."""
    segs = _segs(spec)
    require = any(s.lower() == "require" for s in segs)
    src = next((s for s in segs if s.lower() != "require"
                and (":" not in s or s.lower().startswith("http"))), "")
    b = {"type": "audio", "src": src}
    tr = _kv_opt(segs, "transcript")
    if tr:
        b["transcript"] = tr
    if require:
        b["requireComplete"] = True
    return b


def _embed_block(spec):
    """`*Embed:* <src> [· aspect: 16:9] [· height: 400] [· title: ...]`."""
    segs = _segs(spec)
    src = next((s for s in segs if ":" not in s or s.lower().startswith("http")), "")
    if not src:
        src = segs[0] if segs else ""
    b = {"type": "embed", "src": src}
    asp = _kv_opt(segs, "aspect")
    if asp:
        b["aspect"] = asp
    h = _kv_opt(segs, "height")
    if h and h.isdigit():
        b["height"] = int(h)
    title = _kv_opt(segs, "title")
    if title:
        b["title"] = title
    return b


def _section_block(spec):
    """`*Section:* <color>` opens a colored section; `*Section:* end` closes it.

    A colored section renders a solid brand-color band (white text) auto-bracketed by matching
    ribbon waves (lead-in above, lead-out below) — the renderer adds the waves. color defaults green.
    """
    s = spec.strip().lower()
    if s.startswith("end") or s == "/":
        return {"type": "sectionEnd"}
    colors = {"green", "gold", "dark", "blue", "teal"}
    color = next((t for t in re.split(r'[\s·|]+', s) if t in colors), "green")
    return {"type": "sectionStart", "color": color}


def _transition_block(spec):
    """Parse `*Transition:* <color> <band>` into a transition block.

    color = green (default) | gold | dark | blue | teal   (brand ribbon color)
    band  = top (default) | bottom                        (which wave edge)
    Renders a reusable brand wave divider from brand/transitions/<color>-<band>.png.
    """
    toks = re.split(r'[\s·|]+', spec.strip().lower())
    colors = {"green", "gold", "dark", "blue", "teal"}
    color = next((t for t in toks if t in colors), "green")
    band = "bottom" if "bottom" in toks else "top"
    return {"type": "transition", "color": color, "band": band}


def _visual_block(spec):
    """Parse a `*Visual:* <type> · <description> · slot: `name` [· side: left|right]` directive.

    type   = screenshot | graphic | diagram | photo | decorative (styling hint; decorative ⇒ no caption)
    slot   = the asset filename in the labelled-asset folder, resolved at build (--images)
    side   = left | right  → a 2-column `imageText` block (image beside text); the following body
             run (paragraphs/lists) is merged into its text column in _body_blocks().
    Returns an image / imageText block carrying a private `_slot` for src resolution in import_md().
    """
    slot = re.search(r'slot:\s*`?([^`·|]+?)`?\s*(?:[·|]|$)', spec, re.I)
    side = re.search(r'side:\s*(left|right)', spec, re.I)
    rest = re.sub(r'(slot|side):\s*`?[^`·|]+`?', '', spec, flags=re.I)
    segs = [x.strip(' ·|`') for x in re.split(r'[·|]', rest) if x.strip(' ·|`')]
    vtype = (segs[0] if segs else "graphic").lower()
    desc = segs[1] if len(segs) > 1 else (segs[0] if segs else "")
    fname = slot.group(1).strip() if slot else ""
    src = ("assets/" + fname) if fname else ""
    if side:
        # 2-column image-beside-text; text column filled by the merge pass
        return {"type": "imageText", "src": src, "alt": desc, "_slot": fname,
                "side": side.group(1).lower(), "html": "", "_mergeText": True}
    block = {"type": "image", "variant": "full", "src": src, "alt": desc, "_slot": fname}
    if vtype not in ("decorative", "decoration"):
        block["caption"] = desc
    return block


def _segs(s):
    return [x.strip() for x in re.split(r'[·|]', s) if x.strip()]


def _apply_modal_kv(modal, line):
    """Fill a bounded modal payload from a `key: value` line (card or button modal).

    Accepts heading/body/media/link, with or without a `modal-` prefix.
    media:  `<image|video|embed> · <src> [· <alt>]`     link:  `<url> [· <label>]`
    Body lines accumulate so multi-paragraph prose survives.
    """
    if ':' not in line:
        return
    key, val = line.split(':', 1)
    k = key.strip().lower().replace('modal-', '')
    val = val.strip()
    if k == 'heading':
        modal['heading'] = val
    elif k == 'body':
        modal['_body'] = (modal.get('_body', '') + ' ' + val).strip()
    elif k == 'media':
        seg = _segs(val)
        if len(seg) >= 2:
            modal['media'] = {'type': seg[0].lower(), 'src': seg[1],
                              'alt': seg[2] if len(seg) > 2 else ''}
    elif k == 'link':
        seg = _segs(val)
        if seg:
            modal['link'] = {'href': seg[0], 'label': seg[1] if len(seg) > 1 else 'Open'}


def _finalize_modal(modal):
    """Convert the accumulated `_body` text into body HTML; drop the modal if empty."""
    if not modal:
        return None
    if '_body' in modal:
        body = modal.pop('_body')
        if body:
            modal['html'] = '<p>' + _inline(body) + '</p>'
    return modal or None


def _parse_modal_fence(lines, j):
    """lines[j] is `::: modal`; read key:value lines until a lone `:::`. Returns (modal, next_i)."""
    j += 1
    modal = {}
    while j < len(lines):
        s = lines[j].strip()
        fm = FENCE_RE.match(s)
        if fm:
            if fm.group(1) is None:          # lone ::: closes the fence
                j += 1
            break                            # a named fence ends this one without consuming
        _apply_modal_kv(modal, s)
        j += 1
    return _finalize_modal(modal), j


def _parse_button(lines, i):
    """`*Button:* <label> · primary|secondary · arrow · link: <url> | modal` (+ optional ::: modal fence)."""
    spec = BUTTON_RE.match(lines[i].strip()).group(1)
    i += 1
    seg = _segs(spec)
    label = seg[0] if seg else 'Learn more'
    variant = 'secondary' if any(s.lower() == 'secondary' for s in seg) else 'primary'
    arrow = any(s.lower() == 'arrow' for s in seg)
    block = {'type': 'button', 'label': label, 'buttonVariant': variant, 'arrow': arrow, 'action': 'link'}
    for s in seg[1:]:
        m = re.match(r'link:\s*(\S+)', s, re.I)
        if m:
            block['href'] = m.group(1); block['action'] = 'link'
        elif s.lower() == 'modal':
            block['action'] = 'modal'
    if block['action'] == 'modal':
        j = i
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j < len(lines):
            fm = FENCE_RE.match(lines[j].strip())
            if fm and (fm.group(1) or '').lower() == 'modal':
                modal, j = _parse_modal_fence(lines, j)
                if modal:
                    block['modal'] = modal
                i = j
    return block, i


def _parse_cards(lines, i):
    """`*Cards:* [requireOpen] [columns: N]` then `::: card` blocks, closed by a lone `:::`."""
    header = CARDS_RE.match(lines[i].strip()).group(1)
    i += 1
    grid = {'type': 'cardGrid', 'cards': []}
    if re.search(r'require\s*open', header, re.I):
        grid['requireOpen'] = True
    mcol = re.search(r'columns?:\s*(\d+)', header, re.I)
    if mcol:
        grid['columns'] = int(mcol.group(1))
    cur = None
    while i < len(lines):
        s = lines[i].strip()
        fm = FENCE_RE.match(s)
        if fm:
            tag = (fm.group(1) or '').lower()
            if tag == 'card':
                cur = {}; grid['cards'].append(cur); i += 1; continue
            i += 1; break                    # lone ::: closes the cards block
        if cur is not None and ':' in s:
            key = s.split(':', 1)[0].strip().lower()
            if key in ('title', 'icon', 'teaser', 'href'):
                cur[key] = s.split(':', 1)[1].strip()
            else:
                _apply_modal_kv(cur.setdefault('modal', {}), s)
        i += 1
    for c in grid['cards']:
        if 'modal' in c:
            m = _finalize_modal(c['modal'])
            if m:
                c['modal'] = m
            else:
                c.pop('modal')
    return grid, i


def _body_blocks(text):
    lines = text.split('\n')
    blocks, para, tbl, lst, lst_ord = [], [], [], [], False

    def flush_para():
        nonlocal para
        if para:
            blocks.append({"type": "paragraph", "html": "<p>" + _inline(" ".join(para)) + "</p>"})
            para = []

    def flush_tbl():
        nonlocal tbl
        if tbl:
            blocks.append({"type": "table", "html": _table(tbl)})
            tbl = []

    def flush_lst():
        nonlocal lst
        if lst:
            blocks.append({"type": "list", "ordered": lst_ord, "items": [_inline(x) for x in lst]})
            lst = []

    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if not s:
            flush_para(); flush_tbl(); flush_lst(); i += 1; continue
        if s.startswith('|'):
            flush_para(); flush_lst(); tbl.append(s); i += 1; continue
        flush_tbl()
        if CARDS_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_cards(lines, i)
            blocks.append(block); continue
        if BUTTON_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_button(lines, i)
            blocks.append(block); continue
        if DIVIDER_RE.match(s):
            flush_para(); flush_lst()
            blocks.append({"type": "divider"}); i += 1; continue
        mvis = VISUAL_RE.match(s)
        if mvis:
            flush_para(); flush_lst()
            blocks.append(_visual_block(mvis.group(1))); i += 1; continue
        mnote = NOTE_RE.match(s)
        if mnote:
            flush_para(); flush_lst()
            blocks.append({"type": "note", "html": "<p>" + _inline(mnote.group(1)) + "</p>"}); i += 1; continue
        mst = STATEMENT_RE.match(s)
        if mst:
            flush_para(); flush_lst()
            blocks.append({"type": "statement", "html": "<p>" + _inline(mst.group(1)) + "</p>"}); i += 1; continue
        mvid = VIDEO_RE.match(s)
        if mvid:
            flush_para(); flush_lst()
            blocks.append(_video_block(mvid.group(1))); i += 1; continue
        maud = AUDIO_RE.match(s)
        if maud:
            flush_para(); flush_lst()
            blocks.append(_audio_block(maud.group(1))); i += 1; continue
        memb = EMBED_RE.match(s)
        if memb:
            flush_para(); flush_lst()
            blocks.append(_embed_block(memb.group(1))); i += 1; continue
        mtr = TRANSITION_RE.match(s)
        if mtr:
            flush_para(); flush_lst()
            blocks.append(_transition_block(mtr.group(1))); i += 1; continue
        msec = SECTION_RE.match(s)
        if msec:
            flush_para(); flush_lst()
            blocks.append(_section_block(msec.group(1))); i += 1; continue
        mnum = re.match(r'^\d+\.\s+(.*)', s)
        mbul = re.match(r'^[-*]\s+(.*)', s)
        if mnum:
            flush_para()
            if lst and not lst_ord: flush_lst()
            lst_ord = True; lst.append(mnum.group(1)); i += 1; continue
        if mbul:
            flush_para()
            if lst and lst_ord: flush_lst()
            lst_ord = False; lst.append(mbul.group(1)); i += 1; continue
        flush_lst()
        para.append(s); i += 1
    flush_para(); flush_tbl(); flush_lst()
    return _merge_image_text(blocks)


def _block_inner_html(b):
    """Serialize a content block to inline HTML for an imageText text column."""
    t = b.get("type")
    if t == "paragraph":
        return b.get("html", "")
    if t == "table":
        return b.get("html", "")
    if t == "list":
        tag = "ol" if b.get("ordered") else "ul"
        return f'<{tag}>' + "".join(f"<li>{x}</li>" for x in b.get("items", [])) + f'</{tag}>'
    return ""


def _merge_image_text(blocks):
    """Fold the body run after a `side:` visual into that imageText block's text column.

    Absorbs following paragraph/list/table blocks until the next structural boundary
    (heading, image/imageText, transition, section marker, KC, continue).
    """
    BOUNDARY = {"image", "imageText", "transition", "sectionStart", "sectionEnd",
                "heading", "headingParagraph", "knowledgeCheck", "continue",
                "button", "cardGrid"}
    out, i = [], 0
    while i < len(blocks):
        b = blocks[i]
        if b.get("type") == "imageText" and b.pop("_mergeText", False):
            parts, j = [], i + 1
            while j < len(blocks) and blocks[j].get("type") not in BOUNDARY:
                parts.append(_block_inner_html(blocks[j])); j += 1
            b["html"] = "".join(p for p in parts if p)
            out.append(b); i = j
        else:
            out.append(b); i += 1
    return out


def _knowledge_check(body):
    q = re.search(r'\*Question:\*\s*(.+)', body)
    opts = re.findall(r'^\s*-\s*[A-D]\)\s*(.+)$', body, re.M)
    ans = re.search(r'\*Correct Answer:\*\s*([A-D])', body)
    fb = re.search(r'\*Feedback\s*[—–-]\s*Correct:\*\s*(.+)', body)
    fbno = re.search(r'\*Feedback\s*[—–-]\s*Incorrect:\*\s*(.+)', body)
    correct_idx = "ABCD".index(ans.group(1)) if ans else -1
    return {
        "type": "knowledgeCheck", "multi": False,
        "prompt": _inline(q.group(1)) if q else "",
        "options": [{"html": _inline(o), "correct": i == correct_idx} for i, o in enumerate(opts)],
        "feedback": _inline(fb.group(1)) if fb else "",
        "feedbackIncorrect": _inline(fbno.group(1)) if fbno else "",
    }


def import_md(md_path, which=1, hero=None, image_dir=None):
    text = open(md_path, encoding="utf-8").read()
    # course-level `*Graded:* pass 80` directive (anywhere in the file) → scored course
    gm = re.search(r'\*Graded:\*\s*(?:pass(?:ing)?\s*)?(\d{1,3})', text, re.I)
    graded = bool(gm)
    passing = max(0, min(100, int(gm.group(1)))) if gm else 80
    # `*Retry:* N` → up to N attempts per KC before it locks + reveals (0/absent = one-shot)
    rm = re.search(r'\*Retry:\*\s*(\d+)', text, re.I)
    retry = int(rm.group(1)) if rm else 0
    secs = re.split(r'^##\s+Microlearning\s+', text, flags=re.M)
    # secs[0] = preamble; module k lives at secs[k] starting "k: Title\n..."
    if which < 1 or which >= len(secs):
        raise ValueError(f"Microlearning {which} not found (file has {len(secs)-1})")
    sec = secs[which]
    head, _nl, rest = sec.partition('\n')
    m = re.match(r'\d+:\s*(.+)', head.strip())
    title = (m.group(1) if m else head).strip()
    # drop a trailing "(101)" / "— Workshop" qualifier noise but keep meaningful suffix
    rest = META_CUT.split(rest)[0]

    parts = SLIDE_RE.split(rest)  # [pre, title1, body1, title2, body2, ...]
    blocks = []
    kc_n = 0
    for i in range(1, len(parts), 2):
        s_title = parts[i].strip()
        s_body = META_CUT.split(parts[i + 1])[0].strip() if i + 1 < len(parts) else ""
        if "knowledge check" in s_title.lower() or re.search(r'\*Question:\*', s_body):
            kc = _knowledge_check(s_body)
            if kc["options"]:
                kc_n += 1
                kc["id"] = f"kc{kc_n}"
                # honor a `*Section:* <color>` wrapping the KC (the KC path skips _body_blocks)
                msec = SECTION_RE.search(s_body)
                sec_color = None
                if msec:
                    sb = _section_block(msec.group(1))
                    if sb.get("type") == "sectionStart":
                        sec_color = sb.get("color")
                if sec_color:
                    blocks.append({"type": "sectionStart", "color": sec_color})
                blocks.append({"type": "heading", "level": 2, "html": "<p>Check Your Understanding</p>"})
                blocks.append(kc)
                if sec_color:
                    blocks.append({"type": "sectionEnd"})
            continue
        blocks.append({"type": "heading", "level": 2, "html": f"<p>{_inline(s_title)}</p>"})
        blocks.extend(_body_blocks(s_body))

    for b in blocks:
        b["gated"] = False

    import os
    used = {}
    cand = {n.lower(): n for n in os.listdir(image_dir)} if image_dir else {}

    # resolve *Visual:* slot directives against the labelled-asset folder
    for b in blocks:
        slot = b.pop("_slot", None)
        if slot:
            actual = cand.get(slot.lower())
            if actual:
                used["assets/" + actual] = os.path.join(image_dir, actual)
                b["src"] = "assets/" + actual
            # else: src stays assets/<slot> — asset supplied later (slot-named, per §10)

    # resolve card/button modal media filenames against the same folder
    def _modals():
        for b in blocks:
            if b.get("type") == "button" and b.get("modal"):
                yield b["modal"]
            if b.get("type") == "cardGrid":
                for c in b.get("cards", []):
                    if c.get("modal"):
                        yield c["modal"]
    def _resolve(holder, key):
        v = holder.get(key)
        if v and not v.startswith(("http", "data:", "assets/")):
            actual = cand.get(os.path.basename(v).lower())
            if actual:
                used["assets/" + actual] = os.path.join(image_dir, actual)
                holder[key] = "assets/" + actual
        elif v and v.startswith("assets/"):
            actual = cand.get(os.path.basename(v).lower())
            if actual:
                used["assets/" + actual] = os.path.join(image_dir, actual)

    for modal in _modals():
        m = modal.get("media")
        if m:
            _resolve(m, "src")
    # top-level self-hosted media (video/audio file mode + posters)
    for b in blocks:
        if b.get("type") in ("video", "audio", "embed") and b.get("mode") != "embed":
            _resolve(b, "src")
            _resolve(b, "poster")

    hero_block = None
    if hero and image_dir:
        actual = cand.get(hero.lower())
        if actual:
            used["assets/" + actual] = os.path.join(image_dir, actual)
            hero_block = {"image": "assets/" + actual, "title": title, "subtitle": ""}

    ir = {"schema": "nova-course-ir/v1", "id": slugify(title), "title": title,
          "locale": "en", "accent": "#1EB16A", "hero": hero_block, "blocks": blocks,
          "graded": graded, "passingScore": passing, "retry": retry}
    ir["_stats"] = {"blocks": len(blocks), "assets": len(used)}
    return ir, used


def _parse_visual_spec(spec):
    """Pull {type, desc, slot, side, orient} from a *Visual:* directive body (read-only metadata)."""
    slot = re.search(r'slot:\s*`?([^`·|]+?)`?\s*(?:[·|]|$)', spec, re.I)
    side = re.search(r'side:\s*(left|right)', spec, re.I)
    orient = re.search(r'orient(?:ation)?:\s*(portrait|landscape|square)', spec, re.I)
    rest = re.sub(r'(slot|side|orient(?:ation)?):\s*`?[^`·|]+`?', '', spec, flags=re.I)
    segs = [x.strip(' ·|`') for x in re.split(r'[·|]', rest) if x.strip(' ·|`')]
    return {
        "type": (segs[0] if segs else "graphic").lower(),
        "desc": segs[1] if len(segs) > 1 else (segs[0] if segs else ""),
        "slot": slot.group(1).strip() if slot else "",
        "side": side.group(1).lower() if side else None,
        "orient": orient.group(1).lower() if orient else None,
    }


def collect_assets(md_path, which=1, hero=None):
    """List the art assets a microlearning needs, with the metadata to generate an image prompt.

    Returns dicts: {slot, role, orientation, description, generatable}. `screenshot` visuals are
    real captures (generatable=False); everything else gets a ChatGPT prompt.
    """
    text = open(md_path, encoding="utf-8").read()
    secs = re.split(r'^##\s+Microlearning\s+', text, flags=re.M)
    if which < 1 or which >= len(secs):
        raise ValueError(f"Microlearning {which} not found (file has {len(secs)-1})")
    head, _nl, rest = secs[which].partition('\n')
    m = re.match(r'\d+:\s*(.+)', head.strip())
    title = (m.group(1) if m else head).strip()
    rest = META_CUT.split(rest)[0]

    assets = []
    if hero:
        assets.append({"slot": hero, "role": "cover", "orientation": "landscape",
                       "description": "", "generatable": True})  # role concept fills it (uses title)
    for line in rest.split('\n'):
        mvis = VISUAL_RE.match(line.strip())
        if not mvis:
            continue
        v = _parse_visual_spec(mvis.group(1))
        generatable = v["type"] not in ("screenshot", "screencap", "screen")
        blob = (v["slot"] + " " + v["desc"]).lower()
        if "objectiv" in blob:
            role = "objectives"
        elif v["side"]:
            role = "aside"
        else:
            role = "full"
        assets.append({"slot": v["slot"], "role": role,
                       "orientation": v["orient"],  # explicit override or None (role default used)
                       "description": v["desc"], "generatable": generatable})
    return title, assets
