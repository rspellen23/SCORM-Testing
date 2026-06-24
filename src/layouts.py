"""Canonical content shapes shared by the course HTML blocks (render.py) and the
PPTX slide layouts (slide_layouts.py).

A few layouts grew two slightly different field names for the same content:

    comparison   course block -> `panels[]`   slide -> `columns[]`
    timeline     course block -> milestone `html`   slide -> milestone `body`

So feeding a slide JSON to the course renderer (or a course block to the slide
renderer) silently produced an EMPTY block — the renderer looked up a key that
wasn't there. These normalizers accept BOTH shapes and return one canonical dict
(the IR / course shape), so the same JSON renders correctly on either surface
(audit item 2.7). Pure stdlib — safe to import from the air-gapped render core.
"""
import re

_TAG = re.compile(r"<[^>]+>")
_TOP = ("title", "subtitle", "intro", "footer", "accent")


def strip_tags(s):
    """Plain text for the PPTX surface (which has no HTML)."""
    return _TAG.sub("", s or "").strip()


def normalize_comparison(d):
    """-> {<top-level>, "panels": [{heading, sublabel, accent, items, callout}, ...]}.

    Reads the panel list from `panels` (course) OR `columns` (slide). Panel item
    entries may be inline-HTML strings or [bold, rest] pairs; both renderers
    handle both."""
    d = d or {}
    panels = d.get("panels")
    if panels is None:
        panels = d.get("columns")            # slide-schema alias
    out = {k: d[k] for k in _TOP if d.get(k) is not None}
    out["panels"] = panels or []
    return out


def normalize_timeline(d):
    """-> {<top-level>, "milestones": [{phase, title, html, body, accent}, ...]}.

    Each milestone carries BOTH `html` (course block) and `body` (slide): whichever
    the source provided is mirrored to the other (tags stripped for the slide's
    `body`) so neither renderer reads an empty field."""
    d = d or {}
    out = {k: d[k] for k in _TOP if d.get(k) is not None}
    ms = []
    for m in (d.get("milestones") or []):
        m = dict(m)
        html, body = m.get("html"), m.get("body")
        if html is None and body is not None:
            m["html"] = body                 # course renderer reads html
        if body is None and html is not None:
            m["body"] = strip_tags(html)     # slide renderer reads plain body
        ms.append(m)
    out["milestones"] = ms
    return out
