"""course-builder — local dashboard server (no Streamlit, no GUI toolkit).

A stdlib HTTP server that serves one HTML page + a small JSON API and drives the
SME curriculum workflow as a guided flow:

  1. Source docs  →  2. Generate scripts (Layer 2)  →  3. Approved script
  →  4. Build + preview  →  5. SCORM package in the output folder

Folder selection is an IN-BROWSER navigator (no native dialog, nothing to crash on
the main thread). The server only shells out to src/cli.py and calls
src/docx_review — it reimplements no engine logic.

Launch (double-clickable): dashboard/launch.command (macOS) · dashboard/launch.bat
(Windows)   ·   or: python3 dashboard/server.py
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


def _platform_drive_roots():
    """OS-specific extra roots so the folder navigator reaches external/mounted
    drives. macOS: /Volumes. Windows: each accessible drive root (C:\\, D:\\, …) —
    the analogue of /Volumes, so a source on a second/external drive (D:\\) isn't
    clamped back to home. Linux: nothing extra (home + temp + repo cover it)."""
    if os.name == "nt":
        roots = []
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            d = f"{letter}:\\"
            if os.path.isdir(d):
                roots.append(d)
        return roots
    if os.path.isdir("/Volumes"):
        return ["/Volumes"]               # external/mounted drives on macOS
    return []


def _allow_roots():
    """Directories the file endpoints may read/list/serve under — broad enough to
    keep the folder navigator useful (home + mounted drives + build staging) while
    excluding system trees (/etc) and other users' homes."""
    cands = [os.path.expanduser("~"), ROOT, tempfile.gettempdir()]
    cands.extend(_platform_drive_roots())
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


def _safe_images_dir(v):
    """Resolve an images folder for slide preview/build, confined to the allowed
    roots (same file-read confinement as the other endpoints). Returns the
    expanded path, or None when blank/disallowed/not-a-dir — callers then render
    image slots as labeled placeholders rather than failing."""
    if not v or not isinstance(v, str) or v.startswith("-") or not _within_roots(v):
        return None
    rp = os.path.abspath(os.path.expanduser(v))
    return rp if os.path.isdir(rp) else None


def _deck_images_dir(p):
    """The effective image folder for a deck: the author's chosen folder if any,
    otherwise the brand's built-in image LIBRARY (so on-brand template imagery is
    available by default). The brand library is a trusted in-repo asset dir."""
    import authoring
    chosen = _safe_images_dir(p.get("images"))
    if chosen:
        return chosen
    return authoring.brand_image_dir(_safe_brand(p.get("brand", "_default")))

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
    # "template" is the generic data-driven layout — chosen via the template picker /
    # ingestion (its own region-spec + content), not the manual slide-layout dropdown.
    names = [n for n in names if n != "template"]
    return [n for n in SLIDE_ORDER if n in names] + [n for n in names if n not in SLIDE_ORDER]


def template_layouts():
    """Data-driven template layouts (region-specs) for the picker — name/title/category/
    brand/starter. Empty if the engine import fails (no python-pptx not required here)."""
    try:
        import slide_layouts
        return slide_layouts.template_layout_info()
    except Exception:
        return []


def slide_examples():
    """Starter content (parsed) for each slide layout, keyed by layout name."""
    d = os.path.join(ROOT, "templates", "slide-layouts")
    out = {}
    for lay in slide_layout_names():
        out[lay] = _load_json(os.path.join(d, f"{lay}.example.json"), {})
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
    return _load_json(CONFIG, {})


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


def _load_json(path, default=None):
    """Read + parse a JSON file; return `default` on missing/unreadable/invalid.
    The one JSON-read helper for config/project/manifest reads (module-level;
    distinct from the Handler._read_json POST-body reader)."""
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return default


def read_project(root):
    """Return a project's metadata (project.json) + derived folder map."""
    pj = os.path.join(root, "project.json")
    meta = _load_json(pj, {})
    return {"path": root, "name": meta.get("name") or os.path.basename(root),
            "meta": meta, "folders": project_folders(root)}


def write_project(root, meta):
    """Merge metadata into project.json, stamping updated (and created once)."""
    pj = os.path.join(root, "project.json")
    cur = _load_json(pj, {})
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


# ----- checkpoint / rewind (M15): cheap per-project snapshots -----------------
# Distinct from git: local, automatic before each AI edit, one-click restorable.
# A snapshot copies the project's canonical IR — project.json (which carries the
# full deck) plus the referenced course script .md — into <root>/.snapshots/<id>/
# with a manifest. That 1-2 file copy captures BOTH the deck IR and the course IR
# cheaply (the M15 design: deck + course coverage). Deck AI edits live in browser
# memory, so the dashboard persists the deck (saveProject) then fires a snapshot
# before regenerating; the on-disk course handlers auto-snapshot server-side.

SNAP_DIRNAME = ".snapshots"
SNAP_AUTO_CAP = 40          # trim oldest AUTO snapshots beyond this; keep manual + restore points


def _snap_root(root):
    return os.path.join(os.path.abspath(os.path.expanduser(root)), SNAP_DIRNAME)


def _project_meta(root):
    pj = os.path.join(os.path.abspath(os.path.expanduser(root)), "project.json")
    return _load_json(pj, {})


def _capture_targets(root):
    """Files a snapshot captures: project.json + the referenced script .md (both
    when they exist). The script path is read from project.json's `script` key
    (absolute, written by do_save_course/do_revise)."""
    root = os.path.abspath(os.path.expanduser(root))
    targets = []
    pj = os.path.join(root, "project.json")
    if os.path.isfile(pj):
        targets.append(pj)
    script = _project_meta(root).get("script")
    if script and os.path.isfile(script):
        targets.append(os.path.abspath(script))
    return targets


def _unique_id(dirpath, prefix=""):
    """A filesystem-safe, lexically-sortable, unique id under `dirpath`. Microsecond
    precision keeps ids both unique and correctly ordered even for same-second bursts
    (a numeric -N suffix would mis-sort lexically: -10 before -2). Shared by the
    snapshot store (no prefix) and the template store (kind- prefix)."""
    from datetime import datetime
    base = prefix + datetime.now().strftime("%Y%m%dT%H%M%S%f")   # 20260630T143000123456
    cand, n = base, 1
    while os.path.exists(os.path.join(dirpath, cand)):
        cand = f"{base}-{n:03d}"; n += 1                 # zero-padded so the fallback also sorts
    return cand


def _snap_id(root):
    return _unique_id(_snap_root(root))


def _safe_store_id(sid):
    """A snapshot/template id must be a bare directory name (no path traversal)."""
    return bool(sid) and os.path.basename(sid) == sid and sid not in (".", "..")


def _snap_manifest(root, sid):
    """A single snapshot's manifest dict, or None if the id is unsafe/absent."""
    if not _safe_store_id(sid):
        return None
    return _load_json(os.path.join(_snap_root(root), sid, "snapshot.json"))


def make_snapshot(root, label="", kind="auto"):
    """Copy the project's canonical IR into a new snapshot dir. Returns the
    manifest dict, or None when there is nothing to capture yet."""
    import shutil
    root = os.path.abspath(os.path.expanduser(root))
    targets = _capture_targets(root)
    if not targets:
        return None
    sid = _snap_id(root)
    sdir = os.path.join(_snap_root(root), sid)
    os.makedirs(sdir, exist_ok=True)
    files = []
    for src in targets:
        name = os.path.basename(src)
        try:
            shutil.copy2(src, os.path.join(sdir, name))
        except OSError:
            continue
        files.append({"name": name, "orig": src})
    manifest = {"id": sid, "label": label or "snapshot", "kind": kind,
                "created": _now(), "files": files}
    json.dump(manifest, open(os.path.join(sdir, "snapshot.json"), "w", encoding="utf-8"), indent=2)
    _prune_auto_snapshots(root)
    return manifest


def list_snapshots(root):
    """Manifests for a project's snapshots, newest first."""
    sr = _snap_root(root)
    out = []
    if not os.path.isdir(sr):
        return out
    for name in os.listdir(sr):
        m = _load_json(os.path.join(sr, name, "snapshot.json"))
        if m is not None:
            out.append(m)
    out.sort(key=lambda m: m.get("id", ""), reverse=True)
    return out


def _prune_auto_snapshots(root):
    """Keep the store cheap: drop the oldest AUTO snapshots beyond the cap.
    Manual snapshots and restore points are always kept."""
    import shutil
    autos = [m for m in list_snapshots(root) if m.get("kind") == "auto"]
    for m in autos[SNAP_AUTO_CAP:]:          # list is newest-first; tail = oldest
        try:
            shutil.rmtree(os.path.join(_snap_root(root), m["id"]))
        except OSError:
            pass


def restore_snapshot(root, sid):
    """Restore a snapshot's files to their original locations. First snapshots
    the CURRENT state (kind=restore-point) so a mistaken restore is itself undoable."""
    import shutil
    root = os.path.abspath(os.path.expanduser(root))
    manifest = _snap_manifest(root, sid)
    if manifest is None:
        return {"ok": False, "error": "snapshot not found"}
    sdir = os.path.join(_snap_root(root), sid)
    # Snapshot-then-restore: capture current work so the restore can be undone.
    safety = make_snapshot(root, "Before restore", kind="restore-point")
    restored = []
    for f in manifest.get("files", []):
        src = os.path.join(sdir, f.get("name", ""))
        dest = f.get("orig")
        if not dest or not os.path.isfile(src):
            continue
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src, dest)
            restored.append(dest)
        except OSError:
            continue
    return {"ok": True, "id": sid, "restored": restored, "safety": safety}


def rename_snapshot(root, sid, label=None, kind=None):
    """Update a snapshot's manifest in place (M16 — named version history). Used
    to (a) rename a version, or (b) PROMOTE an existing checkpoint into a kept,
    named `version` by passing kind="version". Only the manifest changes — the
    captured files are untouched. Promoting to `version` also takes the snapshot
    out of auto-prune scope (only kind=="auto" is ever trimmed)."""
    root = os.path.abspath(os.path.expanduser(root))
    manifest = _snap_manifest(root, sid)
    if manifest is None:
        return {"ok": False, "error": "snapshot not found"}
    mf = os.path.join(_snap_root(root), sid, "snapshot.json")
    if label is not None:
        manifest["label"] = label or manifest.get("label") or "version"
    if kind is not None:
        manifest["kind"] = kind
    try:
        json.dump(manifest, open(mf, "w", encoding="utf-8"), indent=2)
    except OSError:
        return {"ok": False, "error": "could not write manifest"}
    return {"ok": True, "snapshot": manifest}


def _auto_snapshot(p, label):
    """Auto-capture the project before a server-side AI edit (no-op without a
    valid, allowlisted project path). Never raises into the edit path."""
    root = p.get("project")
    if root and _within_roots(root):
        try:
            return make_snapshot(root, label, kind="auto")
        except Exception:
            return None
    return None


# ----- saved templates / starters (M17): a GLOBAL, cross-project library ------
# Distinct from the per-project snapshot store (M15/M16): a template lives under
# the user config dir so it is reusable across projects, and "New from template"
# INSTANTIATES it into the current session (it does NOT restore in place). Two kinds:
#   * "project" — the whole project IR (project.json meta, which carries the deck)
#     plus the referenced course-script .md text. Loading it drops the deck +
#     definition fields into the open session, and places the script into the open
#     project's source folder when one is open.
#   * "slide" — a single slide's {layout, content}; inserted into the deck and also
#     surfaced in the deck builder's saved-slide picker.
# The store mirrors the snapshot manifest shape the codebase already knows: one dir
# per template under <config>/templates/<id>/ with a template.json manifest.

TPL_DIRNAME = "templates"


def _tpl_root():
    return os.path.join(CONFIG_DIR, TPL_DIRNAME)


def _tpl_id(kind):
    return _unique_id(_tpl_root(), f"{kind}-")


def _tpl_manifest(tid):
    if not _safe_store_id(tid):
        return None
    return _load_json(os.path.join(_tpl_root(), tid, "template.json"))


def list_templates(kind=None):
    """Template manifests, newest first (optionally filtered by kind)."""
    tr = _tpl_root()
    out = []
    if not os.path.isdir(tr):
        return out
    for name in os.listdir(tr):
        m = _tpl_manifest(name)
        if m and (kind is None or m.get("kind") == kind):
            out.append(m)
    out.sort(key=lambda m: m.get("id", ""), reverse=True)
    return out


def save_project_template(root, name):
    """Capture the current project's IR (its project.json meta, which carries the
    deck) plus the referenced course-script text into a new project template."""
    root = os.path.abspath(os.path.expanduser(root))
    meta = _project_meta(root)
    if not meta:
        return {"ok": False, "error": "nothing to save (no project.json)"}
    tid = _tpl_id("project")
    tdir = os.path.join(_tpl_root(), tid)
    os.makedirs(tdir, exist_ok=True)
    # Drop location/identity fields that must NOT leak into a new session.
    payload = {k: v for k, v in meta.items()
               if k not in ("created", "updated", "name", "script")}
    script_name = None
    script = meta.get("script")
    if script and os.path.isfile(script):
        import shutil
        try:
            shutil.copy2(script, os.path.join(tdir, "script.md"))
            script_name = os.path.basename(script)
        except OSError:
            script_name = None
    json.dump(payload, open(os.path.join(tdir, "payload.json"), "w", encoding="utf-8"), indent=2)
    manifest = {"id": tid, "name": name or "Project starter", "kind": "project",
                "created": _now(), "n_slides": len(payload.get("deck") or []),
                "script_name": script_name,
                "title": payload.get("title") or payload.get("sl_title") or ""}
    json.dump(manifest, open(os.path.join(tdir, "template.json"), "w", encoding="utf-8"), indent=2)
    return {"ok": True, "template": manifest}


def save_slide_template(name, layout, content):
    """Capture a single slide (layout + content JSON string) as a reusable block."""
    tid = _tpl_id("slide")
    tdir = os.path.join(_tpl_root(), tid)
    os.makedirs(tdir, exist_ok=True)
    if not isinstance(content, str):
        content = json.dumps(content or {}, indent=2)
    manifest = {"id": tid, "name": name or "Slide starter", "kind": "slide",
                "created": _now(), "layout": layout or "infographic", "content": content}
    json.dump(manifest, open(os.path.join(tdir, "template.json"), "w", encoding="utf-8"), indent=2)
    return {"ok": True, "template": manifest}


def instantiate_template(tid):
    """Return a template's payload for the client to load into the current session.
    Non-destructive: reads only, writes nothing."""
    m = _tpl_manifest(tid)
    if not m:
        return {"ok": False, "error": "template not found"}
    if m.get("kind") == "slide":
        return {"ok": True, "kind": "slide", "name": m.get("name", ""),
                "layout": m.get("layout", "infographic"), "content": m.get("content", "{}")}
    tdir = os.path.join(_tpl_root(), tid)
    payload = _load_json(os.path.join(tdir, "payload.json"))
    if payload is None:
        return {"ok": False, "error": "template payload unreadable"}
    script_text = None
    sp = os.path.join(tdir, "script.md")
    if os.path.isfile(sp):
        try:
            script_text = open(sp, encoding="utf-8").read()
        except OSError:
            script_text = None
    return {"ok": True, "kind": "project", "name": m.get("name", ""), "meta": payload,
            "script_name": m.get("script_name"), "script_text": script_text}


def delete_template(tid):
    import shutil
    if not _tpl_manifest(tid):
        return {"ok": False, "error": "template not found"}
    try:
        shutil.rmtree(os.path.join(_tpl_root(), tid))
    except OSError:
        return {"ok": False, "error": "could not delete template"}
    return {"ok": True, "id": tid}


def place_template_script(root, name, text):
    """Write a project template's course-script text into an OPEN project's source
    folder (deduped) and record it on the project. The caller confines `root` to the
    allowlist. Returns the written path."""
    root = os.path.abspath(os.path.expanduser(root))
    base = os.path.basename(name or "course.md") or "course.md"
    if not base.lower().endswith(".md"):
        base += ".md"
    src = project_folders(root).get("source") or root
    os.makedirs(src, exist_ok=True)
    stem, ext = os.path.splitext(base)
    dest, n = os.path.join(src, base), 2
    while os.path.exists(dest):
        dest = os.path.join(src, f"{stem}-{n}{ext}"); n += 1
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(text or "")
    write_project(root, {"script": dest})
    return dest


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
    gate = p.get("gate", True)                         # M13: graded courses gate on a failing score
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
        if fmt == "html":
            # Preview-only: render the learner-facing HTML course dir, NO SCORM zip.
            # Packaging is reserved for publish, so previewing never writes a package.
            for w in targets:
                op = os.path.join(out, f"{stem}_m{w}_preview.zip")   # never created
                course_dir = os.path.splitext(op)[0] + ".course"
                a = ["from-md", md, "--which", str(w), "--images", img, "--brand", brand,
                     "--no-package"]
                if validate:
                    a.append("--validate")
                if not animate:
                    a.append("--no-animate")
                if not gate:
                    a.append("--no-gate")
                a += ["--out", op]
                preview = os.path.join(course_dir, "index.html")
                label = f"Course preview · unit {w}" if multi else "Course preview"
                jobs.append({"label": label, "fmt": "html", "args": a,
                             "out": course_dir, "preview": preview})
        elif fmt == "pptx":
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
                if not gate:
                    a.append("--no-gate")
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
    import build_report
    results = []
    for j in build_jobs(pp):
        ok, log = run_cli(j["args"])
        ok = ok and os.path.exists(j["out"])
        prev = j["preview"] if (ok and j["preview"] and os.path.exists(j["preview"])) else None
        # Structured build report (C1): the engine writes <stem>.report.json beside the
        # artifact (it runs in a subprocess, so the report crosses the boundary on disk).
        # Surface it so a degraded build — dropped block, mis-scored quiz — tells the
        # operator in the UI, not just in the stderr log.
        report = build_report.read(j["out"])
        results.append({"label": j["label"], "ok": ok, "out": j["out"], "preview": prev,
                        "log": log, "fmt": j["fmt"], "report": report})
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
        n_slides=int(p["nslides"]) if str(p.get("nslides", "")).strip().isdigit() else None,
        model=p.get("model"),
        images=authoring.list_images(_deck_images_dir(p)),
        preset=p.get("preset"), urls=p.get("urls", ""),
        glossary=authoring.load_glossary(p.get("brand")),
        outline=p.get("outline"))


def do_deck_plan(p):
    """M8 — staged deck pass 1: read sources + return the slide OUTLINE (a
    suggested layout + title + one-liner per slide) for the operator to approve
    and reorder BEFORE the full deck is generated. Mirrors do_plan for the course
    flow; the approved outline rides back into /api/generate-deck as `outline`."""
    import authoring
    got, err = _read_sources_or_error(p.get("source", ""), urls=p.get("urls", ""))
    if err:
        return err
    text, used, skipped = got
    n_slides = int(p["nslides"]) if str(p.get("nslides", "")).strip().isdigit() else None
    prompt = authoring.build_deck_plan_prompt(
        title=p.get("title") or None, focus=p.get("focus", ""), audience=p.get("audience", ""),
        n_slides=n_slides, sources_text=text,
        images=authoring.list_images(_deck_images_dir(p)), preset=p.get("preset"))
    ok, raw, err_s = authoring.run_cli(p.get("provider", "claude"), prompt, model=p.get("model"))
    if not ok:
        return {"ok": False, "error": err_s, "used_sources": used, "skipped": skipped}
    rationale, slides = authoring.parse_deck_plan(raw)
    if not slides:
        return {"ok": False, "error": "The outline pass returned no slides. Raw output:\n" + raw[:600],
                "used_sources": used, "skipped": skipped}
    return {"ok": True, "rationale": rationale, "outline": slides,
            "used_sources": used, "skipped": skipped}


def do_match_layout(p):
    """P4 "describe the slide": deterministically suggest a deck layout from a
    one-sentence intent — no AI call, pure scoring. Mirrors the match-layout CLI
    but enriches every layout with its LAYOUT_PURPOSE hint for the UI. Image
    layouts are allowed because the deck editor's Add-slide picker includes them."""
    import authoring
    intent = (p.get("intent") or "").strip()
    if not intent:
        return {"ok": False, "error": "Describe the slide in a sentence first."}
    res = authoring.match_layout_from_intent(intent, allow_image_layouts=True)
    res["purpose"] = authoring.LAYOUT_PURPOSE.get(res["recommended"], "")
    for r in res["ranked"]:
        r["purpose"] = authoring.LAYOUT_PURPOSE.get(r["layout"], "")
    res["ok"] = True
    return res


def do_chart_csv(p):
    """M7 — turn a pasted CSV/TSV table into a chart block's {categories, series},
    so the operator can fill a chart from a spreadsheet paste. Pure/local (no
    provider, no filesystem); NEVER raises for bad input (returns empty data)."""
    import chart_svg
    data = chart_svg.parse_chart_csv(p.get("csv", ""))
    return {"ok": True, "categories": data["categories"], "series": data["series"]}


def do_regenerate_slide(p):
    """Re-draft ONE slide of the deck (optional guidance), keeping the others
    untouched. The slide-tab analogue of /api/regenerate-unit."""
    import authoring
    content = p.get("content")
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except ValueError:
            content = {}
    return authoring.regenerate_slide(
        provider=p.get("provider", "claude"),
        source_folder=p.get("source", ""),
        layout=p.get("layout", "infographic"),
        current_content=content if isinstance(content, dict) else {},
        slide_summaries=p.get("slide_summaries") or [],
        idx=int(p.get("idx", 1)), total=int(p.get("total", 1)),
        title=p.get("title", ""), focus=p.get("focus", ""),
        audience=p.get("audience", ""), guidance=p.get("guidance", ""),
        model=p.get("model"),
        scope_content=p.get("scope_content", True),
        scope_layout=p.get("scope_layout", True),
        images=authoring.list_images(_deck_images_dir(p)), urls=p.get("urls", ""),
        n=p.get("n", 1), brand=p.get("brand"))


def do_deck_notes(p):
    """One-click "generate speaker notes": draft a notes paragraph per slide for
    the current deck. Returns {ok, notes:[...]}; the client splices them onto the
    DECK items so they ride into the built .pptx notes pages."""
    import authoring
    slides = p.get("slides")
    if not isinstance(slides, list) or not slides:
        return {"ok": False, "error": "Add or generate slides before writing speaker notes."}
    # content may arrive as JSON strings from the editor — parse for the model's view
    norm = []
    for sp in slides:
        sp = sp or {}
        content = sp.get("content")
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except ValueError:
                content = {}
        norm.append({"layout": sp.get("layout", "infographic"), "content": content or {}})
    return authoring.generate_notes(
        provider=p.get("provider", "claude"), slides=norm,
        title=p.get("title", ""), focus=p.get("focus", ""),
        audience=p.get("audience", ""), model=p.get("model"))


def do_deck(p):
    """Assemble a multi-slide, on-brand .pptx PRESENTATION from an ordered list
    of slides via the deck CLI. No project, source docs, or images folder —
    this is the presentation path, distinct from the course flow."""
    import tempfile
    out_dir = os.path.abspath(os.path.expanduser(
        p.get("out") or os.path.join(os.path.expanduser("~"), "Course Builder Slides")))
    os.makedirs(out_dir, exist_ok=True)
    name = re.sub(r"[^\w\- ]+", "", (p.get("name") or "presentation")).strip() or "presentation"
    fmt = "html" if p.get("format") == "html" else "pptx"
    op = os.path.join(out_dir, name + ("." + fmt))

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
        slide = {"layout": sp.get("layout", "infographic"), "content": content or {}}
        if sp.get("theme") in ("dark", "light"):     # carry the cross-cutting theme flag
            slide["theme"] = sp["theme"]
        if isinstance(sp.get("notes"), str) and sp["notes"].strip():  # speaker notes → notes page
            slide["notes"] = sp["notes"]
        # per-slide transition overrides the deck-wide default; "none" opts a slide out
        if sp.get("transition") in ("none", "fade", "cut", "push", "wipe", "split", "cover"):
            slide["transition"] = sp["transition"]
        norm.append(slide)

    cf = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    try:
        json.dump({"slides": norm}, cf)
        cf.close()
        args = ["deck", "--content", cf.name, "--brand", _safe_brand(p.get("brand", "_default")), "--out", op]
        if fmt == "html":
            args += ["--format", "html", "--title", name]
        imgdir = _deck_images_dir(p)
        if imgdir:
            args += ["--images", imgdir]
        tr = p.get("transition")
        if tr and tr in ("fade", "cut", "push", "wipe", "split", "cover"):
            args += ["--transition", tr]
            if p.get("transition_dir") in ("l", "r", "u", "d"):
                args += ["--transition-dir", p["transition_dir"]]
        # Per-element entrance animation (validated in PowerPoint: canonical
        # mainSeq build, float-in, ~0.65s spacing). Baked into the built .pptx.
        anim = p.get("animate")
        if anim and anim in ("fade", "rise", "flyleft", "flyright"):
            args += ["--animate", anim]
        ok, log = run_cli(args)
    finally:
        try:
            os.unlink(cf.name)
        except OSError:
            pass
    ok = ok and os.path.exists(op)
    return {"ok": ok, "out": op, "log": log, "slides": len(norm), "out_dir": out_dir}


def do_deck_svg(p):
    """Render the deck to one faithful SVG poster per slide for the in-browser
    slideshow preview. Reuses the EXACT slide_layouts geometry via slide_svg's
    mock backend (no .pptx, no LibreOffice) so the preview matches the export."""
    import slide_svg, brand as brandmod
    slides = p.get("slides")
    if not isinstance(slides, list) or not slides:
        return {"ok": False, "error": "Add at least one slide to preview."}
    # slide_svg parses content (dict OR JSON string) tolerantly, so a single
    # broken slide previews as an error card instead of blanking the slideshow.
    b = brandmod.load_brand(_safe_brand(p.get("brand", "_default")))
    anim = bool(p.get("animate")) and p.get("animate") != "none"
    svgs = slide_svg.render_deck_svg(slides, b, images_dir=_deck_images_dir(p),
                                     animate=anim)
    return {"ok": True, "svgs": svgs, "count": len(svgs)}


def do_slide_svg(p):
    """Render ONE slide to a faithful SVG poster — the same geometry as the
    deck preview and the .pptx export. Backs the inline Step-2 row thumbnails,
    which fetch per-slide (and the client caches by content) so a single
    regenerate/recolor re-renders only its own thumbnail. Reuses
    render_deck_svg's tolerant parsing → a broken slide becomes an error card,
    never a 500."""
    import slide_svg, brand as brandmod
    b = brandmod.load_brand(_safe_brand(p.get("brand", "_default")))
    slide = {"layout": p.get("layout", "infographic"), "content": p.get("content")}
    if p.get("theme") in ("dark", "light"):     # carry the cross-cutting theme flag
        slide["theme"] = p["theme"]
    svgs = slide_svg.render_deck_svg([slide], b, images_dir=_deck_images_dir(p))
    return {"ok": True, "svg": svgs[0] if svgs else ""}


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
        out_path=out_md, course_title=p.get("title") or None, preset=p.get("preset"),
        urls=p.get("urls", ""), glossary=authoring.load_glossary(p.get("brand")))
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


def _read_sources_or_error(source, urls=""):
    import authoring
    text, used, skipped = authoring.read_sources(source, urls=urls)
    if not text.strip():
        return None, {"ok": False, "error": "No readable source documents found (.md/.txt/.csv/.doc/.docx/.rtf/.odt/.html/.pdf).",
                      "skipped": skipped}
    return (text, used, skipped), None


def do_plan(p):
    """Staged pass 2 — read sources + return the unit BREAKDOWN (titles + objectives).
    Short LLM pass; the dashboard shows it, then scripts each unit in turn."""
    import authoring
    got, err = _read_sources_or_error(p["source"], urls=p.get("urls", ""))
    if err:
        return err
    text, used, skipped = got
    n_units = int(p["units"]) if str(p.get("units", "")).strip().isdigit() else None
    prompt = authoring.build_plan_prompt(
        objective=p.get("objective", ""), audience=p.get("audience", ""),
        archetype=p.get("archetype", "concept-explainer"), n_units=n_units,
        sources_text=text, course_title=p.get("title") or None, preset=p.get("preset"))
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
    got, err = _read_sources_or_error(p["source"], urls=p.get("urls", ""))
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
        images=authoring.list_images(p.get("images")), preset=p.get("preset"),
        glossary=authoring.load_glossary(p.get("brand")))
    ok, raw, err_s = authoring.run_cli(p.get("provider", "claude"), prompt, model=p.get("model"))
    if not ok:
        return {"ok": False, "error": err_s, "idx": idx}
    return {"ok": True, "idx": idx, "md": authoring.clean_output(raw)}


def do_save_course(p):
    """Staged pass 4 — stitch the unit scripts into one course .md, lint it, render
    the SME review .docx(s), and record it on the project."""
    import authoring, re as _re, importlib
    _auto_snapshot(p, "Before save course")        # assembling/overwriting the course .md
    out_dir = p["out"]
    os.makedirs(out_dir, exist_ok=True)
    title = (p.get("title") or "course").strip()
    slug = _re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "course"
    out_md = os.path.join(out_dir, f"{slug}.md")
    full = authoring.assemble_course(p.get("title") or None, p.get("rationale", ""),
                                     p.get("units_md") or [])
    with open(out_md, "w", encoding="utf-8") as fh:
        fh.write(full)
    lint_ok, units, lint_errors = authoring.lint(full, glossary=authoring.load_glossary(p.get("brand")))
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


def do_regenerate_unit(p):
    """Re-draft ONE microlearning in an existing script (optionally with a guidance
    note), splice it back in, re-lint, and re-render that unit's review .docx —
    without touching the other modules."""
    import authoring, importlib
    script = p.get("script")
    if not script or not os.path.isfile(script):
        return {"ok": False, "error": "No script to regenerate from."}
    _auto_snapshot(p, "Before regenerate module")   # the script .md is about to be overwritten
    which = int(p.get("which", 1))
    got, err = _read_sources_or_error(p.get("source"), urls=p.get("urls", ""))
    if err:
        return err
    text, _u, _s = got
    units = [{"title": m["title"], "objective": ""} for m in microlearnings(script)]
    if not (0 < which <= len(units)):
        return {"ok": False, "error": f"unit {which} is out of range (1..{len(units)})"}
    prompt = authoring.build_unit_prompt(
        unit=units[which - 1], all_units=units, idx=which, total=len(units),
        objective=p.get("objective", ""), audience=p.get("audience", ""),
        archetype=p.get("archetype", "concept-explainer"),
        sources_text=text, course_title=p.get("title") or None,
        images=authoring.list_images(p.get("images")), preset=p.get("preset"),
        guidance=p.get("guidance", ""), glossary=authoring.load_glossary(p.get("brand")))
    ok, raw, err_s = authoring.run_cli(p.get("provider", "claude"), prompt, model=p.get("model"))
    if not ok:
        return {"ok": False, "error": err_s}
    # X1: when the caller wants to review the re-draft before it lands, hand back the
    # OLD and NEW unit markdown and DON'T write. The client diffs them block-by-block and
    # posts the merged unit to /api/apply-unit-merge. (The pre-write snapshot above stands
    # as the "before" for that eventual write.)
    if p.get("review"):
        old_md = authoring.extract_unit(open(script, encoding="utf-8").read(), which)
        new_md = authoring.clean_output(raw).strip()
        return {"ok": True, "which": which, "units": len(units),
                "old_md": old_md, "new_md": new_md}
    return _apply_unit_markdown(p, script, which, raw)


def _apply_unit_markdown(p, script, which, new_unit_md):
    """Splice one unit's markdown into the course script, re-lint, and re-render its
    review .docx. Shared by the direct regenerate path and the X1 apply-merge path."""
    import authoring, importlib
    updated = authoring.replace_unit(open(script, encoding="utf-8").read(), which, new_unit_md)
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(updated)
    lint_ok, units_n, lint_errors = authoring.lint(updated, glossary=authoring.load_glossary(p.get("brand")))
    res = {"ok": True, "out": script, "which": which, "units": units_n,
           "lint_ok": lint_ok, "lint_errors": lint_errors}
    try:
        from md_import import import_md
        import docx_review, brand as brandmod
        importlib.reload(docx_review)
        b = brandmod.load_brand(p.get("brand", "_default"))
        slug = os.path.splitext(os.path.basename(script))[0]
        ir, _ = import_md(script, which=which)
        dp = os.path.join(os.path.dirname(script), f"{slug}_m{which}_review.docx")
        docx_review.render_review_docx(ir, dp, brand=b, md_path=script, which=which)
        res["review_docx"] = [dp]
    except Exception as e:
        res["review_warning"] = str(e)
    return res


def do_apply_unit_merge(p):
    """X1 — write the operator's block-by-block MERGE of a regenerated unit. The client
    has already chosen, per block, the new draft or the current text; here we just splice
    the reconstructed unit markdown in (same write/lint/docx path as a direct regen)."""
    script = p.get("script")
    if not script or not os.path.isfile(script):
        return {"ok": False, "error": "No script to apply to."}
    which = int(p.get("which", 1))
    merged = p.get("merged_md", "")
    if not merged.strip():
        return {"ok": False, "error": "Nothing to apply."}
    _auto_snapshot(p, "Before apply merged module")   # the script .md is about to be overwritten
    return _apply_unit_markdown(p, script, which, merged)


def do_translate(p):
    """M5 — translate/localize a built course .md into a target language or locale,
    preserving §8 block structure. One subscription-CLI pass per unit; reuses the
    brand glossary as a keep-verbatim term list; writes a sibling .md tagged with the
    target (non-destructive — the source script is untouched)."""
    import authoring, re as _re
    script = p.get("script")
    if not script or not os.path.isfile(script):
        return {"ok": False, "error": "No script to translate from."}
    target = (p.get("target") or "").strip()
    if not target:
        return {"ok": False, "error": "No target language or locale given."}
    md_text = open(script, encoding="utf-8").read()
    res = authoring.translate_course(p.get("provider", "claude"), md_text, target,
                                     brand=p.get("brand"), model=p.get("model"))
    if not res.get("ok"):
        return res
    slug = _re.sub(r"[^a-z0-9]+", "-", target.lower()).strip("-") or "translated"
    base, ext = os.path.splitext(script)
    out_md = f"{base}.{slug}{ext or '.md'}"
    with open(out_md, "w", encoding="utf-8") as fh:
        fh.write(res["out"])
    res["out"] = out_md
    return res


def do_tm_approve(p):
    """C17 — the final approval step for a full translation: promote the source course's
    PENDING translation-memory units for `target` to approved (reusable). Read-only wrt
    the course files; touches only the memory store. Localizations are already approved
    on write, so this is a no-op for them."""
    import tm
    script = p.get("script")
    target = (p.get("target") or "").strip()
    if not script or not os.path.isfile(script):
        return {"ok": False, "error": "No source script for approval."}
    if not target:
        return {"ok": False, "error": "No target language given."}
    md_text = open(script, encoding="utf-8").read()
    n = tm.approve(target, md_text)
    return {"ok": True, "target": target, "approved": n}


def do_captions(p):
    """M3 — generate local captions for a course's file-mode video/audio blocks.
    Transcribes each resolvable LOCAL media file with a local Whisper, writes a
    sidecar .vtt next to it, and binds it onto the media line so the next build
    renders a <track kind="captions">. Snapshots the script first (it's edited in
    place); remote/embedded media and (no-Whisper) installs are reported skipped."""
    import captions
    script = p.get("script")
    if not script or not os.path.isfile(script):
        return {"ok": False, "error": "No script to caption."}
    _auto_snapshot(p, "Before captions")            # the script .md is edited in place
    base_dir = p.get("assets") or os.path.dirname(os.path.abspath(script))
    md_text = open(script, encoding="utf-8").read()
    new_md, report = captions.caption_markdown(
        md_text, base_dir, lang=(p.get("lang") or "en"),
        overwrite=bool(p.get("overwrite")))
    bound = [r for r in report if r["status"] in ("written", "exists")]
    if bound and new_md != md_text:
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(new_md)
    return {"ok": True, "backend": captions.caption_backend(), "report": report,
            "written": sum(r["status"] == "written" for r in report),
            "bound": len(bound)}


def do_consistency(p):
    """C20 — check one appended unit against the rest of a course for term/voice drift.
    Imports the target unit (default: the last, i.e. the just-appended one) and its
    siblings, runs the deterministic drift check (glossary-aware), and returns the
    findings. Read-only: never touches the script."""
    import re as _re
    import build_report
    from md_import import import_md
    from authoring import load_glossary
    script = p.get("script")
    if not script or not os.path.isfile(script):
        return {"ok": False, "error": "No script to check."}
    text = open(script, encoding="utf-8").read()
    n = len(_re.split(r'^##\s+Microlearning\s+', text, flags=_re.M)) - 1
    if n < 2:
        return {"ok": True, "units": n, "which": None, "findings": [],
                "note": "A course needs two or more units before consistency can be checked."}
    try:
        which = int(p.get("which") or n)
    except (TypeError, ValueError):
        which = n
    which = max(1, min(which, n))
    try:
        new_ir, _ = import_md(script, which=which)
        prior = [import_md(script, which=k)[0] for k in range(1, n + 1) if k != which]
    except Exception as e:
        return {"ok": False, "error": f"Could not import the course units: {e}"}
    gl = load_glossary(p.get("brand") or "_default")
    findings = build_report.consistency_findings(new_ir, prior, glossary=gl)
    return {"ok": True, "units": n, "which": which,
            "title": new_ir.get("title"), "findings": findings}


def do_batch_generate(p):
    """M6 — bulk-generate courses from a manifest CSV. `validate:true` does a dry run (parse +
    per-row checks, generates nothing). Otherwise generates one course per row into `out`,
    reusing authoring.generate(). The manifest may be given as a file path (`csv`) or inline
    text (`csv_text`)."""
    import authoring
    csv_text = p.get("csv_text")
    if not csv_text:
        path = p.get("csv")
        if not path or not os.path.isfile(path):
            return {"ok": False, "error": "No manifest CSV given."}
        csv_text = open(path, encoding="utf-8").read()
    rows, errors = authoring.parse_manifest(csv_text)
    if errors:
        return {"ok": False, "error": "; ".join(errors), "rows": []}
    checks = authoring.validate_manifest(rows)
    if p.get("validate"):
        bad = sum(1 for c in checks if not c["ok"])
        return {"ok": bad == 0, "validate": True, "n": len(rows),
                "ok_count": len(rows) - bad, "fail_count": bad, "rows": checks}
    bad = [c for c in checks if not c["ok"]]
    if bad:
        return {"ok": False, "error": f"{len(bad)} row(s) have issues — run validate to see all.",
                "validate": False, "rows": checks}
    out_dir = p.get("out")
    if not out_dir:
        return {"ok": False, "error": "No output folder given."}
    return authoring.generate_batch(p.get("provider", "claude"), rows, out_dir,
                                    brand=p.get("brand"))


def do_revise(p):
    """Stage 5: apply the SME's reviewed .docx onto the canonical script via the
    subscription CLI; write the updated script to the Approved Scripts folder and
    re-render its review .docx."""
    import authoring, importlib, glob, os as _os
    _auto_snapshot(p, "Before SME revise")          # applying reviewed edits onto the script
    script = p["script"]
    approved_dir = p["approved_dir"]
    out_md = _os.path.join(approved_dir, _os.path.basename(script))
    # `reviewed` may be a single .docx OR a FOLDER: parallel generation drafts one
    # review .docx per module, so the SME hands back several. A folder expands to all
    # its .docx files (skip Word's ~$ lock files); a single file passes straight through.
    reviewed = p["reviewed"]
    if isinstance(reviewed, str) and _os.path.isdir(reviewed):
        reviewed = sorted(f for f in glob.glob(_os.path.join(reviewed, "*.docx"))
                          if not _os.path.basename(f).startswith("~$"))
        if not reviewed:
            return {"ok": False, "error": "no .docx files in that folder."}
    # The SME-reviewed pass is the FINAL draft -> use the most capable model (Opus),
    # regardless of the faster model used to draft. Overridable via COURSE_BUILDER_REVIEW_MODEL.
    review_model = os.environ.get("COURSE_BUILDER_REVIEW_MODEL", "opus").strip() or None
    res = authoring.revise(provider=p.get("provider", "claude"), script_path=script,
                           reviewed_docx=reviewed, out_path=out_md, model=review_model,
                           glossary=authoring.load_glossary(p.get("brand")))
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


def do_snapshot(p):
    """Manually capture a checkpoint of the current project IR (deck + script).
    The dashboard also calls this (kind=auto) before each deck/slide AI edit."""
    root = p.get("project")
    if not root or not _within_roots(root):
        return {"ok": False, "error": "project path not allowed"}
    m = make_snapshot(root, p.get("label", "Manual checkpoint"), kind=p.get("kind", "manual"))
    if not m:
        return {"ok": False, "error": "nothing to snapshot yet"}
    return {"ok": True, "snapshot": m, "snapshots": list_snapshots(root)}


def do_restore(p):
    """Roll the project back to a snapshot (snapshot-then-restore: the current
    state is captured first, so the rewind is itself undoable)."""
    root = p.get("project")
    if not root or not _within_roots(root):
        return {"ok": False, "error": "project path not allowed"}
    res = restore_snapshot(root, p.get("id", ""))
    if res.get("ok"):
        res["snapshots"] = list_snapshots(root)
    return res


def do_rename_snapshot(p):
    """M16 — name a version: rename a snapshot, and/or promote it to a kept,
    named `version` (pass kind="version"). Returns the refreshed snapshot list."""
    root = p.get("project")
    if not root or not _within_roots(root):
        return {"ok": False, "error": "project path not allowed"}
    res = rename_snapshot(root, p.get("id", ""), label=p.get("label"), kind=p.get("kind"))
    if res.get("ok"):
        res["snapshots"] = list_snapshots(root)
    return res


def do_save_template(p):
    """M17 — save the current project OR a single slide as a reusable template."""
    kind = p.get("kind", "project")
    name = (p.get("name") or "").strip()
    if kind == "slide":
        res = save_slide_template(name, p.get("layout"), p.get("content"))
    else:
        root = p.get("project")
        if not root or not _within_roots(root):
            return {"ok": False, "error": "project path not allowed"}
        res = save_project_template(root, name)
    if res.get("ok"):
        res["templates"] = list_templates()
    return res


def do_instantiate_template(p):
    """M17 — return a template's payload to load into the current session. A project
    template may carry a course script, placed into the open project when one is open."""
    tid = p.get("id", "")
    if not _safe_store_id(tid):
        return {"ok": False, "error": "bad template id"}
    res = instantiate_template(tid)
    if res.get("ok") and res.get("kind") == "project" and res.get("script_text"):
        root = p.get("project")
        if root and _within_roots(root):
            try:
                res["script"] = place_template_script(root, res.get("script_name"), res["script_text"])
            except OSError:
                pass
    return res


def do_delete_template(p):
    """M17 — permanently delete a saved template."""
    tid = p.get("id", "")
    if not _safe_store_id(tid):
        return {"ok": False, "error": "bad template id"}
    res = delete_template(tid)
    if res.get("ok"):
        res["templates"] = list_templates()
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
        # Never let the browser serve a stale build of the UI — the page carries a
        # per-process CSRF token and the dashboard is updated in place, so a cached
        # copy means dead buttons + 403s on POST. Always re-fetch.
        self.send_header("Cache-Control", "no-store, must-revalidate")
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
            got, err = _read_sources_or_error(src, urls=p.get("urls", ""))
            if err:
                finish(err); return
            text, used, skipped = got
            n_units = int(p["units"]) if str(p.get("units", "")).strip().isdigit() else None
            _gloss = authoring.load_glossary(p.get("brand"))
            prompt = authoring.build_prompt(
                objective=p.get("objective", ""), audience=p.get("audience", ""),
                archetype=p.get("archetype", "concept-explainer"), n_units=n_units,
                sources_text=text, course_title=p.get("title") or None,
                images=authoring.list_images(p.get("images")), preset=p.get("preset"),
                glossary=_gloss)
            ok, full, gerr = authoring.run_cli_stream(p.get("provider", "claude"), prompt, emit, model=p.get("model"))
            if not ok:
                finish({"ok": False, "error": gerr, "skipped": skipped}); return
            md = authoring.clean_output(full)
            # M1 self-heal: if the streamed draft fails lint, re-prompt to fix it before saving.
            # The raw first draft already streamed to the browser, so announce the repair pass.
            pre_ok, _pn, pre_errs = authoring.lint(md, glossary=_gloss)
            if not pre_ok:
                emit(f"\n\n[self-heal] fixing {len(pre_errs)} lint issue(s)…\n")
            heal = authoring.heal_course_md(p.get("provider", "claude"), md, glossary=_gloss,
                                            model=p.get("model"))
            md = heal["md"]
            # M2 alt-text redraft: fill any informative image missing its description
            # before saving. Announce it like the self-heal pass (draft already streamed).
            pre_gaps = authoring.alt_gaps(md)
            if pre_gaps:
                emit(f"\n[alt-text] drafting alt for {len(pre_gaps)} image(s)…\n")
            alt = authoring.heal_alt_text(p.get("provider", "claude"), md, model=p.get("model"))
            md = alt["md"]
            out_dir = p["out"]; os.makedirs(out_dir, exist_ok=True)
            title = (p.get("title") or "course").strip()
            slug = _re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "course"
            out_md = os.path.join(out_dir, f"{slug}.md")
            with open(out_md, "w", encoding="utf-8") as fh:
                fh.write(md)
            lint_ok, units, lint_errors = heal["lint_ok"], heal["units"], heal["lint_errors"]
            result = {"ok": True, "out": out_md, "units": units, "lint_ok": lint_ok,
                      "lint_errors": lint_errors, "skipped": skipped,
                      "heal_rounds": heal["rounds"], "heal_history": heal["history"],
                      "alt_rounds": alt["rounds"], "alt_gaps": alt["gaps"], "alt_history": alt["history"]}
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

    def _stream_generate_deck(self, p):
        """Streaming deck generation: stream claude's JSON deck to the browser live
        (same isolated, model-selectable pass the course flow uses), then parse +
        lint and return the slide specs for the editor. Writes its OWN chunked
        response and never raises after headers."""
        import authoring
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
            got, err = _read_sources_or_error(src, urls=p.get("urls", ""))
            if err:
                finish(err); return
            text, used, skipped = got
            n_slides = int(p["nslides"]) if str(p.get("nslides", "")).strip().isdigit() else None
            prompt = authoring.build_deck_prompt(p.get("title") or None, p.get("focus", ""),
                                                 p.get("audience", ""), n_slides, text,
                                                 images=authoring.list_images(_deck_images_dir(p)),
                                                 preset=p.get("preset"), outline=p.get("outline"))
            ok, full, gerr = authoring.run_cli_stream(p.get("provider", "claude"), prompt, emit,
                                                      model=p.get("model"))
            if not ok:
                finish({"ok": False, "error": gerr, "skipped": skipped}); return
            try:
                data = json.loads(authoring.clean_json(full))
            except ValueError as e:
                finish({"ok": False, "error": f"the model did not return valid JSON: {e}",
                        "raw": full[:2000], "skipped": skipped}); return
            slides = data.get("slides") if isinstance(data, dict) else data
            if not isinstance(slides, list) or not slides:
                finish({"ok": False, "error": "the model returned no 'slides' list.",
                        "skipped": skipped}); return
            lint_ok, n, lint_errors = authoring.lint_deck(slides)
            finish({"ok": True, "slides": slides, "count": n, "lint_ok": lint_ok,
                    "lint_errors": lint_errors,
                    "lint_warnings": (authoring.deck_palette_warnings(slides)
                                      + authoring.deck_brand_warnings(slides)),
                    "used_sources": used, "skipped": skipped})
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
                        "templates": template_layouts(),
                        "my_templates": list_templates(),
                        "slides_out": os.path.join(os.path.expanduser("~"), "Course Builder Slides")})
        elif u.path == "/api/ai-status":
            import authoring
            self._json({"providers": authoring.provider_status()})
        elif u.path == "/api/assets":
            # Visual-asset library (SVG icons) for the slide picker. Each carries a
            # recolored preview SVG for the thumbnail; the slide stores the bare name,
            # which the renderer resolves + recolors on-brand at render time.
            import assets as _assets
            self._json({"ok": True,
                        "assets": [{"name": n, "svg": _assets.icon_preview_svg(n)}
                                   for n in _assets.list_icons()]})
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
        elif u.path == "/api/readtext":
            # Read a plain-text artifact (the script .md) for the View-script modal.
            # Read-only, confined to the allowlist, capped so a stray huge file can't
            # be slurped into the browser.
            req = q.get("path", [""])[0]
            if not _within_roots(req):
                self._json({"ok": False, "error": "path not allowed"})
            else:
                path = os.path.abspath(os.path.expanduser(req))
                try:
                    if os.path.getsize(path) > 4 * 1024 * 1024:
                        self._json({"ok": False, "error": "file too large to preview"})
                    else:
                        self._json({"ok": True, "text": open(path, encoding="utf-8").read()})
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
        elif u.path == "/api/snapshots":
            req = q.get("project", [""])[0]
            self._json({"snapshots": list_snapshots(req) if _within_roots(req) else []})
        elif u.path == "/api/templates":
            self._json({"templates": list_templates()})
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
            elif u.path == "/api/deck-notes":
                self._json(do_deck_notes(p))
            elif u.path == "/api/deck-svg":
                self._json(do_deck_svg(p))
            elif u.path == "/api/slide-svg":
                self._json(do_slide_svg(p))
            elif u.path == "/api/deck-plan":
                self._json(do_deck_plan(p))
            elif u.path == "/api/match-layout":
                self._json(do_match_layout(p))
            elif u.path == "/api/generate-deck":
                self._json(do_generate_deck(p))
            elif u.path == "/api/generate-deck-stream":
                self._stream_generate_deck(p); return
            elif u.path == "/api/regenerate-slide":
                self._json(do_regenerate_slide(p))
            elif u.path == "/api/chart-csv":
                self._json(do_chart_csv(p))
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
            elif u.path == "/api/regenerate-unit":
                self._json(do_regenerate_unit(p))
            elif u.path == "/api/apply-unit-merge":
                self._json(do_apply_unit_merge(p))
            elif u.path == "/api/publish":
                self._json(do_publish(p))
            elif u.path == "/api/revise":
                self._json(do_revise(p))
            elif u.path == "/api/translate":
                self._json(do_translate(p))
            elif u.path == "/api/tm-approve":
                self._json(do_tm_approve(p))
            elif u.path == "/api/captions":
                self._json(do_captions(p))
            elif u.path == "/api/consistency":
                self._json(do_consistency(p))
            elif u.path == "/api/batch-generate":
                self._json(do_batch_generate(p))
            elif u.path == "/api/snapshot":
                self._json(do_snapshot(p))
            elif u.path == "/api/snapshot/rename":
                self._json(do_rename_snapshot(p))
            elif u.path == "/api/restore":
                self._json(do_restore(p))
            elif u.path == "/api/template/save":
                self._json(do_save_template(p))
            elif u.path == "/api/template/new":
                self._json(do_instantiate_template(p))
            elif u.path == "/api/template/delete":
                self._json(do_delete_template(p))
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
