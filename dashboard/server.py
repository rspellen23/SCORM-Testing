"""course-builder — local dashboard server (no Streamlit, no GUI toolkit).

A stdlib HTTP server that serves one HTML page + a small JSON API and drives the
SME curriculum workflow as a guided flow:

  1. Source docs  →  2. Generate scripts (Layer 2)  →  3. Approved script
  →  4. Build + preview  →  5. SCORM package in the output folder

Folder selection is an IN-BROWSER navigator (no native dialog, nothing to crash on
the main thread). The server only shells out to src/cli.py and calls
src/docx_review — it reimplements no engine logic.

Launch (double-clickable): dashboard/launch.command   ·   or: python3 dashboard/server.py
"""
import os
import re
import sys
import json
import socket
import secrets
import tempfile
import subprocess
import webbrowser
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
CLI = os.path.join(SRC, "cli.py")
HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
# Air-gapped fallback: make the engine importable when the package isn't
# installed. Idempotent; a no-op once `pip install -e .`.
if SRC not in sys.path:
    sys.path.insert(0, SRC)

# --- Phase 5 security: localhost-tool hardening -----------------------------
# This server binds 127.0.0.1 and is driven by its own page. The threats are
# (a) a malicious site the user visits driving this API cross-origin (CSRF) and
# (b) file read/list/serve endpoints escaping to sensitive paths. The token is
# per-process and stamped into the served index.html; only that same-origin page
# can read it (CORS bars a cross-origin site from reading our responses).
CSRF_TOKEN = secrets.token_urlsafe(24)


def _allow_roots():
    """Directories the file endpoints may read/list/serve under — broad enough to
    keep the folder navigator useful (home + mounted drives + build staging) while
    excluding system trees (/etc) and other users' homes."""
    cands = [os.path.expanduser("~"), ROOT, tempfile.gettempdir()]
    if os.path.isdir("/Volumes"):
        cands.append("/Volumes")          # external/mounted drives on macOS
    roots = []
    for c in cands:
        try:
            roots.append(os.path.realpath(c))
        except OSError:
            pass
    return roots


def _within_roots(path):
    """True if `path` resolves to a location inside one of the allowed roots.
    Resolves symlinks first so a link can't tunnel out of the allowlist."""
    if not path:
        return False
    try:
        rp = os.path.realpath(os.path.abspath(os.path.expanduser(path)))
    except OSError:
        return False
    for root in _allow_roots():
        try:
            if os.path.commonpath([root, rp]) == root:
                return True
        except ValueError:                # different drive (Windows)
            continue
    return False


def _safe_path_arg(v, label):
    """Reject a path argument that argparse would misread as a flag (leading '-')."""
    if not isinstance(v, str) or v.startswith("-"):
        raise ValueError(f"invalid {label} path")
    return v


def _safe_brand(b):
    """Confine the build's --brand to a real brand directory."""
    b = b or "_default"
    if b not in list_brands():
        raise ValueError(f"unknown brand: {b}")
    return b

# project scaffold — friendly, numbered so the flow is obvious in Finder
PROJECT_FOLDERS = {
    "source": "1 - Source Documents",
    "images": "2 - Images",
    "drafts": "3 - Draft Scripts (for SME review)",
    "approved": "4 - Approved Scripts",
    "output": "5 - Course Output (upload to LMS)",
}


def list_brands():
    bdir = os.path.join(ROOT, "brands")
    if not os.path.isdir(bdir):
        return ["_default"]
    return sorted(d for d in os.listdir(bdir) if os.path.isdir(os.path.join(bdir, d))) or ["_default"]


SLIDE_ORDER = ["infographic", "process", "comparison", "timeline", "chart", "divider"]


def slide_layout_names():
    """Available slide layouts, in a stable display order (no python-pptx needed)."""
    names = None
    try:
        import slide_layouts
        names = list(slide_layouts.LAYOUTS)
    except Exception:
        d = os.path.join(ROOT, "templates", "slide-layouts")
        if os.path.isdir(d):
            names = [f[:-len(".example.json")] for f in os.listdir(d) if f.endswith(".example.json")]
    names = names or list(SLIDE_ORDER)
    return [n for n in SLIDE_ORDER if n in names] + [n for n in names if n not in SLIDE_ORDER]


def slide_examples():
    """Starter content (parsed) for each slide layout, keyed by layout name."""
    d = os.path.join(ROOT, "templates", "slide-layouts")
    out = {}
    for lay in slide_layout_names():
        try:
            out[lay] = json.load(open(os.path.join(d, f"{lay}.example.json"), encoding="utf-8"))
        except (OSError, ValueError):
            out[lay] = {}
    return out


def microlearnings(md_path):
    try:
        text = open(md_path, encoding="utf-8").read()
    except OSError:
        return []
    return [{"which": i, "title": m.group(1).strip()}
            for i, m in enumerate(
                re.finditer(r"^##\s+Microlearning\s+\d+:\s*(.+)$", text, flags=re.M), 1)]


def ls(path):
    """List sub-directories and files of a directory (for the navigator).
    Returns every non-hidden file in `files`, plus `mds`/`docx` subsets so the
    file-mode picker can mark which are selectable."""
    path = os.path.abspath(os.path.expanduser(path or os.path.expanduser("~")))
    if not os.path.isdir(path):
        path = os.path.expanduser("~")
    dirs, mds, docx, files = [], [], [], []
    try:
        for name in sorted(os.listdir(path), key=str.lower):
            if name.startswith("."):
                continue
            full = os.path.join(path, name)
            if os.path.isdir(full):
                dirs.append(name)
            else:
                files.append(name)
                if name.lower().endswith(".md"):
                    mds.append(name)
                elif name.lower().endswith(".docx"):
                    docx.append(name)
    except PermissionError:
        pass
    parent = os.path.dirname(path)
    return {"path": path, "parent": parent if parent != path else None,
            "dirs": dirs, "mds": mds, "docx": docx, "files": files}


def list_files(folder, exts=None):
    """List files (optionally by extension) in a folder, for the flow's status panels."""
    folder = os.path.expanduser(folder or "")
    if not os.path.isdir(folder):
        return []
    out = []
    for name in sorted(os.listdir(folder), key=str.lower):
        if name.startswith("."):
            continue
        if exts and not name.lower().endswith(tuple(exts)):
            continue
        if os.path.isfile(os.path.join(folder, name)):
            out.append(name)
    return out


def project_setup(root):
    """Create the numbered subfolder structure under a chosen project root."""
    root = os.path.abspath(os.path.expanduser(root))
    os.makedirs(root, exist_ok=True)
    paths = {}
    for key, name in PROJECT_FOLDERS.items():
        p = os.path.join(root, name)
        os.makedirs(p, exist_ok=True)
        paths[key] = p
    return {"root": root, "paths": paths}


# ----- projects workspace (many projects, each its own folder, reopenable) ----

CONFIG_DIR = os.path.expanduser("~/.course-builder")
CONFIG = os.path.join(CONFIG_DIR, "config.json")


def load_config():
    try:
        return json.load(open(CONFIG, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(d):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    cur = load_config()
    cur.update(d)
    json.dump(cur, open(CONFIG, "w", encoding="utf-8"), indent=2)
    return cur


def project_folders(root):
    return {key: os.path.join(root, name) for key, name in PROJECT_FOLDERS.items()}


def _now():
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def read_project(root):
    """Return a project's metadata (project.json) + derived folder map."""
    pj = os.path.join(root, "project.json")
    meta = {}
    if os.path.isfile(pj):
        try:
            meta = json.load(open(pj, encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
    return {"path": root, "name": meta.get("name") or os.path.basename(root),
            "meta": meta, "folders": project_folders(root)}


def write_project(root, meta):
    """Merge metadata into project.json, stamping updated (and created once)."""
    pj = os.path.join(root, "project.json")
    cur = {}
    if os.path.isfile(pj):
        try:
            cur = json.load(open(pj, encoding="utf-8"))
        except (OSError, ValueError):
            cur = {}
    cur.update({k: v for k, v in (meta or {}).items() if v is not None})
    cur.setdefault("created", _now())
    cur["updated"] = _now()
    cur.setdefault("name", os.path.basename(root))
    os.makedirs(root, exist_ok=True)
    json.dump(cur, open(pj, "w", encoding="utf-8"), indent=2)
    return cur


def list_projects(workspace):
    """Folders under the workspace that look like projects (have project.json or the scaffold)."""
    out = []
    workspace = os.path.expanduser(workspace or "")
    if not os.path.isdir(workspace):
        return out
    for name in sorted(os.listdir(workspace), key=str.lower):
        if name.startswith("."):
            continue
        d = os.path.join(workspace, name)
        if not os.path.isdir(d):
            continue
        has_pj = os.path.isfile(os.path.join(d, "project.json"))
        has_scaffold = any(os.path.isdir(os.path.join(d, f)) for f in PROJECT_FOLDERS.values())
        if has_pj or has_scaffold:
            p = read_project(d)
            out.append({"name": p["name"], "path": d,
                        "title": p["meta"].get("title", ""), "updated": p["meta"].get("updated", "")})
    return out


def new_project(workspace, name):
    safe = re.sub(r"[^\w\- ]+", "", name).strip() or "Untitled Project"
    root = os.path.join(os.path.expanduser(workspace), safe)
    project_setup(root)                                   # scaffold the subfolders
    meta = write_project(root, {"name": safe})           # seed project.json
    return {"path": root, "name": safe, "meta": meta, "folders": project_folders(root)}


def run_cli(args):
    proc = subprocess.run([sys.executable, CLI, *args], cwd=ROOT, capture_output=True, text=True)
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


def build_jobs(p):
    """List of job dicts {label, args, out, preview} for a build request."""
    md = _safe_path_arg(p["md"], "md")
    img = _safe_path_arg(p["images"], "images")
    out = _safe_path_arg(p["out"], "out")
    brand, validate = _safe_brand(p.get("brand", "_default")), p.get("validate", True)
    animate = p.get("animate", True)                  # entrance animations on by default
    entire = p.get("scope") == "course"
    which = int(p.get("which", 1))
    mls = microlearnings(md)
    # Production model: each unit is its OWN independent single-SCO package, and
    # the LMS sequences them in a Path. "All units" therefore builds one package
    # PER unit (a from-md loop) — never a single multi-SCO bundle.
    targets = [m["which"] for m in mls] if (entire and mls) else [which]
    multi = len(targets) > 1
    stem = os.path.splitext(os.path.basename(md))[0]
    jobs = []
    for fmt in p.get("formats", []):
        if fmt == "pptx":
            for w in targets:
                op = os.path.join(out, f"{stem}_m{w}.pptx")
                jobs.append({"label": f"PowerPoint · unit {w}", "fmt": "pptx",
                             "args": ["to-pptx", md, "--which", str(w), "--images", img,
                                      "--brand", brand, "--out", op], "out": op, "preview": None})
        else:
            f = "cmi5" if fmt == "cmi5" else "scorm"
            tag = "cmi5" if f == "cmi5" else "scorm12"
            label_base = "cmi5/xAPI package" if f == "cmi5" else "SCORM 1.2 package"
            for w in targets:
                op = os.path.join(out, f"{stem}_m{w}_{tag}.zip")
                a = ["from-md", md, "--which", str(w), "--images", img, "--brand", brand,
                     "--format", f, "--out", op, "--keep-dir"]   # keep the .course dir for preview
                if validate:
                    a.append("--validate")
                if not animate:
                    a.append("--no-animate")
                preview = os.path.join(os.path.splitext(op)[0] + ".course", "index.html")
                label = f"{label_base} · unit {w}" if multi else label_base
                jobs.append({"label": label, "fmt": f, "args": a, "out": op, "preview": preview})
    return jobs


def do_build(p):
    """Build the selected formats. With stage=True, build into a hidden .preview/
    area so the learner-facing course can be reviewed BEFORE it's published."""
    out_root = p["out"]
    target = os.path.join(out_root, ".preview") if p.get("stage") else out_root
    os.makedirs(target, exist_ok=True)
    pp = dict(p); pp["out"] = target
    results = []
    for j in build_jobs(pp):
        ok, log = run_cli(j["args"])
        ok = ok and os.path.exists(j["out"])
        prev = j["preview"] if (ok and j["preview"] and os.path.exists(j["preview"])) else None
        results.append({"label": j["label"], "ok": ok, "out": j["out"], "preview": prev,
                        "log": log, "fmt": j["fmt"]})
    return {"results": results, "staged": bool(p.get("stage")), "out_root": out_root}


def do_generate_deck(p):
    """Convert raw source documents into a templated slide deck via the SAME
    authoring pipeline the course flow uses (provider plumbing + source reading
    + the shared slide-layout templates). Returns the slide specs for review."""
    import authoring
    return authoring.generate_deck(
        provider=p.get("provider", "claude"),
        source_folder=p.get("source", ""),
        title=p.get("title") or None,
        focus=p.get("focus", ""),
        audience=p.get("audience", ""),
        n_slides=int(p["nslides"]) if str(p.get("nslides", "")).strip().isdigit() else None)


def do_deck(p):
    """Assemble a multi-slide, on-brand .pptx PRESENTATION from an ordered list
    of slides via the deck CLI. No project, source docs, or images folder —
    this is the presentation path, distinct from the course flow."""
    import tempfile
    out_dir = os.path.abspath(os.path.expanduser(
        p.get("out") or os.path.join(os.path.expanduser("~"), "Course Builder Slides")))
    os.makedirs(out_dir, exist_ok=True)
    name = re.sub(r"[^\w\- ]+", "", (p.get("name") or "presentation")).strip() or "presentation"
    op = os.path.join(out_dir, name + ".pptx")

    slides = p.get("slides")
    if not isinstance(slides, list) or not slides:
        return {"ok": False, "out": op, "log": "Add at least one slide to the presentation."}
    # each slide may carry content as a JSON string (from the editor) — parse it
    norm = []
    for i, sp in enumerate(slides, 1):
        sp = sp or {}
        content = sp.get("content")
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except ValueError as e:
                return {"ok": False, "out": op, "log": f"Slide {i} content is not valid JSON: {e}"}
        norm.append({"layout": sp.get("layout", "infographic"), "content": content or {}})

    cf = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    try:
        json.dump({"slides": norm}, cf)
        cf.close()
        args = ["deck", "--content", cf.name, "--brand", _safe_brand(p.get("brand", "_default")), "--out", op]
        tr = p.get("transition")
        if tr and tr in ("fade", "cut", "push", "wipe", "split", "cover"):
            args += ["--transition", tr]
            if p.get("transition_dir") in ("l", "r", "u", "d"):
                args += ["--transition-dir", p["transition_dir"]]
        ok, log = run_cli(args)
    finally:
        try:
            os.unlink(cf.name)
        except OSError:
            pass
    ok = ok and os.path.exists(op)
    return {"ok": ok, "out": op, "log": log, "slides": len(norm), "out_dir": out_dir}


def do_publish(p):
    """Move reviewed packages from the preview area into the output folder
    (the upload-ready location) and record the publish in project.json."""
    import shutil
    out_root = p["out"]
    os.makedirs(out_root, exist_ok=True)
    published = []
    for item in p.get("items", []):
        src = item.get("path", "")
        label = item.get("label", os.path.basename(src))
        if not src or not os.path.exists(src):
            published.append({"label": label, "ok": False, "out": src, "err": "build not found"})
            continue
        dst = os.path.join(out_root, os.path.basename(src))
        try:
            shutil.move(src, dst)
            published.append({"label": label, "ok": True, "out": dst})
        except Exception as e:
            published.append({"label": label, "ok": False, "out": src, "err": str(e)})
    proj = p.get("project")
    if proj:
        try:
            write_project(proj, {"published": {"when": _now(),
                                 "files": [x["out"] for x in published if x["ok"]]}})
        except (OSError, ValueError) as e:
            # The move(s) succeeded; only the project.json record failed. Don't
            # fail the publish, but surface it so the lost state isn't invisible.
            sys.stderr.write(f"[server] could not record publish in {proj}: {e}\n")
    return {"published": published, "out_root": out_root}


def do_review(p):
    import importlib
    from md_import import import_md
    import docx_review, brand as brandmod
    importlib.reload(docx_review)
    b = brandmod.load_brand(p.get("brand", "_default"))
    os.makedirs(p["out"], exist_ok=True)
    md = p["md"]
    stem = os.path.splitext(os.path.basename(md))[0]
    targets = ([int(p["which"])] if p.get("scope") == "single"
               else [m["which"] for m in microlearnings(md)])
    results = []
    for w in targets:
        try:
            ir, _ = import_md(md, which=w)
            op = os.path.join(p["out"], f"{stem}_m{w}_review.docx")
            docx_review.render_review_docx(ir, op, brand=b, md_path=md, which=w)
            results.append({"label": f"Unit {w}: {ir['title']}", "ok": True, "out": op, "log": ""})
        except Exception as e:
            results.append({"label": f"Unit {w}", "ok": False, "out": "", "log": str(e)})
    return {"results": results}


def do_generate(p):
    """Stage 2: draft a script from source docs via the chosen subscription CLI,
    then (best-effort) render the SME review .docx from it."""
    import authoring, re as _re
    out_dir = p["out"]
    os.makedirs(out_dir, exist_ok=True)
    title = (p.get("title") or "course").strip()
    slug = _re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "course"
    out_md = os.path.join(out_dir, f"{slug}.md")
    n_units = int(p["units"]) if str(p.get("units", "")).strip().isdigit() else None
    res = authoring.generate(
        provider=p.get("provider", "claude"), source_folder=p["source"],
        objective=p.get("objective", ""), audience=p.get("audience", ""),
        archetype=p.get("archetype", "concept-explainer"), n_units=n_units,
        out_path=out_md, course_title=p.get("title") or None)
    # auto-render review .docx when the draft parses
    if res.get("ok") and res.get("lint_ok"):
        try:
            import importlib
            from md_import import import_md
            import docx_review, brand as brandmod
            importlib.reload(docx_review)
            b = brandmod.load_brand(p.get("brand", "_default"))
            docx_paths = []
            for k in range(1, res.get("units", 0) + 1):
                ir, _ = import_md(out_md, which=k)
                dp = os.path.join(out_dir, f"{slug}_m{k}_review.docx")
                docx_review.render_review_docx(ir, dp, brand=b, md_path=out_md, which=k)
                docx_paths.append(dp)
            res["review_docx"] = docx_paths
        except Exception as e:
            res["review_warning"] = str(e)
    if res.get("ok") and p.get("project"):
        try:
            write_project(p["project"], {"script": out_md, "approved": False})
        except Exception:
            pass
    return res


def _read_sources_or_error(source):
    import authoring
    text, used, skipped = authoring.read_sources(source)
    if not text.strip():
        return None, {"ok": False, "error": "No readable source documents found (.md/.txt/.docx/.pdf).",
                      "skipped": skipped}
    return (text, used, skipped), None


def do_plan(p):
    """Staged pass 2 — read sources + return the unit BREAKDOWN (titles + objectives).
    Short LLM pass; the dashboard shows it, then scripts each unit in turn."""
    import authoring
    got, err = _read_sources_or_error(p["source"])
    if err:
        return err
    text, used, skipped = got
    n_units = int(p["units"]) if str(p.get("units", "")).strip().isdigit() else None
    prompt = authoring.build_plan_prompt(
        objective=p.get("objective", ""), audience=p.get("audience", ""),
        archetype=p.get("archetype", "concept-explainer"), n_units=n_units,
        sources_text=text, course_title=p.get("title") or None)
    ok, raw, err_s = authoring.run_cli(p.get("provider", "claude"), prompt, model=p.get("model"))
    if not ok:
        return {"ok": False, "error": err_s, "used_sources": used, "skipped": skipped}
    rationale, units = authoring.parse_plan(raw)
    if not units:
        return {"ok": False, "error": "The planning pass returned no units. Raw output:\n" + raw[:600],
                "used_sources": used, "skipped": skipped}
    return {"ok": True, "rationale": rationale, "units": units,
            "used_sources": used, "skipped": skipped}


def do_script_unit(p):
    """Staged pass 3 — write ONE unit's §8 script. Called once per unit so the
    dashboard can show live per-unit progress."""
    import authoring
    got, err = _read_sources_or_error(p["source"])
    if err:
        return err
    text, _used, _skipped = got
    units = p.get("all_units") or []
    idx = int(p.get("idx", 1))
    total = int(p.get("total", len(units) or 1))
    unit = p.get("unit") or (units[idx - 1] if 0 < idx <= len(units) else {})
    prompt = authoring.build_unit_prompt(
        unit=unit, all_units=units, idx=idx, total=total,
        objective=p.get("objective", ""), audience=p.get("audience", ""),
        archetype=p.get("archetype", "concept-explainer"),
        sources_text=text, course_title=p.get("title") or None,
        images=authoring.list_images(p.get("images")))
    ok, raw, err_s = authoring.run_cli(p.get("provider", "claude"), prompt, model=p.get("model"))
    if not ok:
        return {"ok": False, "error": err_s, "idx": idx}
    return {"ok": True, "idx": idx, "md": authoring.clean_output(raw)}


def do_save_course(p):
    """Staged pass 4 — stitch the unit scripts into one course .md, lint it, render
    the SME review .docx(s), and record it on the project."""
    import authoring, re as _re, importlib
    out_dir = p["out"]
    os.makedirs(out_dir, exist_ok=True)
    title = (p.get("title") or "course").strip()
    slug = _re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "course"
    out_md = os.path.join(out_dir, f"{slug}.md")
    full = authoring.assemble_course(p.get("title") or None, p.get("rationale", ""),
                                     p.get("units_md") or [])
    with open(out_md, "w", encoding="utf-8") as fh:
        fh.write(full)
    lint_ok, units, lint_errors = authoring.lint(full)
    res = {"ok": True, "out": out_md, "units": units, "lint_ok": lint_ok,
           "lint_errors": lint_errors}
    if lint_ok:
        try:
            from md_import import import_md
            import docx_review, brand as brandmod
            importlib.reload(docx_review)
            b = brandmod.load_brand(p.get("brand", "_default"))
            docx_paths = []
            for k in range(1, units + 1):
                ir, _ = import_md(out_md, which=k)
                dp = os.path.join(out_dir, f"{slug}_m{k}_review.docx")
                docx_review.render_review_docx(ir, dp, brand=b, md_path=out_md, which=k)
                docx_paths.append(dp)
            res["review_docx"] = docx_paths
        except Exception as e:
            res["review_warning"] = str(e)
    if p.get("project"):
        try:
            write_project(p["project"], {"script": out_md, "approved": False})
        except (OSError, ValueError) as e:
            sys.stderr.write(f"[server] could not record script on project: {e}\n")
    return res


def do_revise(p):
    """Stage 5: apply the SME's reviewed .docx onto the canonical script via the
    subscription CLI; write the updated script to the Approved Scripts folder and
    re-render its review .docx."""
    import authoring, importlib, os as _os
    script = p["script"]
    approved_dir = p["approved_dir"]
    out_md = _os.path.join(approved_dir, _os.path.basename(script))
    res = authoring.revise(provider=p.get("provider", "claude"), script_path=script,
                           reviewed_docx=p["reviewed"], out_path=out_md)
    if res.get("ok") and res.get("lint_ok"):
        slug = _os.path.splitext(_os.path.basename(out_md))[0]
        try:
            from md_import import import_md
            import docx_review, brand as brandmod
            importlib.reload(docx_review)
            b = brandmod.load_brand(p.get("brand", "_default"))
            docs = []
            for k in range(1, res.get("units", 0) + 1):
                ir, _ = import_md(out_md, which=k)
                dp = _os.path.join(approved_dir, f"{slug}_m{k}_review.docx")
                docx_review.render_review_docx(ir, dp, brand=b, md_path=out_md, which=k)
                docs.append(dp)
            res["review_docx"] = docs
        except Exception as e:
            res["review_warning"] = str(e)
        if p.get("project"):
            try:
                write_project(p["project"], {"script": out_md, "approved": True})
            except Exception:
                pass
    return res


def list_courses(out_dir):
    """Every built course preview (a .course dir containing index.html) under the
    project's output folder, including the hidden .preview staging area."""
    found = []
    if not out_dir or not os.path.isdir(out_dir):
        return found
    for root in (out_dir, os.path.join(out_dir, ".preview")):
        if not os.path.isdir(root):
            continue
        staged = root.endswith(".preview")
        for name in sorted(os.listdir(root), key=str.lower):
            if not name.endswith(".course"):
                continue
            idx = os.path.join(root, name, "index.html")
            if os.path.isfile(idx):
                found.append({"name": name[:-len(".course")], "index": idx, "staged": staged})
    return found


def reveal(path):
    target = path if os.path.isdir(path) else os.path.dirname(path)
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", target])
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", target])
        elif sys.platform.startswith("win"):
            os.startfile(target)  # noqa
        return True
    except Exception:
        return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass                                  # keep the per-request access log quiet

    def log_error(self, fmt, *args):
        # ...but DON'T swallow errors (the base class routes them through
        # log_message too). Surface them to stderr so failures are visible.
        sys.stderr.write("[server] " + (fmt % args) + "\n")

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path):
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def _serve_index(self):
        """Serve index.html with the per-process CSRF token stamped in."""
        with open(HTML, encoding="utf-8") as f:
            html = f.read().replace("__CSRF_TOKEN__", CSRF_TOKEN)
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _expected_origin(self):
        return "http://" + self.headers.get("Host", "")

    def _same_origin(self):
        """Host must be a real localhost name (blocks DNS-rebinding) and the
        Origin/Referer must be this server's own origin."""
        host = self.headers.get("Host", "")
        if host.split(":")[0] not in ("127.0.0.1", "localhost"):
            return False
        exp = self._expected_origin()
        origin = self.headers.get("Origin")
        if origin is not None:
            return origin == exp
        ref = self.headers.get("Referer", "")
        return ref == exp or ref.startswith(exp + "/")

    def _csrf_ok(self):
        """Full POST guard: same-origin + JSON content-type + valid token."""
        if not self._same_origin():
            return False
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            return False
        return secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), CSRF_TOKEN)

    STREAM_SENTINEL = "\n<<<COURSE_BUILDER_RESULT>>>\n"

    def _stream_generate(self, p):
        """Single-pass STREAMING generation: stream claude's output to the browser
        live, then assemble/lint/save. Writes its OWN chunked response (never via
        _json) and is fully self-contained — it never raises after headers, so the
        do_POST error path can't double-respond."""
        import authoring, re as _re, importlib
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        def emit(t):
            try:
                self.wfile.write(t.encode("utf-8")); self.wfile.flush()
            except Exception:
                pass

        def finish(obj):
            emit(self.STREAM_SENTINEL + json.dumps(obj))

        try:
            src = p.get("source")
            if not src:
                finish({"ok": False, "error": "No source folder given."}); return
            got, err = _read_sources_or_error(src)
            if err:
                finish(err); return
            text, used, skipped = got
            n_units = int(p["units"]) if str(p.get("units", "")).strip().isdigit() else None
            prompt = authoring.build_prompt(
                objective=p.get("objective", ""), audience=p.get("audience", ""),
                archetype=p.get("archetype", "concept-explainer"), n_units=n_units,
                sources_text=text, course_title=p.get("title") or None,
                images=authoring.list_images(p.get("images")))
            ok, full, gerr = authoring.run_cli_stream(p.get("provider", "claude"), prompt, emit, model=p.get("model"))
            if not ok:
                finish({"ok": False, "error": gerr, "skipped": skipped}); return
            md = authoring.clean_output(full)
            out_dir = p["out"]; os.makedirs(out_dir, exist_ok=True)
            title = (p.get("title") or "course").strip()
            slug = _re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "course"
            out_md = os.path.join(out_dir, f"{slug}.md")
            with open(out_md, "w", encoding="utf-8") as fh:
                fh.write(md)
            lint_ok, units, lint_errors = authoring.lint(md)
            result = {"ok": True, "out": out_md, "units": units, "lint_ok": lint_ok,
                      "lint_errors": lint_errors, "skipped": skipped}
            if lint_ok:
                try:
                    from md_import import import_md
                    import docx_review, brand as brandmod
                    importlib.reload(docx_review)
                    b = brandmod.load_brand(p.get("brand", "_default"))
                    docs = []
                    for k in range(1, units + 1):
                        ir, _ = import_md(out_md, which=k)
                        dp = os.path.join(out_dir, f"{slug}_m{k}_review.docx")
                        docx_review.render_review_docx(ir, dp, brand=b, md_path=out_md, which=k)
                        docs.append(dp)
                    result["review_docx"] = docs
                except Exception as e:
                    result["review_warning"] = str(e)
            if p.get("project"):
                try:
                    write_project(p["project"], {"script": out_md, "approved": False})
                except (OSError, ValueError) as e:
                    sys.stderr.write(f"[server] could not record script: {e}\n")
            finish(result)
        except Exception as e:
            finish({"ok": False, "error": str(e)})

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            try:
                self._serve_index()
            except OSError:
                self._json({"error": "index.html missing"}, 500)
        elif u.path == "/api/init":
            import authoring
            cfg = load_config()
            ws = cfg.get("workspace") or os.path.join(os.path.expanduser("~"), "Course Builder Courses")
            self._json({"home": os.path.expanduser("~"), "brands": list_brands(),
                        "folders": PROJECT_FOLDERS,
                        "providers": authoring.provider_status(),
                        "archetypes": authoring.list_archetypes(),
                        "workspace": ws, "workspace_set": bool(cfg.get("workspace")),
                        "projects": list_projects(ws),
                        "layouts": slide_layout_names(), "slide_examples": slide_examples(),
                        "slides_out": os.path.join(os.path.expanduser("~"), "Course Builder Slides")})
        elif u.path == "/api/ai-status":
            import authoring
            self._json({"providers": authoring.provider_status()})
        elif u.path == "/api/ls":
            # Navigator: confine to the allowlist; out-of-root falls back to home.
            req = q.get("path", [""])[0]
            self._json(ls(req if _within_roots(req) else os.path.expanduser("~")))
        elif u.path == "/api/readjson":
            req = q.get("path", [""])[0]
            if not _within_roots(req):
                self._json({"ok": False, "error": "path not allowed"})
            else:
                path = os.path.abspath(os.path.expanduser(req))
                try:
                    self._json({"ok": True, "data": json.load(open(path, encoding="utf-8"))})
                except (OSError, ValueError) as e:
                    self._json({"ok": False, "error": str(e)})
        elif u.path == "/api/scan":
            req = q.get("md", [""])[0]
            self._json({"mls": microlearnings(req) if _within_roots(req) else []})
        elif u.path == "/api/listfiles":
            ext = q.get("ext", [None])[0]
            exts = ext.split(",") if ext else None
            req = q.get("path", [""])[0]
            self._json({"files": list_files(req, exts) if _within_roots(req) else []})
        elif u.path == "/api/courses":
            req = q.get("dir", [""])[0]
            self._json({"courses": list_courses(req) if _within_roots(req) else []})
        elif u.path == "/api/reveal":
            # Side-effecting GET (opens Finder): require same-origin + allowlist.
            req = q.get("path", [""])[0]
            ok = self._same_origin() and _within_roots(req) and reveal(req)
            self._json({"ok": bool(ok)})
        elif u.path.startswith("/preview"):
            # Serve a built course file BY ITS REAL PATH so the course's OWN
            # relative refs (player/player.css, brand/tokens.css, assets/…) all
            # resolve: the URL path mirrors the filesystem path —
            #   /preview/abs/path/to/x.course/index.html
            #   -> relative "player/player.css" becomes
            #      /preview/abs/path/to/x.course/player/player.css
            # Confined to the allowlist roots (realpath), so no escape.
            fs = unquote(u.path[len("/preview"):]) or "/"
            target = os.path.realpath(os.path.abspath(fs))
            if _within_roots(target) and os.path.isfile(target):
                self._file(target)
            else:
                self._json({"error": "not found"}, 404)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        if not self._csrf_ok():
            self._json({"error": "forbidden: cross-origin or missing CSRF token"}, 403)
            return
        try:
            p = self._read_json()
            if u.path == "/api/project":
                self._json(project_setup(p["root"]))
            elif u.path == "/api/workspace":
                ws = os.path.abspath(os.path.expanduser(p["path"]))
                os.makedirs(ws, exist_ok=True)
                save_config({"workspace": ws})
                self._json({"workspace": ws, "projects": list_projects(ws)})
            elif u.path == "/api/project/new":
                # The location chosen in the UI field wins; fall back to the saved
                # workspace, then the default. The chosen folder is remembered.
                ws = (p.get("workspace") or "").strip() or load_config().get("workspace") \
                    or os.path.join(os.path.expanduser("~"), "Course Builder Courses")
                ws = os.path.abspath(os.path.expanduser(ws))
                os.makedirs(ws, exist_ok=True)
                save_config({"workspace": ws})
                res = new_project(ws, p["name"])
                res["projects"] = list_projects(ws)
                res["workspace"] = ws
                self._json(res)
            elif u.path == "/api/project/open":
                self._json(read_project(os.path.expanduser(p["path"])))
            elif u.path == "/api/project/save":
                meta = write_project(os.path.expanduser(p["path"]), p.get("meta", {}))
                self._json({"ok": True, "meta": meta})
            elif u.path == "/api/build":
                self._json(do_build(p))
            elif u.path == "/api/deck":
                self._json(do_deck(p))
            elif u.path == "/api/generate-deck":
                self._json(do_generate_deck(p))
            elif u.path == "/api/review":
                self._json(do_review(p))
            elif u.path == "/api/generate":
                self._json(do_generate(p))
            elif u.path == "/api/generate-stream":
                self._stream_generate(p); return
            elif u.path == "/api/plan":
                self._json(do_plan(p))
            elif u.path == "/api/script-unit":
                self._json(do_script_unit(p))
            elif u.path == "/api/save-course":
                self._json(do_save_course(p))
            elif u.path == "/api/publish":
                self._json(do_publish(p))
            elif u.path == "/api/revise":
                self._json(do_revise(p))
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:
            self._json({"error": str(e)}, 500)


def free_port(start=8765):
    for port in range(start, start + 40):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def main():
    port = free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"\n  course-builder dashboard → {url}")
    print("  (Close this window or press Ctrl+C to stop.)\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")


if __name__ == "__main__":
    main()
