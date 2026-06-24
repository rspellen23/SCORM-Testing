"""Slide-to-slide PowerPoint transitions, injected as OOXML.

python-pptx has no transition API, so we append a `<p:transition>` element to a
slide part directly. Only classic, schema-safe effects are supported
(none/fade/cut/push/wipe/split/cover) — these live in the main `p` namespace and
open reliably everywhere. Morph is intentionally NOT implemented: it needs
per-shape id matching plus the 2015 extension namespace and is fragile to
hand-author, so it would risk corrupt decks.

Usage:
    import pptx_transitions
    pptx_transitions.apply(slide, "fade")                 # one slide
    pptx_transitions.apply_all(prs, "push", direction="l")  # whole deck
"""
from pptx.oxml import parse_xml
from pptx.oxml.ns import nsdecls, qn

EFFECTS = ("none", "fade", "cut", "push", "wipe", "split", "cover")
SPEEDS = ("slow", "med", "fast")
_DIRS = {"l": "l", "r": "r", "u": "u", "d": "d",
         "left": "l", "right": "r", "up": "u", "down": "d"}


def _inner(effect, direction):
    d = _DIRS.get((direction or "").lower())
    if effect == "fade":
        return "<p:fade/>"
    if effect == "cut":
        return "<p:cut/>"
    if effect == "push":
        return '<p:push dir="%s"/>' % (d or "l")
    if effect == "wipe":
        return '<p:wipe dir="%s"/>' % (d or "l")
    if effect == "cover":
        return '<p:cover dir="%s"/>' % (d or "l")
    if effect == "split":
        return '<p:split orient="horz" dir="out"/>'
    return ""


def apply(slide, effect="fade", speed="med", direction=None):
    """Append a `<p:transition>` to one slide. effect='none' removes any existing
    transition. Returns the resolved effect name."""
    effect = (effect or "fade").lower()
    if effect not in EFFECTS:
        raise ValueError("unknown transition %r (have: %s)" % (effect, ", ".join(EFFECTS)))
    speed = speed if speed in SPEEDS else "med"
    sld = slide._element
    for ex in sld.findall(qn("p:transition")):   # replace, don't stack
        sld.remove(ex)
    if effect == "none":
        return effect
    xml = '<p:transition %s spd="%s">%s</p:transition>' % (
        nsdecls("p"), speed, _inner(effect, direction))
    el = parse_xml(xml)
    ref = sld.find(qn("p:clrMapOvr"))            # CT_Slide order: cSld, clrMapOvr, transition
    if ref is None:
        ref = sld.find(qn("p:cSld"))
    if ref is not None:
        ref.addnext(el)
    else:
        sld.append(el)
    return effect


def apply_all(prs, effect="fade", speed="med", direction=None):
    """Apply the same transition to every slide in a presentation."""
    for s in prs.slides:
        apply(s, effect, speed, direction)
    return effect
