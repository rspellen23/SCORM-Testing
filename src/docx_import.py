"""Author a course in Word (.docx) + a folder of named images -> Course IR.

Authoring grammar (builds on the microlearning-template/storyboard format):

  Heading 1            -> course title  (also the hero title if a [HERO] is present)
  Heading 2            -> section heading (navy band)
  Heading 3            -> subheading
  normal paragraph     -> body paragraph (bold/italic/underline preserved)
  numbered/bullet list -> list block

  Line markers (each on its own paragraph):
    [HERO: file.jpg | Title | Subtitle]      -> cover hero
    [IMG: file.png | alt text | caption]     -> full-width image (alt/caption optional)
    [IMG-LEFT: file.png | alt]  / [IMG-RIGHT: ...]  -> image beside the NEXT paragraph
    [NOTE] text...                           -> callout box
    [STATEMENT] text...                      -> centered emphasis line
    [CONTINUE]                               -> gate (reveals following content)
    [KC] ... [/KC]                           -> knowledge check (see below)

  Knowledge check:
    [KC]
    Q: Who can edit a note?
    * Only the user who created it      (a leading * marks the correct answer)
    - Any associated user
    - Only Transfer Center Users
    FB: Notes are private to their author.
    [/KC]

Images are resolved by filename against the supplied image folder.
"""
import os, re, html
from common import slugify, plain_text

MARK = re.compile(r"^\[(HERO|IMG|IMG-LEFT|IMG-RIGHT|NOTE|STATEMENT|CONTINUE|KC|/KC)\b\s*:?\s*(.*?)\]?\s*$", re.I)


def _runs_to_html(para):
    out = []
    for r in para.runs:
        t = html.escape(r.text or "")
        if not t:
            continue
        if r.bold: t = f"<strong>{t}</strong>"
        if r.italic: t = f"<em>{t}</em>"
        if r.underline: t = f"<u>{t}</u>"
        out.append(t)
    return "".join(out).strip()


def _is_list(para):
    s = (para.style.name or "").lower()
    if "list number" in s or "list bullet" in s:
        return "ol" if "number" in s else "ul"
    # fallback: numPr in the paragraph properties
    pPr = para._p.pPr
    if pPr is not None and pPr.numPr is not None:
        return "ol"
    return None


def import_docx(docx_path, image_dir=None):
    from docx import Document  # python-docx
    doc = Document(docx_path)
    image_dir = image_dir or os.path.dirname(os.path.abspath(docx_path))
    available = {n.lower(): n for n in os.listdir(image_dir)} if os.path.isdir(image_dir) else {}

    title = None
    hero = None
    blocks = []
    used = {}          # out_rel -> source path on disk
    pending_list = None  # (tag, [items])
    pending_aside = None  # (side, src, alt) waiting for the next paragraph
    kc = None           # active KC accumulator

    def flush_list():
        nonlocal pending_list
        if pending_list:
            tag, items = pending_list
            blocks.append({"type": "list", "ordered": tag == "ol", "items": items})
            pending_list = None

    def resolve(fname):
        fname = (fname or "").strip()
        actual = available.get(fname.lower())
        if actual:
            rel = "assets/" + actual
            used[rel] = os.path.join(image_dir, actual)
            return rel
        return None

    paras = doc.paragraphs
    for para in paras:
        text = (para.text or "").strip()
        style = (para.style.name or "")

        # --- inside a KC block ---
        if kc is not None:
            if text.upper().startswith("[/KC"):
                blocks.append(kc); kc = None
                continue
            if text.lower().startswith("q:"):
                kc["prompt"] = html.escape(text[2:].strip())
            elif text.startswith("*"):
                kc["options"].append({"html": html.escape(text[1:].strip()), "correct": True})
            elif text.startswith("-"):
                kc["options"].append({"html": html.escape(text[1:].strip()), "correct": False})
            elif text.lower().startswith("fb:"):
                kc["feedback"] = html.escape(text[3:].strip())
            continue

        m = MARK.match(text) if text.startswith("[") else None
        if m:
            flush_list()
            tag = m.group(1).upper()
            arg = m.group(2).strip()
            parts = [p.strip() for p in arg.split("|")]
            if tag == "HERO":
                src = resolve(parts[0]) if parts else None
                hero = {"image": src, "title": parts[1] if len(parts) > 1 else (title or ""),
                        "subtitle": parts[2] if len(parts) > 2 else ""}
            elif tag == "IMG":
                src = resolve(parts[0]) if parts else None
                blocks.append({"type": "image", "variant": "full", "src": src,
                               "alt": parts[1] if len(parts) > 1 else "",
                               "caption": parts[2] if len(parts) > 2 else ""})
            elif tag in ("IMG-LEFT", "IMG-RIGHT"):
                src = resolve(parts[0]) if parts else None
                pending_aside = ("right" if tag == "IMG-RIGHT" else "left", src,
                                 parts[1] if len(parts) > 1 else "")
            elif tag == "NOTE":
                blocks.append({"type": "note", "html": f"<p>{html.escape(arg)}</p>" if arg else ""})
            elif tag == "STATEMENT":
                blocks.append({"type": "statement", "html": html.escape(arg)})
            elif tag == "CONTINUE":
                blocks.append({"type": "continue", "text": arg or "CONTINUE"})
            elif tag == "KC":
                kc = {"type": "knowledgeCheck", "multi": False, "prompt": "", "options": [], "feedback": ""}
            continue

        if not text:
            continue

        # headings
        if style.startswith("Heading 1") or style == "Title":
            flush_list()
            if not title:
                title = text
            else:
                blocks.append({"type": "heading", "level": 2, "html": _runs_to_html(para) or html.escape(text)})
            continue
        if style.startswith("Heading 2"):
            flush_list()
            blocks.append({"type": "heading", "level": 2, "html": _runs_to_html(para) or html.escape(text)})
            continue
        if style.startswith("Heading 3"):
            flush_list()
            blocks.append({"type": "heading", "level": 3, "html": _runs_to_html(para) or html.escape(text)})
            continue

        # lists
        listtag = _is_list(para)
        if listtag:
            if pending_list and pending_list[0] != listtag:
                flush_list()
            if not pending_list:
                pending_list = (listtag, [])
            pending_list[1].append(_runs_to_html(para) or html.escape(text))
            continue
        flush_list()

        # paragraph — possibly the text half of a pending image-aside
        html_frag = f"<p>{_runs_to_html(para) or html.escape(text)}</p>"
        if pending_aside:
            side, src, alt = pending_aside
            blocks.append({"type": "imageText", "src": src, "side": side, "alt": alt, "html": html_frag})
            pending_aside = None
        else:
            blocks.append({"type": "paragraph", "html": html_frag})

    flush_list()
    if kc is not None:
        blocks.append(kc)

    # gating
    gated = False
    for b in blocks:
        if b["type"] == "continue":
            gated = True; b["gated"] = False; continue
        b["gated"] = gated

    title = title or os.path.splitext(os.path.basename(docx_path))[0]
    ir = {"schema": "course-ir/v1", "id": slugify(title), "title": title,
          "locale": "en", "accent": None, "hero": hero, "blocks": blocks}
    ir["_stats"] = {"blocks": len(blocks), "assets": len(used)}
    from ir_validate import validate_ir
    validate_ir(ir, label=ir.get("id", "course"))
    return ir, used
