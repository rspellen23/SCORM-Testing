"""Stage 2 — AI authoring via local subscription CLIs (no API billing).

Drives a locally-installed, subscription-authenticated coding-agent CLI to draft a
microlearning script from source documents — the Segment B.3 step. It uses the
user's existing subscription (Claude Code, or OpenAI's Codex for ChatGPT), not a
metered API key.

Pipeline:
  source docs + objective/audience + archetype
    -> assemble the B.3 prompt (templates/AUTHORING_GUIDE.md + one archetype)
    -> run the chosen CLI headlessly on the subscription
    -> clean the output to bare §8 markdown
    -> LINT through md_import (the spec's hard guardrail) before accepting

Nothing here calls a paid API. The CLIs authenticate against the user's plan.
"""
import os
import sys
import re
import json
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TEMPLATES = os.path.join(ROOT, "templates")

# Make the sibling engine modules importable when running un-installed
# (air-gapped bare `python3`). Idempotent; a no-op once `pip install -e .`.
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import blocks  # the block-vocabulary registry (single source of truth)

ARCHETYPES = {
    "concept-explainer": "Teach an idea/term (what → why → how → apply → recap → KC).",
    "software-procedure": "Do a task in the product (goal → steps → demo → mistakes → recap → KC).",
    "decision-scenario": "Apply a rule (rule → criteria → scenario → decision KC → debrief).",
    "policy-acceptable-use": "Compliance (core rule → why → do/don't → when unsure → KC).",
    "onboarding-company": "Onboard a new hire to the COMPANY (welcome → who we are/mission → how we "
                          "work → your first days/weeks → where to get help → KC).",
    "onboarding-role": "Onboard someone into a ROLE (your mission → core responsibilities → tools & "
                       "workflows → who you work with → what good looks like / early wins → KC).",
}

# Course PURPOSE presets — the course-side analogue of DECK_PRESETS. A PROMPT-LAYER
# profile that shapes the generated course's VOICE/DEPTH, ASSESSMENT posture, and
# LENGTH. ORTHOGONAL to the archetype (which sets the teaching STRUCTURE): a preset
# never changes the §8 block vocabulary or the brand — only tone, depth, and how hard
# the assessment leans. "standard" is the neutral default (no injection). The guidance
# is something the model adapts to the material, not a rigid mandate.
COURSE_PRESETS = {
    "standard": {
        "label": "Standard (default)",
        "desc": "Let the material and archetype decide voice and depth.",
        "voice": "", "assessment": "", "units": None,
    },
    "compliance": {
        "label": "Regulatory / policy compliance",
        "desc": "Mandatory training where the rules and their consequences must be unmissable.",
        "voice": ("Authoritative, precise, and unambiguous. State the rule plainly, then why it "
                  "matters and what happens if it's broken. No hedging; define every term; skip "
                  "humor and filler."),
        "assessment": ("Make mastery the point: prefer a graded course (`*Graded:* pass 80`) with at "
                       "least one knowledge check per unit that tests the ACTUAL rule, not trivia. "
                       "Use a `*Scenario:*` for a realistic judgment call where one fits."),
        "units": None,
    },
    "onboarding": {
        "label": "New-hire onboarding",
        "desc": "A warm, orienting introduction for someone new to the company or role.",
        "voice": ("Warm, welcoming, and relevance-first. Address the learner directly (\"you\"), "
                  "connect to their first days and what they'll actually do, and reassure. Plain "
                  "language; expand acronyms on first use."),
        "assessment": ("Keep checks light and confidence-building — a knowledge check that confirms "
                       "orientation, not a hard exam. Always point to where to get help."),
        "units": None,
    },
    "product-skill": {
        "label": "Product / software skill",
        "desc": "Teach the learner to DO a task in the product, with practice.",
        "voice": ("Practical and task-focused: show, then have them practice. Lead with the goal, "
                  "walk the concrete steps (a `*Process:*`), name the common mistake, and keep it "
                  "hands-on. Use screenshots only where 'what does it look like' genuinely helps."),
        "assessment": ("Test APPLICATION, not recall: a `*Scenario:*` ('what would you do?') or a "
                       "knowledge check on a realistic task decision beats a definition question."),
        "units": None,
    },
    "refresher": {
        "label": "Quick refresher",
        "desc": "Brief reinforcement for learners who already know the basics.",
        "voice": ("Brisk and high-signal. Assume prior exposure — skip fundamentals, lead with what "
                  "changed or what's most often gotten wrong, and stay tight. One idea per slide."),
        "assessment": "One focused knowledge check on the highest-stakes point is enough.",
        "units": "1-2",
    },
}


def list_course_presets():
    """[{key,label,desc}] for the dashboard Purpose selector on the course tab."""
    return [{"key": k, "label": v["label"], "desc": v["desc"]} for k, v in COURSE_PRESETS.items()]


def course_preset_directive(preset):
    """The prompt block injected for a course PURPOSE preset, or '' for the neutral
    default / an unknown key. Tolerant of None/garbage (mirrors _preset_directive)."""
    p = COURSE_PRESETS.get((preset or "standard"))
    if not p or not (p.get("voice") or p.get("assessment")):
        return ""
    parts = [f"COURSE PURPOSE: {p['label']} — {p['desc']}"]
    if p.get("voice"):
        parts.append("VOICE & DEPTH: " + p["voice"])
    if p.get("assessment"):
        parts.append("ASSESSMENT POSTURE: " + p["assessment"])
    if p.get("units"):
        parts.append(f"LENGTH: unless a specific unit count is set, aim for roughly {p['units']} unit(s).")
    return "\n".join(parts)


def _course_preset_block(preset):
    """The fenced PURPOSE section for a course prompt, or '' when neutral."""
    d = course_preset_directive(preset)
    return f"\n================= COURSE PURPOSE =================\n{d}\n" if d else ""

# ── Shared design-intelligence (AUTHORING GUIDE §0b) ──────────────────────────
# The single source of truth for "which structure fits this content." Used by BOTH
# the course generator (build_prompt) and the deck generator (build_deck_prompt) so
# the two pipelines never drift. Block-level extras (cards/note/statement/chart) are
# course-only; the 5 named slide layouts are all a deck has.
LAYOUT_MATCH = (
    "- Ordered steps / a how-to / a pipeline → process (numbered, single-column).\n"
    "- 2–3 things compared, A vs B, or old vs new → comparison (side-by-side panels).\n"
    "- Phases, a roadmap, dates, or chronology → timeline.\n"
    "- One big idea = a problem + a framework + goals → infographic poster.\n"
    "- A section break or title → divider."
)

# Course-only block choices, layered on top of LAYOUT_MATCH.
COURSE_LAYOUT_EXTRA = (
    "- Parallel peer items (features, roles, components, gates) → a *Cards:* grid.\n"
    "- A 'what would you do?' decision case → a *Scenario:* (a situation + response choices each with "
    "feedback; mark the best choice `· preferred`). Ideal for decision/judgment practice. To BRANCH "
    "(different choices lead to different next scenes), give each destination scene an `id: <name>` "
    "line and route a choice with `· goto: <name>`; a branching scene needs no `· preferred`.\n"
    "- A predict-then-reveal, or pacing a long unit so the learner commits before a reveal → a "
    "*Continue:* gate (hides everything after it until the learner clicks; use it deliberately, not "
    "as decoration).\n"
    "- CHOOSE AN INTERACTION BY LEARNING OBJECTIVE, not for novelty (AUTHORING GUIDE §0b.2 chooser): "
    "LABEL a diagram/screenshot/interface → *DragDrop:* (with an `image:` + positioned `zone:`s); "
    "CLASSIFY / sort items into groups → *Categorize:*; ORDER steps or a chronology → *Sequence:*; "
    "ASSOCIATE pairs (term↔definition, cause↔effect, role↔tool) → *Matching:*; RECALL a term in context "
    "→ *FillBlank:*; RECALL a term from its definition → *Crossword:*; PRIME vocabulary before teaching "
    "it (recognition only, not assessment) → *WordSearch:*; REVIEW across 2–4 topics → *QuizBoard:*; "
    "randomized RETRIEVAL practice → *GameShow:*; build FLUENCY on facts that must be fast → "
    "*SpeedStreak:*. Pick the activity whose interaction matches what the learner must DO with the "
    "knowledge; full grammar for each is in the AUTHORING GUIDE.\n"
    "- The teaching substance itself → ordinary paragraphs (single column).\n"
    "- Use a MULTI-COLUMN block (comparison/cards) ONLY when the items are truly parallel and short "
    "enough to scan side-by-side; if they are sequential, dependent, or long, keep ONE column "
    "(forcing serial content into columns splits attention).\n"
    "- GRADED COURSES (`*Graded:* pass 80`): to report a per-topic SUBSCORE and require mastery of a "
    "topic, wrap the topic's knowledge checks with a named section `*Section:* blue · <Topic> · pass 70` "
    "(and `*Section:* end`). KCs sharing the same `<Topic>` name roll up into one scored objective; only "
    "KCs inside a graded section count toward the grade (inline KCs stay formative/practice). Omit "
    "`· pass N` to report the subscore without gating on it. Add `*Gate:* off` (default on) if the course "
    "should COMPLETE even when the learner fails — informational courses that still report a score."
)

# Media selection — Mayer's multimedia principles (coherence/signaling/contiguity).
MEDIA_RULES = (
    "- DEFAULT IS NO IMAGE. Add a visual ONLY when it carries information or genuinely aids pacing; "
    "gratuitous 'filler' decoration measurably HURTS learning (coherence). Never add an image to fill "
    "space.\n"
    "- Software UI / 'where do I click / what does it look like' → *Visual:* screenshot.\n"
    "- A sequence or motion that must be SEEN performed → a VIDEO in the Build-Notes Media plan (not a "
    "still, not *Visual:*).\n"
    "- Structure, flow, relationships, architecture, before→after → *Visual:* diagram.\n"
    "- A purely emotional/pacing hook with no information → *Visual:* decorative, sparingly, at a "
    "section opener only (decorative ⇒ no caption).\n"
    "- One visual per idea, placed next to the text it supports (contiguity).\n"
    "- ALT TEXT (accessibility, always-on): every informative `*Visual:*` MUST include its "
    "`<description / alt text>` middle segment — a short, specific description of what the image "
    "CONVEYS to a learner who cannot see it (the meaning, not 'image of…' or the filename). Only a "
    "`*Visual:* decorative` may omit the description (screen readers skip it). A screenshot, diagram, "
    "graphic, or photo with a blank description is an accessibility defect."
)

# Emphasis — signaling principle (emphasis only works when sparse).
EMPHASIS_RULES = (
    "- Paragraph = the actual teaching exposition (the substance).\n"
    "- *Note:* = a SECONDARY aside (caution/tip/exception/'good to know'), set apart from the main "
    "flow — if it is core teaching, it is a paragraph, not a note.\n"
    "- *Statement:* = ONE memorable principle to land; use rarely (≈1 per unit) or it stops signaling."
)

# Data → chart, with the no-fabrication guardrail (folded in from the old standalone rule).
CHART_RULE = (
    "- Real quantitative data FROM THE SOURCE → *Chart:* — but plot ONLY numbers that appear "
    "LITERALLY in the source (never estimate, round from vague language, extrapolate, or invent), and "
    "every chart MUST end with a `source:` line. No real numbers → write prose; a sourceless chart is "
    "rejected by the build. Add a `takeaway:` line — ONE plain-language sentence stating the single "
    "most important insight the chart shows (the 'so what'), drawn only from the plotted numbers. "
    "Chart types: `bar`, `groupedBar`, `stackedBar`, `horizontalBar`, `horizontalStackedBar`, "
    "`line`, `area`, `pie`, `donut` — pick the one that fits (horizontal bars when category names "
    "are long; a part-to-whole share → pie/donut; a trend over time → line/area)."
)

# Taste / anti-slop discipline. Distilled from the "anti-slop frontend" taste
# principles (read-the-room, anti-default, cut-ruthlessly, no-AI-tells) and
# INVERTED for this tool's reality: the brand design system — palette, fonts,
# and the fixed layout set — is LOCKED, so "taste" here is not reaching past the
# defaults (the frontend skill's stance) but using the locked system with
# restraint and deliberate variety. See templates/TASTE_GUIDE.md.
TASTE_RULE = (
    "- TASTE (anti-sameness, always-on): the brand palette, fonts and layout set are FIXED — never "
    "invent a font, color, or layout. Taste here is VARIETY and RESTRAINT inside that system. Do NOT "
    "default the whole thing to one look: vary the layout family across sections (don't repeat the same "
    "layout on back-to-back slides) and vary the accent across sections rather than pinning everything "
    "to one accent.\n"
    "- CUT RUTHLESSLY: one idea per slide. Short heading, tight body. No data-dumps; if content "
    "overflows, move it to another slide or a better-fitting layout — never cram, and never split a "
    "single chart/diagram/table across slides.\n"
    "- COPY, NO AI TELLS: use concrete verbs, not filler ('elevate', 'seamless', 'unleash', 'leverage', "
    "'robust', 'next-gen', 'revolutionize', 'unlock', 'empower' are banned as filler). No fake-precise "
    "numbers — cite a statistic only if it appears LITERALLY in the source. Use real specifics, never "
    "'John Doe'/'Acme'. Name a step by what it DOES ('Submit the request'), not 'Step 1 / Stage 1'. "
    "Avoid the em-dash-as-flourish tell: prefer a period, comma, or colon.\n"
    "- QUOTES: keep a quote to about three lines, trimmed to the point; attribute it with a name AND "
    "role, never a bare name."
)

# subscription-authenticated CLIs we drive headlessly (NOT metered APIs).
# Each runs on the user's plan via its own login — no API key is ever passed.
PROVIDERS = {
    "claude": {
        "label": "Claude (Claude Code subscription)",
        "bin": "claude",
        # `claude -p` reads the prompt from stdin and prints the answer to stdout.
        # Scrub CLAUDECODE so it still works if the dashboard is launched from a
        # Claude Code terminal (Claude Code refuses to nest otherwise).
        "scrub_env": ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"),
        "install": "Claude Pro/Max — `claude` is the Claude Code CLI; run `claude` once and log in.",
    },
    "codex": {
        "label": "ChatGPT (OpenAI Codex subscription)",
        "bin": "codex",
        # `codex exec -` reads the FULL prompt from stdin; --output-last-message
        # writes ONLY the final agent message (clean, no event chatter).
        # Scrub OPENAI_API_KEY / CODEX_API_KEY so Codex authenticates via the
        # ChatGPT *subscription* login, never an accidental metered API key.
        "scrub_env": ("OPENAI_API_KEY", "CODEX_API_KEY"),
        "install": "ChatGPT Plus/Pro/Business/Enterprise — install with `npm install -g @openai/codex` "
                   "(or `brew install --cask codex`), then run `codex` and choose "
                   "“Sign in with ChatGPT” (not an API key).",
    },
}


def provider_status():
    """Which subscription CLIs are installed on this machine."""
    out = {}
    for key, p in PROVIDERS.items():
        out[key] = {"label": p["label"], "available": shutil.which(p["bin"]) is not None,
                    "install": p["install"]}
    return out


def list_archetypes():
    return [{"key": k, "desc": v} for k, v in ARCHETYPES.items()]


# --------------------------------------------------------------- source reading

# Formats are read CROSS-PLATFORM (pure-Python) wherever possible so PC and Mac
# teammates get the same result. macOS `textutil` is used as a higher-fidelity
# fallback for the rich formats when present, but is never required.
_PLAINTEXT_EXTS = (".md", ".txt", ".markdown", ".text", ".csv", ".tsv", ".log", ".rst")
_OCR_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp")
# C1 — transcripts + media as course sources. A caption file is parsed into clean
# prose (cue numbers/settings/tags stripped); a media file is transcribed by the
# LOCAL Whisper seam (captions.py — no metered API) and parsed the same way.
_TRANSCRIPT_EXTS = (".vtt", ".srt")
_MEDIA_EXTS = (".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi",
               ".mp3", ".m4a", ".wav", ".ogg", ".oga", ".flac", ".aac")
# Legacy binary .doc has no reliable cross-platform reader — we deliberately call it
# out (open in Word → Save As .docx) instead of relying on a macOS-only converter,
# so the behavior is identical for everyone on the team.
_CALLOUT_EXTS = {".doc": "legacy .doc — open in Word and “Save As” .docx"}

# C5 — ingestion bounds (defense-in-depth). A stray huge file or a decompression
# bomb (a tiny .odt/image that expands to gigabytes) shouldn't OOM the operator's
# machine; it should skip with a note. Limits are generous for real course sources.
_MAX_SOURCE_BYTES = 64 * 1024 * 1024            # per-file on-disk cap (64 MB)
_MAX_TOTAL_SOURCE_BYTES = 256 * 1024 * 1024     # cap across all sources in one read
_MAX_DECOMPRESSED_BYTES = 64 * 1024 * 1024      # cap a single zip member (odt) decompressed
_MAX_IMAGE_PIXELS = 64 * 1024 * 1024            # ~64 MP — caps a decompression-bomb image


def _read_via_textutil(path):
    """macOS-native text extraction (high fidelity). Returns text, or None when
    textutil is unavailable (non-macOS) or the conversion fails — so the caller
    can fall back to the cross-platform reader."""
    import shutil
    import subprocess
    if not shutil.which("textutil"):
        return None
    try:
        r = subprocess.run(["textutil", "-convert", "txt", "-stdout", path],
                           capture_output=True, text=True, timeout=90)
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def _strip_markup(xml):
    """Crude tag-strip + entity-unescape — good enough to turn HTML/ODT body XML
    into readable source text for the model."""
    import html
    import re
    xml = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", xml)
    xml = re.sub(r"(?is)</(p|div|br|li|tr|h[1-6]|para|text:p)\s*>", "\n", xml)
    xml = re.sub(r"(?s)<[^>]+>", " ", xml)
    text = html.unescape(xml)
    return re.sub(r"[ \t]*\n[ \t]*", "\n", re.sub(r"[ \t]+", " ", text)).strip()


def _html_to_text(path):
    try:
        return _strip_markup(open(path, encoding="utf-8", errors="replace").read())
    except OSError:
        return ""


_URL_TIMEOUT = 20                               # seconds for a source-URL fetch


def _read_url(url):
    """Fetch a URL with the stdlib (no extra deps, no metered API) and return its
    readable text. HTML is run through the same tag-strip as local .html sources;
    other text content is returned verbatim. Returns the text, or None on any
    failure (unreachable host, timeout, HTTP error, oversized body, binary) — the
    caller turns None into an actionable skip note rather than a silent drop.
    Honors the per-file byte cap; offline → None."""
    import urllib.request
    import urllib.error
    if not url or not url.lower().startswith(("http://", "https://", "file://")):
        return None
    req = urllib.request.Request(url, headers={"User-Agent": "course-builder/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=_URL_TIMEOUT) as resp:
            ctype = (resp.headers.get_content_type() or "").lower()
            # read one byte past the cap so an oversized body is detected, not truncated
            raw = resp.read(_MAX_SOURCE_BYTES + 1)
            charset = resp.headers.get_content_charset() or "utf-8"
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if len(raw) > _MAX_SOURCE_BYTES:
        return None                               # oversized → skip-with-note
    if ctype and not (ctype.startswith("text/") or "html" in ctype
                      or "xml" in ctype or "json" in ctype):
        return None                               # binary (pdf/image/…): not a text source
    body = raw.decode(charset, "replace")
    if "html" in ctype or "xml" in ctype or "<html" in body[:2048].lower():
        return _strip_markup(body)
    return body


def _odt_to_text(path):
    """ODT is a zip; the body lives in content.xml. Pure-Python, cross-platform."""
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            # C5: refuse a decompression bomb — check the member's DECLARED
            # uncompressed size before reading it into memory.
            if z.getinfo("content.xml").file_size > _MAX_DECOMPRESSED_BYTES:
                return ""
            return _strip_markup(z.read("content.xml").decode("utf-8", "replace"))
    except Exception:
        return ""


def _rtf_to_text(path):
    """Minimal RTF → text: drop control words/groups, keep the literal runs.
    Not a full RTF parser, but enough to recover source prose cross-platform."""
    import re
    try:
        rtf = open(path, encoding="latin-1", errors="replace").read()
    except OSError:
        return ""
    rtf = re.sub(r"\\par[d]?\b", "\n", rtf)
    rtf = re.sub(r"\\'[0-9a-fA-F]{2}", "", rtf)        # hex-escaped bytes
    rtf = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", rtf)       # control words
    rtf = rtf.replace("{", "").replace("}", "")
    return re.sub(r"\n[ \t]*", "\n", rtf).strip()


def _tesseract_cmd():
    """Locate the Tesseract binary cross-platform. It's on PATH on macOS/Linux
    (brew/apt) and usually on Windows too — BUT the UB-Mannheim Windows installer
    drops `tesseract.exe` under Program Files and does NOT add it to PATH, so an
    operator who installs it can still hit a false "OCR not available". So when
    `shutil.which` misses on Windows, also probe the default install locations.
    Returns the binary path, or None if Tesseract genuinely isn't installed."""
    found = shutil.which("tesseract")
    if found:
        return found
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            cand = os.path.join(base, "Tesseract-OCR", "tesseract.exe")
            if os.path.isfile(cand):
                return cand
    return None


def _ocr_image(path):
    """Read text out of an image via Tesseract OCR (cross-platform). Returns the
    text, "" if the image holds no text, or None when OCR isn't available (so the
    file is reported as skipped with an install hint rather than silently dropped).
    Needs the `tesseract` binary (see _tesseract_cmd) + the `pytesseract` package;
    Pillow ships with the engine already."""
    cmd = _tesseract_cmd()
    if not cmd:
        return None
    try:
        import pytesseract
        from PIL import Image
    except Exception:
        return None
    # On Windows the binary is often off PATH (found via the install-path probe),
    # so point pytesseract straight at it; harmless to set on every platform.
    pytesseract.pytesseract.tesseract_cmd = cmd
    # C5: cap pixels so a decompression-bomb image raises (and is skipped) instead
    # of allocating gigabytes; PIL warns at the cap and errors at 2x it.
    Image.MAX_IMAGE_PIXELS = _MAX_IMAGE_PIXELS
    try:
        return pytesseract.image_to_string(Image.open(path)) or ""
    except Exception:
        return None


def _ocr_pdf(path):
    """Tier-2 PDF reader: render each page to a PIL image and OCR via Tesseract.
    Called when pypdf extracts no text (scanned / image-based PDF). Returns text,
    "" when OCR runs but the pages hold no readable text, or None when a required
    backend is absent — so the caller reports a skip-with-install-hint rather than
    silently dropping the file. Needs Tesseract + pymupdf (`pip install pymupdf`)."""
    cmd = _tesseract_cmd()
    if not cmd:
        return None
    try:
        import fitz          # pymupdf — renders PDF pages to bitmaps
        import io
        import pytesseract
        from PIL import Image
    except Exception:
        return None
    pytesseract.pytesseract.tesseract_cmd = cmd
    Image.MAX_IMAGE_PIXELS = _MAX_IMAGE_PIXELS
    try:
        doc = fitz.open(path)
        pages = []
        for page in doc:
            # 2× scale gives Tesseract enough resolution to be accurate on typical
            # 72-dpi PDF pages without blowing up memory for large documents.
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            pages.append(pytesseract.image_to_string(img) or "")
        doc.close()
        return "\n".join(pages)
    except Exception:
        return ""


# ---- C1: transcript → prose --------------------------------------------------

# Paragraph/marker cadence for transcript prose. A gap between cues of at least
# _TRANSCRIPT_GAP starts a new paragraph (a weak-but-real topic-boundary signal);
# a sparse [m:ss] marker is kept at most every _TRANSCRIPT_MARKER_EVERY so the
# model sees WHERE in the recording a passage sits without timestamp noise on
# every line (James's fork: provider segments, timestamps as hints).
_TRANSCRIPT_GAP = 2.0             # seconds of silence → paragraph break
_TRANSCRIPT_MARKER_EVERY = 60.0   # min seconds between kept [m:ss] markers

# `00:01:02.345 --> 00:01:04.000 align:start` (VTT) or `00:01:02,345 --> …` (SRT);
# the hour part is optional in VTT.
_CUE_TS_RE = re.compile(
    r"^\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[.,](\d{1,3})\s*-->\s*"
    r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")


def _cue_seconds(h, m, s, ms):
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int((ms or "0").ljust(3, "0")) / 1000.0


def _mark_ts(seconds):
    """Seconds → a compact `[m:ss]` / `[h:mm:ss]` source-position marker."""
    t = max(0, int(seconds))
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"[{h}:{m:02d}:{s:02d}]" if h else f"[{m}:{s:02d}]"


def _parse_cues(text):
    """Parse WebVTT or SRT into `[(start, end, text), ...]`. Headers (WEBVTT,
    NOTE/STYLE blocks), numeric cue indexes, cue settings after the arrow and
    inline tags (`<v Name>`, `<i>`, …) are all dropped. Tolerant — a malformed
    block is skipped, never raised on."""
    import html
    cues = []
    cur = None                                    # (start, end, [lines])
    in_note = False
    for line in (text or "").splitlines():
        m = _CUE_TS_RE.match(line)
        if m:
            in_note = False
            if cur and cur[2]:
                cues.append((cur[0], cur[1], " ".join(cur[2])))
            cur = (_cue_seconds(*m.groups()[:4]), _cue_seconds(*m.groups()[4:]), [])
            continue
        stripped = line.strip()
        if not stripped:                          # blank line ends a cue / NOTE block
            if cur and cur[2]:
                cues.append((cur[0], cur[1], " ".join(cur[2])))
            cur = None
            in_note = False
            continue
        if cur is None:
            # Between cues: WEBVTT header, NOTE/STYLE/REGION blocks, SRT indexes.
            if stripped.upper().startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
                in_note = True
                continue
            if stripped.isdigit() or in_note:
                continue
            continue                              # stray text outside any cue
        clean = html.unescape(re.sub(r"<[^>]+>", "", stripped)).strip()
        if clean:
            cur[2].append(clean)
    if cur and cur[2]:
        cues.append((cur[0], cur[1], " ".join(cur[2])))
    return cues


def _transcript_to_prose(text):
    """VTT/SRT text → clean prose paragraphs with sparse `[m:ss]` position
    markers. Consecutive duplicate cue texts (rolling captions) are dropped.
    Returns "" when nothing parses; never raises."""
    cues = _parse_cues(text)
    paras, buf = [], []
    last_end = None
    last_marker = None
    para_start = None
    for start, end, cue in cues:
        if buf and cue == buf[-1]:
            last_end = end
            continue
        # Break on a silence gap, or once a paragraph runs long — unbroken
        # narration still gets a marker opportunity every ~minute.
        if buf and ((last_end is not None and start - last_end >= _TRANSCRIPT_GAP)
                    or start - para_start >= _TRANSCRIPT_MARKER_EVERY):
            paras.append((para_start, " ".join(buf)))
            buf = []
        if not buf:
            para_start = start
        buf.append(cue)
        last_end = end
    if buf:
        paras.append((para_start, " ".join(buf)))
    out = []
    for start, body in paras:
        if last_marker is None or start - last_marker >= _TRANSCRIPT_MARKER_EVERY:
            out.append(f"{_mark_ts(start)} {body}")
            last_marker = start
        else:
            out.append(body)
    return "\n\n".join(out)


def _transcribe_media(path):
    """Transcribe a media file to VTT via the LOCAL Whisper seam (captions.py,
    M3 — no metered API). Returns VTT text, or None when no backend is installed
    or the run fails. Module-level so tests can stub it."""
    try:
        import captions
        return captions.transcribe_to_vtt(path)
    except Exception:
        return None


def _read_one(path):
    low = path.lower()
    if low.endswith(_PLAINTEXT_EXTS):
        try:
            return open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            return ""
    if low.endswith(".docx"):
        try:
            from docx import Document
            return "\n".join(p.text for p in Document(path).paragraphs)
        except Exception:
            return _read_via_textutil(path)       # mac fallback if python-docx chokes
    if low.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            text = "\n".join((pg.extract_text() or "") for pg in PdfReader(path).pages)
            if text.strip():
                return text
        except Exception:
            pass
        return _ocr_pdf(path)   # tier-2: scanned / image-based PDF
    if low.endswith((".html", ".htm")):
        return _read_via_textutil(path) or _html_to_text(path)
    if low.endswith(".odt"):
        return _read_via_textutil(path) or _odt_to_text(path)
    if low.endswith((".rtf", ".rtfd")):
        return _read_via_textutil(path) or _rtf_to_text(path)
    if low.endswith(_OCR_IMAGE_EXTS):
        return _ocr_image(path)                   # OCR (cross-platform via Tesseract)
    if low.endswith(_TRANSCRIPT_EXTS):            # C1: caption file → clean prose
        try:
            raw = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            return ""
        return _transcript_to_prose(raw)
    if low.endswith(_MEDIA_EXTS):                 # C1: media → local Whisper → prose
        vtt = _transcribe_media(path)
        if vtt is None:
            return None                           # no backend → skip-with-note
        return _transcript_to_prose(vtt)
    return None                                   # .doc + anything else → see _CALLOUT_EXTS


def _skip_reason(name):
    """A human, actionable note for a file we couldn't read (shown in the UI)."""
    ext = os.path.splitext(name)[1].lower()
    if ext in _CALLOUT_EXTS:
        return f"{name} ({_CALLOUT_EXTS[ext]})"
    if ext == ".pdf":
        missing = []
        if not _tesseract_cmd():
            missing.append("Tesseract OCR")
        try:
            import fitz  # noqa: F401
        except Exception:
            missing.append("pymupdf (`pip install pymupdf`)")
        if missing:
            return (f"{name} (scanned PDF — install {' and '.join(missing)} "
                    f"to extract text from image-based pages)")
        return f"{name} (scanned PDF — OCR failed)"
    if ext in _OCR_IMAGE_EXTS:
        return f"{name} (image — install Tesseract OCR to read text from images)"
    if ext in _MEDIA_EXTS:
        return (f"{name} (media — install faster-whisper (`pip install "
                f"faster-whisper`) or a whisper.cpp binary to transcribe it)")
    return name


def _coerce_urls(urls):
    """Normalize the `urls` arg (a list, or a newline/comma-separated string from
    the dashboard) into a clean list of non-empty URL strings."""
    if not urls:
        return []
    if isinstance(urls, str):
        import re
        urls = re.split(r"[\n,]+", urls)
    return [u.strip() for u in urls if u and u.strip()]


def read_sources(path, urls=None):
    """Concatenate readable source docs from a FOLDER or a single FILE, plus any
    URLs (Q6 — a pasted link is fetched and tag-stripped into a source alongside
    files). Caption files (.vtt/.srt) and media files (C1 — transcribed by the
    local Whisper seam) enter as cleaned SOURCE TRANSCRIPT prose. Returns
    (text, used_files, skipped_files). Skipped entries carry an actionable note
    (e.g. a .doc to convert, an image needing OCR, media needing Whisper, an
    unreachable URL)."""
    path = os.path.expanduser(path or "")
    used, skipped, parts = [], [], []
    if os.path.isfile(path):
        targets = [path]
    elif os.path.isdir(path):
        targets = [os.path.join(path, n) for n in sorted(os.listdir(path), key=str.lower)
                   if not n.startswith(".")]
    else:
        targets = []                              # no file/folder, but URLs may still apply
    total = 0
    for full in targets:
        if not os.path.isfile(full):
            continue
        name = os.path.basename(full)
        low = name.lower()
        # C1: a media file is never loaded whole — Whisper streams it and only the
        # (small) transcript enters the source set, so the on-disk byte caps don't
        # apply; its transcript text is charged to the total instead, below.
        is_media = low.endswith(_MEDIA_EXTS)
        try:
            size = os.path.getsize(full)
        except OSError:
            size = 0
        # C5: skip an over-large file (and stop once the whole source set gets too
        # big) with an actionable note, rather than loading it and risking OOM.
        if not is_media and size > _MAX_SOURCE_BYTES:
            skipped.append(f"{name} (skipped — larger than "
                           f"{_MAX_SOURCE_BYTES // (1024 * 1024)} MB)")
            continue
        if not is_media and total + size > _MAX_TOTAL_SOURCE_BYTES:
            skipped.append(f"{name} (skipped — source set exceeds the "
                           f"{_MAX_TOTAL_SOURCE_BYTES // (1024 * 1024)} MB total cap)")
            continue
        if not is_media:
            total += size
        text = _read_one(full)
        if text is None:
            skipped.append(_skip_reason(name))    # unreadable — with a how-to note
            continue
        if text.strip():
            if is_media or low.endswith(_TRANSCRIPT_EXTS):
                tsize = len(text.encode("utf-8", "replace"))
                if is_media:
                    if total + tsize > _MAX_TOTAL_SOURCE_BYTES:
                        skipped.append(f"{name} (skipped — source set exceeds the "
                                       f"{_MAX_TOTAL_SOURCE_BYTES // (1024 * 1024)} MB total cap)")
                        continue
                    total += tsize
                parts.append(f"===== SOURCE TRANSCRIPT: {name} =====\n"
                             f"(Spoken-word transcript; [m:ss] markers show position "
                             f"in the recording — use them to find topic boundaries, "
                             f"never copy them into the course.)\n{text.strip()}")
            else:
                parts.append(f"===== SOURCE DOCUMENT: {name} =====\n{text.strip()}")
            used.append(name)
    # Q6: fetch any URLs as additional sources (offline/onfail → skip-with-note).
    for url in _coerce_urls(urls):
        text = _read_url(url)
        if text is None:
            skipped.append(f"{url} (skipped — could not fetch a readable page; "
                           f"check the link, your connection, or that it isn't too large)")
            continue
        if text.strip():
            size = len(text.encode("utf-8", "replace"))
            if total + size > _MAX_TOTAL_SOURCE_BYTES:
                skipped.append(f"{url} (skipped — source set exceeds the "
                               f"{_MAX_TOTAL_SOURCE_BYTES // (1024 * 1024)} MB total cap)")
                continue
            total += size
            parts.append(f"===== SOURCE URL: {url} =====\n{text.strip()}")
            used.append(url)
    return "\n\n".join(parts), used, skipped


# --------------------------------------------------------------- prompt assembly

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")


def list_images(folder):
    """Filenames of the image assets available in `folder` (for the prompt)."""
    if not folder or not os.path.isdir(folder):
        return []
    return sorted(n for n in os.listdir(folder)
                  if n.lower().endswith(_IMAGE_EXTS) and not n.startswith("."))


def brand_image_dir(brand_name):
    """The brand's built-in image LIBRARY folder (<brand>/images), or None. Lets a
    deck draw on on-brand template imagery by default — without the author having
    to pick an images folder. Used as the fallback when no folder is selected."""
    try:
        import brand as _brand
        d = _brand.load_brand(brand_name).asset("images")
        return d if d and os.path.isdir(d) else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# M4 — Glossary / termbank + banned-words guardrail.
# A brand-level `glossary.json` (preferred terms + a banned word list) merged the
# same way brand.json is: the universal `_default` layer UNDER the profile layer.
# Two jobs: (1) inject approved terminology into the generation prompt so the model
# uses the right product names; (2) raise a BLOCKING lint error when a banned word
# or a wrong-term ("instead_of") phrase appears in generated markdown. Both default
# OFF (glossary=None / empty) so callers that pass nothing are byte-identical.
# ---------------------------------------------------------------------------

def load_glossary(brand_name=None):
    """Merge the universal `_default` glossary UNDER `<brand>/glossary.json`.
    `preferred` lists are concatenated (profile after default); `banned` words are
    unioned (case-insensitively, order-stable). Returns {"preferred": [...],
    "banned": [...]} — empty lists if no glossary files exist. Never raises."""
    import json as _json

    def _read(d):
        if not d:
            return {}
        p = os.path.join(d, "glossary.json")
        try:
            with open(p, encoding="utf-8") as fh:
                data = _json.load(fh)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    try:
        import brand as _brand
        b = _brand.load_brand(brand_name if brand_name else _brand.DEFAULT)
        default_dir = os.path.join(_brand.BRANDS_DIR, _brand.DEFAULT)
        profile_dir = b.path
    except Exception:
        return {"preferred": [], "banned": []}

    layers = [_read(default_dir)]
    if profile_dir and os.path.abspath(profile_dir) != os.path.abspath(default_dir):
        layers.append(_read(profile_dir))

    preferred, banned, seen = [], [], set()
    for layer in layers:
        for entry in (layer.get("preferred") or []):
            if isinstance(entry, dict) and (entry.get("term") or "").strip():
                preferred.append(entry)
        for w in (layer.get("banned") or []):
            w = (w or "").strip()
            if w and w.lower() not in seen:
                seen.add(w.lower())
                banned.append(w)
    return {"preferred": preferred, "banned": banned}


def _glossary_is_empty(glossary):
    return not glossary or (not glossary.get("preferred") and not glossary.get("banned"))


def glossary_prompt_block(glossary):
    """A TERMINOLOGY rule line for the generation prompt, or "" when the glossary is
    empty (so prompts stay byte-identical without a glossary). Lists each approved
    term (with the shorthand to avoid) and the banned words, on ONE `- ` rule line
    matching the surrounding always-on rules."""
    if _glossary_is_empty(glossary):
        return ""
    parts = []
    terms = []
    for e in glossary.get("preferred") or []:
        term = (e.get("term") or "").strip()
        if not term:
            continue
        avoid = [a for a in (e.get("instead_of") or []) if (a or "").strip()]
        terms.append(f"“{term}”" + (f" (never {', '.join(repr(a) for a in avoid)})" if avoid else ""))
    if terms:
        parts.append("use the APPROVED terms exactly — " + "; ".join(terms))
    banned = [w for w in (glossary.get("banned") or []) if (w or "").strip()]
    if banned:
        parts.append("NEVER use these banned words: " + ", ".join(banned))
    if not parts:
        return ""
    return ("- TERMINOLOGY (always-on — approved termbank; the build REJECTS a banned word or wrong "
            "term): " + ". ".join(parts) + ".")


# Code/URL spans that should not be scanned for banned/wrong terms (a banned word
# inside a code sample or a URL is not prose). Stripped before the word scan.
_GLOSS_STRIP = [
    re.compile(r"```.*?```", re.S),       # fenced code
    re.compile(r"`[^`]*`"),               # inline code
    re.compile(r"\]\([^)]*\)"),           # markdown link/image targets
    re.compile(r"https?://\S+"),          # bare URLs
]


def _gloss_scrub(md_text):
    t = md_text or ""
    for rx in _GLOSS_STRIP:
        t = rx.sub(" ", t)
    return t


def glossary_lint_issues(md_text, glossary):
    """Blocking lint findings (list of error strings) for generated markdown: each
    BANNED word that appears, and each wrong-term `instead_of` phrase (→ "use the
    approved term"). Whole-word, case-insensitive; code spans/URLs are excluded so a
    banned word in a code sample doesn't false-fire. Empty glossary → no findings."""
    if _glossary_is_empty(glossary):
        return []
    text = _gloss_scrub(md_text)
    errors = []
    for w in glossary.get("banned") or []:
        w = (w or "").strip()
        if w and re.search(rf"(?i)\b{re.escape(w)}\b", text):
            errors.append(f"banned word “{w}” appears in the output — remove it "
                          f"(non-approved/filler term; see the brand glossary)")
    for e in glossary.get("preferred") or []:
        term = (e.get("term") or "").strip()
        for bad in (e.get("instead_of") or []):
            bad = (bad or "").strip()
            if bad and re.search(rf"(?i)\b{re.escape(bad)}\b", text):
                errors.append(f"wrong term “{bad}” appears — use the approved term "
                              f"“{term}” (brand glossary)")
    return errors


def _image_directive(images):
    """Tell the model the EXACT image files it may place — or none. Without this the
    model invents slot filenames that match nothing and render as broken images."""
    if images:
        listing = "\n".join("    - " + n for n in images)
        return ("AVAILABLE IMAGES — the ONLY image files that exist. Use a `*Visual:* <type> · "
                "<desc> · slot: `exact-filename`` ONLY for a file in this list, and only where it "
                "genuinely aids learning. If none fits a slide, use NO image. NEVER invent a "
                "filename — an unmatched slot renders nothing.\n" + listing)
    return ("AVAILABLE IMAGES: none. Do NOT reference image files or put a `slot:` on a *Visual:* — "
            "describe the intended visual in words only, where it helps.")


def build_prompt(objective, audience, archetype, n_units, sources_text, course_title=None,
                 images=None, preset=None, glossary=None):
    guide_path = os.path.join(TEMPLATES, "AUTHORING_GUIDE.md")
    guide = open(guide_path, encoding="utf-8").read() if os.path.isfile(guide_path) else ""
    arch_path = os.path.join(TEMPLATES, f"{archetype}.md")
    archetype_text = open(arch_path, encoding="utf-8").read() if os.path.isfile(arch_path) else ""

    unit_instr = (f"Produce exactly {n_units} microlearning unit(s). Even at a fixed count, apply the "
                  "backward-design discipline (AUTHORING GUIDE §0.4): map the source's learning points "
                  "and distribute them across the units so coverage is complete and prerequisite-ordered."
                  if n_units
                  else "Decompose the material with BACKWARD DESIGN (AUTHORING GUIDE §0.4): first derive "
                       "the full set of learning points the source supports, then segment them into "
                       "however many 10–15-minute units it takes so that EVERY learning point lands in "
                       "some unit (one `## Microlearning N:` per unit). Sequence units by prerequisite "
                       "(earlier enables later; never reference what hasn't been taught) and avoid "
                       "redundancy. The unit count is driven by COMPLETE COVERAGE of the source, NOT by "
                       "the number of learning objectives. One objective may span several units, and one "
                       "unit may serve several objectives. Never cap the number of units to the number of "
                       "objectives listed — segment the full material end to end. When you produce more "
                       "than one unit, add a `**Curriculum Rationale:**` line in the file preamble "
                       "stating why this set of units and this order (§0.4).")
    title_line = f"Course/batch title: {course_title}\n" if course_title else ""

    # Coming-soon block types (schema + renderer exist, but no authoring grammar
    # yet — produced only by Rise/docx import). Naming them keeps the AI from
    # emitting a half-wired block that would silently degrade. Sourced from the
    # registry so this list can never drift from blocks.BLOCKS.
    coming_soon = ", ".join(sorted(blocks.coming_soon_types()))
    coming_soon_rule = (
        f"- COMING SOON (do NOT author): the block types [{coming_soon}] are not yet "
        "authorable — they exist only as import-only stubs. Never emit them; use the "
        "available §8 grammar instead.") if coming_soon else ""
    _gloss = glossary_prompt_block(glossary)
    gloss = ("\n" + _gloss) if _gloss else ""

    return f"""You are an instructional designer drafting a microlearning SCRIPT in the \
exact markdown grammar the build pipeline consumes. Follow the AUTHORING GUIDE and the chosen \
ARCHETYPE precisely.

HARD OUTPUT RULES:
- Output ONLY the markdown script. No preamble, no explanation, no surrounding ``` code fences.
- Start the response with the first `## Microlearning 1: <Title>` line.
- It MUST parse through the §8 grammar on the first try (Slide 1 is always Learning Objectives with
  a *Visual:*; KCs use the `- A)` form with exactly one `*Correct Answer:*`).
- Ground every slide ONLY in the SOURCE MATERIAL. Do NOT invent product behavior or facts.
{coming_soon_rule}
- {unit_instr}
- PEDAGOGY (always-on — AUTHORING GUIDE §0): write for an ADULT learner. Open each unit with the
  learner's stake/relevance (Knowles), connect to prior experience, and stay problem-centered. Build
  each unit as problem → demonstrate → apply → integrate (Merrill), riding Gagné's nine events as the
  slide spine (hook → objectives → recall → present → guidance → KC → feedback → assess → recap/
  transfer). A draft that parses but is a flat content-dump is a DEFECT, not a pass.
- MEDIA & LAYOUT (always-on — AUTHORING GUIDE §0b): match each piece of content to its right
  treatment — these are grounded design rules, not style. Which structure fits the content:
{LAYOUT_MATCH}
{COURSE_LAYOUT_EXTRA}
  Which media (or none):
{MEDIA_RULES}
{CHART_RULE}
  Emphasis (note vs statement vs paragraph):
{EMPHASIS_RULES}
- TASTE (always-on — restraint + variety inside the locked brand system):
{TASTE_RULE}{gloss}
- DEFENSIBLE DESIGN: every unit's Build Notes MUST include a `Design Rationale:` line that states WHY
  the unit is built as it is — named to the §0 (pedagogy) AND §0b (media/layout) principles, covering
  BOTH the structure and the PRESENTATION choices (why this layout, why this media treatment or none,
  why a note vs prose). Keep it to 1–3 short lines, under the `**Articulate Build Notes:**` marker.

{_image_directive(images)}
{_course_preset_block(preset)}
{title_line}LEARNING OBJECTIVES / INTENT (the lens for the course — NOT a table of contents, and
NOT a cap on the number of units): {objective}
AUDIENCE: {audience}

================= AUTHORING GUIDE (always-on rules) =================
{guide}

================= ARCHETYPE: {archetype} =================
{archetype_text}

================= SOURCE MATERIAL =================
{sources_text}

================= END SOURCE MATERIAL =================
Now write the script. Remember: bare §8 markdown only, starting at `## Microlearning 1:`."""


# ----------------------------------------------- STAGED generation (multi-pass)
# Instead of one monolithic call that writes the whole course (opaque + slow),
# generation runs in passes the dashboard drives one at a time so progress is
# visible and a failure never loses everything:
#   1. read_sources()        -> readable text          (no LLM)
#   2. build_plan_prompt()   -> the unit BREAKDOWN      (short LLM pass)
#   3. build_unit_prompt()   -> one unit's script       (one LLM pass PER unit)
#   4. assemble_course()     -> stitched script.md      (no LLM)

def _guide_and_archetype(archetype):
    guide_path = os.path.join(TEMPLATES, "AUTHORING_GUIDE.md")
    guide = open(guide_path, encoding="utf-8").read() if os.path.isfile(guide_path) else ""
    arch_path = os.path.join(TEMPLATES, f"{archetype}.md")
    arch = open(arch_path, encoding="utf-8").read() if os.path.isfile(arch_path) else ""
    return guide, arch


def build_plan_prompt(objective, audience, archetype, n_units, sources_text, course_title=None,
                      preset=None):
    """Pass 2 — PLAN only. Returns a short, strictly-formatted unit breakdown.

    The third column is the unit's MEASURABLE outcomes — these become the seed for that
    unit's required Slide-1 `*Objectives:*` block when the unit is scripted (so the plan
    and the rendered objectives stay consistent: auto-derived objectives)."""
    count = (f"Produce exactly {n_units} unit(s)." if n_units
             else "Use as many 10–15-minute units as COMPLETE COVERAGE of the source needs "
                  "(driven by coverage, NOT by the number of objectives).")
    desc = ARCHETYPES.get(archetype, archetype)   # ARCHETYPES maps key -> description string
    title_line = f"Course title: {course_title}\n" if course_title else ""
    return f"""You are an instructional designer PLANNING a microlearning course from source material.
Do NOT write any slides yet — output ONLY the unit breakdown.

Apply BACKWARD DESIGN: derive the full set of learning points the source supports, then segment
them into 10–15-minute units so EVERY point is covered, prerequisite-ordered (earlier enables
later), with no redundancy. {count}

OUTPUT FORMAT — output EXACTLY this and nothing else (no prose, no code fences):
RATIONALE: <one or two sentences on why this set of units and this teaching order>
UNIT | <short unit title> | <2–4 MEASURABLE outcomes this unit teaches — what the learner will be
able to DO, each starting with an observable verb (identify, decide, apply…), separated by "; ">
UNIT | <short unit title> | <...>
(one `UNIT |` line per unit, in teaching order)
{_course_preset_block(preset)}
{title_line}COURSE INTENT (the lens — NOT a cap on unit count): {objective}
AUDIENCE: {audience}
ARCHETYPE: {archetype} — {desc}

================= SOURCE MATERIAL =================
{sources_text}
================= END SOURCE MATERIAL =================
Now output ONLY the RATIONALE line and the UNIT lines."""


def parse_plan(raw):
    """Parse a plan pass into (rationale, [{title, objective}, ...]). Tolerant."""
    rationale, units = "", []
    for line in (raw or "").splitlines():
        s = line.strip().lstrip("-*# ").strip()
        if not s:
            continue
        up = s.upper()
        if up.startswith("RATIONALE:"):
            rationale = s.split(":", 1)[1].strip()
        elif up.startswith("UNIT") and "|" in s:
            parts = [p.strip() for p in s.split("|")]
            # parts[0] == "UNIT" (or "UNIT 1"); title/objective follow
            title = parts[1] if len(parts) > 1 else ""
            objective = parts[2] if len(parts) > 2 else ""
            if title:
                units.append({"title": title, "objective": objective})
    return rationale, units


def build_unit_prompt(unit, all_units, idx, total, objective, audience, archetype,
                      sources_text, course_title=None, images=None, preset=None,
                      guidance="", glossary=None):
    """Pass 3 — write ONE unit's full §8 script, with the whole plan as context.

    `guidance` is an optional one-sentence steer for a targeted REGENERATION
    ("make it more clinical", "3 KCs", "warmer tone") — first-class, woven into
    the prompt so the model applies it instead of doing a blind reroll. Empty on
    a first-pass generation."""
    guide, arch = _guide_and_archetype(archetype)
    plan_list = "\n".join(f"{i}. {u.get('title','')} — {u.get('objective','')}"
                          for i, u in enumerate(all_units, 1))
    coming_soon = ", ".join(sorted(blocks.coming_soon_types()))
    cs_rule = (f"- COMING SOON (do NOT author): [{coming_soon}] — import-only stubs; never emit them."
               if coming_soon else "")
    title_line = f"Course title: {course_title}\n" if course_title else ""
    guidance = (guidance or "").strip()
    g = (f"\nREVISION GUIDANCE (apply it faithfully — it overrides default choices where they "
         f"conflict, but never the HARD OUTPUT RULES or §8 grammar): {guidance}\n"
         if guidance else "")
    _gloss = glossary_prompt_block(glossary)
    gloss = ("\n" + _gloss) if _gloss else ""
    return f"""You are an instructional designer writing ONE microlearning unit's SCRIPT in the exact \
§8 markdown grammar the build pipeline consumes. Follow the AUTHORING GUIDE and ARCHETYPE precisely.

This is unit {idx} of {total}. Write ONLY this one unit — do NOT write the others.

FULL COURSE PLAN (context so your unit fits, sequences correctly, and does NOT overlap the rest):
{plan_list}

THIS UNIT:
  Title: {unit.get('title','')}
  Teaches: {unit.get('objective','')}
{g}
HARD OUTPUT RULES:
- Output ONLY the markdown for THIS unit. No preamble, no explanation, no ``` code fences.
- Start the response with `## Microlearning {idx}: {unit.get('title','')}`.
- It MUST parse the §8 grammar on the first try (Slide 1 is always Learning Objectives with a
  *Visual:*; KCs use the `- A)` form with exactly one *Correct Answer:*).
- AUTO-DERIVED OBJECTIVES: open Slide 1 with an `*Objectives:*` block whose 3–5 outcomes come
  DIRECTLY from this unit's plan objective above ("Teaches: {unit.get('objective','')}"). Each
  outcome is ONE observable action the learner will be able to perform — start with a verb
  (identify, decide, apply…), never "understand"/"know". Stay faithful to the plan; do NOT add
  outcomes this unit doesn't actually cover.
- Ground every slide ONLY in the SOURCE MATERIAL. Do NOT invent product behavior or facts.
{cs_rule}
- PEDAGOGY (AUTHORING GUIDE §0): write for an ADULT learner — open with the learner's stake/relevance
  (Knowles), build problem → demonstrate → apply → integrate (Merrill) on Gagné's nine-event spine. A
  unit that parses but is a flat content-dump is a DEFECT.
- MEDIA & LAYOUT (§0b): match content to the right structure/media treatment (or none).{gloss}
- DEFENSIBLE DESIGN: this unit's `**Articulate Build Notes:**` MUST include a `Design Rationale:` line
  (1–3 lines) naming the §0 and §0b principles behind its structure AND presentation choices.

{_image_directive(images)}
{_course_preset_block(preset)}
{title_line}COURSE INTENT: {objective}
AUDIENCE: {audience}

================= AUTHORING GUIDE (always-on rules) =================
{guide}

================= ARCHETYPE: {archetype} =================
{arch}

================= SOURCE MATERIAL =================
{sources_text}
================= END SOURCE MATERIAL =================
Now write ONLY unit {idx}, starting at `## Microlearning {idx}: {unit.get('title','')}`."""


def extract_unit(md_text, which):
    """Return the `## Microlearning {which}:` section (heading through the line before
    the next unit heading), stripped. Empty string if that unit isn't present. This is
    the OLD side of the X1 regenerate diff — the current text before a re-draft."""
    heads = list(re.finditer(r'(?m)^##\s+Microlearning\s+(\d+)\s*:', md_text))
    target = next((h for h in heads if int(h.group(1)) == which), None)
    if not target:
        return ""
    start = target.start()
    nxt = next((h for h in heads if h.start() > start), None)
    end = nxt.start() if nxt else len(md_text)
    return md_text[start:end].strip()


def replace_unit(md_text, which, new_unit_md):
    """Splice a freshly-regenerated single unit back into a course .md, replacing
    the `## Microlearning {which}:` section in place (preamble + other units kept)."""
    heads = list(re.finditer(r'(?m)^##\s+Microlearning\s+(\d+)\s*:', md_text))
    target = next((h for h in heads if int(h.group(1)) == which), None)
    if not target:
        return md_text                                  # unit not found — no-op
    start = target.start()
    nxt = next((h for h in heads if h.start() > start), None)
    end = nxt.start() if nxt else len(md_text)
    body = clean_output(new_unit_md).strip()
    body = re.sub(r'(?m)^##\s+Microlearning\s+\d+\s*:', f'## Microlearning {which}:', body, count=1)
    if not re.search(r'(?m)^##\s+Microlearning\s+\d+\s*:', body):
        body = f"## Microlearning {which}: Unit {which}\n\n{body}"
    return (md_text[:start].rstrip() + "\n\n" + body + "\n\n" + md_text[end:].lstrip("\n")).strip() + "\n"


def assemble_course(course_title, rationale, unit_mds):
    """Pass 4 — stitch unit scripts into one course .md (renumbered, with preamble)."""
    parts = []
    pre = []
    if course_title:
        pre.append(f"# {course_title}")
    if rationale:
        pre.append(f"**Curriculum Rationale:** {rationale}")
    if pre:
        parts.append("\n\n".join(pre))
    for i, md in enumerate(unit_mds, 1):
        body = clean_output(md).strip()
        if re.search(r"^##\s+Microlearning\s+\d+\s*:", body, flags=re.M):
            body = re.sub(r"^##\s+Microlearning\s+\d+\s*:", f"## Microlearning {i}:",
                          body, count=1, flags=re.M)
        else:
            body = f"## Microlearning {i}: Unit {i}\n\n{body}"
        parts.append(body)
    return ("\n\n".join(p for p in parts if p).strip() + "\n")


# --------------------------------------------------------------- CLI driving

# Isolate the app's claude calls from the user's PERSONAL Claude config so this is
# "just claude for this app, nothing else" (and so a cold subprocess can't hang or
# get polluted by it). Verified 2026-06-23: yields no MCP connectors, no hooks/
# settings (the SessionStart "Layer 1" hook stops leaking into scripts), and still
# runs the full Opus model.
#   --strict-mcp-config (no --mcp-config) -> load ZERO MCP servers (Gmail/Cal/Drive)
#   --setting-sources project,local       -> skip USER settings = no personal hooks
#   --tools ""                            -> no agentic tools (one-shot completion)
_ISOLATE = ["--strict-mcp-config", "--setting-sources", "project,local", "--tools", ""]


def run_cli(provider, prompt, timeout=None, model=None):
    """Run the subscription CLI headlessly on the user's plan. Returns (ok, text, err).

    claude: `claude -p --tools "" --output-format text` < prompt -> answer on stdout.
            Tools are DISABLED on purpose: this is a one-shot text generation (the
            source is already inline in the prompt), so the agent must not spend
            turns on tool use — which is what made a small course stall for minutes.
    codex:  `codex exec --sandbox read-only --output-last-message <f> -` < prompt
            -> final agent message written to <f> (clean), falling back to stdout.

    timeout defaults to COURSE_BUILDER_GEN_TIMEOUT (env) or 1800s — generous so a
    heavy default model (Opus + extended thinking) can finish a multi-unit script.
    """
    if timeout is None:
        try:
            timeout = int(os.environ.get("COURSE_BUILDER_GEN_TIMEOUT", "1800"))
        except (TypeError, ValueError):
            timeout = 1800
    p = PROVIDERS.get(provider)
    if not p:
        return False, "", f"unknown provider {provider}"
    if shutil.which(p["bin"]) is None:
        return False, "", f"{p['bin']} not installed — {p['install']}"
    env = {k: v for k, v in os.environ.items() if k not in p.get("scrub_env", ())}
    workdir = tempfile.gettempdir()

    if provider == "codex":
        fd, last = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        argv = ["codex", "exec", "--sandbox", "read-only",
                "--output-last-message", last, "-"]
        try:
            proc = subprocess.run(argv, input=prompt, capture_output=True, text=True,
                                  env=env, cwd=workdir, timeout=timeout)
        except subprocess.TimeoutExpired:
            return False, "", f"codex timed out after {timeout}s"
        except Exception as e:
            return False, "", str(e)
        out = ""
        try:
            out = open(last, encoding="utf-8").read()
        except OSError:
            pass
        finally:
            try:
                os.unlink(last)
            except OSError:
                pass
        if not out.strip():
            out = proc.stdout
        if proc.returncode != 0 and not out.strip():
            return False, out, (proc.stderr or f"codex exited {proc.returncode}").strip()
        return True, out, ""

    # claude — one-shot text generation, NO tools (avoid agentic turns/stalls).
    # Use the user's FULL-subscription default model (no downgrade) — this is their
    # own work and quality comes first. A heavy default (Opus + extended thinking)
    # legitimately takes minutes on a multi-unit script, so the timeout above is
    # generous. COURSE_BUILDER_GEN_MODEL can pin a specific model only if ever wanted.
    gen_model = (model or os.environ.get("COURSE_BUILDER_GEN_MODEL", "")).strip()
    argv = ["claude", "-p"] + _ISOLATE + ["--output-format", "text"]
    if gen_model:
        argv += ["--model", gen_model]
    try:
        proc = subprocess.run(argv, input=prompt, capture_output=True, text=True,
                              env=env, cwd=workdir, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "", f"claude timed out after {timeout}s"
    except Exception as e:
        return False, "", str(e)
    if proc.returncode != 0:
        return False, proc.stdout, (proc.stderr or f"claude exited {proc.returncode}").strip()
    return True, proc.stdout, ""


def run_cli_stream(provider, prompt, on_chunk, timeout=None, model=None):
    """Like run_cli, but STREAM the model's output: call on_chunk(text) for each
    piece as it arrives, and return (ok, full_text, err) at the end. Uses the same
    isolated invocation (--strict-mcp-config, no tools, full model). claude only;
    other providers fall back to the blocking run_cli + a single on_chunk."""
    if timeout is None:
        try:
            timeout = int(os.environ.get("COURSE_BUILDER_GEN_TIMEOUT", "1800"))
        except (TypeError, ValueError):
            timeout = 1800
    if provider != "claude":
        ok, text, err = run_cli(provider, prompt)
        if ok and text:
            try:
                on_chunk(text)
            except Exception:
                pass
        return ok, text, err
    if shutil.which("claude") is None:
        return False, "", f"claude not installed — {PROVIDERS['claude']['install']}"
    env = {k: v for k, v in os.environ.items()
           if k not in PROVIDERS["claude"].get("scrub_env", ())}
    gen_model = (model or os.environ.get("COURSE_BUILDER_GEN_MODEL", "")).strip()
    # stream-json + partial messages = REAL token streaming (text mode buffers and
    # shows nothing until the end). Tokens arrive as type:"stream_event" with
    # event.delta.text; the final full text is the type:"result" event's `result`.
    argv = (["claude", "-p"] + _ISOLATE
            + ["--output-format", "stream-json", "--include-partial-messages", "--verbose"])
    if gen_model:
        argv += ["--model", gen_model]
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True,
                                env=env, cwd=tempfile.gettempdir())
    except Exception as e:
        return False, "", str(e)
    import threading
    killed = {"v": False}
    timer = threading.Timer(timeout, lambda: (killed.__setitem__("v", True), proc.kill()))
    timer.start()
    acc, result_text = [], None
    try:
        proc.stdin.write(prompt)
        proc.stdin.close()
        for line in iter(proc.stdout.readline, ""):
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except ValueError:
                continue
            if obj.get("type") == "stream_event":
                txt = ((obj.get("event") or {}).get("delta") or {}).get("text")
                if txt:
                    acc.append(txt)
                    try:
                        on_chunk(txt)
                    except Exception:
                        pass        # client gone — keep draining so the save still completes
            elif obj.get("type") == "result" and isinstance(obj.get("result"), str):
                result_text = obj["result"]
        proc.wait()
    finally:
        timer.cancel()
    full = result_text if result_text is not None else "".join(acc)
    if killed["v"]:
        return False, full, f"claude timed out after {timeout}s"
    if proc.returncode != 0:
        err = ""
        try:
            err = proc.stderr.read()
        except Exception:
            pass
        return False, full, (err or f"claude exited {proc.returncode}").strip()
    return True, full, ""


def clean_output(text):
    """Strip code fences and any chatter before the first unit header."""
    if not text:
        return ""
    t = text.strip()
    # drop a leading ```/```markdown fence and its closing fence
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n", "", t)
        t = re.sub(r"\n```\s*$", "", t)
    m = re.search(r"^#\s+.+|^##\s+Microlearning\s+\d+:", t, flags=re.M)
    if m:
        t = t[m.start():]
    return t.strip() + "\n"


# --------------------------------------------------------------- lint guardrail

def lint(md_text, glossary=None):
    """Dry-run every unit through md_import. Returns (ok, units, errors).

    `glossary` (from load_glossary) adds the M4 termbank guard: a banned word or a
    wrong-term phrase in the output is a BLOCKING error. None/empty → no term checks
    (callers that pass nothing are unchanged)."""
    from md_import import import_md
    n = len(re.split(r"^##\s+Microlearning\s+", md_text, flags=re.M)) - 1
    if n < 1:
        return False, 0, ["no '## Microlearning N:' unit produced"]
    errors = []
    # M4 termbank: banned words / wrong terms in the generated markdown are blocking.
    errors.extend(glossary_lint_issues(md_text, glossary))
    # Coming-soon stub guard: a `*Scenario:*` / `*Continue:*` / `*HeadingParagraph:*`
    # marker has no parser yet, so md_import would silently degrade it to a
    # paragraph. Catch the authoring attempt and flag it instead of swallowing it.
    cs_names = "|".join(re.escape(t) for t in sorted(blocks.coming_soon_types()))
    if cs_names:
        for m in re.finditer(rf"(?im)^\*\s*({cs_names})\s*:\*", md_text):
            errors.append(f"`*{m.group(1)}:*` is a COMING-SOON block type — not yet "
                          f"authorable (import-only). Remove it or use the available §8 grammar.")
    # Knowledge-check answer-line faults the parser absorbs silently: a label after
    # prose (dropped → mis-scored) and duplicate option labels (correct answer maps to
    # the first match only). Raw scan because the parsed IR no longer carries either signal.
    from md_import import kc_answer_issues_in
    errors.extend(kc_answer_issues_in(md_text))
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(md_text)
        tmp = fh.name
    try:
        for k in range(1, n + 1):
            try:
                ir, _ = import_md(tmp, which=k)
                if not ir.get("blocks"):
                    errors.append(f"unit {k}: parsed but produced no blocks")
                for b in ir.get("blocks", []):
                    # no-invented-metrics guardrail: a chart that plots data MUST cite a
                    # source. A sourceless chart is rejected so a fabricated/unverifiable
                    # figure can never ship.
                    if b.get("type") == "chart":
                        has_data = any(isinstance(v, (int, float))
                                       for s in (b.get("series") or []) for v in (s.get("data") or []))
                        if has_data and not (b.get("source") or "").strip():
                            errors.append(f"unit {k}: a chart has no `source:` line — every chart must "
                                          f"cite the source document/table its numbers came from "
                                          f"(no-invented-metrics rule)")
                    if b.get("type") == "knowledgeCheck":
                        opts = b.get("options") or []
                        if len(opts) < 2:
                            errors.append(f"unit {k}: a knowledge check has fewer than 2 options — "
                                          f"a real question needs at least two `- A)` choices")
                        n_correct = sum(1 for o in opts if o.get("correct"))
                        if not b.get("multi") and n_correct != 1:
                            errors.append(f"unit {k}: a knowledge check must mark exactly ONE correct "
                                          f"option (found {n_correct}) — check the `*Correct Answer:*` "
                                          f"letter is present and matches one of the listed options")
                        if b.get("multi") and (n_correct < 2 or n_correct >= len(opts)):
                            errors.append(f"unit {k}: a multi-select knowledge check (multiple "
                                          f"`*Correct Answer:*` letters) must mark at least TWO correct "
                                          f"options and leave at least one wrong (found {n_correct} of "
                                          f"{len(opts)}) — otherwise it isn't a real 'choose all' question")
                    # M13 — a section pass threshold only scores in a graded course
                    if b.get("type") == "sectionStart" and b.get("pass") is not None and not ir.get("graded"):
                        errors.append(f"unit {k}: a `*Section:*` sets `pass {b['pass']}` but the course "
                                      f"isn't graded — add `*Graded:* pass N` so section thresholds can score")
                    if b.get("type") == "scenario":
                        scenes = b.get("scenes") or []
                        if not any(sc.get("responses") for sc in scenes):
                            errors.append(f"unit {k}: a *Scenario:* has no response choices — each "
                                          f"`::: scene` needs at least one `- <response>` line")
                        else:
                            # Per-scene: a scene with narrative but NO choices is an
                            # unanswerable dead-end. The old check passed if ANY ONE
                            # scene had choices, letting later empty scenes through.
                            for sc in scenes:
                                if (sc.get("title") or sc.get("html")) and not sc.get("responses"):
                                    snip = re.sub(r"<[^>]+>", "",
                                                  sc.get("title") or sc.get("html") or "").strip()[:40]
                                    errors.append(f"unit {k}: a *Scenario:* scene “{snip}” has narrative "
                                                  f"but no `- <response>` choices — every decision scene "
                                                  f"needs at least one response (a dead-end can't be answered)")
                                    break
                        for sc in scenes:
                            resps = sc.get("responses") or []
                            # A branching scene (any choice routes via `· goto:`) is a
                            # decision fork, not a judged question — the routing IS the
                            # interaction, so a single model answer isn't required. Only
                            # non-branching scenes still need a `· preferred`.
                            if any(r.get("goto") for r in resps):
                                continue
                            if resps and not any(r.get("preferred") for r in resps):
                                errors.append(f"unit {k}: a *Scenario:* scene has choices but none marked "
                                              f"`· preferred` — mark the best choice so the learner gets a "
                                              f"clear model answer")
                                break
                        # M14 branching: every `· goto:` target must name a real scene.
                        # Scene ids match the renderer: authored `id:` else `scene-<n>`.
                        scene_ids = {(sc.get("id") or f"scene-{n}")
                                     for n, sc in enumerate(scenes, 1)}
                        for sc in scenes:
                            for r in (sc.get("responses") or []):
                                tgt = r.get("goto")
                                if tgt and tgt not in scene_ids:
                                    errors.append(f"unit {k}: a *Scenario:* choice routes `· goto: {tgt}` "
                                                  f"but no scene has that id — add `id: {tgt}` to the target "
                                                  f"scene (or fix the goto)")
                                    break
                            else:
                                continue
                            break
                    if b.get("type") == "objectives" and not (b.get("items") or []):
                        errors.append(f"unit {k}: an *Objectives:* block has no outcomes — list at "
                                      f"least one learner-outcome bullet, or remove the block (an empty "
                                      f"objectives section ships a lead-in with nothing under it)")
                    if b.get("type") == "categorize":
                        ids = {bk.get("id") for bk in (b.get("buckets") or [])}
                        for it in (b.get("pool") or []):
                            tgt = it.get("target")
                            if not tgt or tgt not in ids:
                                label = re.sub(r"<[^>]+>", "", it.get("html") or "").strip()
                                errors.append(f"unit {k}: the categorize item “{label}” doesn't map to a "
                                              f"real bucket — its `-> <bucket>` name must match a "
                                              f"`bucket:` line exactly (else it's unanswerable)")
                                break
                    if b.get("type") == "matching":
                        pairs = b.get("pairs") or []
                        if len(pairs) < 2:
                            errors.append(f"unit {k}: a matching block needs at least two `pair: <left> -> "
                                          f"<right>` lines (a single pair isn't a real matching question)")
                        elif any(not (p.get("left") or "").strip() or not (p.get("right") or "").strip()
                                 for p in pairs):
                            errors.append(f"unit {k}: a matching `pair:` is missing its left or right side — "
                                          f"each must read `pair: <left> -> <right>`")
                    if b.get("type") == "sequence":
                        steps = b.get("steps") or []
                        if len(steps) < 2:
                            errors.append(f"unit {k}: a sequence needs at least two `step:` lines (there's "
                                          f"nothing to order with fewer than two steps)")
                    if b.get("type") == "fillBlank":
                        blanks = b.get("blanks") or []
                        if not blanks:
                            errors.append(f"unit {k}: a fill-in-the-blank block has no `blank: <text> -> "
                                          f"<answer>` lines")
                        elif any(not (bl.get("answers") or []) for bl in blanks):
                            errors.append(f"unit {k}: a fill-in-the-blank `blank:` has no accepted answer "
                                          f"after `->` (it would be unanswerable)")
                    # Gamification / activity blocks: the build DROPS any malformed part
                    # (a question missing its `a:`/`option:`, a non-interlocking word, a
                    # <2-letter term), so a block whose surviving collection is EMPTY looks
                    # fine in the script but ships inert — unanswerable, and it silently
                    # can't be completed/scored. Flag the empty result so the author fixes
                    # the source instead of shipping a dead activity. (Mirrors the
                    # categorize/matching/sequence/fillBlank guards above.)
                    if b.get("type") == "dragDrop":
                        zones, pool = b.get("zones") or [], b.get("pool") or []
                        if not zones or not pool:
                            errors.append(f"unit {k}: a *DragDrop:* needs at least one `zone:` and one "
                                          f"`item: <label> -> <zone>` line (as written it has "
                                          f"{len(zones)} zone(s) and {len(pool)} item(s))")
                        else:
                            zids = {z.get("id") for z in zones}
                            for it in pool:
                                if it.get("target") not in zids:
                                    label = re.sub(r"<[^>]+>", "", it.get("html") or "").strip()
                                    errors.append(f"unit {k}: the drag-drop item “{label}” doesn't map to a "
                                                  f"real zone — its `-> <zone>` name must match a `zone:` "
                                                  f"line exactly (else it's unanswerable)")
                                    break
                    if b.get("type") == "wordSearch" and not (b.get("words") or []):
                        errors.append(f"unit {k}: a *WordSearch:* produced no findable words — list a few "
                                      f"`term:` entries of at least two letters (shorter terms are dropped)")
                    if b.get("type") == "crossword" and not (b.get("words") or []):
                        errors.append(f"unit {k}: a *Crossword:* produced no solvable entries — list "
                                      f"`word: ANSWER | clue` lines of at least two letters")
                    if b.get("type") == "gameShow" and not (b.get("slices") or []):
                        errors.append(f"unit {k}: a *GameShow:* produced no answerable questions — each "
                                      f"needs a `q:` stem, an `a:` correct answer, and at least one "
                                      f"`option:` distractor")
                    if b.get("type") == "speedStreak" and not (b.get("rounds") or []):
                        errors.append(f"unit {k}: a *SpeedStreak:* produced no answerable questions — each "
                                      f"needs a `q:` stem, an `a:` correct answer, and at least one "
                                      f"`option:` distractor")
                    if b.get("type") == "quizBoard" and not (b.get("board") or []):
                        errors.append(f"unit {k}: a *QuizBoard:* produced no answerable tiles — each "
                                      f"`category:` needs at least one `q:`/`a:`/`option:` question group")
                    if b.get("type") == "reflection" and not b.get("prompt"):
                        errors.append(f"unit {k}: a *Reflection:* has no prompt — put the reflective "
                                      f"question on the `*Reflection:*` line so the learner knows what to "
                                      f"write about (add a `model:` answer and `criteria:` for self-assessment)")
            except Exception as e:
                errors.append(f"unit {k}: {e}")
    finally:
        os.unlink(tmp)
    return (not errors), n, errors


# --------------------------------------------------- translate / localize (M5)
# One-source -> translated course: translate a BUILT course .md into another
# language (or localize into an English dialect) while PRESERVING the §8 block
# structure verbatim. Runs one subscription-CLI pass per unit (robust for big
# courses; a failure loses only one unit), reuses the M4 glossary as a
# KEEP-VERBATIM term list, and verifies the block structure survived.

# English dialects/locales -> LOCALIZE (adjust spelling/terminology/idiom, stay
# English) rather than TRANSLATE (render into a different language). The UK case
# is the driver ([[project_uk_localization_audit]]); any `en-XX` is treated the
# same way.
_UK_LOCALE_RX = re.compile(
    r"^\s*(uk|gb|british|british\s+english|uk\s+english|en[-_ ]?gb|en[-_ ]?uk)\s*$", re.I)
_EN_LOCALE_RX = re.compile(r"^\s*en[-_ ]([a-z]{2})\s*$", re.I)


def resolve_target(target):
    """Map a free-text target to {name, mode}. `mode` is "localize" for an English
    dialect/locale (adjust, don't translate the language) or "translate" otherwise."""
    t = (target or "").strip()
    if _UK_LOCALE_RX.match(t):
        return {"name": "British English (en-GB)", "mode": "localize"}
    m = _EN_LOCALE_RX.match(t)
    if m:
        return {"name": f"English ({t})", "mode": "localize"}
    return {"name": t or "the target language", "mode": "translate"}


def glossary_keep_terms(glossary):
    """The approved product/brand terms (M4 `preferred`) to keep VERBATIM during
    translation — a product name like "Transfer IQ Pro" must never be localized."""
    if _glossary_is_empty(glossary):
        return []
    out = []
    for e in glossary.get("preferred") or []:
        term = (e.get("term") or "").strip()
        if term:
            out.append(term)
    return out


def _split_units(md_text):
    """Yield (number, unit_md) for each `## Microlearning N:` section (preamble excluded)."""
    heads = list(re.finditer(r"(?m)^##\s+Microlearning\s+(\d+)\s*:", md_text))
    for i, h in enumerate(heads):
        start = h.start()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(md_text)
        yield int(h.group(1)), md_text[start:end].strip()


def course_structure(md_text):
    """A structural fingerprint of a course .md for translate verification: per unit,
    the ordered list of block TYPES the §8 parser produces. Structure-preserving
    translation must keep this identical (only human-readable text changes). A unit
    that fails to parse is recorded as None."""
    from md_import import import_md
    n = len(re.split(r"^##\s+Microlearning\s+", md_text, flags=re.M)) - 1
    units = []
    if n < 1:
        return units
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(md_text)
        tmp = fh.name
    try:
        for k in range(1, n + 1):
            try:
                ir, _ = import_md(tmp, which=k)
                units.append([b.get("type") for b in ir.get("blocks", [])])
            except Exception:
                units.append(None)
    finally:
        os.unlink(tmp)
    return units


def structure_diff(src_struct, out_struct):
    """Compare two course_structure() fingerprints; return a list of drift issues
    (empty == identical structure)."""
    issues = []
    if len(src_struct) != len(out_struct):
        issues.append(f"unit count changed: {len(src_struct)} → {len(out_struct)}")
        return issues
    for i, (a, b) in enumerate(zip(src_struct, out_struct), 1):
        if a is None or b is None:
            issues.append(f"unit {i}: could not be parsed after translation")
        elif a != b:
            issues.append(f"unit {i}: block structure changed {a} → {b}")
    return issues


def build_translate_prompt(chunk_md, target_name, mode="translate", keep_terms=None, glossary=None):
    """A structure-preserving translate/localize prompt for one course-md fragment
    (a unit, or the preamble). Marker keywords, fences, option letters, chart numbers,
    asset paths, and brand terms are pinned; only human-readable text is rewritten."""
    keep_terms = keep_terms or []
    if mode == "localize":
        task = (f"LOCALIZE this course markdown into {target_name}. It is currently US English — "
                f"do NOT translate it into another language, keep it English. Adjust ONLY what "
                f"locale correctness requires: spelling, regional terminology, date/number/currency "
                f"conventions, and idiom. Make the MINIMUM changes needed; leave everything else "
                f"exactly as written.")
        verb, verbing = "LOCALIZE", "localized"
    else:
        task = (f"TRANSLATE this course markdown into {target_name}. Render every piece of "
                f"human-readable, learner-facing text naturally and fluently for an adult learner, "
                f"as a professional instructional translator would.")
        verb, verbing = "TRANSLATE", "translated"
    keep_block = ""
    if keep_terms:
        keep_block = ("\n- KEEP THESE PRODUCT/BRAND TERMS VERBATIM (never translate, inflect, or alter): "
                      + "; ".join(f"“{t}”" for t in keep_terms) + ".")
    banned = [w for w in ((glossary or {}).get("banned") or []) if (w or "").strip()]
    banned_block = ("\n- Do NOT introduce any of these banned words: " + ", ".join(banned) + "."
                    if banned else "")
    return f"""You are a professional instructional-design translator/localizer. {task}

This markdown is written in a STRICT authoring grammar (the "§8" grammar) that a build pipeline \
parses. If you change ANY structural token, the build breaks. Translate the WORDS, preserve the \
STRUCTURE exactly.

HARD OUTPUT RULES:
- Output ONLY the resulting markdown — no preamble, no explanation, no code fences.
- Preserve the document structure 1:1: the SAME number of units, slides, blocks, list items, table \
rows, options, and scenes, in the SAME order. Do not add, drop, merge, split, or reorder anything.
- KEEP THESE TOKENS EXACTLY AS-IS (English, unchanged) — they are PARSER KEYWORDS, not prose:
  • unit headers `## Microlearning N:` — translate the TITLE after the colon; keep the word \
`Microlearning` and the number.
  • slide headers `**Slide K — …**` — translate the heading text; keep the word `Slide`, the number, \
and the em dash.
  • every `*Marker:*` label EXACTLY: `*Question:*`, `*Correct Answer:*`, `*Feedback — Correct:*`, \
`*Feedback — Incorrect:*`, `*Visual:*`, `*Chart:*`, `*Infographic:*`, `*Scenario:*`, `*Continue:*`, \
`*Objectives:*`, `*Retry:*`, `*Graded:*`, `*Gate:*`, `*Section:*` — translate only the text AFTER the marker (see value exceptions below).
  • inside a `*Section:*` line, translate ONLY the objective NAME segment; keep the color word, keep the \
`· pass N` threshold (word `pass` + the number) verbatim, and keep `*Section:* end` as-is.
  • option letters `- A)` `- B)` `- C)` `- D)` — translate the option TEXT, keep the letter.
  • `:::` fence lines and their fence names (`::: scene`, `::: left`, `::: right`, `::: card`, \
`::: goals`, `::: goal`) and the lone closing `:::`.
  • field KEYS inside `*Chart:*`/`*Infographic:*` blocks (`title:`, `subtitle:`, `categories:`, \
`series:`, `yLabel:`, `xLabel:`, `source:`, `takeaway:`, `footer:`, `heading:`, `intro:`, `callout:`, \
`sublabel:`, `num:`, `body:`, `label:`, `accent:`) — translate the VALUE after the colon, keep the key.
  • the inline response markers `· preferred` and `· feedback:` — translate the feedback text after \
`feedback:`, keep the markers.
- LEAVE THESE VALUES UNCHANGED: `accent:` roles (`primary`/`secondary`/`tertiary`/`dark`), the letter(s) \
on `*Correct Answer:*`, `*Retry:*`/`*Graded:*`/`*Gate:*` values, the `*Section:*` color word + `· pass N` \
threshold, and every `num:` number.
- NUMBERS ARE DATA: every numeric value in a `*Chart:*` (numeric `categories:`, `series:` values) is a \
literal figure — copy it EXACTLY. Never translate, reformat, or localize the digits.
- Leave every `slot:`/asset filename, file path, URL, and `` `code` `` span EXACTLY as written.
- The `**Articulate Build Notes:**` and `**Sources**` markers stay verbatim; you may translate the prose \
under them.{keep_block}{banned_block}

================= COURSE MARKDOWN TO {verb} =================
{chunk_md}
================= END =================
Now output ONLY the {verbing} markdown, structure preserved."""


def translate_course(provider, md_text, target, brand=None, model=None, glossary=None,
                     verify=True, use_tm=True):
    """Translate/localize a built course .md into `target`, preserving §8 structure.

    Runs one subscription-CLI pass per `## Microlearning N:` unit (plus one for the
    preamble, if any), reassembles, then re-parses and compares the block structure
    against the source. Reuses the M4 glossary as a KEEP-VERBATIM term list AND as
    the banned-word lint.

    C17 — translation memory: when `use_tm`, an APPROVED source→target unit is reused
    VERBATIM (no LLM call), and every newly-translated unit is remembered (a LOCALIZE
    unit approved immediately, a TRANSLATE unit pending an explicit approval step). The
    result reports `tm_reused`/`tm_stored`/`pending_approval`.

    Returns a result dict (ok/out/units/mode/structure_ok/structure_issues/lint_ok/
    lint_errors/tm_*). No metered API — `run_cli` is the seam a test stubs."""
    if glossary is None:
        glossary = load_glossary(brand)
    tgt = resolve_target(target)
    keep = glossary_keep_terms(glossary)
    import tm as _tm

    heads = list(re.finditer(r"(?m)^##\s+Microlearning\s+(\d+)\s*:", md_text))
    if not heads:
        return {"ok": False, "error": "no '## Microlearning N:' unit found to translate",
                "out": md_text}

    src_struct = course_structure(md_text)
    parts = []
    tm_reused, tm_stored = 0, 0

    def _pass(chunk):
        prompt = build_translate_prompt(chunk, tgt["name"], mode=tgt["mode"],
                                        keep_terms=keep, glossary=glossary)
        return run_cli(provider, prompt, model=model)

    preamble = md_text[:heads[0].start()].strip()
    if preamble:
        ok, raw, err = _pass(preamble)
        if not ok:
            return {"ok": False, "error": err, "out": md_text, "which": "preamble"}
        parts.append(clean_output(raw).strip())

    for num, unit_md in _split_units(md_text):
        # C17: an approved memory hit is reused verbatim — no LLM call, no re-review.
        cached = _tm.lookup(target, unit_md) if use_tm else None
        if cached is not None:
            unit_out = cached
            tm_reused += 1
        else:
            ok, raw, err = _pass(unit_md)
            if not ok:
                return {"ok": False, "error": err, "out": md_text, "which": num}
            unit_out = clean_output(raw).strip()
        # pin the unit number so numbering can never drift through the round-trip
        unit_out = re.sub(r"(?m)^##\s+Microlearning\s+\d+\s*:", f"## Microlearning {num}:",
                          unit_out, count=1)
        if use_tm and cached is None:
            _tm.remember(target, unit_md, unit_out, mode=tgt["mode"])
            tm_stored += 1
        parts.append(unit_out)

    out = ("\n\n".join(p for p in parts if p).strip() + "\n")

    res = {"ok": True, "out": out, "target": tgt["name"], "mode": tgt["mode"],
           "units": len(src_struct), "tm_reused": tm_reused, "tm_stored": tm_stored,
           "pending_approval": bool(tgt["mode"] == "translate" and tm_stored)}
    if verify:
        issues = structure_diff(src_struct, course_structure(out))
        res["structure_ok"] = not issues
        res["structure_issues"] = issues
        lint_ok, _n, lint_errors = lint(out, glossary=glossary)
        res["lint_ok"] = lint_ok
        res["lint_errors"] = lint_errors
    return res


# --------------------------------------------------------------- orchestrate

def _docx_comments(path):
    """Best-effort: pull reviewer comments out of a .docx (word/comments.xml)."""
    import zipfile, xml.etree.ElementTree as ET
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    out = []
    try:
        z = zipfile.ZipFile(path)
        if "word/comments.xml" not in z.namelist():
            return out
        root = ET.fromstring(z.read("word/comments.xml"))
        for c in root.findall(f"{W}comment"):
            txt = "".join(t.text or "" for t in c.iter(f"{W}t")).strip()
            if txt:
                who = c.get(f"{W}author", "").strip()
                out.append(f"[{who}] {txt}" if who else txt)
    except Exception:
        pass
    return out


def revise(provider, script_path, reviewed_docx, out_path, model=None, glossary=None):
    """Apply an SME's reviewed/commented .docx back onto the canonical script.

    Reads the current §8 script + the reviewed doc's body text + any tracked
    comments, then drives the subscription CLI to produce the updated script,
    lint-gated like generation."""
    try:
        current = open(script_path, encoding="utf-8").read()
    except OSError as e:
        return {"ok": False, "error": f"can't read current script: {e}"}
    # `reviewed_docx` may be a single path or a LIST: parallel generation produces one
    # review .docx per module, so the SME hands back several. Read each, label it by its
    # module number when the filename carries one, and merge comments — one revise pass
    # over the whole script sees every reviewer's edits at once.
    docs = list(reviewed_docx) if isinstance(reviewed_docx, (list, tuple)) else [reviewed_docx]
    sections, comments = [], []
    for d in docs:
        text = _read_one(d) or ""
        cmts = _docx_comments(d)
        if not text.strip() and not cmts:
            continue
        m = re.search(r'_m(\d+)_review', os.path.basename(str(d)))
        label = f"Microlearning {m.group(1)}" if m else os.path.basename(str(d))
        sections.append((label, text))
        comments.extend(cmts)
    if not sections:
        return {"ok": False, "error": "no readable reviewed document(s) found (.docx expected)."}
    body = ("\n\n".join(f"----- {lbl} -----\n{txt}" for lbl, txt in sections)
            if len(sections) > 1 else sections[0][1])
    comments_block = ("\n".join(f"- {c}" for c in comments)) if comments else "(none found)"

    prompt = f"""You are revising a microlearning SCRIPT (§8 markdown) to incorporate an \
SME's review. Apply the reviewer's edits and comments to the CURRENT SCRIPT and return the updated \
script.

HARD OUTPUT RULES:
- Output ONLY the updated markdown script. No preamble, no explanation, no ``` fences.
- Start at the first `## Microlearning 1:` line. It MUST parse through the §8 grammar.
- Make exactly the changes the reviewer asked for; preserve everything else. Keep the structure
  (Slide 1 = Learning Objectives with a *Visual:*; KCs use `- A)` with one *Correct Answer:*).
- Do not invent facts; only apply the reviewer's intent.

================= CURRENT SCRIPT =================
{current}

================= REVIEWER'S DOCUMENT (their edited text) =================
{body}

================= REVIEWER COMMENTS =================
{comments_block}

================= END =================
Now output the full updated script, bare §8 markdown only, starting at `## Microlearning 1:`."""

    ok, raw, err = run_cli(provider, prompt, model=model)
    if not ok:
        return {"ok": False, "error": err}
    md_text = clean_output(raw)
    lint_ok, units, lint_errors = lint(md_text, glossary=glossary if glossary is not None else load_glossary())
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(md_text)
    return {"ok": True, "out": out_path, "units": units, "lint_ok": lint_ok,
            "lint_errors": lint_errors, "comments_found": len(comments), "provider": provider}


# one-line purpose hints so the model picks the right template; the SCHEMA itself
# comes from the canonical templates/slide-layouts/*.example.json (shared with the
# slide renderer) — we never re-describe the schema here.
LAYOUT_PURPOSE = {
    "divider": "the title slide, or a section break",
    "process": "3–6 sequential numbered steps (a how-to / pipeline)",
    "comparison": "2–3 side-by-side panels (A vs B, old vs new, options)",
    "timeline": "3–6 milestones along a line (roadmap / phases / dates)",
    "infographic": "one big idea: a problem column + numbered framework cards + a goals row",
    "image": "an edge-to-edge image with a title/caption. mode: \"hero\" (big image below the header, default), \"full\" (full-bleed image with the title overlaid — great for a section opener), or \"banner\" (a wide image band under the header, with an intro/caption below)",
    "imagetext": "an image flush to one side of the slide beside a short text column (intro + a few bullets) — side left or right",
    "cards": "2–4 equal cards for parallel items (components, options, features) — NOT a sequence",
    "quote": "a full-bleed pull-quote with attribution",
    "statement": "one big impact line or a single large metric (KPI), centered full-bleed",
    "bullets": "a clean agenda / takeaways list in one or two columns",
    "agenda": "a numbered table of contents: ordered sections, each a title + one-line description",
    "sectionheader": "a numbered SECTION BREAK opening a major section: a big section number + title (use between sections, NOT as the deck title — that's `divider`)",
    "cycles": "a CIRCULAR / repeating process: 3–6 steps that loop (PDCA, a feedback or continuous-improvement cycle) — NOT a one-way `process` or `timeline`. Keep it to 6 steps or fewer; for a longer sequence use `process` or `timeline` (a cycle must fit on ONE slide — never split it)",
    "closing": "a full-bleed thank-you / closing slide (optional contact lines), with the brand wordmark",
}

# layouts the deck generator may emit. image/imagetext are offered ONLY when an
# images folder is supplied (otherwise the model has no real files to place).
_IMAGE_LAYOUTS = ["image", "imagetext"]
_LAYOUT_ORDER = ["divider", "agenda", "sectionheader", "process", "cycles", "comparison",
                 "timeline", "infographic", "cards", "quote", "statement", "bullets", "closing"]

# ── Intent → layout matcher (capability P4, "describe the slide") ──────────────
# FORMALIZES the LAYOUT_MATCH prose (~line 132) and the LAYOUT_PURPOSE hints (above)
# into a real, testable scoring function: given a one-sentence description of what a
# slide should DO ("compare the 3 deployment models"), it returns the deck layouts
# whose purpose fits, best first — so a caller gets a real layout instead of falling
# back to a generic bullet list. Pure/deterministic: NO LLM call, no metered API.
# The cues are lifted straight from the words in LAYOUT_MATCH / LAYOUT_PURPOSE so the
# two never drift into a parallel vocabulary; test_layout_match asserts every key is
# a real layout. A cue containing a space/hyphen/period/apostrophe is matched as a
# substring; a bare token is matched as a whole word (so "step" never fires inside
# "misstep"). A layout's score is the count of DISTINCT cues it matches.
LAYOUT_CUES = {
    "process":       ["step", "steps", "how-to", "how to", "pipeline", "procedure",
                      "workflow", "walkthrough", "stage", "stages", "sequential", "in order"],
    "comparison":    ["compare", "comparison", "versus", "vs", "contrast", "difference",
                      "differences", "pros and cons", "trade-off", "tradeoff", "options",
                      "side by side", "side-by-side", "old vs new"],
    "timeline":      ["timeline", "roadmap", "phase", "phases", "chronology", "milestone",
                      "milestones", "history", "over time", "schedule", "dates", "quarters"],
    "infographic":   ["problem", "framework", "goals", "big idea", "overview", "at a glance",
                      "poster", "the challenge"],
    "cycles":        ["cycle", "cycles", "loop", "repeating", "continuous", "feedback loop",
                      "pdca", "iterative", "recurring"],
    "cards":         ["cards", "components", "features", "roles", "parallel", "categories",
                      "pillars", "options grid"],
    "agenda":        ["agenda", "table of contents", "outline", "contents", "what we'll cover"],
    "sectionheader": ["section header", "section break", "open the section", "start of section"],
    "divider":       ["title slide", "divider", "cover slide", "section title", "chapter"],
    "quote":         ["quote", "pull-quote", "pull quote", "testimonial", "saying"],
    "statement":     ["statement", "impact line", "metric", "kpi", "big number", "single stat",
                      "headline number"],
    "bullets":       ["bullets", "bullet list", "takeaways", "key points", "summary points",
                      "list of points"],
    "closing":       ["closing", "thank you", "thank-you", "wrap-up", "wrap up", "final slide",
                      "contact"],
    "image":         ["image", "photo", "picture", "hero image", "full-bleed image"],
    "imagetext":     ["image beside", "image with text", "screenshot with text", "image and text"],
}


def match_layout_from_intent(intent, allow_image_layouts=False):
    """Deterministically map a one-sentence slide INTENT to deck layouts, best-fit
    first. Returns {"intent","recommended","confident","ranked"} where ranked is a
    list of {"layout","score","cues"} for every layout that matched ≥1 cue, sorted by
    score (desc) then _LAYOUT_ORDER (the generator's own priority) so ties are stable.
    `recommended` is the top match; when NOTHING matches it falls back to "bullets"
    with confident=False, so the caller can tell the intent was too vague to place
    rather than treating a generic bullet list as a real choice. `confident` is True
    only when the top layout strictly out-scores the runner-up. Pure — no LLM call."""
    text = " " + re.sub(r"\s+", " ", (intent or "").strip().lower()) + " "
    order = {name: i for i, name in enumerate(_LAYOUT_ORDER + _IMAGE_LAYOUTS)}
    ranked = []
    for layout, cues in LAYOUT_CUES.items():
        if layout in _IMAGE_LAYOUTS and not allow_image_layouts:
            continue
        hits = []
        for cue in cues:
            if re.search(r"[ .\-']", cue):                       # phrase → substring
                found = cue in text
            else:                                                # token → whole word
                found = re.search(rf"\b{re.escape(cue)}\b", text) is not None
            if found:
                hits.append(cue)
        if hits:
            ranked.append({"layout": layout, "score": len(hits), "cues": hits})
    ranked.sort(key=lambda r: (-r["score"], order.get(r["layout"], 99)))
    if ranked:
        recommended = ranked[0]["layout"]
        confident = len(ranked) == 1 or ranked[0]["score"] > ranked[1]["score"]
    else:
        recommended, confident = "bullets", False
    return {"intent": intent, "recommended": recommended,
            "confident": confident, "ranked": ranked}

# Deck PURPOSE presets — purpose-specific profiles that shape the generated deck's
# STRUCTURE (recommended layout arc), VOICE (tone), and LENGTH. They are a prompt
# layer only: every preset uses the SAME on-brand layouts and the active brand —
# the difference is structure and tone, never divergent styling. "general" is the
# neutral default (no injection). The arc is GUIDANCE the model adapts to the
# material, not a rigid mandate.
DECK_PRESETS = {
    "general": {
        "label": "General (default)",
        "desc": "Let the material decide the structure.",
        "arc": "", "tone": "", "slides": None,
    },
    "formal": {
        "label": "Formal presentation",
        "desc": "A polished, executive-ready presentation.",
        "arc": ("Open with a divider title slide, then an `agenda`. Frame major sections with "
                "`divider` section breaks. Carry the substance in `comparison`, `infographic`, "
                "`process`, and `timeline` slides. Land key points with a `statement`. Close "
                "with a `closing` slide."),
        "tone": ("Polished, confident, and concise. Lead with conclusions; keep each slide to one "
                 "clear point. Neutral-formal register; minimal jargon."),
        "slides": "10-12",
    },
    "debrief": {
        "label": "Debrief / retrospective",
        "desc": "A candid debrief on what happened and what's next.",
        "arc": ("Open with a divider title, then a one-slide context summary (`statement` or "
                "`bullets`). Walk the sequence of events with `timeline` or `process`. Contrast "
                "what worked vs. what didn't with a `comparison`. End on clear takeaways and next "
                "steps (`bullets`), then a brief `closing`."),
        "tone": ("Candid, factual, and outcome-focused. State what happened plainly; emphasize "
                 "learnings and concrete next actions over narrative."),
        "slides": "6-10",
    },
    "workshop": {
        "label": "Live training workshop",
        "desc": "An interactive, instructor-led training workshop.",
        "arc": ("Open with a divider title, then an `agenda` of objectives. Teach one concept per "
                "slide using `infographic`, `process`, and `cards`; use `comparison` to distinguish "
                "related ideas. Pause on `statement` slides for emphasis. Recap with `bullets`, "
                "then `closing`."),
        "tone": ("Instructional, plain-language, and engaging. Address the learner directly "
                 "(\"you\"). One idea per slide; prefer more, simpler slides over dense ones. "
                 "Define terms on first use."),
        "slides": "10-16",
    },
    "client": {
        "label": "Client-facing",
        "desc": "A clear, benefit-led deck for an external client audience.",
        "arc": ("Open with a divider title, then an overview (`statement` or `bullets`). Present "
                "value and capabilities with `cards` and `comparison`; show how it works with "
                "`process`; evidence outcomes with `timeline` or `statement`. Close with a "
                "`closing` slide carrying contact details."),
        "tone": ("Benefit-led, reassuring, and jargon-light. Translate internal product/feature "
                 "names into plain customer value. Avoid internal aliases and acronyms; never "
                 "expose internal-only detail."),
        "slides": "8-12",
    },
    "pitch": {
        "label": "Pitch deck",
        "desc": "A punchy, persuasive pitch deck.",
        "arc": ("Open with a divider title, then the problem (`statement` or `infographic`), the "
                "solution (`cards` or `process`), what makes it different (`comparison`), proof or "
                "traction (`statement` or `timeline`), and a single clear ask (`statement`). Close "
                "with a `closing` slide."),
        "tone": ("Punchy and persuasive. Big, confident statements; minimal text per slide; build "
                 "narrative momentum problem -> solution -> proof -> ask."),
        "slides": "8-12",
    },
}


def _preset_directive(preset):
    """The prompt block injected for a deck PURPOSE preset, or '' for the neutral
    default / an unknown key. Tolerant of None/garbage."""
    p = DECK_PRESETS.get((preset or "general"))
    if not p or not (p.get("arc") or p.get("tone")):
        return ""
    parts = [f"PRESENTATION PURPOSE: {p['label']} — {p['desc']}"]
    if p.get("arc"):
        parts.append("RECOMMENDED ARC (adapt to the material; never pad with empty slides): "
                     + p["arc"])
    if p.get("tone"):
        parts.append("VOICE & TONE: " + p["tone"])
    if p.get("slides"):
        parts.append(f"LENGTH: aim for roughly {p['slides']} slides unless the material clearly "
                     "warrants more or fewer.")
    return "\n".join(parts)


def _load_layout_templates(names):
    """Load the named per-layout example templates (the SAME files the slide
    renderer ships), preserving order; skip any that are missing/unreadable."""
    import json as _json
    d = os.path.join(TEMPLATES, "slide-layouts")
    out = {}
    if os.path.isdir(d):
        for lay in names:
            fp = os.path.join(d, f"{lay}.example.json")
            if os.path.isfile(fp):
                try:
                    out[lay] = _json.load(open(fp, encoding="utf-8"))
                except ValueError:
                    pass
    return out


def load_slide_templates(images=None):
    """The canonical per-layout content templates shared by the deck and slide
    pipelines. The image layouts are included ONLY when image files are available
    (so the model isn't told to place pictures that don't exist)."""
    names = list(_LAYOUT_ORDER) + (_IMAGE_LAYOUTS if images else [])
    return _load_layout_templates(names)


def build_deck_plan_prompt(title, focus, audience, n_slides, sources_text, images=None,
                           preset=None):
    """M8 — OUTLINE only. Returns a short, strictly-formatted slide breakdown
    (a suggested layout + title + one-liner per slide) the operator approves and
    reorders BEFORE the full deck is generated — cutting wasted regeneration.

    Mirrors build_plan_prompt for the course flow. The approved outline is fed
    back into build_deck_prompt(outline=...) to drive the content pass."""
    count = (f"Produce exactly {n_slides} slides." if n_slides
             else "Use however many slides the material warrants — typically 6–12.")
    ttl = f"PRESENTATION TITLE: {title}\n" if title else ""
    aud = f"AUDIENCE: {audience}\n" if audience else ""
    pre = _preset_directive(preset)
    pre_block = f"\n================= PRESENTATION PURPOSE =================\n{pre}\n" if pre else ""
    layout_names = list(_LAYOUT_ORDER) + (_IMAGE_LAYOUTS if images else [])
    layout_guide = "\n".join(f"- {lay}: {LAYOUT_PURPOSE.get(lay, '')}" for lay in layout_names)
    return f"""You are a presentation designer PLANNING a slide DECK from source material.
Do NOT write any slide content yet — output ONLY the slide outline.

Sketch the deck as an ordered list of slides: OPEN with a `divider` title slide, then sequence
the material so each slide makes ONE clear point and the story flows. For each slide, choose the
best-fitting layout for the point it makes (the SAME design rules the deck generator uses — §0b).
{count}

OUTPUT FORMAT — output EXACTLY this and nothing else (no prose, no code fences):
RATIONALE: <one or two sentences on the deck's arc and why this order>
SLIDE | <layout> | <short slide title> | <one line: the single point this slide makes>
SLIDE | <layout> | <short slide title> | <...>
(one `SLIDE |` line per slide, in presentation order)

AVAILABLE LAYOUTS (use one exact name per slide as the second field):
{layout_guide}
{pre_block}
{ttl}{aud}FOCUS / WHAT TO EMPHASIZE: {focus or "(summarize the key content faithfully)"}

================= SOURCE MATERIAL =================
{sources_text}
================= END SOURCE MATERIAL =================
Now output ONLY the RATIONALE line and the SLIDE lines."""


def parse_deck_plan(raw):
    """Parse a deck-outline pass into (rationale, [{layout, title, summary}, ...]).

    Tolerant, mirroring parse_plan: each `SLIDE |` line may carry a suggested
    layout as its first field. Handles both the full `SLIDE | layout | title |
    one-liner` form and a layout-less `SLIDE | title | one-liner` form; an
    absent/unknown layout falls back to 'infographic' so every row stays a valid,
    pickable slide."""
    valid = set(_LAYOUT_ORDER) | set(_IMAGE_LAYOUTS)
    rationale, slides = "", []
    for line in (raw or "").splitlines():
        s = line.strip().lstrip("-*# ").strip()
        if not s:
            continue
        up = s.upper()
        if up.startswith("RATIONALE:"):
            rationale = s.split(":", 1)[1].strip()
        elif up.startswith("SLIDE") and "|" in s:
            parts = [p.strip() for p in s.split("|")]
            rest = parts[1:]            # drop the "SLIDE" (or "SLIDE 1") marker
            layout = "infographic"
            if rest and rest[0].lower() in valid:
                layout = rest[0].lower()
                rest = rest[1:]         # a valid named layout -> consume it
            elif len(rest) >= 3:
                rest = rest[1:]         # `layout|title|one-liner` shape but a bad layout name -> drop it
            title = rest[0] if rest else ""
            summary = rest[1] if len(rest) > 1 else ""
            if title or summary:
                slides.append({"layout": layout, "title": title, "summary": summary})
    return rationale, slides


def build_deck_prompt(title, focus, audience, n_slides, sources_text, images=None, preset=None,
                      glossary=None, outline=None):
    import json as _json
    templates = load_slide_templates(images=images)
    guide = "\n\n".join(
        f'### layout "{lay}" — {LAYOUT_PURPOSE.get(lay, "")}\n{_json.dumps(ex, indent=2)}'
        for lay, ex in templates.items())
    # M8: an approved outline PINS the slide sequence, titles, and per-slide layout;
    # the content pass fills them. With no outline this is byte-identical to before.
    if outline:
        _ol = "\n".join(
            f"{i}. [{(s or {}).get('layout', '')}] {(s or {}).get('title', '')} — "
            f"{(s or {}).get('summary', '')}" for i, s in enumerate(outline, 1))
        count = (f"Produce EXACTLY these {len(outline)} slides, in THIS order — the operator "
                 "approved this outline. Use the layout named in [brackets] for each slide and "
                 "fill its content from that slide's point.")
        outline_block = ("\n================= APPROVED SLIDE OUTLINE (follow this order, these "
                         "titles, and the [bracketed] layout per slide; fill each slide's content) "
                         f"=================\n{_ol}\n")
    else:
        count = (f"Produce exactly {n_slides} slides." if n_slides
                 else "Use however many slides the material warrants — typically 6–12.")
        outline_block = ""
    ttl = f"PRESENTATION TITLE: {title}\n" if title else ""
    aud = f"AUDIENCE: {audience}\n" if audience else ""
    pre = _preset_directive(preset)
    pre_block = f"\n================= PRESENTATION PURPOSE =================\n{pre}\n" if pre else ""
    layout_names = ", ".join(list(_LAYOUT_ORDER) + (_IMAGE_LAYOUTS if images else []))
    img_rule = ("\n- IMAGES: on an `image` or `imagetext` slide, set \"image\" to one of the "
                "available filenames below — never invent one. Use these layouts only where a "
                "real image genuinely helps.\n" + _image_directive(images) if images else "")
    _gloss = glossary_prompt_block(glossary)
    gloss = ("\n" + _gloss) if _gloss else ""
    return f"""You are a presentation designer. Convert the SOURCE MATERIAL into an on-brand \
slide DECK by choosing, for each slide, the best-fitting template LAYOUT and filling its content.

HARD OUTPUT RULES:
- Output ONLY a single JSON object: {{"slides": [ {{"layout": "<name>", "content": {{...}}}}, ... ]}}.
- No preamble, no explanation, no markdown, no ``` fences. The FIRST character must be '{{'.
- "layout" must be one of: {layout_names}.
- "content" MUST match that layout's schema below; omit keys you don't need.
- "theme" is OPTIONAL per slide: "dark" or "light". Omit it to use each layout's natural
  theme (most content layouts are light; title/divider/section/closing/quote/statement are dark).
  Set it only to deliberately flip ONE slide — e.g. a "light" section break for contrast, or a
  "dark" statement among light slides. Keep a deck visually consistent; don't alternate randomly.
- "notes" is OPTIONAL per slide: a short plain-language speaker-notes paragraph (2-4 sentences)
  the presenter would say out loud for that slide — context, the "why", a transition. It rides
  into the PowerPoint notes page and is never shown on the slide. Omit it if you have nothing
  useful to add; never just restate the slide's bullets verbatim.
- Match the layout to the content (the SAME design rules the course generator uses — §0b):
{LAYOUT_MATCH}
- Taste (restraint + variety inside the FIXED brand system — never invent fonts/colors/layouts):
{TASTE_RULE}{gloss}
- Open with a divider title slide. Ground EVERY slide ONLY in the source material; do NOT invent facts.{img_rule}
- {count}

{ttl}{aud}FOCUS / WHAT TO EMPHASIZE: {focus or "(summarize the key content faithfully)"}
{pre_block}{outline_block}
- "accent" is optional anywhere and must be one of primary|secondary|tertiary|dark (colors come from
  the brand). Each "items" entry is either ["bold lead"," rest of line"] or a plain string. Keep text
  tight so it fits one slide.

================= LAYOUT TEMPLATES (fill these — the placeholder text shows the schema) =================
{guide}

================= SOURCE MATERIAL =================
{sources_text}

================= END SOURCE MATERIAL =================
Now output the JSON deck object. First character '{{', last character '}}'. Nothing else."""


def clean_json(text):
    """Strip fences/chatter and return the outermost {...} JSON substring."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n", "", t)
        t = re.sub(r"\n```\s*$", "", t)
    i, j = t.find("{"), t.rfind("}")
    if i != -1 and j != -1 and j > i:
        t = t[i:j + 1]
    return t


def lint_deck(slides):
    """Guardrail: confirm every layout is known and the deck actually renders.
    Returns (ok, n, errors)."""
    if not slides:
        return False, 0, ["no slides produced"]
    # "template" = the generic data-driven layout (a named region-spec). Valid to author
    # by hand or via ingestion, but NOT in _LAYOUT_ORDER so the AI never spontaneously
    # picks it (it needs an explicit template name + matching content).
    valid = set(_LAYOUT_ORDER) | set(_IMAGE_LAYOUTS) | {"template"}
    errors = [f"slide {i}: unknown layout {(s or {}).get('layout')!r}"
              for i, s in enumerate(slides, 1) if (s or {}).get("layout") not in valid]
    # the optional cross-cutting theme override must be dark|light when present
    errors += [f"slide {i}: invalid theme {(s or {}).get('theme')!r} (use \"dark\" or \"light\")"
               for i, s in enumerate(slides, 1)
               if (s or {}).get("theme") not in (None, "dark", "light")]
    # optional speaker notes must be a string when present
    errors += [f"slide {i}: notes must be text, got {type((s or {}).get('notes')).__name__}"
               for i, s in enumerate(slides, 1)
               if (s or {}).get("notes") is not None and not isinstance((s or {}).get("notes"), str)]
    if errors:
        return False, len(slides), errors
    import slide_layouts
    fd, tmp = tempfile.mkstemp(suffix=".pptx")
    os.close(fd)
    try:
        slide_layouts.export_deck(slides, tmp)
    except Exception as e:
        errors.append(str(e))
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return (not errors), len(slides), errors


# Color-driven layouts whose content items carry an explicit "accent"
# (primary/secondary/tertiary/dark). Mirror of RECOLOR_LAYOUTS in
# dashboard/index.html — a single accent pinned across all of these reads as
# mono-tone. Keep the two sets in sync.
_COLOR_DRIVEN_LAYOUTS = frozenset({
    "infographic", "process", "comparison", "timeline", "cards", "cycles", "divider"})


def _collect_accents(node):
    """Recursively gather every explicit, non-empty string value sitting under an
    "accent" key in a slide's content (robust to per-layout nesting: items,
    panels, steps, groups all key their accent the same way)."""
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "accent" and isinstance(v, str) and v.strip():
                out.append(v.strip().lower())
            else:
                out.extend(_collect_accents(v))
    elif isinstance(node, list):
        for v in node:
            out.extend(_collect_accents(v))
    return out


def deck_palette_warnings(slides):
    """Non-blocking palette-variety nudge (serves [[feedback_course_color_palette_variety]]).

    Warn — never block — when a deck PINS an explicit accent on its color-driven
    slides and every one of those pins is the SAME accent across 2+ slides, i.e.
    the deck defaults the whole thing to one accent. Decks that leave accents to
    auto-cycle (no explicit pins) are varied by construction and never warn. A
    demo deck may be single-accent by choice, so this is a WARNING, not an error.
    Returns a list of warning strings (empty = clean)."""
    if not isinstance(slides, list):
        return []
    pinned_slides = 0
    accents = set()
    for s in slides:
        if not isinstance(s, dict) or s.get("layout") not in _COLOR_DRIVEN_LAYOUTS:
            continue
        found = _collect_accents(s.get("content"))
        if found:
            pinned_slides += 1
            accents.update(found)
    if pinned_slides >= 2 and len(accents) == 1:
        only = next(iter(accents))
        return [f"All {pinned_slides} color-driven slides pin the same accent "
                f"(\"{only}\") — vary accents across sections to use the full palette, "
                f"or leave \"accent\" off to auto-cycle. (Single-accent demo deck? "
                f"Safe to ignore.)"]
    return []


# --- M10: brand-compliance nudges over slide IR tokens ---------------------
# Symbolic accent tokens that resolve to brand-safe colors in the renderer
# (slide_layouts._accent / _tok_color). Anything that is neither one of these
# nor an explicit #hex is an unknown token.
_SYMBOLIC_ACCENTS = frozenset({
    "primary", "secondary", "tertiary", "dark", "tint", "white", "grey",
    "card", "node", "ink", "muted", "rule_color"})

_HEX_RE = re.compile(r'^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$')

# accents render as strips / numbers / small text / fills on the white card
# base; WCAG floor for large text / UI components is 3:1.
_CONTRAST_FLOOR = 3.0
_WHITE = "#ffffff"
# brand rule (blueprint logos map): white/reversed logo on dark backgrounds,
# color logo on light backgrounds.
_LOGO_WHITE_HINTS = ("white", "reverse", "reversed", "knockout")


def _norm_hex(s):
    """Normalize a hex color string to lowercase 6-digit '#rrggbb', or None."""
    m = _HEX_RE.match((s or "").strip())
    if not m:
        return None
    h = m.group(1).lower()
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h


def _rel_luminance(hexc):
    """WCAG relative luminance (0..1) of a normalized '#rrggbb'."""
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(int(hexc[i:i + 2], 16)) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(hex1, hex2):
    """WCAG contrast ratio (1..21) between two normalized hex colors."""
    l1, l2 = _rel_luminance(hex1), _rel_luminance(hex2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _iter_hex_strings(node):
    """Yield every value that IS a bare hex color string anywhere in a slide's
    content (regardless of which key holds it) — catches off-palette explicit
    colors. Hexes embedded inside prose are ignored (whole-value match only)."""
    out = []
    if isinstance(node, dict):
        for v in node.values():
            out.extend(_iter_hex_strings(v))
    elif isinstance(node, list):
        for v in node:
            out.extend(_iter_hex_strings(v))
    elif isinstance(node, str) and _HEX_RE.match(node.strip()):
        out.append(node.strip())
    return out


def _brand_hex_set(brand):
    """Lowercased, normalized set of every hex the brand sanctions
    (palette values + accentSnap + defaultAccent). Empty if no brand."""
    out = set()
    if not brand:
        return out
    for v in (brand.get("palette", {}) or {}).values():
        nh = _norm_hex(v)
        if nh:
            out.add(nh)
    for v in (brand.get("accentSnap") or []):
        nh = _norm_hex(v)
        if nh:
            out.add(nh)
    nh = _norm_hex(brand.get("defaultAccent"))
    if nh:
        out.add(nh)
    return out


def _logo_theme_warnings(slide, n):
    """Warn when a manually placed logo image's variant conflicts with the
    slide's EXPLICIT theme (white/reversed belongs on dark, color on light).
    Only fires when both a logo-named image AND an explicit theme are present —
    an absent theme uses the brand default, which is not a misuse."""
    content = slide.get("content")
    if not isinstance(content, dict):
        return []
    img = content.get("image")
    if not isinstance(img, str) or "logo" not in img.lower():
        return []
    theme = slide.get("theme")
    if theme not in ("dark", "light"):
        return []
    name = img.lower()
    is_white = any(h in name for h in _LOGO_WHITE_HINTS)
    is_color = ("color" in name or "colour" in name)
    if is_white and theme == "light":
        return [f"slide {n}: white/reversed logo \"{img}\" on a light theme may "
                f"be invisible — use the color logo on light backgrounds."]
    if is_color and theme == "dark":
        return [f"slide {n}: color logo \"{img}\" on a dark theme may be "
                f"invisible — use the white/reversed logo on dark backgrounds."]
    return []


def deck_brand_warnings(slides, brand=None):
    """Non-blocking brand-compliance nudges over slide IR tokens (M10): the
    deck-side analogue of the course brand checker. Flags off-palette explicit
    colors, unknown accent tokens, low-contrast accent colors (real WCAG ratio
    vs the white card base), and logo-variant/theme mismatches. WARN — never
    block (mirrors deck_palette_warnings); a deliberate off-brand choice stays
    an operator call. Returns a list of warning strings (empty = clean)."""
    if not isinstance(slides, list):
        return []
    if brand is None:
        try:
            import brand as _brandmod
            brand = _brandmod.load_brand()
        except Exception:
            brand = None
    allowed = _brand_hex_set(brand)
    off_palette, low_contrast, unknown = {}, {}, {}
    logo_warns = []
    for i, s in enumerate(slides, 1):
        if not isinstance(s, dict):
            continue
        content = s.get("content")
        # accent role: hex -> contrast check; bare token -> known/unknown
        for a in _collect_accents(content):
            nh = _norm_hex(a)
            if nh:
                # the brand palette is sanctioned by design (its accents render
                # as fills, not body text) — only flag legibility for colors
                # that aren't in the system AND are too light to read.
                if nh not in allowed and _contrast_ratio(nh, _WHITE) < _CONTRAST_FLOOR:
                    low_contrast.setdefault(nh, set()).add(i)
            elif a not in _SYMBOLIC_ACCENTS:
                unknown.setdefault(a, set()).add(i)
        # any explicit hex anywhere -> off-palette check
        for hx in _iter_hex_strings(content):
            nh = _norm_hex(hx)
            if nh and allowed and nh not in allowed:
                off_palette.setdefault(nh, set()).add(i)
        logo_warns += _logo_theme_warnings(s, i)

    def _slidelist(s):
        return ", ".join(str(x) for x in sorted(s))

    warns = []
    for nh in sorted(off_palette):
        warns.append(f"off-palette color \"{nh}\" on slide(s) {_slidelist(off_palette[nh])} "
                     f"— not in the brand palette; use a brand color or a symbolic "
                     f"accent (primary/secondary/tertiary/dark).")
    for nh in sorted(low_contrast):
        warns.append(f"low-contrast color \"{nh}\" on slide(s) {_slidelist(low_contrast[nh])} "
                     f"— contrast vs a white background is {_contrast_ratio(nh, _WHITE):.1f}:1 "
                     f"(below {_CONTRAST_FLOOR:.0f}:1); may render hard to read.")
    for a in sorted(unknown):
        warns.append(f"unknown accent \"{a}\" on slide(s) {_slidelist(unknown[a])} "
                     f"— use a symbolic accent (primary/secondary/tertiary/dark) "
                     f"or a brand hex.")
    return warns + logo_warns


def generate_deck(provider, source_folder, title=None, focus="", audience="", n_slides=None,
                  model=None, images=None, preset=None, urls=None, glossary=None, outline=None):
    """Convert raw source documents into a templated slide deck (list of
    {layout, content}). Mirrors generate() but the output is a deck spec, not a
    course script. `images` (filenames available in the slide tab's image folder)
    unlocks the image/imagetext layouts. `urls` adds pasted links as sources.
    Never raises for normal failures."""
    import json as _json
    sources_text, used, skipped = read_sources(source_folder, urls=urls)
    if not sources_text.strip():
        return {"ok": False, "error": "No readable source documents found (.md/.txt/.csv/.doc/.docx/.rtf/.odt/.html/.pdf).",
                "skipped": skipped}
    if glossary is None:
        glossary = load_glossary()
    prompt = build_deck_prompt(title, focus, audience, n_slides, sources_text, images=images,
                               preset=preset, glossary=glossary, outline=outline)
    ok, raw, err = run_cli(provider, prompt, model=model)
    if not ok:
        return {"ok": False, "error": err, "used_sources": used, "skipped": skipped}
    try:
        data = _json.loads(clean_json(raw))
    except ValueError as e:
        return {"ok": False, "error": f"the model did not return valid JSON: {e}",
                "raw": raw[:2000], "used_sources": used, "skipped": skipped}
    slides = data.get("slides") if isinstance(data, dict) else data
    if not isinstance(slides, list) or not slides:
        return {"ok": False, "error": "the model returned no 'slides' list.",
                "used_sources": used, "skipped": skipped}
    lint_ok, n, lint_errors = lint_deck(slides)
    return {"ok": True, "slides": slides, "count": n, "lint_ok": lint_ok,
            "lint_errors": lint_errors,
            "lint_warnings": deck_palette_warnings(slides) + deck_brand_warnings(slides),
            "used_sources": used, "skipped": skipped, "provider": provider}


def build_deck_notes_prompt(slides, title="", focus="", audience=""):
    """Prompt to write one short speaker-notes paragraph per EXISTING deck slide.
    The model sees the assembled deck and returns a parallel notes array — this is
    the one-click "generate speaker notes" action, distinct from initial deck gen."""
    import json as _json
    deck = [{"n": i, "layout": (s or {}).get("layout"), "content": (s or {}).get("content")}
            for i, s in enumerate(slides, 1)]
    ttl = f"PRESENTATION TITLE: {title}\n" if title else ""
    aud = f"AUDIENCE: {audience}\n" if audience else ""
    foc = f"FOCUS / EMPHASIS: {focus}\n" if focus else ""
    return f"""You are coaching the presenter of the slide deck below. For EACH slide, write a \
short speaker-notes paragraph (2-4 sentences) of what they should SAY out loud — the context, \
the "why", the point to land, a natural transition to the next slide. Do NOT just restate the \
slide's visible bullets; add the spoken layer around them. Plain language, first-person presenter voice.

{ttl}{aud}{foc}
HARD OUTPUT RULES:
- Output ONLY a single JSON object: {{"notes": ["<slide 1 notes>", "<slide 2 notes>", ...]}}.
- The "notes" array MUST have EXACTLY {len(slides)} entries, in slide order.
- No preamble, no markdown, no ``` fences. The FIRST character must be '{{'.
- Use "" for a slide that genuinely needs no spoken notes (e.g. a pure title slide).

================= DECK ({len(slides)} slides) =================
{_json.dumps(deck, indent=2)}
================= END DECK =================
Now output the JSON notes object. First character '{{', last character '}}'. Nothing else."""


def generate_notes(provider, slides, title="", focus="", audience="", model=None):
    """Generate one speaker-notes paragraph per slide for an existing deck.
    Returns {"ok", "notes": [...]} where notes is padded/truncated to len(slides).
    Never raises for normal failures."""
    import json as _json
    if not isinstance(slides, list) or not slides:
        return {"ok": False, "error": "no slides to annotate"}
    prompt = build_deck_notes_prompt(slides, title=title, focus=focus, audience=audience)
    ok, raw, err = run_cli(provider, prompt, model=model)
    if not ok:
        return {"ok": False, "error": err}
    try:
        data = _json.loads(clean_json(raw))
    except ValueError as e:
        return {"ok": False, "error": f"the model did not return valid JSON: {e}", "raw": raw[:2000]}
    notes = data.get("notes") if isinstance(data, dict) else data
    if not isinstance(notes, list):
        return {"ok": False, "error": "the model returned no 'notes' list.", "raw": raw[:2000]}
    # normalize to one string per slide (pad short, truncate long)
    out = [("" if i >= len(notes) or notes[i] is None else str(notes[i]).strip())
           for i in range(len(slides))]
    return {"ok": True, "notes": out, "provider": provider}


def build_regen_slide_prompt(layout, current_content, slide_summaries, idx, total,
                             title, focus, audience, sources_text, guidance,
                             scope_content=True, scope_layout=True, images=None,
                             variant=0, variants=1):
    """Prompt to re-draft ONE slide of an existing deck — keeps it coherent with
    the other slides (passed as summaries) and grounded in the source. Shares the
    canonical layout templates with build_deck_prompt.

    scope_content / scope_layout narrow what may change:
      content only  -> reword/improve the TEXT, keep the same layout
      layout only   -> keep the wording/substance, re-express in the best-fitting layout
      both          -> a free re-draft (may change layout AND reword)"""
    import json as _json
    templates = load_slide_templates(images=images)
    guide = "\n\n".join(
        f'### layout "{lay}" — {LAYOUT_PURPOSE.get(lay, "")}\n{_json.dumps(ex, indent=2)}'
        for lay, ex in templates.items())
    others = "\n".join(slide_summaries) or "(this is the only slide)"
    cur = _json.dumps({"layout": layout, "content": current_content}, indent=2)
    ttl = f"PRESENTATION TITLE: {title}\n" if title else ""
    aud = f"AUDIENCE: {audience}\n" if audience else ""
    foc = f"FOCUS / EMPHASIS: {focus}\n" if focus else ""
    g = f"\nREVISION GUIDANCE (apply it faithfully): {guidance}\n" if guidance else ""
    # When several treatments are requested at once, nudge each one to differ so the
    # operator gets a real choice. variants<=1 -> empty line -> byte-identical prompt.
    var = (f"\nTREATMENT VARIANT {variant} OF {variants}: produce a DISTINCT treatment — a "
           "different angle, structure, emphasis, or (where the layout may change) a "
           "different layout from the other variants. Avoid the single most obvious "
           "version; make this one meaningfully different so the operator has a real "
           "choice between treatments.\n") if variants > 1 else ""
    layout_names = ", ".join(list(_LAYOUT_ORDER) + (_IMAGE_LAYOUTS if images else []))
    if scope_layout:
        layout_rule = (f'- "layout" must be one of: {layout_names}. Keep "{layout}" unless a '
                       f'different one of those clearly fits the revised content better.')
    else:
        layout_rule = (f'- "layout" MUST stay "{layout}" — do NOT change it. Output that '
                       f'exact layout.')
    if scope_content and not scope_layout:
        scope_rule = ("\nREVISION SCOPE: Re-word and sharpen the TEXT only. Keep the SAME "
                      f'layout ("{layout}") and the same overall structure; improve clarity, '
                      "tone, and concision.\n")
    elif scope_layout and not scope_content:
        scope_rule = ("\nREVISION SCOPE: Keep the existing wording and substance; re-express "
                      "THIS SAME content in whichever layout fits it best. Do not introduce new "
                      "facts or reword beyond what the new structure requires.\n")
    else:
        scope_rule = ("\nREVISION SCOPE: Full re-draft — you may change the layout AND reword "
                      "the content (still grounded only in the source).\n")
    return f"""You are a presentation designer revising ONE slide inside an existing deck.
Re-draft slide {idx} of {total}. Keep it coherent with the rest of the deck and do NOT \
duplicate the other slides' content.
{scope_rule}
HARD OUTPUT RULES:
- Output ONLY a single JSON object: {{"layout": "<name>", "content": {{...}}}}.
- No preamble, no explanation, no markdown, no ``` fences. The FIRST character must be '{{'.
{layout_rule}
- "content" MUST match that layout's schema below; omit keys you don't need.
- Ground the slide ONLY in the source material; do NOT invent facts.
{LAYOUT_MATCH}
{(chr(10) + _image_directive(images)) if images else ""}
{ttl}{aud}{foc}{g}{var}
THE OTHER SLIDES (for context — keep THIS slide distinct from them):
{others}

THE CURRENT SLIDE (revise this one):
{cur}

================= LAYOUT TEMPLATES (fill these — the placeholder text shows the schema) =================
{guide}

================= SOURCE MATERIAL =================
{sources_text}

================= END SOURCE MATERIAL =================
Now output the revised slide JSON object. First character '{{', last character '}}'. Nothing else."""


def _coerce_regen_slide(raw, layout, scope_layout):
    """Parse a model's raw regen output into (layout, content). Tolerates a
    {"slides":[...]} wrapper or a bare content object, validates the layout name,
    and honors a locked layout. Raises ValueError if the text isn't JSON."""
    import json as _json
    data = _json.loads(clean_json(raw))
    if isinstance(data, dict) and isinstance(data.get("slides"), list) and data["slides"]:
        data = data["slides"][0] or {}
    if isinstance(data, dict) and ("layout" in data or "content" in data):
        lay = data.get("layout") or layout
        content = data.get("content") if isinstance(data.get("content"), dict) else {}
    else:                                            # model returned bare content
        lay, content = layout, (data if isinstance(data, dict) else {})
    valid = set(_LAYOUT_ORDER) | set(_IMAGE_LAYOUTS)
    if lay not in valid:
        lay = layout
    if not scope_layout:                 # layout was locked — ignore any AI layout change
        lay = layout
    return lay, content


def _slide_text_volume(content):
    """Rough word count over every string leaf of a slide's content — a cheap
    density proxy used by the candidate ranker."""
    n = 0
    stack = [content]
    while stack:
        v = stack.pop()
        if isinstance(v, str):
            n += len(v.split())
        elif isinstance(v, dict):
            stack.extend(v.values())
        elif isinstance(v, (list, tuple)):
            stack.extend(v)
    return n


def rank_slide_candidates(candidates, brand=None):
    """Deterministically order regen candidates best-first (no AI). A valid
    (lint-ok) slide outranks an invalid one; then fewer brand warnings, then a
    moderate text density. Attaches an integer `score` to each candidate and
    returns a new list; the sort is stable so ties keep generation order."""
    def score(c):
        s = 1000 if c.get("lint_ok") else 0
        try:
            warns = deck_brand_warnings([{"layout": c.get("layout"),
                                          "content": c.get("content") or {}}], brand)
        except Exception:
            warns = []
        s -= 25 * len(warns)
        vol = _slide_text_volume(c.get("content") or {})
        if vol < 8:                      # too sparse to be a useful slide
            s -= (8 - vol) * 2
        elif vol > 70:                   # overstuffed
            s -= (vol - 70)
        return s
    scored = [dict(c, score=score(c)) for c in candidates]
    return sorted(scored, key=lambda c: -c["score"])


def regenerate_slide(provider, source_folder, layout, current_content, slide_summaries,
                     idx, total, title="", focus="", audience="", guidance="", model=None,
                     scope_content=True, scope_layout=True, images=None, urls=None,
                     n=1, brand=None):
    """Re-draft a SINGLE slide (optionally with guidance), keeping the rest of the
    deck untouched. `scope_content`/`scope_layout` narrow what may change (text-only,
    layout-only, or both).

    With n<=1 (default) returns {ok, layout, content, lint_ok, lint_errors, skipped}.
    With n>1 it drafts N distinct treatments and returns the same shape (the top-ranked
    candidate hoisted for backward compatibility) PLUS `candidates`: a best-first list
    of {layout, content, lint_ok, lint_errors, score} the operator can pick from. Never
    raises for normal failures. Mirrors regenerate-one-module on the course side."""
    sources_text, used, skipped = read_sources(source_folder, urls=urls)
    if not sources_text.strip():
        return {"ok": False, "error": "No readable source documents found (.md/.txt/.csv/.doc/.docx/.rtf/.odt/.html/.pdf)."}
    try:
        n = max(1, min(int(n), 5))       # cap to keep AI cost bounded
    except (TypeError, ValueError):
        n = 1

    def _draft(variant, variants):
        """One AI pass -> a candidate dict, or (None, error)."""
        prompt = build_regen_slide_prompt(layout, current_content, slide_summaries, idx,
                                          total, title, focus, audience, sources_text,
                                          guidance, scope_content=scope_content,
                                          scope_layout=scope_layout, images=images,
                                          variant=variant, variants=variants)
        ok, raw, err = run_cli(provider, prompt, model=model)
        if not ok:
            return None, err
        try:
            lay, content = _coerce_regen_slide(raw, layout, scope_layout)
        except ValueError as e:
            return None, f"the model did not return valid JSON: {e}"
        lint_ok, _n, lint_errors = lint_deck([{"layout": lay, "content": content}])
        return {"layout": lay, "content": content, "lint_ok": lint_ok,
                "lint_errors": lint_errors}, None

    if n <= 1:
        cand, err = _draft(0, 1)
        if cand is None:
            return {"ok": False, "error": err}
        return {"ok": True, "layout": cand["layout"], "content": cand["content"],
                "lint_ok": cand["lint_ok"], "lint_errors": cand["lint_errors"],
                "skipped": skipped}

    cands, last_err = [], ""
    for k in range(n):
        cand, err = _draft(k + 1, n)
        if cand is not None:
            cands.append(cand)
        else:
            last_err = err
    if not cands:
        return {"ok": False, "error": last_err or "the model returned no usable slide."}
    ranked = rank_slide_candidates(cands, brand)
    top = ranked[0]
    return {"ok": True, "candidates": ranked, "layout": top["layout"],
            "content": top["content"], "lint_ok": top["lint_ok"],
            "lint_errors": top["lint_errors"], "skipped": skipped}


# --- M1: self-healing generation loop -------------------------------------------------------------
# After a course is drafted we already run the build-time `lint()`. M1 closes the loop: if the draft
# has BLOCKING violations, re-prompt the provider to fix ONLY those, re-lint, and keep the best draft
# — up to a small cap — BEFORE the operator ever sees output. This hides the boring, mechanical
# failures the system can already detect. Any issues that survive the cap are RETURNED (heal_rounds +
# residual lint_errors), never silently shipped. `run_cli` is the one seam a test stubs (no metered
# API). The loop is shared by both course-generation paths (generate() and the streaming path).

SELF_HEAL_ROUNDS = 2   # cap on fix-and-recheck passes after a course generation (James, M1)


def build_repair_prompt(md_text, lint_errors):
    """Ask the provider to fix SPECIFIC §8 lint violations in an already-drafted course,
    changing as little else as possible. Mirrors build_prompt's HARD OUTPUT RULES so the
    corrected script re-parses on the first try."""
    issues = "\n".join(f"- {e}" for e in lint_errors) or "- (unspecified)"
    return f"""You are fixing a microlearning SCRIPT (§8 markdown) that FAILED the build's automated \
lint. Correct ONLY the listed problems and change as little else as possible — do not rewrite \
content, restructure slides, or renumber units.

HARD OUTPUT RULES:
- Output ONLY the corrected markdown script. No preamble, no explanation, no surrounding ``` code fences.
- Start the response with the first `## Microlearning 1:` line. It MUST parse through the §8 grammar.
- Make the MINIMUM edits that clear the listed violations; keep every unit's content, ordering, and
  numbering intact.

================= LINT VIOLATIONS TO FIX =================
{issues}

================= CURRENT SCRIPT =================
{md_text}

================= END =================
Now output the full corrected script, bare §8 markdown only, starting at `## Microlearning 1:`."""


def heal_course_md(provider, md_text, glossary=None, *, model=None,
                   max_rounds=SELF_HEAL_ROUNDS, on_round=None):
    """M1 fix-and-recheck loop. Lint `md_text`; while it has BLOCKING violations and rounds
    remain, re-prompt the provider to fix ONLY those violations, re-lint, and keep the BEST
    (fewest-error) draft — so a repair pass can never ship something worse than the first draft.

    Returns {md, lint_ok, units, lint_errors, rounds, history}:
      - `rounds`  = repair passes actually made (0 when the first draft was already clean).
      - `history` = per-round {round, before, ok, after} for the build report / result panel.
    Stops early when a pass fails or stops reducing the error count. Never raises for normal
    failures — a provider error just ends the loop and returns the best draft so far. `run_cli`
    is the stubbed seam (no metered API)."""
    if glossary is None:
        glossary = load_glossary()
    best_md = md_text
    best_ok, best_units, best_errors = lint(best_md, glossary=glossary)
    history, rounds = [], 0
    while not best_ok and rounds < max(0, max_rounds):
        rounds += 1
        ok, raw, err = run_cli(provider, build_repair_prompt(best_md, best_errors), model=model)
        if not ok:
            history.append({"round": rounds, "before": list(best_errors), "ok": False,
                            "after": [f"repair pass failed: {err}"]})
            break
        cand_md = clean_output(raw)
        cand_ok, cand_units, cand_errors = lint(cand_md, glossary=glossary)
        history.append({"round": rounds, "before": list(best_errors), "ok": cand_ok,
                        "after": list(cand_errors)})
        if on_round:
            try:
                on_round(rounds, cand_ok, cand_errors)
            except Exception:
                pass
        # adopt the repair only if it cleared lint or strictly reduced the error count;
        # a regression or a stall means keep the best draft and stop burning passes.
        if cand_ok or len(cand_errors) < len(best_errors):
            best_md, best_ok, best_units, best_errors = cand_md, cand_ok, cand_units, cand_errors
            if best_ok:
                break
        else:
            break
    return {"md": best_md, "lint_ok": best_ok, "units": best_units,
            "lint_errors": best_errors, "rounds": rounds, "history": history}


ALT_HEAL_ROUNDS = 2   # cap on alt-text redraft passes after a course generation (James, M2)


def alt_gaps(md_text):
    """M2 oracle. Dry-run every unit through md_import and return the list of
    INFORMATIVE images that are missing alt text: [{unit, src, slot}]. Decorative
    `*Visual:*` images are excluded (their empty alt is intentional). Shares the
    per-unit import pattern with `lint()`; used both to flag gaps and as the
    convergence check for the alt redraft loop below."""
    from md_import import import_md
    n = len(re.split(r"^##\s+Microlearning\s+", md_text, flags=re.M)) - 1
    if n < 1:
        return []
    gaps = []
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(md_text)
        tmp = fh.name
    try:
        for k in range(1, n + 1):
            try:
                ir, _ = import_md(tmp, which=k)
            except Exception:
                continue                                    # a parse failure is lint's job, not ours
            for b in ir.get("blocks", []):
                if b.get("type") not in ("image", "imageText") or not b.get("src"):
                    continue
                if b.get("decorative"):
                    continue
                from build_report import alt_is_weak
                if alt_is_weak(b.get("alt")):
                    src = b.get("src") or ""
                    gaps.append({"unit": k, "src": src, "slot": os.path.basename(src)})
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return gaps


def build_alt_repair_prompt(md_text, gaps):
    """Ask the provider to add ALT TEXT to the specific `*Visual:*` directives that
    are missing their `<description / alt text>` segment — writing a short, specific
    description of what each image conveys, drawn from the surrounding slide text,
    and changing nothing else. Mirrors build_prompt's HARD OUTPUT RULES so the
    corrected script re-parses on the first try. No vision — text context only."""
    lines = "\n".join(
        f"- Unit {g['unit']}: the `*Visual:*` for `{g['slot']}` has no description"
        for g in gaps) or "- (unspecified)"
    return f"""You are fixing the ACCESSIBILITY of a microlearning SCRIPT (§8 markdown): some \
informative `*Visual:*` directives are MISSING their alt-text description. For each one listed, add a \
short, specific `<description / alt text>` as the directive's middle segment — describe what the image \
CONVEYS to a learner who cannot see it (the meaning, drawn from the surrounding slide text), NOT \
"image of…" or the filename. Change NOTHING else: do not rewrite content, add or remove slides, \
restructure, or renumber. Keep the `slot:` and any `side:` exactly as they are.

The grammar is: `*Visual:* <type> · <description / alt text> · slot: `<file>``

HARD OUTPUT RULES:
- Output ONLY the corrected markdown script. No preamble, no explanation, no surrounding ``` code fences.
- Start the response with the first `## Microlearning 1:` line. It MUST parse through the §8 grammar.
- Make the MINIMUM edits that add the missing descriptions; keep every unit's content and numbering intact.

================= VISUALS MISSING ALT TEXT =================
{lines}

================= CURRENT SCRIPT =================
{md_text}

================= END =================
Now output the full corrected script, bare §8 markdown only, starting at `## Microlearning 1:`."""


def heal_alt_text(provider, md_text, *, model=None, max_rounds=ALT_HEAL_ROUNDS, on_round=None):
    """M2 alt-text redraft loop (James's fork 2). While informative images are missing
    alt text and rounds remain, re-prompt the provider to draft descriptions for ONLY
    those images (text context, no vision), re-scan, and keep the draft with the FEWEST
    gaps — so a redraft can never make alt coverage worse.

    Returns {md, gaps, rounds, history}:
      - `gaps`    = the images STILL missing alt after the loop (never silently dropped;
                    they ride into the build report's a11y section).
      - `rounds`  = redraft passes actually made (0 when the draft already had full alt).
      - `history` = per-round {round, before, ok, after}. Never raises for normal
                    failures — a provider error just ends the loop and returns the best
                    draft. `run_cli` is the stubbed seam (no metered API)."""
    best_md = md_text
    best_gaps = alt_gaps(best_md)
    history, rounds = [], 0
    while best_gaps and rounds < max(0, max_rounds):
        rounds += 1
        ok, raw, err = run_cli(provider, build_alt_repair_prompt(best_md, best_gaps), model=model)
        if not ok:
            history.append({"round": rounds, "before": len(best_gaps), "ok": False,
                            "after": f"alt redraft pass failed: {err}"})
            break
        cand_md = clean_output(raw)
        cand_gaps = alt_gaps(cand_md)
        history.append({"round": rounds, "before": len(best_gaps),
                        "ok": not cand_gaps, "after": len(cand_gaps)})
        if on_round:
            try:
                on_round(rounds, not cand_gaps, cand_gaps)
            except Exception:
                pass
        # adopt only if the redraft strictly reduced the gap count; a stall or a
        # regression means keep the best draft and stop burning passes.
        if len(cand_gaps) < len(best_gaps):
            best_md, best_gaps = cand_md, cand_gaps
            if not best_gaps:
                break
        else:
            break
    return {"md": best_md, "gaps": best_gaps, "rounds": rounds, "history": history}


def generate(provider, source_folder, objective, audience, archetype, n_units, out_path,
             course_title=None, preset=None, urls=None, glossary=None):
    """Full Stage-2 run. Returns a result dict (never raises for normal failures)."""
    if not objective or not audience:
        return {"ok": False, "error": "Objective and audience are required (no drafting without them)."}
    if archetype not in ARCHETYPES:
        return {"ok": False, "error": f"unknown archetype {archetype}"}
    sources_text, used, skipped = read_sources(source_folder, urls=urls)
    if not sources_text.strip():
        return {"ok": False, "error": "No readable source documents found (.md/.txt/.csv/.doc/.docx/.rtf/.odt/.html/.pdf).",
                "skipped": skipped}

    if glossary is None:
        glossary = load_glossary()
    prompt = build_prompt(objective, audience, archetype, n_units, sources_text, course_title,
                          preset=preset, glossary=glossary)
    ok, raw, err = run_cli(provider, prompt)
    if not ok:
        return {"ok": False, "error": err, "used_sources": used, "skipped": skipped}

    md_text = clean_output(raw)
    # M1: self-heal the draft before it's written — re-prompt to fix any lint violations,
    # keeping the best draft. Residuals ride out in lint_errors + heal_rounds (never dropped).
    heal = heal_course_md(provider, md_text, glossary=glossary)
    md_text = heal["md"]
    lint_ok, units, lint_errors = heal["lint_ok"], heal["units"], heal["lint_errors"]
    # M2: alt-text redraft — after lint is healed, re-prompt to fill any informative
    # image missing its description. Residual gaps ride out in alt_gaps + alt_rounds
    # and are surfaced in the build report's a11y section (never silently dropped).
    alt = heal_alt_text(provider, md_text)
    md_text = alt["md"]
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(md_text)
    return {"ok": True, "out": out_path, "units": units, "lint_ok": lint_ok,
            "lint_errors": lint_errors, "used_sources": used, "skipped": skipped,
            "provider": provider, "heal_rounds": heal["rounds"], "heal_history": heal["history"],
            "alt_rounds": alt["rounds"], "alt_gaps": alt["gaps"], "alt_history": alt["history"]}


# --- M6: CSV manifest -> bulk generate ------------------------------------------------------------
# One manifest row per course. The columns mirror the per-course generate() params so a batch
# run is exactly N ordinary generations. Sources are pointed at the SAME way the dashboard does:
# a `source` folder (or single file) column PLUS an optional `urls` column (James's fork).

# Canonical column -> aliases (case/space/underscore-insensitive). First alias that appears in the
# header wins for that column; unknown headers are ignored (not an error) so operators can annotate.
MANIFEST_ALIASES = {
    "title":     ["title", "course", "course title", "name"],
    "objective": ["objective", "objectives", "goal", "learning objective"],
    "audience":  ["audience", "learner", "learners", "role"],
    "archetype": ["archetype", "type", "template"],
    "units":     ["units", "n units", "modules", "microlearnings"],
    "source":    ["source", "sources", "source folder", "folder", "docs"],
    "urls":      ["urls", "url", "links", "link"],
    "preset":    ["preset", "style"],
    "brand":     ["brand"],
}


def _norm_header(h):
    return re.sub(r"[\s_]+", " ", (h or "").strip().lower())


def parse_manifest(csv_text):
    """Parse a manifest CSV into a list of normalized row dicts. Returns (rows, errors).

    Column headers are matched case/space/underscore-insensitively against MANIFEST_ALIASES;
    unrecognized columns are ignored. Fully blank rows are skipped. Each row carries a 1-based
    `row` (the source spreadsheet row, header = row 1) for operator-facing error messages."""
    import csv, io
    text = (csv_text or "").lstrip("﻿")            # strip a UTF-8 BOM if present
    if not text.strip():
        return [], ["manifest is empty"]
    reader = csv.reader(io.StringIO(text))
    try:
        rows_raw = list(reader)
    except csv.Error as e:
        return [], [f"could not parse CSV: {e}"]
    if not rows_raw:
        return [], ["manifest is empty"]
    header = rows_raw[0]
    # map each canonical column -> its index in the header (first matching alias)
    norm = [_norm_header(h) for h in header]
    col_idx = {}
    for canon, aliases in MANIFEST_ALIASES.items():
        for i, h in enumerate(norm):
            if h in aliases and canon not in col_idx:
                col_idx[canon] = i
    errors = []
    for req in ("objective", "audience", "source"):
        if req not in col_idx:
            errors.append(f"manifest is missing a required column: {req}")
    if errors:
        return [], errors
    rows = []
    for n, raw in enumerate(rows_raw[1:], start=2):     # data rows; header is row 1
        if not any((c or "").strip() for c in raw):
            continue                                    # skip fully blank lines
        def cell(canon):
            i = col_idx.get(canon)
            return (raw[i].strip() if i is not None and i < len(raw) else "")
        rows.append({
            "row": n,
            "title": cell("title"),
            "objective": cell("objective"),
            "audience": cell("audience"),
            "archetype": cell("archetype") or "concept-explainer",
            "units": cell("units"),
            "source": cell("source"),
            "urls": cell("urls"),
            "preset": cell("preset"),
            "brand": cell("brand"),
        })
    if not rows:
        errors.append("manifest has a header but no data rows")
    return rows, errors


def validate_manifest(rows):
    """Dry-run check of parsed manifest rows WITHOUT generating anything. Returns a list of
    {row, title, ok, issues} — one per row, in order. A row is ok when it has an objective and
    audience, a known archetype, and a readable source (an existing folder/file OR some urls)."""
    out = []
    for r in rows:
        issues = []
        if not r.get("objective"):
            issues.append("missing objective")
        if not r.get("audience"):
            issues.append("missing audience")
        if r.get("archetype") not in ARCHETYPES:
            issues.append(f"unknown archetype {r.get('archetype')!r} "
                          f"(one of: {', '.join(sorted(ARCHETYPES))})")
        src = os.path.expanduser(r.get("source") or "")
        has_urls = bool(_coerce_urls(r.get("urls")))
        if src:
            if not (os.path.isdir(src) or os.path.isfile(src)):
                issues.append(f"source not found: {r.get('source')}")
        elif not has_urls:
            issues.append("no source folder/file and no urls")
        units = r.get("units")
        if units and not str(units).strip().isdigit():
            issues.append(f"units must be a whole number, got {units!r}")
        out.append({"row": r.get("row"), "title": r.get("title") or "(untitled)",
                    "ok": not issues, "issues": issues})
    return out


def generate_batch(provider, rows, out_dir, brand=None, glossary=None, on_row=None):
    """Generate one course per manifest row into out_dir, reusing the per-course generate().
    Continue-on-error: a failing row is recorded and the batch proceeds. Output filenames are
    slugged from the row title (objective as fallback) and de-duplicated so no row overwrites
    another. `on_row(i, total, row)` is an optional progress hook. Returns a summary dict."""
    os.makedirs(out_dir, exist_ok=True)
    results = []
    used_slugs = {}
    total = len(rows)
    for i, r in enumerate(rows):
        if on_row:
            try:
                on_row(i, total, r)
            except Exception:
                pass
        base = (r.get("title") or r.get("objective") or "course")
        slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-") or "course"
        used_slugs[slug] = used_slugs.get(slug, 0) + 1
        if used_slugs[slug] > 1:
            slug = f"{slug}-{used_slugs[slug]}"          # disambiguate a repeated title
        out_md = os.path.join(out_dir, f"{slug}.md")
        units = int(r["units"]) if str(r.get("units", "")).strip().isdigit() else None
        row_brand = r.get("brand") or brand
        g = load_glossary(row_brand) if r.get("brand") else (glossary if glossary is not None
                                                             else load_glossary(brand))
        res = generate(provider, source_folder=r.get("source", ""), objective=r.get("objective", ""),
                       audience=r.get("audience", ""), archetype=r.get("archetype") or "concept-explainer",
                       n_units=units, out_path=out_md, course_title=r.get("title") or None,
                       preset=r.get("preset") or None, urls=r.get("urls") or None, glossary=g)
        results.append({"row": r.get("row"), "title": r.get("title") or slug,
                        "ok": bool(res.get("ok")), "out": res.get("out", ""),
                        "units": res.get("units"), "lint_ok": res.get("lint_ok"),
                        "lint_errors": res.get("lint_errors", []),
                        "error": res.get("error"), "skipped": res.get("skipped", [])})
    ok_count = sum(1 for x in results if x["ok"])
    return {"ok": ok_count > 0, "results": results, "n": total,
            "ok_count": ok_count, "fail_count": total - ok_count}
