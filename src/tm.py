"""C17 — translation memory: reuse previously-approved translations across courses.

The translate/localize pass (C15, authoring.translate_course) runs one subscription-CLI
pass per `## Microlearning N:` unit. Most SME re-review cost is spent re-checking units
that haven't changed since the last time they were translated — a shared intro, a safety
notice, or an untouched unit in a course UPDATE. Translation memory removes that cost: an
APPROVED source→target unit is remembered, and when the same source unit is translated
into the same target again it is reused VERBATIM — no LLM call, no re-review.

The store is a small local JSON file per target language under the shared config dir
(`~/.course-builder/tm/<target-slug>.json`), keyed by a hash of the normalized source
unit. It is GLOBAL (cross-course) on purpose — that's where the reuse lives.

Approval model (James's rule):
  - LOCALIZE (an English dialect, e.g. en-GB) is minimal and glossary-guarded, so a
    localized unit is stored APPROVED immediately and reused on the next run.
  - TRANSLATE (a different language) is stored PENDING (approved=False). It is NOT reused
    until an operator runs the explicit approval step — the "final approval" for a full
    translation. `approve()` promotes a source course's pending units to approved.

Everything here is pure/deterministic and never raises on a bad/missing store (it degrades
to "no memory"): the memory is an optimization, never the deliverable. No metered API.
"""
import hashlib
import json
import os
import re
import time

TM_DIRNAME = "tm"


def _config_dir():
    """The shared config root (`~/.course-builder`), same root the dashboard uses.
    Overridable via COURSE_BUILDER_HOME so tests can point at a temp dir."""
    return os.environ.get("COURSE_BUILDER_HOME") or os.path.expanduser("~/.course-builder")


def target_slug(target):
    """A filesystem-safe slug for a target language/locale ('British English (en-GB)'
    → 'british-english-en-gb'). The store is per-target so languages never collide."""
    return re.sub(r"[^a-z0-9]+", "-", (target or "").lower()).strip("-") or "target"


def tm_path(target):
    return os.path.join(_config_dir(), TM_DIRNAME, target_slug(target) + ".json")


def _normalize_unit(unit_md):
    """The keying form of a source unit: drop the `## Microlearning N:` NUMBER (so the
    same unit reused at a different position still matches) and trim trailing whitespace
    on every line. Title and body text are kept — they are what gets translated."""
    t = re.sub(r"(?m)^(##\s+Microlearning)\s+\d+\s*:", r"\1:", unit_md or "")
    t = "\n".join(line.rstrip() for line in t.splitlines())
    return t.strip()


def unit_hash(unit_md):
    return hashlib.sha256(_normalize_unit(unit_md).encode("utf-8")).hexdigest()


def load(target):
    """The TM for a target as {hash: entry}. Empty dict on missing/corrupt store."""
    try:
        with open(tm_path(target), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(target, data):
    """Best-effort persist. A write failure must never break a translate."""
    p = tm_path(target)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        return p
    except OSError:
        return None


def lookup(target, source_unit_md, *, approved_only=True):
    """The remembered TARGET text for a source unit, or None. By default only APPROVED
    entries are returned (the reuse path); pass approved_only=False to also see pending."""
    entry = load(target).get(unit_hash(source_unit_md))
    if not entry:
        return None
    if approved_only and not entry.get("approved"):
        return None
    return entry.get("target")


def remember(target, source_unit_md, target_unit_md, *, mode, now=None):
    """Store a source→target unit. LOCALIZE units are approved immediately; TRANSLATE
    units are stored PENDING (approved=False) until `approve()` promotes them. An
    existing APPROVED entry is never silently downgraded. Returns the entry's approved
    flag (True == immediately reusable)."""
    data = load(target)
    h = unit_hash(source_unit_md)
    approved = (mode == "localize")
    prev = data.get(h)
    if prev and prev.get("approved") and not approved:
        # keep the approved wording; don't overwrite a blessed translation with pending MT
        return True
    data[h] = {
        "source": _normalize_unit(source_unit_md),
        "target": target_unit_md,
        "approved": approved,
        "mode": mode,
        "ts": now if now is not None else time.time(),
    }
    _save(target, data)
    return approved


def approve(target, source_md, *, now=None):
    """Promote every PENDING unit of `source_md` (a full course .md) to approved for
    `target` — the explicit final-approval step for a full translation. Returns the
    number of units promoted."""
    data = load(target)
    n = 0
    for _num, unit_md in _iter_units(source_md):
        h = unit_hash(unit_md)
        entry = data.get(h)
        if entry and not entry.get("approved"):
            entry["approved"] = True
            entry["approved_ts"] = now if now is not None else time.time()
            n += 1
    if n:
        _save(target, data)
    return n


def pending_count(target, source_md):
    """How many of `source_md`'s units are remembered for `target` but not yet approved
    (i.e. how many the approval step would promote). Zero → nothing to approve."""
    data = load(target)
    n = 0
    for _num, unit_md in _iter_units(source_md):
        entry = data.get(unit_hash(unit_md))
        if entry and not entry.get("approved"):
            n += 1
    return n


def _iter_units(md_text):
    """(number, unit_md) for each `## Microlearning N:` section — mirrors
    authoring._split_units without importing authoring (tm stays dependency-free)."""
    heads = list(re.finditer(r"(?m)^##\s+Microlearning\s+(\d+)\s*:", md_text or ""))
    for i, h in enumerate(heads):
        start = h.start()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(md_text)
        yield int(h.group(1)), md_text[start:end].strip()
