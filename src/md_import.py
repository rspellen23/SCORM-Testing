"""Markdown microlearning drafts -> Course IR.

Tuned to the standard microlearning draft format:

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
import wordsearch
import crossword
import gameshow
import quizboard
import speedstreak

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
QUOTE_RE = re.compile(r'^\*Quote:\*\s*(.+)$', re.I)
ACCORDION_RE = re.compile(r'^\*Accordion:\*\s*(.*)$', re.I)
PROCESS_RE = re.compile(r'^\*Process:\*\s*(.*)$', re.I)
FLASHCARD_RE = re.compile(r'^\*Flashcard:\*\s*(.*)$', re.I)
CATEGORIZE_RE = re.compile(r'^\*(?:Categorize|Sort):\*\s*(.*)$', re.I)
DRAGDROP_RE = re.compile(r'^\*(?:DragDrop|Drag[-\s]?and[-\s]?Drop|Drag):\*\s*(.*)$', re.I)
WORDSEARCH_RE = re.compile(r'^\*(?:WordSearch|Word[-\s]?Search|Word[-\s]?Find|WordFind):\*\s*(.*)$', re.I)
CROSSWORD_RE = re.compile(r'^\*(?:Crossword|Cross[-\s]?Word):\*\s*(.*)$', re.I)
GAMESHOW_RE = re.compile(r'^\*(?:GameShow|Game[-\s]?Show|Wheel|SpinWheel|Spin[-\s]?the[-\s]?Wheel):\*\s*(.*)$', re.I)
QUIZBOARD_RE = re.compile(r'^\*(?:QuizBoard|Quiz[-\s]?Board|Jeopardy|Game[-\s]?Board|Board):\*\s*(.*)$', re.I)
SPEEDSTREAK_RE = re.compile(r'^\*(?:SpeedStreak|Speed[-\s]?Streak|Speed[-\s]?Round|Speed[-\s]?Quiz|Rapid[-\s]?Fire|RapidFire|Streak):\*\s*(.*)$', re.I)
MATCHING_RE = re.compile(r'^\*(?:Matching|Match):\*\s*(.*)$', re.I)
SEQUENCE_RE = re.compile(r'^\*(?:Sequence|Order|Ordering):\*\s*(.*)$', re.I)
FILLBLANK_RE = re.compile(r'^\*(?:FillBlank|Fill-?in(?:-the-blank)?|Fill|Blank|Cloze):\*\s*(.*)$', re.I)
# C5 — a question BANK: `*Bank:* draw N` opens a pool of question children (KC + the
# M12 matching/sequence/fill types); the player draws N at runtime. Closed by
# `*Bank:* end`, a lone `:::`, or a slide/section boundary. END is checked first so a
# closer isn't mistaken for an opener (the opener's `.*` also matches "end").
QUESTIONBANK_END_RE = re.compile(r'^\*(?:Bank|QuestionBank):\*\s*end\s*$', re.I)
QUESTIONBANK_RE = re.compile(r'^\*(?:Bank|QuestionBank):\*\s*(.*)$', re.I)
TIMELINE_RE = re.compile(r'^\*Timeline:\*\s*(.*)$', re.I)
COMPARISON_RE = re.compile(r'^\*Comparison:\*\s*(.*)$', re.I)
CHART_RE = re.compile(r'^\*Chart:\*\s*(.*)$', re.I)
INFOGRAPHIC_RE = re.compile(r'^\*Infographic:\*\s*(.*)$', re.I)
CONTINUE_RE = re.compile(r'^\*Continue:\*\s*(.*)$', re.I)
SCENARIO_RE = re.compile(r'^\*Scenario:\*\s*(.*)$', re.I)
REFLECTION_RE = re.compile(r'^\*(?:Reflection|Reflect|Open[-\s]?Response|Free[-\s]?Text):\*\s*(.*)$', re.I)
OBJECTIVES_RE = re.compile(r'^\*(?:Objectives|Learning Objectives):\*\s*(.*)$', re.I)

# A fenced/keyed block must never run past the next slide / unit / meta marker:
# if an author forgets the closing lone `:::`, the block stops here instead of
# eating the rest of the unit (the unclosed-fence swallow, audit item 2.5).
# This is the boundary the infographic parser already enforced; it is shared by
# all the fenced parsers so they behave identically.
FENCE_BOUNDARY_RE = re.compile(r'^(\*\*Slide\b|\*\*Articulate|\*\*Sources?\b|##\s)', re.I)
_CHART_ALIASES = {                       # author-friendly spellings -> canonical enum
    "bar": "bar", "column": "bar", "col": "bar",
    "line": "line", "trend": "line",
    "area": "area", "areachart": "area", "filled-line": "area",
    "pie": "pie",
    "donut": "donut", "doughnut": "donut",
    "stacked": "stackedBar", "stackedbar": "stackedBar", "stacked-bar": "stackedBar",
    "grouped": "groupedBar", "groupedbar": "groupedBar", "grouped-bar": "groupedBar",
    "clustered": "groupedBar",
    "horizontal": "horizontalBar", "horizontalbar": "horizontalBar", "hbar": "horizontalBar",
    "barh": "horizontalBar", "bar-h": "horizontalBar",
    "horizontalstacked": "horizontalStackedBar", "horizontal-stacked": "horizontalStackedBar",
    "hstacked": "horizontalStackedBar", "stackedh": "horizontalStackedBar",
}


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
    _apply_captions(b, segs)
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
    _apply_captions(b, segs)
    return b


def _apply_captions(b, segs):
    """M3: bind a caption track (`· captions: file.vtt [· lang: xx]`) onto a
    media block. `captions:` may be an auto-generated sidecar (see captions.py)
    or an author-supplied .vtt/.srt. Absent when not authored, so the IR stays
    byte-identical for un-captioned media."""
    caps = _kv_opt(segs, "captions")
    if caps:
        b["captions"] = caps
        lang = _kv_opt(segs, "lang") or _kv_opt(segs, "captionsLang")
        if lang:
            b["captionsLang"] = lang


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

    M13 — a section wrapping a knowledge check may also declare a GRADED OBJECTIVE:
    `*Section:* blue · Medication Safety · pass 70` — the `· <name>` labels a scored
    objective and the optional `· pass <N>` sets its section threshold (0..100). KCs that
    share a section name roll up into ONE objective (a per-section subscore). A bare token
    `quiz`/`graded`/`scored` marks the section graded without a threshold. A plain
    `*Section:* <color>` stays a purely VISUAL band — byte-identical IR (no name/graded/pass).
    """
    raw = spec.strip()
    if raw.lower().startswith("end") or raw == "/":
        return {"type": "sectionEnd"}
    colors = {"green", "gold", "dark", "blue", "teal"}
    color = next((t for t in re.split(r'[\s·|]+', raw.lower()) if t in colors), "green")
    block = {"type": "sectionStart", "color": color}
    passv = None
    graded = False
    names = []
    for seg in re.split(r'[·|]', raw):
        seg = seg.strip()
        if not seg:
            continue
        low = seg.lower()
        m = re.match(r'pass(?:ing)?\s*(\d{1,3})\s*%?$', low)
        if m:
            passv = max(0, min(100, int(m.group(1)))); graded = True; continue
        if low in ("quiz", "graded", "scored"):
            graded = True; continue
        # a name segment: drop any bare color token, keep the rest as the objective label
        toks = [t for t in re.split(r'\s+', seg) if t and t.lower() not in colors]
        if toks:
            names.append(" ".join(toks))
    name = " ".join(names).strip()
    if name:
        block["name"] = name; graded = True
    if graded:
        block["graded"] = True
    if passv is not None:
        block["pass"] = passv
    return block


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
    is_dec = vtype in ("decorative", "decoration")
    if side:
        # 2-column image-beside-text; text column filled by the merge pass
        b = {"type": "imageText", "src": src, "alt": desc, "_slot": fname,
             "side": side.group(1).lower(), "html": "", "_mergeText": True}
        if is_dec:
            b["decorative"] = True          # a11y (M2): an empty alt here is intentional, not an omission
        return b
    block = {"type": "image", "variant": "full", "src": src, "alt": desc, "_slot": fname}
    if is_dec:
        block["decorative"] = True          # a11y (M2): decorative ⇒ empty alt is valid; skip alt check
    else:
        block["caption"] = desc
    return block


def _segs(s):
    return [x.strip() for x in re.split(r'[·|]', s) if x.strip()]


def _scene_slug(s):
    """Normalize a scenario scene id / `goto:` target so authors can write it loosely.
    `Escalate Now` and `escalate-now` both slug to `escalate-now`; a `goto:` and the
    `id:` it points at match after slugging."""
    return re.sub(r'[^a-z0-9]+', '-', (s or "").strip().lower()).strip('-')


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
        grid['columns'] = min(4, max(1, int(mcol.group(1))))   # schema caps columns at 4
    cur = None
    while i < len(lines):
        s = lines[i].strip()
        if FENCE_BOUNDARY_RE.match(s):       # unclosed fence: stop at the next marker, don't consume it
            break
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


def _quote_block(spec):
    """`*Quote:* <text> · by: <name> · slot: `bg.jpg``."""
    segs = _segs(spec)
    text = segs[0] if segs else ""
    by = _kv_opt(segs, "by")
    b = {"type": "quote", "html": "<p>" + _inline(text) + "</p>"}
    if by:
        b["attribution"] = "<p>" + _inline(by) + "</p>"
    slot = re.search(r'slot:\s*`?([^`·|]+?)`?\s*(?:[·|]|$)', spec, re.I)
    if slot:
        b["_slot"] = slot.group(1).strip()
    return b


def _read_fences(lines, i):
    """Read `::: <tag>` groups (key: value lines) until a lone `:::`. Returns (groups, next_i).
    A group with no key:value lines collects its body from a single 'body:'-less run is not
    supported — use explicit `key: value` lines (title/body/front/back/slot)."""
    groups, cur = [], None
    while i < len(lines):
        s = lines[i].strip()
        if FENCE_BOUNDARY_RE.match(s):    # unclosed fence: stop at the next marker, don't consume it
            break
        fm = FENCE_RE.match(s)
        if fm:
            if fm.group(1) is None:      # lone ::: closes the block
                i += 1
                break
            cur = {}
            groups.append(cur)
            i += 1
            continue
        if cur is not None and ':' in s:
            k, v = s.split(':', 1)
            cur[k.strip().lower()] = v.strip()
        i += 1
    return groups, i


def _parse_accordion(lines, i, kind="accordion"):
    """`*Accordion:*`/`*Process:*` then `::: item`/`::: step` (title:/body:/slot:) groups, lone `:::` closes."""
    i += 1
    groups, i = _read_fences(lines, i)
    entries = []
    for g in groups:
        e = {"title": g.get("title", ""),
             "html": ("<p>" + _inline(g["body"]) + "</p>") if g.get("body") else ""}
        if g.get("slot"):
            e["src"] = g["slot"]
        if kind == "process":
            e["kind"] = g.get("kind", "step")
        entries.append(e)
    return {"type": kind, "entries": entries}, i


def _parse_flashcard(lines, i):
    """`*Flashcard:*` then `::: card` (front:/back:/frontslot:/backslot:) groups, lone `:::` closes."""
    i += 1
    groups, i = _read_fences(lines, i)
    entries = []
    for g in groups:
        e = {"frontHtml": "<p>" + _inline(g.get("front", "")) + "</p>",
             "backHtml": "<p>" + _inline(g.get("back", "")) + "</p>"}
        if g.get("frontslot"):
            e["frontSrc"] = g["frontslot"]
        if g.get("backslot"):
            e["backSrc"] = g["backslot"]
        entries.append(e)
    return {"type": "flashcard", "entries": entries}, i


def _parse_categorize(lines, i):
    """`*Categorize:* [prompt: ...]` then `bucket: <title>` / `item: <text> -> <bucket title>` lines, lone `:::` closes."""
    header = CATEGORIZE_RE.match(lines[i].strip()).group(1)
    i += 1
    block = {"type": "categorize", "buckets": [], "pool": []}
    mp = re.search(r'prompt:\s*(.+)$', header, re.I)
    if mp:
        block["prompt"] = _inline(mp.group(1).strip())
    name2id = {}
    while i < len(lines):
        s = lines[i].strip()
        if FENCE_BOUNDARY_RE.match(s):       # unclosed fence: stop at the next marker, don't consume it
            break
        if FENCE_RE.match(s):
            i += 1
            break
        if not s:
            i += 1
            continue
        mb = re.match(r'bucket:\s*(.+)$', s, re.I)
        mi = re.match(r'item:\s*(.+?)\s*(?:->|=>|»)\s*(.+)$', s, re.I)
        if mb:
            bid = "b" + str(len(block["buckets"]) + 1)
            title = mb.group(1).strip()
            name2id[title.lower()] = bid
            block["buckets"].append({"id": bid, "title": _inline(title)})
        elif mi:
            block["pool"].append({"html": _inline(mi.group(1).strip()),
                                  "_target_name": mi.group(2).strip().lower()})
        i += 1
    for p in block["pool"]:
        p["target"] = name2id.get(p.pop("_target_name", ""), "")
    return block, i


def _parse_dragDrop(lines, i):
    """`*DragDrop:* [prompt: ...]` then optional `image: <src>`, `zone: <title> [@ x,y]`
    and `item: <label> -> <zone title>` lines, lone `:::` closes. Mirrors _parse_categorize:
    the learner drags each label onto its correct zone (partial credit). `@ x,y` (percent)
    positions a zone over the background diagram; `image:` sets that diagram."""
    header = DRAGDROP_RE.match(lines[i].strip()).group(1)
    i += 1
    block = {"type": "dragDrop", "zones": [], "pool": []}
    mp = re.search(r'prompt:\s*(.+)$', header, re.I)
    if mp:
        block["prompt"] = _inline(mp.group(1).strip())
    name2id = {}
    while i < len(lines):
        s = lines[i].strip()
        if FENCE_BOUNDARY_RE.match(s):       # unclosed fence: stop at the next marker, don't consume it
            break
        if FENCE_RE.match(s):
            i += 1
            break
        if not s:
            i += 1
            continue
        mimg = re.match(r'image:\s*(.+)$', s, re.I)
        mz = re.match(r'zone:\s*(.+)$', s, re.I)
        mi = re.match(r'item:\s*(.+?)\s*(?:->|=>|»)\s*(.+)$', s, re.I)
        if mimg:
            block["src"] = mimg.group(1).strip()
        elif mz:
            zid = "z" + str(len(block["zones"]) + 1)
            title = mz.group(1).strip()
            zone = {"id": zid}
            mpos = re.search(r'\s*@\s*([\d.]+)\s*,\s*([\d.]+)\s*$', title)
            if mpos:
                title = title[:mpos.start()].strip()
                zone["x"] = float(mpos.group(1))
                zone["y"] = float(mpos.group(2))
            zone["title"] = _inline(title)
            name2id[title.lower()] = zid
            block["zones"].append(zone)
        elif mi:
            block["pool"].append({"html": _inline(mi.group(1).strip()),
                                  "_target_name": mi.group(2).strip().lower()})
        i += 1
    for p in block["pool"]:
        p["target"] = name2id.get(p.pop("_target_name", ""), "")
    # a diagram with no positioned zones falls back to the labeled-row layout at render
    return block, i


def _parse_wordSearch(lines, i):
    """`*WordSearch:* [prompt: ...]` then `term: <WORD> [| <clue>]` lines, lone `:::` closes.

    The author supplies only the terms (and optional clues); the letter grid is GENERATED
    here at build time via wordsearch.generate() so the IR — and therefore the build — is
    deterministic and self-contained. Non-letter characters in a term are stripped for the
    grid but the ORIGINAL text is shown in the word list. Scored with partial credit
    (words found / total), mirroring matching/dragDrop."""
    header = WORDSEARCH_RE.match(lines[i].strip()).group(1)
    i += 1
    block = {"type": "wordSearch"}
    mp = re.search(r'prompt:\s*(.+)$', header, re.I)
    if mp:
        block["prompt"] = _inline(mp.group(1).strip())
    terms = []          # (display_text, cleaned, clue|None) in authored order
    while i < len(lines):
        s = lines[i].strip()
        if FENCE_BOUNDARY_RE.match(s):       # unclosed fence: stop at the next marker, don't consume it
            break
        if FENCE_RE.match(s):
            i += 1
            break
        if not s:
            i += 1
            continue
        mt = re.match(r'(?:term|word):\s*(.+)$', s, re.I)
        if mt:
            body = mt.group(1).strip()
            clue = None
            if "|" in body:
                body, clue = body.split("|", 1)
                body, clue = body.strip(), clue.strip()
            cleaned = wordsearch.clean_word(body)
            if len(cleaned) >= 2:
                terms.append((body, cleaned, clue or None))
        i += 1
    puzzle = wordsearch.generate([c for (_d, c, _cl) in terms])
    clue_by_word = {c: cl for (_d, c, cl) in terms}
    disp_by_word = {c: d for (d, c, _cl) in terms}
    for w in puzzle.get("words", []):
        cl = clue_by_word.get(w["text"])
        if cl:
            w["clue"] = _inline(cl)
        disp = disp_by_word.get(w["text"])
        if disp and disp.upper() != w["text"]:   # multi-word / punctuated term → show the original in the list
            w["display"] = _inline(disp)
    block["grid"] = puzzle.get("grid", [])
    block["words"] = puzzle.get("words", [])
    block["size"] = puzzle.get("size", 0)
    return block, i


def _parse_crossword(lines, i):
    """`*Crossword:* [prompt: ...]` then `word: <ANSWER> | <clue>` lines, lone `:::` closes.

    The author supplies the answers and their clues; the interlocking numbered grid is
    GENERATED here at build time via crossword.generate() so the IR — and therefore the
    build — is deterministic and self-contained. Non-letter characters in an answer are
    stripped for the grid; the ORIGINAL text is shown in the clue list heading. A word that
    can't be interlocked with the others is dropped (its clue then doesn't appear). Scored
    with partial credit (words solved / total), mirroring wordSearch/matching."""
    header = CROSSWORD_RE.match(lines[i].strip()).group(1)
    i += 1
    block = {"type": "crossword"}
    mp = re.search(r'prompt:\s*(.+)$', header, re.I)
    if mp:
        block["prompt"] = _inline(mp.group(1).strip())
    entries = []        # (display_text, cleaned, clue|None) in authored order
    while i < len(lines):
        s = lines[i].strip()
        if FENCE_BOUNDARY_RE.match(s):       # unclosed fence: stop at the next marker, don't consume it
            break
        if FENCE_RE.match(s):
            i += 1
            break
        if not s:
            i += 1
            continue
        mw = re.match(r'(?:word|clue|answer):\s*(.+)$', s, re.I)
        if mw:
            body = mw.group(1).strip()
            clue = None
            if "|" in body:
                body, clue = body.split("|", 1)
                body, clue = body.strip(), clue.strip()
            cleaned = crossword.clean_word(body)
            if len(cleaned) >= 2:
                entries.append((body, cleaned, clue or None))
        i += 1
    puzzle = crossword.generate([c for (_d, c, _cl) in entries])
    clue_by_word = {c: cl for (_d, c, cl) in entries}
    disp_by_word = {c: d for (d, c, _cl) in entries}
    for w in puzzle.get("words", []):
        cl = clue_by_word.get(w["text"])
        if cl:
            w["clue"] = _inline(cl)
        disp = disp_by_word.get(w["text"])
        if disp and disp.upper() != w["text"]:   # multi-word / punctuated answer → show the original
            w["display"] = _inline(disp)
    block["grid"] = puzzle.get("grid", [])
    block["words"] = puzzle.get("words", [])
    block["rows"] = puzzle.get("rows", 0)
    block["cols"] = puzzle.get("cols", 0)
    return block, i


def _parse_gameShow(lines, i):
    """`*GameShow:* [prompt: ...]` then repeated `q:`/`a:`/`option:` lines, lone `:::` closes.

    Each question is a group: a `q:` stem, an `a:` (correct answer), and one or more
    `option:` (distractor) lines; a new `q:` starts the next question. The options are
    shuffled DETERMINISTICALLY at build time via gameshow.build() so the correct-option
    index is fixed in the IR (the player never re-shuffles → resume-stable). A question
    missing its stem, its answer, or every distractor is dropped. Scored with partial
    credit (answered N of M correctly), mirroring wordSearch/crossword."""
    header = GAMESHOW_RE.match(lines[i].strip()).group(1)
    i += 1
    block = {"type": "gameShow"}
    mp = re.search(r'prompt:\s*(.+)$', header, re.I)
    if mp:
        block["prompt"] = _inline(mp.group(1).strip())
    questions = []          # [{"q","correct","distractors":[...]}] in authored order
    cur = None
    while i < len(lines):
        s = lines[i].strip()
        if FENCE_BOUNDARY_RE.match(s):       # unclosed fence: stop at the next marker, don't consume it
            break
        if FENCE_RE.match(s):
            i += 1
            break
        if not s:
            i += 1
            continue
        mq = re.match(r'(?:q|question):\s*(.+)$', s, re.I)
        if mq:
            cur = {"q": mq.group(1).strip(), "correct": "", "distractors": []}
            questions.append(cur)
            i += 1
            continue
        ma = re.match(r'(?:a|answer|correct):\s*(.+)$', s, re.I)
        if ma and cur is not None:
            cur["correct"] = ma.group(1).strip()
            i += 1
            continue
        mo = re.match(r'(?:option|distractor|wrong):\s*(.+)$', s, re.I)
        if mo and cur is not None:
            cur["distractors"].append(mo.group(1).strip())
        i += 1
    built = gameshow.build(questions)
    slices = []
    for sl in built.get("slices", []):
        slices.append({"q": _inline(sl["q"]), "options": [_inline(o) for o in sl["options"]],
                       "answer": sl["answer"]})
    block["slices"] = slices
    return block, i


def _parse_quizBoard(lines, i):
    """`*QuizBoard:* [prompt: ...]` then repeated `category:` columns, each holding
    `q:`/`a:`/`option:` question groups; lone `:::` closes the block.

    A `category:` line starts a new column; under it, each question is a group of a
    `q:` stem, an `a:` (correct answer) and one or more `option:` (distractor) lines,
    a new `q:` starting the next question (= the next row/tile). Tiles are numbered
    top-down and given an escalating point value by quizboard.build(), which also
    shuffles each MCQ's options DETERMINISTICALLY (reusing gameshow.build) so the
    correct-option index is fixed in the IR. A question missing its stem/answer/every
    distractor is dropped; a column with no surviving tile is dropped. Scored with
    weighted partial credit (points earned / points possible)."""
    header = QUIZBOARD_RE.match(lines[i].strip()).group(1)
    i += 1
    block = {"type": "quizBoard"}
    mp = re.search(r'prompt:\s*(.+)$', header, re.I)
    if mp:
        block["prompt"] = _inline(mp.group(1).strip())
    categories = []         # [{"name","questions":[{"q","correct","distractors":[...]}]}]
    cat = None
    cur = None
    while i < len(lines):
        s = lines[i].strip()
        if FENCE_BOUNDARY_RE.match(s):       # unclosed fence: stop at the next marker, don't consume it
            break
        if FENCE_RE.match(s):
            i += 1
            break
        if not s:
            i += 1
            continue
        mc = re.match(r'(?:category|column|col):\s*(.+)$', s, re.I)
        if mc:
            cat = {"name": mc.group(1).strip(), "questions": []}
            categories.append(cat)
            cur = None
            i += 1
            continue
        mq = re.match(r'(?:q|question):\s*(.+)$', s, re.I)
        if mq and cat is not None:            # a question before any category is ignored (category-first)
            cur = {"q": mq.group(1).strip(), "correct": "", "distractors": []}
            cat["questions"].append(cur)
            i += 1
            continue
        ma = re.match(r'(?:a|answer|correct):\s*(.+)$', s, re.I)
        if ma and cur is not None:
            cur["correct"] = ma.group(1).strip()
            i += 1
            continue
        mo = re.match(r'(?:option|distractor|wrong):\s*(.+)$', s, re.I)
        if mo and cur is not None:
            cur["distractors"].append(mo.group(1).strip())
        i += 1
    built = quizboard.build(categories)
    cols = []
    for c in built.get("board", []):
        cols.append({"name": _inline(c["name"]), "tiles": [
            {"q": _inline(t["q"]), "options": [_inline(o) for o in t["options"]],
             "answer": t["answer"], "value": t["value"]} for t in c["tiles"]]})
    block["board"] = cols
    block["cols"] = built.get("cols", 0)
    block["rows"] = built.get("rows", 0)
    return block, i


def _parse_speedStreak(lines, i):
    """`*SpeedStreak:* [timer: N] [prompt: ...]` then repeated `q:`/`a:`/`option:`
    lines, lone `:::` closes.

    A fast one-at-a-time MCQ run built from the same `q:`/`a:`/`option:` groups
    gameShow uses (a new `q:` starts the next question). Options are shuffled
    DETERMINISTICALLY at build time via speedstreak.build() → gameshow.build() so the
    correct-option index is fixed in the IR (the player never re-shuffles → resume-
    stable). An optional `timer: N` (whole seconds) adds a per-question countdown that
    drives only a COSMETIC speed bonus — correctness and the graded {got,max} have no
    time limit. Scored with partial credit (answered N of M correctly), mirroring
    gameShow. Put `prompt:` LAST on the header if you also set a timer."""
    header = SPEEDSTREAK_RE.match(lines[i].strip()).group(1)
    i += 1
    block = {"type": "speedStreak"}
    mt = re.search(r'timer:\s*(\d+)', header, re.I)
    timer = int(mt.group(1)) if mt else 0
    mp = re.search(r'prompt:\s*(.+)$', header, re.I)
    if mp:
        # defensively drop a trailing `timer: N` if the author put the prompt first
        ptxt = re.sub(r'\s*timer:\s*\d+\s*$', '', mp.group(1).strip(), flags=re.I)
        if ptxt.strip():
            block["prompt"] = _inline(ptxt.strip())
    questions = []          # [{"q","correct","distractors":[...]}] in authored order
    cur = None
    while i < len(lines):
        s = lines[i].strip()
        if FENCE_BOUNDARY_RE.match(s):       # unclosed fence: stop at the next marker, don't consume it
            break
        if FENCE_RE.match(s):
            i += 1
            break
        if not s:
            i += 1
            continue
        mq = re.match(r'(?:q|question):\s*(.+)$', s, re.I)
        if mq:
            cur = {"q": mq.group(1).strip(), "correct": "", "distractors": []}
            questions.append(cur)
            i += 1
            continue
        ma = re.match(r'(?:a|answer|correct):\s*(.+)$', s, re.I)
        if ma and cur is not None:
            cur["correct"] = ma.group(1).strip()
            i += 1
            continue
        mo = re.match(r'(?:option|distractor|wrong):\s*(.+)$', s, re.I)
        if mo and cur is not None:
            cur["distractors"].append(mo.group(1).strip())
        i += 1
    built = speedstreak.build(questions, timer=timer)
    rounds = []
    for sl in built.get("rounds", []):
        rounds.append({"q": _inline(sl["q"]), "options": [_inline(o) for o in sl["options"]],
                       "answer": sl["answer"]})
    block["rounds"] = rounds
    if built.get("timer"):          # only emit when set → an untimed block stays byte-identical
        block["timer"] = built["timer"]
    return block, i


def _parse_matching(lines, i):
    """`*Matching:* [prompt: ...]` then `pair: <left> -> <right>` lines, lone `:::` closes.

    M12 — the learner matches each LEFT item to its correct RIGHT partner (a select of
    all rights). Scored with PARTIAL credit (per-pair). Mirrors _parse_categorize."""
    header = MATCHING_RE.match(lines[i].strip()).group(1)
    i += 1
    block = {"type": "matching", "pairs": []}
    mp = re.search(r'prompt:\s*(.+)$', header, re.I)
    if mp:
        block["prompt"] = _inline(mp.group(1).strip())
    while i < len(lines):
        s = lines[i].strip()
        if FENCE_BOUNDARY_RE.match(s):       # unclosed fence: stop at the next marker
            break
        if FENCE_RE.match(s):
            i += 1
            break
        if not s:
            i += 1
            continue
        mpr = re.match(r'pair:\s*(.+?)\s*(?:->|=>|»)\s*(.+)$', s, re.I)
        if mpr:
            pid = "p" + str(len(block["pairs"]) + 1)
            block["pairs"].append({"id": pid, "left": _inline(mpr.group(1).strip()),
                                   "right": _inline(mpr.group(2).strip())})
        i += 1
    return block, i


def _parse_sequence(lines, i):
    """`*Sequence:* [prompt: ...]` then `step: <text>` lines IN CORRECT ORDER, lone `:::` closes.

    M12 — the authoring order IS the correct order. The learner assigns each step its
    position (1..N); scored with PARTIAL credit (per step). Mirrors _parse_matching."""
    header = SEQUENCE_RE.match(lines[i].strip()).group(1)
    i += 1
    block = {"type": "sequence", "steps": []}
    mp = re.search(r'prompt:\s*(.+)$', header, re.I)
    if mp:
        block["prompt"] = _inline(mp.group(1).strip())
    while i < len(lines):
        s = lines[i].strip()
        if FENCE_BOUNDARY_RE.match(s):
            break
        if FENCE_RE.match(s):
            i += 1
            break
        if not s:
            i += 1
            continue
        mst = re.match(r'step:\s*(.+)$', s, re.I)
        if mst:
            sid = "s" + str(len(block["steps"]) + 1)
            block["steps"].append({"id": sid, "html": _inline(mst.group(1).strip())})
        i += 1
    return block, i


def _parse_fillblank(lines, i):
    """`*FillBlank:* [prompt: ...]` then `blank: <text with ___> -> <answer> | <alt>` lines.

    M12 — `___` marks where the text input goes (if absent, the input follows the text).
    Answers after `->` are an accept-list (pipe-separated); matching is lenient (trim /
    collapse whitespace / case-insensitive), applied in the player. Mirrors _parse_matching."""
    header = FILLBLANK_RE.match(lines[i].strip()).group(1)
    i += 1
    block = {"type": "fillBlank", "blanks": []}
    mp = re.search(r'prompt:\s*(.+)$', header, re.I)
    if mp:
        block["prompt"] = _inline(mp.group(1).strip())
    while i < len(lines):
        s = lines[i].strip()
        if FENCE_BOUNDARY_RE.match(s):
            break
        if FENCE_RE.match(s):
            i += 1
            break
        if not s:
            i += 1
            continue
        mbl = re.match(r'blank:\s*(.+?)\s*(?:->|=>|»)\s*(.+)$', s, re.I)
        if mbl:
            text = mbl.group(1).strip()
            answers = [a.strip() for a in mbl.group(2).split("|") if a.strip()]
            bid = "f" + str(len(block["blanks"]) + 1)
            if "___" in text:
                before, _sep, after = text.partition("___")
                blank = {"id": bid, "before": _inline(before.strip()),
                         "after": _inline(after.strip()), "answers": answers}
            else:
                blank = {"id": bid, "before": _inline(text), "after": "", "answers": answers}
            block["blanks"].append(blank)
        i += 1
    return block, i


def _parse_bank(lines, i):
    """`*Bank:* [draw N]` opens a question POOL; children are ordinary question blocks
    parsed by the EXISTING parsers (KC via `_knowledge_check`; matching/sequence/fill via
    their `_parse_*`, each self-closing on its own `:::`). A KC child runs to the next
    child marker/boundary. The bank ends at `*Bank:* end`, a lone `:::`, or a slide/section
    boundary. `draw` absent → draw the whole pool (no randomization). The player draws N at
    runtime (C5); this parser just collects the pool."""
    header = QUESTIONBANK_RE.match(lines[i].strip()).group(1)
    i += 1
    md = re.search(r'draw\s+(\d+)', header, re.I)
    draw = int(md.group(1)) if md else None
    questions = []
    n = len(lines)

    def _is_child_start(s):
        return bool(MATCHING_RE.match(s) or SEQUENCE_RE.match(s)
                    or FILLBLANK_RE.match(s) or re.match(r'\*Question:\*', s, re.I))

    while i < n:
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if FENCE_BOUNDARY_RE.match(s):
            break                                  # slide/section boundary: don't consume
        if QUESTIONBANK_END_RE.match(s) or FENCE_RE.match(s):
            i += 1                                 # `*Bank:* end` / lone `:::` closes the bank
            break
        if MATCHING_RE.match(s):
            block, i = _parse_matching(lines, i); questions.append(block); continue
        if SEQUENCE_RE.match(s):
            block, i = _parse_sequence(lines, i); questions.append(block); continue
        if FILLBLANK_RE.match(s):
            block, i = _parse_fillblank(lines, i); questions.append(block); continue
        if re.match(r'\*Question:\*', s, re.I):
            j = i + 1
            while j < n:
                sj = lines[j].strip()
                if (FENCE_BOUNDARY_RE.match(sj) or QUESTIONBANK_END_RE.match(sj)
                        or FENCE_RE.match(sj) or _is_child_start(sj)):
                    break
                j += 1
            kc = _knowledge_check("\n".join(lines[i:j]))
            if kc.get("options"):
                questions.append(kc)
            i = j
            continue
        i += 1                                     # skip stray prose inside the bank
    if draw is None:
        draw = len(questions)
    return {"type": "questionBank", "draw": draw, "questions": questions}, i


def _parse_timeline(lines, i):
    """`*Timeline:*` then `::: milestone` (phase:/title:/body:/accent:) groups, lone `:::` closes.

    Renders as a vertical roadmap (HTML parity with the timeline slide layout). accent is a brand
    role (primary|secondary|tertiary|dark); omit to auto-cycle.
    """
    i += 1
    groups, i = _read_fences(lines, i)
    milestones = []
    for g in groups:
        m = {}
        if g.get("phase"):
            m["phase"] = g["phase"]
        if g.get("title"):
            m["title"] = _inline(g["title"])
        if g.get("body"):
            m["html"] = "<p>" + _inline(g["body"]) + "</p>"
        if g.get("accent"):
            m["accent"] = g["accent"].lower()
        milestones.append(m)
    return {"type": "timeline", "milestones": milestones}, i


def _parse_comparison(lines, i):
    """`*Comparison:*` then `::: panel` groups; inside each, `heading:`/`sublabel:`/`accent:`/`callout:`
    lines plus `- bullet` item lines. A lone `:::` closes the block. 2-3 panels (old-vs-new / A/B/C).
    """
    i += 1
    panels, cur = [], None
    while i < len(lines):
        s = lines[i].strip()
        if FENCE_BOUNDARY_RE.match(s):       # unclosed fence: stop at the next marker, don't consume it
            break
        fm = FENCE_RE.match(s)
        if fm:
            if fm.group(1) is None:          # lone ::: closes the block
                i += 1
                break
            cur = {"items": []}              # a named fence (::: panel) starts a new panel
            panels.append(cur)
            i += 1
            continue
        if cur is not None and s:
            mb = re.match(r'^[-*]\s+(.*)', s)
            if mb:
                cur["items"].append(_inline(mb.group(1).strip()))
            elif ':' in s:
                k, v = s.split(':', 1)
                k, v = k.strip().lower(), v.strip()
                if k in ("heading", "callout"):
                    cur[k] = _inline(v)
                elif k in ("sublabel", "accent"):
                    cur[k] = v
        i += 1
    out = []
    for p in panels:
        panel = {}
        for k in ("heading", "sublabel", "callout"):
            if p.get(k):
                panel[k] = p[k]
        if p.get("accent"):
            panel["accent"] = p["accent"].lower()
        if p.get("items"):
            panel["items"] = p["items"]
        out.append(panel)
    return {"type": "comparison", "panels": out}, i


def _parse_scenario(lines, i):
    """`*Scenario:*` then `::: scene` groups. Inside each scene:
        id: <scene id>                  (optional; the target name a `· goto:` points at)
        title: <scene title>            (optional)
        <prose lines>                   the scene narrative (the decision prompt)
        - <response> [· preferred] [· goto: <scene-id>] [· feedback: <text>]   (one per choice)
    A lone `:::` closes the block.

    TWO modes, decided purely by whether any choice carries a `· goto:` target:
      * NO targets → a LINEAR decision walk-through: every scene shown at once and
        the `preferred` choice marked (the original linear-fallback renderer,
        byte-identical). For practice, mark exactly ONE preferred response per scene.
      * ANY target → TRUE branching (M14): the player shows one scene at a time and a
        choice routes to its `goto` scene. `id:` names a scene so a `goto` can reach it.
    """
    i += 1
    scenes, narr = [], []
    cur = None

    def _flush():
        # fold accumulated narrative prose into the current scene's html column
        if cur is not None and narr:
            cur["html"] = cur.get("html", "") + "<p>" + _inline(" ".join(narr)) + "</p>"
        narr.clear()

    while i < len(lines):
        s = lines[i].strip()
        if FENCE_BOUNDARY_RE.match(s):           # unclosed fence: stop at the next marker
            break
        fm = FENCE_RE.match(s)
        if fm:
            _flush()
            if fm.group(1) is None:              # lone ::: closes the block
                i += 1
                break
            cur = {"responses": []}              # ::: scene starts a new scene
            scenes.append(cur)
            i += 1
            continue
        if cur is None or not s:
            i += 1
            continue
        mb = re.match(r'^[-*]\s+(.*)', s)
        if mb:
            _flush()                             # a choice line ends the narrative run
            raw = mb.group(1)
            # feedback: is TERMINAL — capture everything after the first `· feedback:`
            # verbatim so the `·`/`|` chars the grammar uses elsewhere don't split the
            # remediation prose away (A3). Only the head (response text + flags) is _segs'd.
            mfb = re.search(r'[·|]\s*feedback\s*:\s*(.+)$', raw, re.I)
            head = raw[:mfb.start()] if mfb else raw
            segs = _segs(head)
            resp = {"html": "<p>" + _inline(segs[0] if segs else "") + "</p>"}
            for seg in segs[1:]:
                if re.match(r'(?:preferred|correct|best)$', seg, re.I):
                    resp["preferred"] = True
                else:
                    # `goto: <scene-id>` routes this choice to a named scene (M14
                    # branching). Slugged so `Escalate Now` and `escalate-now` match.
                    mg = re.match(r'(?:goto|target|to)\s*:\s*(.+)$', seg, re.I)
                    if mg:
                        resp["goto"] = _scene_slug(mg.group(1))
            if mfb:
                resp["feedback"] = "<p>" + _inline(mfb.group(1).strip()) + "</p>"
            cur["responses"].append(resp)
        elif re.match(r'^id\s*:', s, re.I):
            _flush()
            cur["id"] = _scene_slug(s.split(':', 1)[1])
        elif re.match(r'^title\s*:', s, re.I):
            _flush()
            cur["title"] = _inline(s.split(':', 1)[1].strip())
        else:
            narr.append(s)
        i += 1
    _flush()
    out = []
    for sc in scenes:
        scene = {}
        if sc.get("id"):
            scene["id"] = sc["id"]
        if sc.get("title"):
            scene["title"] = sc["title"]
        if sc.get("html"):
            scene["html"] = sc["html"]
        if sc.get("responses"):
            scene["responses"] = sc["responses"]
        out.append(scene)
    return {"type": "scenario", "scenes": out}, i


def _parse_reflection(lines, i):
    """`*Reflection:* <prompt>` then optional `model:` / `criteria:` lines; a lone `:::`
    (or the next marker) closes the block.

        *Reflection:* <the reflective question / prompt>
        <more prompt prose>            (optional; appended to the prompt)
        model: <a strong example answer the learner self-checks against>
        criteria: <one rubric point a good answer includes>
        criteria: <another rubric point>
        :::

    A free-text / open-response block: at runtime the learner types into a textarea,
    submits, then the model answer + criteria REVEAL for self-assessment. It is
    NON-GRADED — completion-only. There is no runtime AI scorer (a published SCORM
    package runs offline); the `model:` answer and `criteria:` are authored at build
    time (the LLM writes them from the course content), so the learner has something
    concrete to compare their own response against.

    The prompt may be given on the header line and/or as plain prose lines before the
    first `model:`/`criteria:`. `model:` accumulates multi-line prose; `criteria:`
    lines each become one rubric bullet.
    """
    prompt = [(REFLECTION_RE.match(lines[i].strip()).group(1) or "").strip()]
    i += 1
    model, criteria = [], []
    while i < len(lines):
        s = lines[i].strip()
        if FENCE_BOUNDARY_RE.match(s):           # unclosed fence: stop at the next marker
            break
        fm = FENCE_RE.match(s)
        if fm:
            i += 1
            if fm.group(1) is None:              # a lone ::: closes the block
                break
            continue                             # ignore a stray "::: name" opener
        mm = re.match(r'^model\s*:\s*(.*)$', s, re.I)
        if mm:
            model.append(mm.group(1).strip())
            i += 1
            continue
        mc = re.match(r'^(?:criteri(?:on|a)|rubric)\s*:\s*(.*)$', s, re.I)
        if mc:
            if mc.group(1).strip():
                criteria.append(mc.group(1).strip())
            i += 1
            continue
        if s and model:                          # prose after model: continues the answer
            model.append(s)
        elif s:                                  # prose before any key extends the prompt
            prompt.append(s)
        i += 1
    block = {"type": "reflection"}
    ptxt = " ".join(p for p in prompt if p).strip()
    if ptxt:
        block["prompt"] = "<p>" + _inline(ptxt) + "</p>"
    mtxt = " ".join(m for m in model if m).strip()
    if mtxt:
        block["model"] = "<p>" + _inline(mtxt) + "</p>"
    if criteria:
        block["criteria"] = [_inline(c) for c in criteria]
    return block, i


def _parse_objectives(lines, i):
    """`*Objectives:* [intro line]` then `- ` bullets (the learner-facing outcomes),
    one per line, until a blank line / the next marker. The text after the marker is an
    optional lead-in (defaults to 'After this lesson, you will be able to:'). Produces a
    semantic `objectives` block so Slide-1 objectives are first-class, not a plain list.
    """
    intro = (OBJECTIVES_RE.match(lines[i].strip()).group(1) or "").strip()
    i += 1
    items = []
    while i < len(lines):
        s = lines[i].strip()
        if not s or FENCE_BOUNDARY_RE.match(s):
            break
        mb = re.match(r'^[-*]\s+(.*)', s)
        if mb:
            items.append(_inline(mb.group(1).strip()))
            i += 1
            continue
        mnum = re.match(r'^\d+\.\s+(.*)', s)
        if mnum:
            items.append(_inline(mnum.group(1).strip()))
            i += 1
            continue
        break                                  # a non-list line ends the objectives block
    block = {"type": "objectives", "items": items}
    if intro:
        block["intro"] = _inline(intro)
    return block, i


def _ig_split_item(raw):
    """A left-column bullet `bold — detail` -> ["bold", " — detail"] (slide-schema pair).
    No em dash -> a plain string. Matches the 'infographic' slide content shape."""
    raw = raw.strip()
    m = re.match(r'^(.*?)\s*[—–-]\s+(.*)$', raw)
    if m:
        return [_inline(m.group(1).strip()), " — " + _inline(m.group(2).strip())]
    return _inline(raw)


def _parse_infographic(lines, i):
    """`*Infographic:* <title>` then top-level `subtitle:`/`footer:` lines and flat fences:
      `::: left`   heading:/intro:/callout: + `- bold — detail` bullets
      `::: right`  heading:/sublabel:
      `::: card`   num:/title:/body:/accent:        (one per framework card, repeatable)
      `::: goals`  label:                            (the goals-strip label)
      `::: goal`   title:/body:/accent:              (one per goal, repeatable)
    A lone `:::` closes the whole block. Produces b["infographic"] == the slide content schema,
    so one JSON serves both the slide generator and this course block.
    """
    title = (INFOGRAPHIC_RE.match(lines[i].strip()).group(1) or "").strip()
    i += 1
    ig = {}
    if title:
        ig["title"] = _inline(title)
    left, right, cards, goals_items, goals_label = {"items": []}, {}, [], [], None
    mode, cur, seen_fence = None, None, False        # mode: None|left|right|card|goals|goal
    # the block ends at the next slide/meta/unit marker — supports BOTH a single terminal `:::`
    # and a `:::` after every fence (whichever the author writes). Shared with the other
    # fenced parsers as FENCE_BOUNDARY_RE so the unclosed-fence behavior is identical.
    end_re = FENCE_BOUNDARY_RE
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        fm = FENCE_RE.match(s)
        if fm:
            if fm.group(1) is None:                  # lone ::: closes the CURRENT fence
                mode, cur = None, None
                i += 1
                continue
            seen_fence = True
            tag = fm.group(1).lower()
            if tag == "left":
                mode, cur = "left", None
            elif tag == "right":
                mode, cur = "right", None
            elif tag == "card":
                cur = {}; cards.append(cur); mode = "card"
            elif tag in ("goals", "goalstrip"):
                mode, cur = "goals", None
            elif tag == "goal":
                cur = {}; goals_items.append(cur); mode = "goal"
            else:
                mode, cur = None, None
            i += 1
            continue
        if end_re.match(s):                          # next block/slide/meta — stop, don't consume
            break
        if mode is None:
            if not seen_fence:                       # top-level keys before any fence
                if ':' in s:
                    k, v = s.split(':', 1)
                    k = k.strip().lower()
                    if k in ("subtitle", "footer"):
                        ig[k] = _inline(v.strip())
                i += 1
                continue
            break                                    # content after the fences closed → block ends
        mb = re.match(r'^[-*]\s+(.*)', s)
        if mb and mode == "left":
            left["items"].append(_ig_split_item(mb.group(1)))
        elif ':' in s:
            k, v = s.split(':', 1)
            k, v = k.strip().lower(), v.strip()
            if mode == "left" and k in ("heading", "intro", "callout"):
                left[k] = v if k == "heading" else _inline(v)
            elif mode == "right" and k in ("heading", "sublabel"):
                right[k] = v
            elif mode == "card" and cur is not None and k in ("num", "accent", "title", "body"):
                cur[k] = _inline(v) if k in ("title", "body") else v
            elif mode == "goals" and k == "label":
                goals_label = v
            elif mode == "goal" and cur is not None and k in ("accent", "title", "body"):
                cur[k] = _inline(v) if k in ("title", "body") else v
        i += 1
    if left.get("heading") or left.get("intro") or left.get("callout") or left["items"]:
        if not left["items"]:
            left.pop("items")
        ig["left"] = left
    if right:
        if cards:
            right["cards"] = cards
        ig["right"] = right
    elif cards:
        ig["right"] = {"cards": cards}
    if goals_label or goals_items:
        g = {}
        if goals_label:
            g["label"] = goals_label.split("|") if "|" in goals_label else goals_label.split()
        if goals_items:
            g["items"] = goals_items
        ig["goals"] = g
    return {"type": "infographic", "infographic": ig}, i


def _chart_num(x):
    """Parse one data cell to a number (or None for a missing/blank value).
    Tolerates a stray %, a leading $, and surrounding spaces; NO thousands separators
    (comma is the value delimiter), so write 1200 not 1,200."""
    x = (x or "").strip().lstrip("$").rstrip("%").strip()
    if x == "" or x.lower() in ("null", "na", "n/a", "-", "—"):
        return None
    try:
        return int(x) if re.fullmatch(r"-?\d+", x) else float(x)
    except ValueError:
        return None


def _parse_chart(lines, i):
    """`*Chart:* <bar|line|area|pie|donut|stackedBar|groupedBar|horizontalBar|horizontalStackedBar>` then `key: value` lines until a
    blank line. Keys: `categories:` (comma-separated labels), `series:` (repeatable —
    `Name = v1, v2, ...` or just `v1, v2, ...` for one unnamed series), `title:`,
    `xLabel:`, `yLabel:`, `source:`, `takeaway:`.

    `takeaway:` is an OPTIONAL one-line plain-language insight (the "so what")
    rendered with the chart. `source:` is the no-invented-metrics guardrail — the renderer shows it and the
    AI-generation lint rejects a chart that lacks one. Values use NO thousands
    separators (comma is the delimiter); use `null` for a missing data point.
    """
    m = CHART_RE.match(lines[i].strip())
    raw = (m.group(1) or "bar").strip()
    ctype = _CHART_ALIASES.get(raw.lower(), raw or "bar")
    i += 1
    block = {"type": "chart", "chart": ctype, "categories": [], "series": []}
    while i < len(lines):
        s = lines[i].strip()
        if FENCE_BOUNDARY_RE.match(s):       # unclosed keyed block: stop at the next marker (e.g. **Articulate:)
            break
        if not s:
            i += 1
            break
        if ':' not in s:
            break
        k, _, v = s.partition(':')
        k, v = k.strip().lower(), v.strip()
        if k == "categories":
            block["categories"] = [c.strip() for c in v.split(',') if c.strip()]
        elif k == "series":
            name, sep, nums = v.partition('=')
            if not sep:                       # no "Name =" -> a single unnamed series
                name, nums = "", v
            block["series"].append({"name": name.strip(),
                                    "data": [_chart_num(x) for x in nums.split(',')]})
        elif k in ("xlabel", "x"):
            block["xLabel"] = _inline(v)
        elif k in ("ylabel", "y"):
            block["yLabel"] = _inline(v)
        elif k == "title":
            block["title"] = _inline(v)
        elif k == "source":
            block["source"] = _inline(v)
        elif k == "takeaway":
            block["takeaway"] = _inline(v)
        i += 1
    return block, i


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
        mq = QUOTE_RE.match(s)
        if mq:
            flush_para(); flush_lst()
            blocks.append(_quote_block(mq.group(1))); i += 1; continue
        if ACCORDION_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_accordion(lines, i, "accordion"); blocks.append(block); continue
        if PROCESS_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_accordion(lines, i, "process"); blocks.append(block); continue
        if FLASHCARD_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_flashcard(lines, i); blocks.append(block); continue
        if CATEGORIZE_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_categorize(lines, i); blocks.append(block); continue
        if DRAGDROP_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_dragDrop(lines, i); blocks.append(block); continue
        if WORDSEARCH_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_wordSearch(lines, i); blocks.append(block); continue
        if CROSSWORD_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_crossword(lines, i); blocks.append(block); continue
        if GAMESHOW_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_gameShow(lines, i); blocks.append(block); continue
        if QUIZBOARD_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_quizBoard(lines, i); blocks.append(block); continue
        if SPEEDSTREAK_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_speedStreak(lines, i); blocks.append(block); continue
        if QUESTIONBANK_RE.match(s) and not QUESTIONBANK_END_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_bank(lines, i); blocks.append(block); continue
        if MATCHING_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_matching(lines, i); blocks.append(block); continue
        if SEQUENCE_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_sequence(lines, i); blocks.append(block); continue
        if FILLBLANK_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_fillblank(lines, i); blocks.append(block); continue
        if TIMELINE_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_timeline(lines, i); blocks.append(block); continue
        if COMPARISON_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_comparison(lines, i); blocks.append(block); continue
        if CHART_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_chart(lines, i); blocks.append(block); continue
        if INFOGRAPHIC_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_infographic(lines, i); blocks.append(block); continue
        if OBJECTIVES_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_objectives(lines, i); blocks.append(block); continue
        if SCENARIO_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_scenario(lines, i); blocks.append(block); continue
        if REFLECTION_RE.match(s):
            flush_para(); flush_lst()
            block, i = _parse_reflection(lines, i); blocks.append(block); continue
        mcont = CONTINUE_RE.match(s)
        if mcont:
            flush_para(); flush_lst()
            label = mcont.group(1).strip()
            blocks.append({"type": "continue", "text": label or "CONTINUE"}); i += 1; continue
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

    Only the prose blocks the text column can actually render (paragraph/list/table —
    everything `_block_inner_html` serializes) are absorbed; ANY other block type ends
    the run and stands on its own. This is an allowlist on purpose: a denylist silently
    swallowed structured blocks (accordion/process/comparison/timeline/infographic/
    chart/categorize/flashcard/…) that followed a `side:` visual, because the serializer
    returns "" for them. Allowlisting keeps every current and future block type safe by
    default.
    """
    ABSORB = {"paragraph", "list", "table"}
    out, i = [], 0
    while i < len(blocks):
        b = blocks[i]
        if b.get("type") == "imageText" and b.pop("_mergeText", False):
            parts, j = [], i + 1
            while j < len(blocks) and blocks[j].get("type") in ABSORB:
                parts.append(_block_inner_html(blocks[j])); j += 1
            b["html"] = "".join(p for p in parts if p)
            out.append(b); i = j
        else:
            out.append(b); i += 1
    return out


def _kc_answer_letters(body, letters):
    """The correct-answer letters from a `*Correct Answer:*` line, matched against the
    option letters. Accepts ONE letter (`C`) or SEVERAL (`A, C` / `A and C` / `A/C`) —
    more than one ⇒ a MULTI-select check ('choose all that apply').

    Tokenizes the RHS left-to-right and keeps only single A–Z labels. The FIRST
    non-label prose token ENDS the answer list, so a stray letter sitting *after*
    prose (`A, C and also note B`) can't leak in as a third answer — that pattern
    silently mis-scores graded quizzes; `kc_answer_issues_in` raises it in lint().
    Returns an ordered, de-duplicated list of in-range letters."""
    m = re.search(r'\*Correct Answer:\*\s*(.+)', body)
    if not m:
        return []
    out, seen = [], set()
    for tk in re.split(r'[,\s/&]+|\band\b', m.group(1), flags=re.I):
        tk = tk.strip().rstrip(".)").upper()
        if not tk:
            continue  # separator collapse (`A and C` → ['A','','','C']) — skip, keep scanning
        if len(tk) == 1 and tk.isalpha() and tk in letters:
            if tk not in seen:
                seen.add(tk); out.append(tk)
        else:
            break  # first prose / out-of-range token ends the list (no leak past it)
    return out


def _knowledge_check(body):
    q = re.search(r'\*Question:\*\s*(.+)', body)
    # accept `- A)`, `- a.`, `- B)` ... (letter + `.` or `)`); capture the letter so
    # the correct answer is matched by LETTER, not by blind position. Out-of-range or
    # missing answers leave NO option correct -> authoring.lint() flags it (no silent mis-score).
    pairs = re.findall(r'^\s*-\s*([A-Za-z])[.)]\s*(.+)$', body, re.M)
    letters = [p[0].upper() for p in pairs]
    opts = [p[1] for p in pairs]
    # one correct letter = single-select; several (`A, C`) = multi-select ('all that apply').
    ans_letters = _kc_answer_letters(body, letters)
    correct = {letters.index(a) for a in ans_letters}
    multi = len(ans_letters) > 1
    fb = re.search(r'\*Feedback\s*[—–-]\s*Correct:\*\s*(.+)', body)
    fbno = re.search(r'\*Feedback\s*[—–-]\s*Incorrect:\*\s*(.+)', body)
    return {
        "type": "knowledgeCheck", "multi": multi,
        "prompt": _inline(q.group(1)) if q else "",
        "options": [{"html": _inline(o), "correct": i in correct} for i, o in enumerate(opts)],
        "feedback": _inline(fb.group(1)) if fb else "",
        "feedbackIncorrect": _inline(fbno.group(1)) if fbno else "",
    }


def _kc_answer_has_leak(rhs, letters):
    """True when a valid option label appears AFTER non-label prose on a
    `*Correct Answer:*` RHS (e.g. `A, C and also note B`). The parser drops the
    trailing label; lint surfaces it so a silently mis-scored quiz is caught.
    Benign trailing prose with no later label (`B is the right one`) is NOT a leak."""
    seen_prose = False
    for tk in re.split(r'[,\s/&]+|\band\b', rhs, flags=re.I):
        tk = tk.strip().rstrip(".)").upper()
        if not tk:
            continue
        is_label = len(tk) == 1 and tk.isalpha() and tk in letters
        if is_label and seen_prose:
            return True
        if not is_label:
            seen_prose = True
    return False


def kc_answer_issues_in(md_text):
    """Lint helper. Re-scans raw §8 text for knowledge-check answer-line faults the
    parser silently absorbs, tagged by unit number:
      (A1) a letter label AFTER prose on `*Correct Answer:*` — dropped, likely a
           mis-scored answer the author meant to mark correct;
      (A2) duplicate option labels — `*Correct Answer:*` maps to the FIRST match
           only, so the wrong option can be scored correct with no crash.
    Returns a list of human-readable messages (empty when clean)."""
    issues = []
    secs = re.split(r'^##\s+Microlearning\s+', md_text, flags=re.M)
    for k in range(1, len(secs)):
        _head, _nl, rest = secs[k].partition('\n')
        rest = META_CUT.split(rest)[0]
        parts = SLIDE_RE.split(rest)
        for i in range(1, len(parts), 2):
            s_body = META_CUT.split(parts[i + 1])[0] if i + 1 < len(parts) else ""
            if not re.search(r'\*Question:\*', s_body):
                continue
            letters = [m.group(1).upper()
                       for m in re.finditer(r'^\s*-\s*([A-Za-z])[.)]\s*.+$', s_body, re.M)]
            if not letters:
                continue
            dups = sorted({l for l in letters if letters.count(l) > 1})
            if dups:
                issues.append(
                    f"unit {k}: a knowledge check repeats option label(s) "
                    f"{', '.join(dups)} — each `- A)` choice must have a UNIQUE letter "
                    f"(the `*Correct Answer:*` letter maps to the first match only, so a "
                    f"duplicate silently scores the wrong option)")
            ans = re.search(r'\*Correct Answer:\*\s*(.+)', s_body)
            if ans and _kc_answer_has_leak(ans.group(1), letters):
                issues.append(
                    f"unit {k}: a knowledge check's `*Correct Answer:*` line mixes answer "
                    f"letters with prose — a letter AFTER the prose was dropped and not scored. "
                    f"List only the answer letters (e.g. `A, C`).")
    return issues


def import_md(md_path, which=1, hero=None, image_dir=None):
    text = open(md_path, encoding="utf-8").read()
    # course-level `*Graded:* pass 80` directive (anywhere in the file) → scored course
    gm = re.search(r'\*Graded:\*\s*(?:pass(?:ing)?\s*)?(\d{1,3})', text, re.I)
    graded = bool(gm)
    passing = max(0, min(100, int(gm.group(1)))) if gm else 80
    # `*Retry:* N` → up to N attempts per KC before it locks + reveals (0/absent = one-shot)
    rm = re.search(r'\*Retry:\*\s*(\d+)', text, re.I)
    retry = int(rm.group(1)) if rm else 0
    # `*Gate:* on|off` (M13) → does a FAILING score block completion? Default: graded
    # courses gate (byte-identical to prior behavior — a failing learner is offered a
    # retry, not marked complete); an author can turn it off so an informational course
    # completes regardless of quiz score. A build can also force it off (--no-gate).
    gm2 = re.search(r'\*Gate:\*\s*(on|off|yes|no|true|false)', text, re.I)
    gate = (gm2.group(1).lower() in ("on", "yes", "true")) if gm2 else True
    # `*Preset:* <key>` (C19) — the course PURPOSE preset (compliance/onboarding/
    # product-skill/refresher/standard). Sets the audience READING-LEVEL band the build
    # report flags against; also the natural home for the generation-time voice profile.
    pm = re.search(r'\*Preset:\*\s*([a-z][a-z\-]*)', text, re.I)
    preset = pm.group(1).lower() if pm else None
    # `*Points:* on` (gamification #3) — opt-in points/XP MOTIVATIONAL overlay. Purely
    # cosmetic (never affects the graded score, the completion gate, or the LMS score):
    # each scorable block auto-earns points weighted by category (check/question/game),
    # partial-credit blocks pro-rata, and a running total drives a level TIER in the HUD.
    # Optional weight overrides ride the same line: `*Points:* on check=10 question=15 game=25`.
    # Absent (or `off`) → no overlay, byte-identical output.
    xp = None
    xm = re.search(r'\*Points:\*\s*(on|off|yes|no|true|false)([^\n]*)', text, re.I)
    if xm and xm.group(1).lower() in ("on", "yes", "true"):
        weights = {"check": 10, "question": 15, "game": 20}
        for cat, val in re.findall(r'(check|question|game)\s*=\s*(\d+)', xm.group(2), re.I):
            weights[cat.lower()] = int(val)
        xp = {"weights": weights,
              "tiers": [["Novice", 0.0], ["Proficient", 0.5], ["Skilled", 0.8], ["Expert", 1.0]]}
    # `*Celebrate:* on` (gamification #6) — opt-in CONFETTI celebration overlay. Purely
    # cosmetic (never affects the score, the gate, or the LMS record): a zero-dependency
    # canvas burst fires on the enabled moments — a graded-quiz PASS, an XP LEVEL-UP, and/or
    # COURSE COMPLETION. Like *Points:* it's a COURSE-LEVEL directive, NOT a block type.
    # `*Celebrate:* on` turns on all three; tune per-trigger with `pass=/level=/complete=`
    # (e.g. `*Celebrate:* on level=off`). Honors prefers-reduced-motion at play time. Absent
    # (or `off`) → no overlay, byte-identical output. Alias: `*Confetti:*`.
    celebrate = None
    cm = re.search(r'\*(?:Celebrate|Confetti):\*\s*(on|off|yes|no|true|false)([^\n]*)', text, re.I)
    if cm and cm.group(1).lower() in ("on", "yes", "true"):
        trig = {"pass": True, "level": True, "complete": True}
        for k, val in re.findall(r'(pass|level|complete)\s*=\s*(on|off|yes|no|true|false)', cm.group(2), re.I):
            trig[k.lower()] = val.lower() in ("on", "yes", "true")
        celebrate = trig
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
    objectives = []      # M13 — ordered, unique graded sections (subscore objectives)
    obj_index = {}       # objective id → the objectives[] entry (dedupe by section name)

    def _register_objective(sb):
        # M13/M12 — a graded section names a scored OBJECTIVE; blocks sharing a name (KCs +
        # M12 matching/sequencing/fill) roll up into ONE subscore, deduped by slug. Returns
        # the objective id so the caller can tag the block's "objective". Only call when the
        # course is graded AND the section is graded.
        oname = sb.get("name") or sb.get("color", "green").title()
        oid = slugify(oname)
        existing = obj_index.get(oid)
        if existing is None:
            obj_index[oid] = {"id": oid, "name": oname, "pass": sb.get("pass")}
            objectives.append(obj_index[oid])
        elif sb.get("pass") is not None and existing.get("pass") is None:
            existing["pass"] = sb.get("pass")
        return oid
    for i in range(1, len(parts), 2):
        s_title = parts[i].strip()
        s_body = META_CUT.split(parts[i + 1])[0].strip() if i + 1 < len(parts) else ""
        # C5 — a `*Bank:*` body carries its own `*Question:*` children; it must NOT trip the
        # single-KC slide path (which would consume the whole slide as one KC and drop the
        # bank). Route bank slides to _body_blocks, where _parse_bank handles them.
        has_bank = bool(re.search(r'^\*(?:Bank|QuestionBank):\*', s_body, re.I | re.M))
        if not has_bank and ("knowledge check" in s_title.lower() or re.search(r'\*Question:\*', s_body)):
            kc = _knowledge_check(s_body)
            if kc["options"]:
                kc_n += 1
                kc["id"] = f"kc{kc_n}"
                # honor a `*Section:* <color>` wrapping the KC (the KC path skips _body_blocks)
                msec = SECTION_RE.search(s_body)
                sec_start = None
                if msec:
                    sb = _section_block(msec.group(1))
                    if sb.get("type") == "sectionStart":
                        sec_start = sb
                        # M13 — a graded section names a scored OBJECTIVE; KCs that share a
                        # name roll up into one subscore. Tag this KC + register the objective.
                        # Only in a graded course — in an ungraded one a named section is inert
                        # (and lint flags a `pass` threshold as needing `*Graded:*`).
                        if graded and sb.get("graded"):
                            kc["objective"] = _register_objective(sb)
                if sec_start:
                    blocks.append(sec_start)
                blocks.append({"type": "heading", "level": 2, "html": "<p>Check Your Understanding</p>"})
                blocks.append(kc)
                if sec_start:
                    blocks.append({"type": "sectionEnd"})
            continue
        blocks.append({"type": "heading", "level": 2, "html": f"<p>{_inline(s_title)}</p>"})
        body = _body_blocks(s_body)
        # M12→M13 — a matching/sequencing/fill block inside a GRADED *Section:* rolls up into
        # that section's subscore (SECTION-TAGGED ONLY: an inline block stays formative). Walk
        # the section spans this slide produced; only tag inside a graded band, mirroring the KC
        # path's `graded and sb.get("graded")` guard (a named section in an ungraded course is inert).
        if graded:
            cur_obj = None
            for bb in body:
                bt = bb.get("type")
                if bt == "sectionStart":
                    cur_obj = _register_objective(bb) if bb.get("graded") else None
                elif bt == "sectionEnd":
                    cur_obj = None
                elif cur_obj and bt in ("matching", "sequence", "fillBlank", "dragDrop", "wordSearch", "crossword", "gameShow", "quizBoard", "speedStreak"):
                    bb["objective"] = cur_obj
                elif cur_obj and bt == "questionBank":
                    # C5 — a bank in a graded section is summative; every drawn child rolls
                    # into the section subscore, so tag the bank AND each pooled question.
                    bb["objective"] = cur_obj
                    for q in bb.get("questions", []):
                        q["objective"] = cur_obj
        blocks.extend(body)

    # Gated reveals: a `*Continue:*` gate hides everything AFTER it until the learner
    # clicks it (progressive reveal). Mirror the docx importer (docx_import.py): walk
    # the unit's blocks; a `continue` is itself ungated (it IS the reveal trigger) and
    # flips every following block to gated. No continue → every block ungated as before.
    gated = False
    for b in blocks:
        if b.get("type") == "continue":
            b["gated"] = False
            gated = True
        else:
            b["gated"] = gated

    import os
    from buildlog import get_logger
    _log = get_logger(__name__)
    warnings = []                      # operator-facing silent-drop notices → _stats
    used = {}
    cand = ({n.lower(): n for n in os.listdir(image_dir)}
            if image_dir and os.path.isdir(image_dir) else {})

    # resolve *Visual:* slot directives against the labelled-asset folder
    for b in blocks:
        slot = b.pop("_slot", None)
        if slot:
            actual = cand.get(slot.lower())
            if actual:
                used["assets/" + actual] = os.path.join(image_dir, actual)
                b["src"] = "assets/" + actual
            elif image_dir:
                # An images folder WAS provided but no file matches this slot, so the
                # asset doesn't exist — don't ship a broken <img>. Blank the src; the
                # render layer drops the image and keeps the text. This is a SILENT
                # drop for the operator, so record + log it (build report C1).
                b["src"] = ""
                msg = (f"visual slot “{slot}” has no matching file in the images "
                       f"folder — the image was dropped (text kept)")
                warnings.append(msg)
                _log.warning("%s", msg)
            # else (no image_dir): src stays assets/<slot> — asset supplied later (§10)

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
    # interactive-block entry media (accordion/process/flashcard)
    for b in blocks:
        for e in b.get("entries", []) or []:
            for key in ("src", "frontSrc", "backSrc"):
                if e.get(key):
                    _resolve(e, key)

    hero_block = None
    if hero and image_dir:
        actual = cand.get(hero.lower())
        if actual:
            used["assets/" + actual] = os.path.join(image_dir, actual)
            hero_block = {"image": "assets/" + actual, "title": title, "subtitle": ""}

    ir = {"schema": "course-ir/v1", "id": slugify(title), "title": title,
          "locale": "en", "accent": None, "hero": hero_block, "blocks": blocks,
          "graded": graded, "passingScore": passing, "retry": retry,
          "gateCompletion": gate, "objectives": objectives}
    if preset:
        ir["preset"] = preset          # C19 — audience band for the readability report (absent → byte-identical)
    if xp:
        ir["xp"] = xp                  # gamification #3 — points/XP overlay config (absent → byte-identical)
    if celebrate:
        ir["celebrate"] = celebrate    # gamification #6 — confetti overlay config (absent → byte-identical)
    ir["_stats"] = {"blocks": len(blocks), "assets": len(used), "warnings": warnings}
    from ir_validate import validate_ir
    validate_ir(ir, label=ir.get("id", "course"))
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
