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
    "sales-rep-onboarding": "Ramp a new sales rep (role + 30-day success → product overview → ICP & "
                            "personas → sales process/methodology → toolkit → first 30 days → KC).",
    "objection-handling": "Handle sales objections with LAER (cold open → instinct KC → LAER framework "
                          "→ competitor / price / timing dialogues → scenario KC → takeaway).",
}

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
    "- The teaching substance itself → ordinary paragraphs (single column).\n"
    "- Use a MULTI-COLUMN block (comparison/cards) ONLY when the items are truly parallel and short "
    "enough to scan side-by-side; if they are sequential, dependent, or long, keep ONE column "
    "(forcing serial content into columns splits attention)."
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
    "- One visual per idea, placed next to the text it supports (contiguity)."
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
    "rejected by the build."
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

def _read_one(path):
    low = path.lower()
    if low.endswith((".md", ".txt", ".markdown")):
        try:
            return open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            return ""
    if low.endswith(".docx"):
        try:
            from docx import Document
            return "\n".join(p.text for p in Document(path).paragraphs)
        except Exception:
            return ""
    if low.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            return "\n".join((pg.extract_text() or "") for pg in PdfReader(path).pages)
        except Exception:
            return ""
    return None                                   # unsupported (e.g. images)


def read_sources(path):
    """Concatenate readable source docs from a FOLDER or a single FILE.
    Returns (text, used_files, skipped_files)."""
    path = os.path.expanduser(path or "")
    used, skipped, parts = [], [], []
    if os.path.isfile(path):
        targets = [path]
    elif os.path.isdir(path):
        targets = [os.path.join(path, n) for n in sorted(os.listdir(path), key=str.lower)
                   if not n.startswith(".")]
    else:
        return "", used, skipped
    for full in targets:
        if not os.path.isfile(full):
            continue
        name = os.path.basename(full)
        text = _read_one(full)
        if text is None:
            skipped.append(name)                  # unsupported format (e.g. image)
            continue
        if text.strip():
            parts.append(f"===== SOURCE DOCUMENT: {name} =====\n{text.strip()}")
            used.append(name)
    return "\n\n".join(parts), used, skipped


# --------------------------------------------------------------- prompt assembly

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")


def list_images(folder):
    """Filenames of the image assets available in `folder` (for the prompt)."""
    if not folder or not os.path.isdir(folder):
        return []
    return sorted(n for n in os.listdir(folder)
                  if n.lower().endswith(_IMAGE_EXTS) and not n.startswith("."))


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
                 images=None):
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
- DEFENSIBLE DESIGN: every unit's Build Notes MUST include a `Design Rationale:` line that states WHY
  the unit is built as it is — named to the §0 (pedagogy) AND §0b (media/layout) principles, covering
  BOTH the structure and the PRESENTATION choices (why this layout, why this media treatment or none,
  why a note vs prose). Keep it to 1–3 short lines, under the `**Articulate Build Notes:**` marker.

{_image_directive(images)}

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


def build_plan_prompt(objective, audience, archetype, n_units, sources_text, course_title=None):
    """Pass 2 — PLAN only. Returns a short, strictly-formatted unit breakdown."""
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
UNIT | <short unit title> | <the specific learning points / objective this unit teaches>
UNIT | <short unit title> | <...>
(one `UNIT |` line per unit, in teaching order)

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
                      sources_text, course_title=None, images=None):
    """Pass 3 — write ONE unit's full §8 script, with the whole plan as context."""
    guide, arch = _guide_and_archetype(archetype)
    plan_list = "\n".join(f"{i}. {u.get('title','')} — {u.get('objective','')}"
                          for i, u in enumerate(all_units, 1))
    coming_soon = ", ".join(sorted(blocks.coming_soon_types()))
    cs_rule = (f"- COMING SOON (do NOT author): [{coming_soon}] — import-only stubs; never emit them."
               if coming_soon else "")
    title_line = f"Course title: {course_title}\n" if course_title else ""
    return f"""You are an instructional designer writing ONE microlearning unit's SCRIPT in the exact \
§8 markdown grammar the build pipeline consumes. Follow the AUTHORING GUIDE and ARCHETYPE precisely.

This is unit {idx} of {total}. Write ONLY this one unit — do NOT write the others.

FULL COURSE PLAN (context so your unit fits, sequences correctly, and does NOT overlap the rest):
{plan_list}

THIS UNIT:
  Title: {unit.get('title','')}
  Teaches: {unit.get('objective','')}

HARD OUTPUT RULES:
- Output ONLY the markdown for THIS unit. No preamble, no explanation, no ``` code fences.
- Start the response with `## Microlearning {idx}: {unit.get('title','')}`.
- It MUST parse the §8 grammar on the first try (Slide 1 is always Learning Objectives with a
  *Visual:*; KCs use the `- A)` form with exactly one *Correct Answer:*).
- Ground every slide ONLY in the SOURCE MATERIAL. Do NOT invent product behavior or facts.
{cs_rule}
- PEDAGOGY (AUTHORING GUIDE §0): write for an ADULT learner — open with the learner's stake/relevance
  (Knowles), build problem → demonstrate → apply → integrate (Merrill) on Gagné's nine-event spine. A
  unit that parses but is a flat content-dump is a DEFECT.
- MEDIA & LAYOUT (§0b): match content to the right structure/media treatment (or none).
- DEFENSIBLE DESIGN: this unit's `**Articulate Build Notes:**` MUST include a `Design Rationale:` line
  (1–3 lines) naming the §0 and §0b principles behind its structure AND presentation choices.

{_image_directive(images)}

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

def lint(md_text):
    """Dry-run every unit through md_import. Returns (ok, units, errors)."""
    from md_import import import_md
    n = len(re.split(r"^##\s+Microlearning\s+", md_text, flags=re.M)) - 1
    if n < 1:
        return False, 0, ["no '## Microlearning N:' unit produced"]
    errors = []
    # Coming-soon stub guard: a `*Scenario:*` / `*Continue:*` / `*HeadingParagraph:*`
    # marker has no parser yet, so md_import would silently degrade it to a
    # paragraph. Catch the authoring attempt and flag it instead of swallowing it.
    cs_names = "|".join(re.escape(t) for t in sorted(blocks.coming_soon_types()))
    if cs_names:
        for m in re.finditer(rf"(?im)^\*\s*({cs_names})\s*:\*", md_text):
            errors.append(f"`*{m.group(1)}:*` is a COMING-SOON block type — not yet "
                          f"authorable (import-only). Remove it or use the available §8 grammar.")
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
            except Exception as e:
                errors.append(f"unit {k}: {e}")
    finally:
        os.unlink(tmp)
    return (not errors), n, errors


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


def revise(provider, script_path, reviewed_docx, out_path):
    """Apply an SME's reviewed/commented .docx back onto the canonical script.

    Reads the current §8 script + the reviewed doc's body text + any tracked
    comments, then drives the subscription CLI to produce the updated script,
    lint-gated like generation."""
    try:
        current = open(script_path, encoding="utf-8").read()
    except OSError as e:
        return {"ok": False, "error": f"can't read current script: {e}"}
    body = _read_one(reviewed_docx) or ""
    if not body.strip():
        return {"ok": False, "error": "reviewed document is empty or unreadable (.docx expected)."}
    comments = _docx_comments(reviewed_docx)
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

    ok, raw, err = run_cli(provider, prompt)
    if not ok:
        return {"ok": False, "error": err}
    md_text = clean_output(raw)
    lint_ok, units, lint_errors = lint(md_text)
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
}
_LAYOUT_ORDER = ["divider", "process", "comparison", "timeline", "infographic"]


def load_slide_templates():
    """The canonical per-layout content templates — the SAME files the slide
    renderer ships, so the deck pipeline and the slide pipeline share templates."""
    import json as _json
    d = os.path.join(TEMPLATES, "slide-layouts")
    out = {}
    if os.path.isdir(d):
        for lay in _LAYOUT_ORDER:
            fp = os.path.join(d, f"{lay}.example.json")
            if os.path.isfile(fp):
                try:
                    out[lay] = _json.load(open(fp, encoding="utf-8"))
                except ValueError:
                    pass
    return out


def build_deck_prompt(title, focus, audience, n_slides, sources_text):
    import json as _json
    templates = load_slide_templates()
    guide = "\n\n".join(
        f'### layout "{lay}" — {LAYOUT_PURPOSE.get(lay, "")}\n{_json.dumps(ex, indent=2)}'
        for lay, ex in templates.items())
    count = (f"Produce exactly {n_slides} slides." if n_slides
             else "Use however many slides the material warrants — typically 6–12.")
    ttl = f"PRESENTATION TITLE: {title}\n" if title else ""
    aud = f"AUDIENCE: {audience}\n" if audience else ""
    return f"""You are a presentation designer. Convert the SOURCE MATERIAL into an on-brand \
slide DECK by choosing, for each slide, the best-fitting template LAYOUT and filling its content.

HARD OUTPUT RULES:
- Output ONLY a single JSON object: {{"slides": [ {{"layout": "<name>", "content": {{...}}}}, ... ]}}.
- No preamble, no explanation, no markdown, no ``` fences. The FIRST character must be '{{'.
- "layout" must be one of: infographic, process, comparison, timeline, divider.
- "content" MUST match that layout's schema below; omit keys you don't need.
- Match the layout to the content (the SAME design rules the course generator uses — §0b):
{LAYOUT_MATCH}
- Open with a divider title slide. Ground EVERY slide ONLY in the source material; do NOT invent facts.
- {count}

{ttl}{aud}FOCUS / WHAT TO EMPHASIZE: {focus or "(summarize the key content faithfully)"}

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
    valid = {"infographic", "process", "comparison", "timeline", "divider"}
    errors = [f"slide {i}: unknown layout {(s or {}).get('layout')!r}"
              for i, s in enumerate(slides, 1) if (s or {}).get("layout") not in valid]
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


def generate_deck(provider, source_folder, title=None, focus="", audience="", n_slides=None):
    """Convert raw source documents into a templated slide deck (list of
    {layout, content}). Mirrors generate() but the output is a deck spec, not a
    course script. Never raises for normal failures."""
    import json as _json
    sources_text, used, skipped = read_sources(source_folder)
    if not sources_text.strip():
        return {"ok": False, "error": "No readable source documents found (.md/.txt/.docx).",
                "skipped": skipped}
    prompt = build_deck_prompt(title, focus, audience, n_slides, sources_text)
    ok, raw, err = run_cli(provider, prompt)
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
            "lint_errors": lint_errors, "used_sources": used, "skipped": skipped,
            "provider": provider}


def generate(provider, source_folder, objective, audience, archetype, n_units, out_path,
             course_title=None):
    """Full Stage-2 run. Returns a result dict (never raises for normal failures)."""
    if not objective or not audience:
        return {"ok": False, "error": "Objective and audience are required (no drafting without them)."}
    if archetype not in ARCHETYPES:
        return {"ok": False, "error": f"unknown archetype {archetype}"}
    sources_text, used, skipped = read_sources(source_folder)
    if not sources_text.strip():
        return {"ok": False, "error": "No readable source documents found (.md/.txt/.docx).",
                "skipped": skipped}

    prompt = build_prompt(objective, audience, archetype, n_units, sources_text, course_title)
    ok, raw, err = run_cli(provider, prompt)
    if not ok:
        return {"ok": False, "error": err, "used_sources": used, "skipped": skipped}

    md_text = clean_output(raw)
    lint_ok, units, lint_errors = lint(md_text)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(md_text)
    return {"ok": True, "out": out_path, "units": units, "lint_ok": lint_ok,
            "lint_errors": lint_errors, "used_sources": used, "skipped": skipped,
            "provider": provider}
