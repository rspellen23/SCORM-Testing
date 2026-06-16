"""Rise published-HTML export (-raw- zip) -> Course IR + extracted assets.

Extends the runtime-data.js decoder. Maps the Rise block taxonomy onto the IR
block set (see schema/IR_SCHEMA.md). mondrian/flashcard/interactive blocks are
skipped in v1 (counted + reported), per the 2026-06-04 scope decision.
"""
import re, base64, json, zipfile, os, posixpath
from collections import Counter
from common import clean_html, plain_text, slugify, norm_name

DEFAULT_ACCENT = "#1EB16A"  # TeleGreen

# Official TeleTracking accent-eligible hexes (vivid palette only, no greys).
BRAND_ACCENTS = ["#1EB16A", "#069696", "#539BD2", "#003E51", "#0B2C37",
                 "#ECBD00", "#F27D05", "#BD362F", "#4EE89E"]


def snap_accent(hexstr):
    """Snap an arbitrary Rise accent to the nearest official TeleTracking color."""
    try:
        h = (hexstr or "").lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except Exception:
        return DEFAULT_ACCENT
    def dist(c):
        c = c.lstrip("#")
        return (int(c[0:2],16)-r)**2 + (int(c[2:4],16)-g)**2 + (int(c[4:6],16)-b)**2
    return min(BRAND_ACCENTS, key=dist)


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
    img = (media or {}).get("image") or {}
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


def block_to_ir(b, idx, used, stats):
    fam, var = b.get("family"), b.get("variant")
    it0 = _items(b)[0] if _items(b) else {}

    def img(rec):
        path = _resolve_image(rec.get("media"), idx)
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

    stats["skipped"][f"{fam}/{var}"] += 1
    return None


def import_rise(zip_path):
    """Return (ir_dict, {in_zip_path: out_rel_path}) for assets to copy."""
    with zipfile.ZipFile(zip_path) as zf:
        data = _decode(zf)
        idx = _asset_index(zf)
        asset_paths = {p: zf.getinfo(p) for p in zf.namelist()}  # noqa: keep handle scope
        course = data.get("course", {})
        title = plain_text(course.get("title")) or "Course"
        accent = snap_accent(((course.get("theme") or {}).get("colorAccent")) or DEFAULT_ACCENT)

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
            "schema": "nova-course-ir/v1",
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
        return ir, copy_map, zip_path
