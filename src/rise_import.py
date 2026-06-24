"""Rise published-HTML export (-raw- zip) -> Course IR + extracted assets.

Extends the runtime-data.js decoder. Maps the Rise block taxonomy onto the IR
block set (see schema/IR_SCHEMA.md). mondrian/flashcard/interactive blocks are
skipped in v1 (counted + reported), per the 2026-06-04 scope decision.
"""
import re, base64, json, zipfile, os, posixpath
from collections import Counter
from common import clean_html, plain_text, slugify, norm_name

NEUTRAL_ACCENT = "#3B82F6"  # generic fallback when no brand profile is supplied


def snap_accent(hexstr, accents, default):
    """Snap an arbitrary source accent to the nearest brand-eligible color.

    `accents` is the active brand profile's accent-eligible hex list
    (brand.json -> "accentSnap"). Empty list => no snapping; return `default`.
    """
    if not accents:
        return default
    try:
        h = (hexstr or "").lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:
        return default
    def dist(c):
        c = c.lstrip("#")
        return (int(c[0:2],16)-r)**2 + (int(c[2:4],16)-g)**2 + (int(c[4:6],16)-b)**2
    return min(accents, key=dist)


def _decode(zf):
    name = [n for n in zf.namelist() if n.endswith("runtime-data.js")][0]
    raw = zf.read(name).decode("utf-8", "replace")
    b64 = re.search(r'__jsonp\("runtime-data\.js","([A-Za-z0-9+/=]+)"', raw).group(1)
    return json.loads(base64.b64decode(b64))


def _asset_index(zf):
    """Map normalised basename -> in-zip path for everything under content/assets/."""
    idx = {}
    for n in zf.namelist():
        if "/assets/" in n and not n.endswith("/"):
            idx[norm_name(posixpath.basename(n))] = n
    return idx


def _resolve_image(media, idx):
    media = media or {}
    img = media.get("image") or media.get("tmp", {}).get("image") or {}
    cands = []
    for k in ("crushedKey", "originalUrl", "key"):
        if img.get(k):
            cands.append(img[k])
    oi = img.get("originalImage") or {}
    for k in ("crushedKey", "originalUrl", "key"):
        if oi.get(k):
            cands.append(oi[k])
    for c in cands:
        base = norm_name(posixpath.basename(c))
        if base in idx:
            return idx[base]
    return None


def _items(block):
    return block.get("items") or []


def _walk(items, out):
    for it in items or []:
        out.append(it)
        for k in ("items", "children"):
            if isinstance(it.get(k), list) and it.get("family") == "mondrian":
                _walk(it[k], out)  # flatten mondrian children only


def _resolve_named(fname, idx):
    """Resolve a plain Rise asset filename (e.g. 'TMMGT-PM-06.mp4') to its in-zip path."""
    if not fname:
        return None
    base = norm_name(posixpath.basename(fname))
    return idx.get(base)


def block_to_ir(b, idx, used, stats):
    fam, var = b.get("family"), b.get("variant")
    it0 = _items(b)[0] if _items(b) else {}

    def img(rec):
        path = _resolve_image(rec.get("media"), idx)
        if path:
            used.add(path)
            return "assets/" + posixpath.basename(path)
        return None

    def named(fname):
        path = _resolve_named(fname, idx)
        if path:
            used.add(path)
            return "assets/" + posixpath.basename(path)
        return None

    if fam == "text" and var in ("heading", "subheading"):
        return {"type": "heading", "level": 2 if var == "heading" else 3,
                "html": clean_html(it0.get("heading"))}
    if fam == "text" and var in ("heading paragraph", "subheading paragraph"):
        return {"type": "headingParagraph",
                "level": 2 if var.startswith("heading") else 3,
                "headingHtml": clean_html(it0.get("heading")),
                "html": clean_html(it0.get("paragraph"))}
    if fam == "text" and var == "paragraph":
        return {"type": "paragraph", "html": clean_html(it0.get("paragraph"))}
    if fam == "text" and var == "table":
        return {"type": "table", "html": clean_html(it0.get("paragraph"))}
    if fam == "text" and var == "two column":
        return {"type": "paragraph", "html": clean_html(it0.get("paragraph") or it0.get("heading"))}

    if fam == "image" and var == "hero":
        return {"type": "image", "variant": "hero", "src": img(it0),
                "alt": plain_text(it0.get("caption")) or "",
                "html": clean_html(it0.get("paragraph"))}
    if fam == "image" and var == "full":
        return {"type": "image", "variant": "full", "src": img(it0),
                "alt": plain_text(it0.get("caption")) or "",
                "caption": plain_text(it0.get("caption"))}
    if fam == "image" and var == "text aside":
        return {"type": "imageText", "src": img(it0), "side": "left",
                "alt": plain_text(it0.get("caption")) or "",
                "html": clean_html(it0.get("paragraph"))}

    if fam == "impact" and var == "note":
        return {"type": "note", "html": clean_html(it0.get("paragraph"))}
    if fam == "impact":  # 'd' statement (and any other impact variant)
        return {"type": "statement", "html": clean_html(it0.get("paragraph"))}

    if fam == "list":
        items = [clean_html(x.get("paragraph")) for x in _items(b) if x.get("paragraph")]
        return {"type": "list", "ordered": var != "bulleted", "items": items}

    if fam == "divider":
        return {"type": "divider"}

    if fam == "continue":
        return {"type": "continue", "text": plain_text(it0.get("title")) or "CONTINUE"}

    if fam == "knowledgeCheck":
        answers = it0.get("answers") or []
        return {"type": "knowledgeCheck",
                "multi": it0.get("type") == "MULTIPLE_RESPONSE",
                "prompt": clean_html(it0.get("title")),
                "options": [{"html": clean_html(a.get("title")), "correct": bool(a.get("correct"))}
                            for a in answers],
                "feedback": clean_html(it0.get("feedback"))}

    if fam == "multimedia" and var == "video":
        media = it0.get("media") or {}
        cv = media.get("customVideo") or {}
        src = named(cv.get("src"))
        if not src:  # streamed-only (no bundled file) — don't emit a broken <video>
            stats["skipped"][f"{fam}/{var}"] += 1
            return None
        blk = {"type": "video", "mode": "file", "src": src,
               "caption": plain_text(it0.get("caption"))}
        poster = named(cv.get("poster"))
        if poster:
            blk["poster"] = poster
        capfile = cv.get("subtitle")
        if not capfile:
            caps = (media.get("video") or {}).get("captions") or []
            capfile = caps[0].get("url") if caps else None
        capsrc = named(capfile)
        if capsrc:
            blk["captions"] = capsrc
        return blk

    if fam == "image" and var == "text overlay":
        return {"type": "image", "variant": "overlay", "src": img(it0),
                "alt": plain_text(it0.get("caption")) or "",
                "html": clean_html(it0.get("caption"))}

    if fam == "quote":
        bgmedia = (it0.get("background") or {}).get("media")
        return {"type": "quote", "html": clean_html(it0.get("paragraph")),
                "attribution": clean_html(it0.get("name")),
                "src": img({"media": bgmedia}) if bgmedia else None}

    if fam == "interactive" and var == "accordion":
        return {"type": "accordion",
                "entries": [{"title": plain_text(it.get("title")),
                             "html": clean_html(it.get("description")),
                             "src": img(it)} for it in _items(b)]}

    if fam == "interactive-fullscreen" and var == "process":
        entries = []
        for it in _items(b):
            if it.get("isHidden"):
                continue
            title, body = plain_text(it.get("title")), clean_html(it.get("description"))
            if not (title or body):
                continue
            entries.append({"kind": it.get("type") or "step", "title": title,
                            "html": body, "src": img(it)})
        return {"type": "process", "entries": entries}

    if fam == "flashcard":
        entries = []
        for it in _items(b):
            fr, bk = it.get("front") or {}, it.get("back") or {}
            entries.append({"frontHtml": clean_html(fr.get("description")), "frontSrc": img(fr),
                            "backHtml": clean_html(bk.get("description")), "backSrc": img(bk)})
        return {"type": "flashcard", "entries": entries}

    if fam == "interactive-fullscreen" and var == "sorting":
        buckets = [{"id": str(p.get("id")), "title": plain_text(p.get("title"))}
                   for p in (b.get("piles") or [])]
        pool = [{"html": plain_text(it.get("title")), "target": str(it.get("pileId"))}
                for it in _items(b)]
        return {"type": "categorize", "buckets": buckets, "pool": pool}

    if fam == "interactive-fullscreen" and var == "scenario":
        scenes = []
        for scene in _items(b):
            narr, responses = [], []
            for sl in scene.get("slides", []):
                d = clean_html(sl.get("description"))
                if d:
                    narr.append(d)
                for r in sl.get("responses", []):
                    responses.append({"html": clean_html(r.get("description")),
                                      "feedback": clean_html(r.get("feedback")),
                                      "preferred": r.get("action") == "continue"})
            scenes.append({"title": plain_text(scene.get("title")),
                           "html": "".join(narr), "responses": responses})
        return {"type": "scenario", "scenes": scenes}

    stats["skipped"][f"{fam}/{var}"] += 1
    return None


def import_rise(zip_path, brand=None):
    """Return (ir_dict, {in_zip_path: out_rel_path}) for assets to copy.

    `brand` (a brand.Brand) supplies the accent-snap palette + default accent so
    no client colors are hardcoded here; None => the neutral fallback.
    """
    accents = (brand.get("accentSnap") if brand else None) or []
    default_accent = (brand.accent if brand else NEUTRAL_ACCENT)
    with zipfile.ZipFile(zip_path) as zf:
        data = _decode(zf)
        idx = _asset_index(zf)
        asset_paths = {p: zf.getinfo(p) for p in zf.namelist()}  # noqa: keep handle scope
        course = data.get("course", {})
        title = plain_text(course.get("title")) or "Course"
        accent = snap_accent(((course.get("theme") or {}).get("colorAccent")) or default_accent,
                             accents, default_accent)

        flat = []
        for les in course.get("lessons", []):
            _walk(les.get("items", []), flat)

        used = set()
        stats = {"skipped": Counter()}
        blocks = []
        for b in flat:
            ir = block_to_ir(b, idx, used, stats)
            if ir:
                blocks.append(ir)

        # gating: everything after a `continue` (until the next one) is gated
        gated = False
        for blk in blocks:
            if blk["type"] == "continue":
                gated = True
                blk["gated"] = False
                continue
            blk["gated"] = gated

        # hero promotion: if the first visual block is a hero image, lift it to course.hero
        hero = None
        for blk in blocks:
            if blk["type"] == "image" and blk.get("variant") == "hero" and blk.get("src"):
                hero = {"image": blk["src"], "title": title,
                        "subtitle": plain_text(blk.get("html"))}
                blocks.remove(blk)
                break

        ir = {
            "schema": "course-ir/v1",
            "id": slugify(title),
            "title": title,
            "locale": course.get("exportLocale") or "en",
            "accent": accent,
            "hero": hero,
            "blocks": blocks,
        }
        copy_map = {p: "assets/" + posixpath.basename(p) for p in used}
        ir["_stats"] = {"blocks": len(blocks), "assets": len(used),
                        "skipped": dict(stats["skipped"])}
        from ir_validate import validate_ir
        validate_ir(ir, label=ir.get("id", "course"))
        return ir, copy_map, zip_path
