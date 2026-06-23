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
import re
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TEMPLATES = os.path.join(ROOT, "templates")

ARCHETYPES = {
    "concept-explainer": "Teach an idea/term (what → why → how → apply → recap → KC).",
    "software-procedure": "Do a task in the product (goal → steps → demo → mistakes → recap → KC).",
    "decision-scenario": "Apply a rule (rule → criteria → scenario → decision KC → debrief).",
    "policy-acceptable-use": "Compliance (core rule → why → do/don't → when unsure → KC).",
}

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
    return None                                   # unsupported (e.g. .pdf)


def read_sources(folder):
    """Concatenate readable source docs. Returns (text, used_files, skipped_files)."""
    folder = os.path.expanduser(folder or "")
    used, skipped, parts = [], [], []
    if not os.path.isdir(folder):
        return "", used, skipped
    for name in sorted(os.listdir(folder), key=str.lower):
        if name.startswith("."):
            continue
        full = os.path.join(folder, name)
        if not os.path.isfile(full):
            continue
        text = _read_one(full)
        if text is None:
            skipped.append(name)                  # unsupported format (PDF needs PyMuPDF)
            continue
        if text.strip():
            parts.append(f"===== SOURCE DOCUMENT: {name} =====\n{text.strip()}")
            used.append(name)
    return "\n\n".join(parts), used, skipped


# --------------------------------------------------------------- prompt assembly

def build_prompt(objective, audience, archetype, n_units, sources_text, course_title=None):
    guide_path = os.path.join(TEMPLATES, "AUTHORING_GUIDE.md")
    guide = open(guide_path, encoding="utf-8").read() if os.path.isfile(guide_path) else ""
    arch_path = os.path.join(TEMPLATES, f"{archetype}.md")
    archetype_text = open(arch_path, encoding="utf-8").read() if os.path.isfile(arch_path) else ""

    unit_instr = (f"Produce exactly {n_units} microlearning unit(s)." if n_units
                  else "Decompose the material into however many 10–15-minute units it warrants "
                       "(one `## Microlearning N:` per unit).")
    title_line = f"Course/batch title: {course_title}\n" if course_title else ""

    return f"""You are an instructional designer drafting a microlearning SCRIPT in the \
exact markdown grammar the build pipeline consumes. Follow the AUTHORING GUIDE and the chosen \
ARCHETYPE precisely.

HARD OUTPUT RULES:
- Output ONLY the markdown script. No preamble, no explanation, no surrounding ``` code fences.
- Start the response with the first `## Microlearning 1: <Title>` line.
- It MUST parse through the §8 grammar on the first try (Slide 1 is always Learning Objectives with
  a *Visual:*; KCs use the `- A)` form with exactly one `*Correct Answer:*`).
- Ground every slide ONLY in the SOURCE MATERIAL. Do NOT invent product behavior or facts.
- {unit_instr}

{title_line}LEARNING OBJECTIVE (required intent): {objective}
AUDIENCE: {audience}

================= AUTHORING GUIDE (always-on rules) =================
{guide}

================= ARCHETYPE: {archetype} =================
{archetype_text}

================= SOURCE MATERIAL =================
{sources_text}

================= END SOURCE MATERIAL =================
Now write the script. Remember: bare §8 markdown only, starting at `## Microlearning 1:`."""


# --------------------------------------------------------------- CLI driving

def run_cli(provider, prompt, timeout=600):
    """Run the subscription CLI headlessly on the user's plan. Returns (ok, text, err).

    claude: `claude -p` < prompt  -> answer on stdout.
    codex:  `codex exec --sandbox read-only --output-last-message <f> -` < prompt
            -> final agent message written to <f> (clean), falling back to stdout.
    """
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

    # claude
    argv = ["claude", "-p"]
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
    import sys
    sys.path.insert(0, HERE)
    from md_import import import_md
    n = len(re.split(r"^##\s+Microlearning\s+", md_text, flags=re.M)) - 1
    if n < 1:
        return False, 0, ["no '## Microlearning N:' unit produced"]
    errors = []
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(md_text)
        tmp = fh.name
    try:
        for k in range(1, n + 1):
            try:
                ir, _ = import_md(tmp, which=k)
                if not ir.get("blocks"):
                    errors.append(f"unit {k}: parsed but produced no blocks")
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
