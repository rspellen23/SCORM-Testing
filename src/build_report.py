"""Course Builder — structured build report.

The engine never crashes on malformed input: it drops to empty and keeps going.
For a hands-on author that's a feature; for an *operator* running real workloads
it's the central liability — a dropped block or a mis-scored quiz ships unnoticed.

This module turns the build's scattered, stderr-only signals (IR import warnings,
the §8 lint pass, the PowerPoint flatten's dropped-block set, SCORM conformance
lint) into ONE structured report that travels with the build:

    report = assemble(ir, lint_errors=…, dropped=…, conformance_errors=…, conformance_warnings=…)
    write(report, out_path)          # -> <stem>.report.json next to the artifact

The dashboard reads that JSON back (the build runs in a subprocess, so the report
must cross the process boundary on disk) and shows the operator, in the UI, when
a build degraded — not just in stderr. The on-disk JSON is also the persistence:
every build leaves its report beside the artifact.

`assemble` is pure (dict in, dict out) so it can be unit-tested without a build.
"""
import html
import json
import os
import re

REPORT_SUFFIX = ".report.json"

# M2 — WCAG conformance pass. The automated checks below catch the accessibility
# mistakes a build can detect on its own (a missing alt attribute, a skipped
# heading level, a brand pair that fails contrast, an unlabeled control). They are
# a floor, NOT a certificate: judgement calls — is this alt text actually useful,
# is the reading order sensible, are captions accurate — still need a human. The
# note travels in the report so the operator never mistakes "0 findings" for
# "WCAG conformant".
WCAG_NOTE = (
    "Automated accessibility checks are a floor, not full WCAG conformance. They flag "
    "missing alt text, skipped heading levels, brand-color contrast below AA, and unlabeled "
    "knowledge-check controls. A human reviewer must still confirm alt text is meaningful, "
    "reading/focus order is sensible, media captions are accurate, and interaction is "
    "keyboard-operable before certifying WCAG 2.1 AA."
)

# Foreground/background brand token pairs to check for WCAG AA contrast, with a
# `large` flag (headings/band text ride the 3:1 large-text threshold; body text
# the 4.5:1 normal threshold). Keyed to the --brand-* contract in tokens.css; a
# pair whose tokens a profile omits is skipped, never guessed.
CONTRAST_PAIRS = [
    ("--brand-ink", "--brand-page-bg", False, "body text on the page"),
    ("--brand-ink-soft", "--brand-page-bg", False, "secondary/caption text on the page"),
    ("--brand-heading", "--brand-page-bg", True, "headings on the page"),
    ("--brand-ink", "--brand-surface", False, "text on a surface/card"),
    ("--brand-band-ink", "--brand-band-bg", True, "band (section-header) text"),
    ("--brand-accent-ink", "--brand-page-bg", False, "accent/link text on the page"),
    ("--brand-correct", "--brand-page-bg", False, "correct-answer feedback text"),
    ("--brand-incorrect", "--brand-page-bg", False, "incorrect-answer feedback text"),
]


def parse_tokens_css(text):
    """Parse a brand `tokens.css` into {--brand-var: '#rrggbb'}. Only 3/6-digit hex
    values are kept (fonts, radii, widths are ignored) so the map is safe to feed
    straight into the contrast checker. Best-effort and forgiving of formatting."""
    import re
    out = {}
    for m in re.finditer(r"(--brand-[a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{3}|#[0-9A-Fa-f]{6})\b", text or ""):
        out[m.group(1)] = m.group(2)
    return out


def _hex_to_rgb(h):
    h = (h or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return None
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def _relative_luminance(rgb):
    """WCAG 2.x relative luminance of an sRGB color (0..1)."""
    def _lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (_lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(hex1, hex2):
    """WCAG contrast ratio between two hex colors (1.0 .. 21.0), or None if either
    color is unparseable."""
    a, b = _hex_to_rgb(hex1), _hex_to_rgb(hex2)
    if a is None or b is None:
        return None
    la, lb = _relative_luminance(a), _relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# A `*Visual:*` with no `<description>` segment falls back to alt = the bare type
# keyword ("screenshot", "graphic", …) — technically non-empty but useless to a
# screen-reader user. Treat an empty alt OR a single generic token as a real gap so
# the check catches the omission the grammar actually produces.
_GENERIC_ALT = {
    "screenshot", "graphic", "diagram", "photo", "image", "picture",
    "illustration", "visual", "decorative", "decoration", "figure", "img",
}


def alt_is_weak(alt):
    """True when `alt` is missing or non-descriptive (empty/whitespace, or a single
    generic token like 'screenshot'). Shared by the build report's alt check and the
    generation-time alt redraft oracle so both agree on what counts as a gap."""
    a = (alt or "").strip()
    if not a:
        return True
    return a.lower() in _GENERIC_ALT


def _iter_media(ir):
    """Yield (where, block) for every alt-bearing raster image in the IR — the
    top-level `image`/`imageText` blocks plus the nested per-entry images that
    accordion/steps carry. Decorative-by-design art (flip-card faces via
    frontSrc/backSrc, section-transition ribbons) has no `src`+`alt` pair in the
    IR and so is intentionally excluded — only images that SHOULD describe
    themselves are checked."""
    for i, b in enumerate(ir.get("blocks") or []):
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        # `decorative` images (authored `*Visual:* decorative`) legitimately carry an
        # empty alt so screen readers skip them — not an omission, so not checked.
        if t in ("image", "imageText") and b.get("src") and not b.get("decorative"):
            yield (f"{t} #{i + 1}", b)
        for entry in (b.get("entries") or []):
            if isinstance(entry, dict) and entry.get("src") and not entry.get("decorative"):
                yield (f"{t} entry in block #{i + 1}", entry)


def a11y_findings(ir, brand_tokens=None):
    """M2 accessibility checks over a built Course IR. Returns a list of findings,
    each `{check, severity, where, message}`. Pure: walks the given IR and an
    optional resolved brand token map ({--brand-*: '#hex'}, from `parse_tokens_css`).

    Every finding is a WARNING — accessibility gaps are surfaced for the operator
    but never flip the build's `ok` flag (a course still builds; James's call). The
    four checks mirror the spec: alt-text presence, heading order, brand-token
    contrast, and knowledge-check control labels."""
    findings = []

    def add(check, where, message):
        findings.append({"check": check, "severity": "warn", "where": where, "message": message})

    # (1) alt text — every content image should describe itself (empty alt is only
    # valid for decorative images, which this grammar routes through other block
    # types; an empty alt on a real image is almost always an omission).
    for where, b in _iter_media(ir):
        if alt_is_weak(b.get("alt")):
            add("alt-text", where,
                "image alt text is missing or non-descriptive — add a short description "
                "of what it conveys, or mark the image decorative")

    # (2) heading order — the document outline must not skip a level going down
    # (WCAG 1.3.1 / 2.4.10). Outline = the course h1 (hero/title) followed by each
    # heading block's level. A jump deeper than one level (e.g. h1 -> h3 with no h2)
    # is flagged; the fixed h1->h2->h3 scale this renderer uses is conformant.
    outline = []
    if (ir.get("title") or (ir.get("hero") or {}).get("title")):
        outline.append(1)
    for i, b in enumerate(ir.get("blocks") or []):
        if not isinstance(b, dict):
            continue
        if b.get("type") in ("heading", "headingParagraph"):
            lvl = b.get("level", 2) or 2
            outline.append(lvl)
            txt = b.get("html") or b.get("headingHtml") or ""
            if not _strip_tags(txt).strip():
                add("heading-order", f"heading #{i + 1}", "heading has no text")
    prev = None
    for lvl in outline:
        if prev is not None and lvl > prev + 1:
            add("heading-order", f"h{prev}→h{lvl}",
                f"heading level jumps from h{prev} to h{lvl} — do not skip a level "
                f"(add the intervening h{prev + 1} or lift this heading)")
        prev = lvl

    # (3) brand-token contrast — resolved brand pairs must meet WCAG AA (4.5:1
    # normal text, 3:1 large text). A curated palette usually passes; when it does
    # not, the whole course inherits the failure, so it is worth proving.
    tokens = brand_tokens or {}
    for fg, bg, large, label in CONTRAST_PAIRS:
        if fg in tokens and bg in tokens:
            ratio = contrast_ratio(tokens[fg], tokens[bg])
            floor = 3.0 if large else 4.5
            if ratio is not None and ratio + 1e-9 < floor:
                add("contrast", f"{fg} on {bg}",
                    f"{label}: contrast {ratio:.2f}:1 is below WCAG AA "
                    f"{floor:g}:1 ({tokens[fg]} on {tokens[bg]})")

    # (4) knowledge-check labels — a screen-reader user needs a question prompt and
    # a text label on every option; an empty prompt or option is an unlabeled
    # control (WCAG 1.1.1 / 4.1.2).
    for i, b in enumerate(ir.get("blocks") or []):
        if not isinstance(b, dict) or b.get("type") != "knowledgeCheck":
            continue
        if not _strip_tags(b.get("prompt") or "").strip():
            add("kc-labels", f"knowledgeCheck #{i + 1}", "knowledge check has no question prompt text")
        for j, o in enumerate(b.get("options") or []):
            if not _strip_tags((o or {}).get("html") or "").strip():
                add("kc-labels", f"knowledgeCheck #{i + 1} option {j + 1}",
                    "knowledge-check option has no text label")

    return findings


def _strip_tags(s):
    return re.sub(r"<[^>]+>", "", s or "")


# ---- C19: readability + voice lint (deterministic, non-blocking) -------------
#
# A course whose prose reads ABOVE its audience band is FLAGGED (a warning, never a
# build failure — same non-blocking model as the M2 a11y findings). The band is
# audience-driven: it comes from the course PURPOSE preset (a course declares one with
# a `*Preset:*` line → ir["preset"]). Bands mirror authoring.COURSE_PRESETS but live
# here to avoid a circular import (authoring already imports build_report). Everything
# is deterministic (Flesch-Kincaid + sentence-length heuristics) — no metered API.

READING_BANDS = {
    "standard": 14.0,       # let the material decide; only very dense prose flags
    "compliance": 12.0,     # authoritative, but the rules must be unmissable
    "onboarding": 9.0,      # warm, plain language, accessible to a brand-new hire
    "product-skill": 11.0,  # practical / task-focused
    "refresher": 12.0,      # brisk; assumes prior exposure
}
_LONG_SENTENCE_WORDS = 30
_VOWEL_RUN = re.compile(r"[aeiouy]+", re.I)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")


def _syllables(word):
    """Rough English syllable count (deterministic): vowel groups, minus a silent
    trailing 'e', floor 1. Good enough for a Flesch-Kincaid estimate."""
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    n = len(_VOWEL_RUN.findall(w))
    if w.endswith("e") and n > 1:
        n -= 1
    return max(1, n)


def _fk_stats(text):
    """(grade, ease, n_words, n_sentences) via Flesch-Kincaid over plain text, or
    (None, None, n_words, n_sentences) when there's too little prose to be meaningful."""
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    words = _WORD_RE.findall(text)
    n_s, n_w = len(sentences), len(words)
    if n_w < 20 or n_s < 1:
        return None, None, n_w, n_s
    syl = sum(_syllables(w) for w in words)
    wps, spw = n_w / n_s, syl / n_w
    grade = 0.39 * wps + 11.8 * spw - 15.59
    ease = 206.835 - 1.015 * wps - 84.6 * spw
    return round(grade, 1), round(ease, 1), n_w, n_s


def _prose_parts(ir):
    """The learner-facing prose of a Course IR as a LIST of per-block segments
    (headings, paragraphs, statements, notes, list items, KC prompts, bank children),
    tags stripped. Kept as separate parts so callers that must not span a heading→body
    boundary (C20 term detection) can, while `_course_prose` just joins them."""
    out = []

    def take(html_str):
        t = _strip_tags(html_str or "").strip()
        if t:
            out.append(t)

    def walk(blocks):
        for b in blocks or []:
            if not isinstance(b, dict):
                continue
            for key in ("html", "prompt", "headingHtml", "text"):
                if b.get(key):
                    take(b[key])
            for it in (b.get("items") or []):
                if isinstance(it, str):
                    take(it)
            if b.get("type") == "questionBank":
                walk(b.get("questions"))

    walk(ir.get("blocks"))
    return out


def _course_prose(ir):
    """The learner-facing prose of a Course IR, tags stripped, joined into one string."""
    return " ".join(_prose_parts(ir))


def readability_findings(ir, *, preset=None):
    """C19 — deterministic readability + voice signals over the built IR prose.
    NON-BLOCKING: every finding is 'info' or 'warn' and never flips the build `ok`.
    The audience band comes from the course PURPOSE preset (kwarg → ir['preset'] →
    'standard'): prose above the band is flagged, and over-long sentences (a voice /
    clarity signal that muddies any preset's register) are flagged too."""
    if not isinstance(ir, dict):
        return []
    prose = _course_prose(ir)
    grade, ease, n_w, _n_s = _fk_stats(prose)
    if grade is None:
        return []                                   # too little prose to assess
    key = preset or ir.get("preset") or "standard"
    band = READING_BANDS.get(key, READING_BANDS["standard"])
    findings = [{"check": "reading-level", "severity": "info", "where": "course",
                 "message": f"Flesch-Kincaid grade {grade} (reading ease {ease}) over {n_w} words; "
                            f"audience band ≤ grade {band:g}"}]
    if grade > band:
        findings.append({"check": "reading-level", "severity": "warn", "where": "course",
                         "message": f"prose reads at grade {grade}, above the grade {band:g} band for this "
                                    f"audience — shorten sentences and prefer plainer words"})
    long_n = sum(1 for s in re.split(r"[.!?]+", prose) if len(_WORD_RE.findall(s)) > _LONG_SENTENCE_WORDS)
    if long_n:
        findings.append({"check": "sentence-length", "severity": "warn", "where": "course",
                         "message": f"{long_n} sentence(s) run over {_LONG_SENTENCE_WORDS} words — "
                                    f"split them so the point isn't lost"})
    return findings


# ---- C20: cross-unit consistency (appended-unit drift) -----------------------
#
# When a new unit is appended to a multi-unit course it can DRIFT from the units
# already there — in VOICE (its reading level lands far from its siblings) or in
# TERMS (a product/feature name written with different casing than the rest, or a
# glossary-banned / wrong term the other units avoid). C20 flags that drift so the
# operator catches it before the added unit ships next to established ones.
# Deterministic and NON-BLOCKING (same model as C19/M2): every finding is a warning
# and never flips the build `ok`. Reuses the C19 prose/FK helpers; the glossary pass
# is done with a small local scan rather than importing authoring (build_report must
# stay dependency-light — authoring imports IT, so the reverse would be circular).

VOICE_DRIFT_GRADES = 3.0   # FK-grade gap from the sibling median that flags a unit

# A multi-word run of Capitalized words — the surface form of a product/feature name
# ("Transfer IQ Pro", "Bed Board"). Single words are excluded (too many false hits
# from ordinary sentence-initial capitals); 2–4 words keeps it to real proper phrases.
_PROPER_TERM_RE = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*){1,3}\b")
# Common words that only capitalize because they open a sentence — strip them off the
# front of a matched phrase so "When Transfer Center" canonicalizes to "Transfer Center".
_TERM_STOP = {
    "the", "a", "an", "this", "that", "these", "those", "it", "they", "we", "you",
    "he", "she", "when", "if", "for", "and", "but", "or", "to", "in", "on", "at", "by",
    "as", "so", "then", "now", "here", "there", "each", "every", "all", "some",
    "what", "why", "how", "who", "whom", "whose", "where", "which", "will", "would",
    "should", "could", "can", "may", "must", "do", "does", "did", "is", "are", "was",
    "were", "be", "been", "our", "your", "their", "my", "his", "her", "its", "us",
    "them", "i", "of", "with", "from", "after", "before", "once", "while",
}


def _median(nums):
    s = sorted(nums)
    n = len(s)
    if not n:
        return None
    m = n // 2
    return s[m] if n % 2 else (s[m - 1] + s[m]) / 2.0


def _proper_terms(text):
    """{lower-key: canonical surface} for the multi-word Capitalized phrases in `text`
    (product/feature names). First occurrence's surface wins as canonical. A leading
    sentence-opener ("The", "When", …) is stripped so it isn't mistaken for part of the
    name; a phrase that shrinks below two words after stripping is dropped."""
    out = {}
    for m in _PROPER_TERM_RE.finditer(text or ""):
        words = re.sub(r"\s+", " ", m.group(0).strip()).split()
        while words and words[0].lower() in _TERM_STOP:
            words = words[1:]
        if len(words) < 2:
            continue
        surf = " ".join(words)
        out.setdefault(surf.lower(), surf)
    return out


def _proper_terms_over(parts):
    """{lower-key: canonical} over a LIST of prose parts (per-part so a phrase never
    spans a heading→body join). Entities are unescaped first. First surface wins."""
    out = {}
    for p in parts:
        for k, v in _proper_terms(html.unescape(p or "")).items():
            out.setdefault(k, v)
    return out


def _term_casing_drift(new_parts, prior_parts):
    """(canonical, offending) pairs where the appended unit writes an established
    proper term with a different casing/spelling than the rest of the course. The
    established spelling comes from the prior units; each new-unit part is searched
    case-insensitively so a fully lowercased variant ('transfer iq pro') is caught."""
    established = _proper_terms_over(prior_parts)
    seen, drift = set(), []
    for _key, canon in established.items():
        pat = re.compile(r"\b" + r"\s+".join(re.escape(w) for w in canon.split()) + r"\b", re.I)
        for part in new_parts:
            for m in pat.finditer(html.unescape(part or "")):
                surf = re.sub(r"\s+", " ", m.group(0))
                if surf != canon and (canon, surf) not in seen:
                    seen.add((canon, surf))
                    drift.append((canon, surf))
    return drift


def _glossary_term_hits(text, glossary):
    """The set of glossary-guarded terminology problems present in `text`: each banned
    word and each wrong `instead_of` phrase, as a human-readable clause. Whole-word,
    case-insensitive. Empty glossary → empty set. A tiny local scan (not authoring's
    lint) so build_report stays free of the authoring import."""
    if not glossary:
        return set()
    hits = set()
    t = text or ""
    for w in glossary.get("banned") or []:
        w = (w or "").strip()
        if w and re.search(rf"(?i)\b{re.escape(w)}\b", t):
            hits.add(f"uses the non-approved term “{w}”")
    for e in glossary.get("preferred") or []:
        term = (e.get("term") or "").strip()
        for bad in (e.get("instead_of") or []):
            bad = (bad or "").strip()
            if bad and re.search(rf"(?i)\b{re.escape(bad)}\b", t):
                hits.add(f"uses “{bad}” for what the approved term calls “{term}”")
    return hits


def consistency_findings(new_ir, prior_irs, *, glossary=None):
    """C20 — flag where a newly-appended unit drifts from the rest of its course.

    `new_ir`      the appended unit's Course IR.
    `prior_irs`   the sibling units already in the course (a list of IRs).
    `glossary`    an optional {preferred, banned} termbank (from authoring.load_glossary),
                  used only to catch a wrong/banned term the appended unit introduces
                  that the rest of the course avoids.

    Returns a list of `{check, severity, where, message}` findings, all `warn` and
    NON-BLOCKING. Pure and deterministic. Empty when there's nothing to compare
    against (a single-unit course) or too little prose to assess."""
    findings = []
    if not isinstance(new_ir, dict) or not prior_irs:
        return findings
    new_parts = _prose_parts(new_ir)
    new_text = " ".join(new_parts)
    prior_part_lists = [_prose_parts(ir) for ir in prior_irs if isinstance(ir, dict)]
    prior_parts = [p for parts in prior_part_lists for p in parts]
    prior_text = " ".join(prior_parts)

    def add(check, message):
        findings.append({"check": check, "severity": "warn", "where": "appended unit", "message": message})

    # (1) voice drift — the appended unit's reading level vs the sibling median.
    new_grade = _fk_stats(new_text)[0]
    prior_grades = [g for g in (_fk_stats(" ".join(parts))[0] for parts in prior_part_lists)
                    if g is not None]
    if new_grade is not None and prior_grades:
        base = _median(prior_grades)
        if abs(new_grade - base) > VOICE_DRIFT_GRADES:
            harder = new_grade > base
            add("voice-drift",
                f"reads at grade {new_grade}, {abs(new_grade - base):.1f} levels "
                f"{'harder' if harder else 'simpler'} than the rest of the course "
                f"(grade ~{base:g}) — match the course's established reading level")

    # (2) term casing/spelling drift — an established proper term written differently.
    for canon, surf in _term_casing_drift(new_parts, prior_parts):
        add("term-drift",
            f"writes “{surf}” but the rest of the course uses “{canon}” — "
            f"use the established spelling/casing")

    # (3) glossary drift — a wrong/banned term the appended unit introduces that the
    # rest avoids (a course-wide glossary miss is lint/C16's job, not a DRIFT signal).
    new_hits = _glossary_term_hits(html.unescape(new_text), glossary)
    prior_hits = _glossary_term_hits(html.unescape(prior_text), glossary)
    for msg in sorted(new_hits - prior_hits):
        add("term-drift", f"the appended unit {msg}, but the rest of the course does not — align terminology")

    return findings


def consistency_findings_course(unit_irs, *, glossary=None):
    """Run C20 for a whole multi-unit build: a course build has no single 'appended'
    unit, so every unit is checked against its siblings and findings are tagged by unit
    number. Empty for a single-unit course. Reuses `consistency_findings` per unit."""
    irs = [ir for ir in (unit_irs or []) if isinstance(ir, dict)]
    if len(irs) < 2:
        return []
    out = []
    for i, ir in enumerate(irs):
        rest = irs[:i] + irs[i + 1:]
        for f in consistency_findings(ir, rest, glossary=glossary):
            g = dict(f)
            g["where"] = f"unit {i + 1}"
            out.append(g)
    return out


def report_path(out_path):
    """The report path for a build artifact: `<stem>.report.json` beside it.

    Shared by the writer (CLI) and the reader (dashboard) so both derive the
    same location from the artifact path alone — no out-of-band handshake.
    """
    return os.path.splitext(out_path)[0] + REPORT_SUFFIX


def assemble(ir, *, lint_errors=None, dropped=None,
             conformance_errors=None, conformance_warnings=None, brand_tokens=None,
             preset=None, consistency=None):
    """Build the structured report from a build's signals. Pure.

    - `ir`                  the Course IR (its `_stats` carries blocks/assets and
                            any import-time drop WARNINGS recorded by md_import).
    - `lint_errors`         the §8 `authoring.lint` errors (KC mis-scoring, missing
                            chart source, …) — correctness problems, surfaced as ERRORS
                            even though a package was still produced.
    - `dropped`             {block_type: count} the PowerPoint flatten couldn't render
                            statically (only meaningful for a .pptx build).
    - `conformance_*`       SCORM conformance lint results (when `--validate`).
    - `brand_tokens`        {--brand-*: '#hex'} resolved from the build's tokens.css
                            (from `parse_tokens_css`), so the a11y pass can check
                            brand-color contrast. Omit → contrast check is skipped.

    - `consistency`         C20 cross-unit drift findings (from consistency_findings_course),
                            computed by the multi-unit caller since assemble sees one IR.

    Returns: {title, blocks, assets, warnings[str], errors[str], dropped{}, a11y[],
    a11y_note, readability[], consistency[], ok}.  `ok` is False when anything
    correctness-level (lint or
    conformance ERROR) is present, so the dashboard can flag an otherwise-
    "successful" build as suspect. The M2 `a11y` findings are non-blocking — they
    travel in the report but never flip `ok`.
    """
    st = (ir.get("_stats") or {}) if isinstance(ir, dict) else {}
    warnings = list(st.get("warnings") or [])           # import-time drops (e.g. missing assets)
    errors = []

    # rise_import records unsupported block variants it couldn't map as `skipped`
    # ({"fam/var": count}) — the same silent-drop disease; surface them too.
    for variant, c in (st.get("skipped") or {}).items():
        if c:
            warnings.append(f"{c} “{variant}” source block(s) had no equivalent and were skipped on import")

    dropped = {k: v for k, v in (dropped or {}).items() if v}
    for t, c in dropped.items():
        warnings.append(
            f"{c} “{t}” block(s) had no static equivalent and were dropped "
            f"from the PowerPoint")

    for w in (conformance_warnings or []):
        warnings.append(f"SCORM conformance: {w}")

    for e in (lint_errors or []):
        errors.append(e)
    for e in (conformance_errors or []):
        errors.append(f"SCORM conformance: {e}")

    a11y = a11y_findings(ir, brand_tokens=brand_tokens) if isinstance(ir, dict) else []
    readability = readability_findings(ir, preset=preset)   # C19 (non-blocking)

    return {
        "title": ir.get("title") if isinstance(ir, dict) else None,
        "blocks": st.get("blocks"),
        "assets": st.get("assets"),
        "warnings": warnings,
        "errors": errors,
        "dropped": dropped,
        "a11y": a11y,                 # M2: accessibility findings (non-blocking)
        "a11y_note": WCAG_NOTE,       # the automated-checks-are-a-floor disclaimer
        "readability": readability,   # C19: readability + voice findings (non-blocking)
        "consistency": list(consistency or []),  # C20: appended-unit drift (non-blocking)
        "ok": not errors,             # a11y + readability + consistency never flip this
    }


def write(report, out_path):
    """Persist `report` to `<stem>.report.json` beside the artifact. Returns the path.

    Best-effort: a write failure must never fail an otherwise-good build, so it is
    swallowed (the build report is observability, not the deliverable).
    """
    p = report_path(out_path)
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    except OSError:
        return None
    return p


def read(out_path):
    """Read the report beside an artifact, or None if absent/unreadable."""
    p = report_path(out_path)
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
