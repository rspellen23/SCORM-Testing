"""CourseCraft — local dashboard server (no Streamlit, no GUI toolkit).

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
import subprocess
import webbrowser
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
CLI = os.path.join(SRC, "cli.py")
HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
sys.path.insert(0, SRC)

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


def microlearnings(md_path):
    try:
        text = open(md_path, encoding="utf-8").read()
    except OSError:
        return []
    return [{"which": i, "title": m.group(1).strip()}
            for i, m in enumerate(
                re.finditer(r"^##\s+Microlearning\s+\d+:\s*(.+)$", text, flags=re.M), 1)]


def ls(path):
    """List sub-directories and .md files of a directory (for the navigator)."""
    path = os.path.abspath(os.path.expanduser(path or os.path.expanduser("~")))
    if not os.path.isdir(path):
        path = os.path.expanduser("~")
    dirs, mds, docx = [], [], []
    try:
        for name in sorted(os.listdir(path), key=str.lower):
            if name.startswith("."):
                continue
            full = os.path.join(path, name)
            if os.path.isdir(full):
                dirs.append(name)
            elif name.lower().endswith(".md"):
                mds.append(name)
            elif name.lower().endswith(".docx"):
                docx.append(name)
    except PermissionError:
        pass
    parent = os.path.dirname(path)
    return {"path": path, "parent": parent if parent != path else None,
            "dirs": dirs, "mds": mds, "docx": docx}


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

CONFIG_DIR = os.path.expanduser("~/.coursecraft")
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
    md, img, out = p["md"], p["images"], p["out"]
    brand, validate = p.get("brand", "_default"), p.get("validate", True)
    entire = p.get("scope") == "course"
    which = int(p.get("which", 1))
    mls = microlearnings(md)
    stem = os.path.splitext(os.path.basename(md))[0]
    jobs = []
    for fmt in p.get("formats", []):
        if fmt == "pptx":
            targets = [m["which"] for m in mls] if entire else [which]
            for w in targets:
                op = os.path.join(out, f"{stem}_m{w}.pptx")
                jobs.append({"label": f"PowerPoint · unit {w}", "fmt": "pptx",
                             "args": ["to-pptx", md, "--which", str(w), "--images", img,
                                      "--brand", brand, "--out", op], "out": op, "preview": None})
        else:
            f = "cmi5" if fmt == "cmi5" else "scorm"
            tag = "cmi5" if f == "cmi5" else "scorm12"
            label = "cmi5/xAPI package" if f == "cmi5" else "SCORM 1.2 package"
            if entire:
                op = os.path.join(out, f"{stem}_course_{tag}.zip")
                a = ["from-md-course", md, "--images", img, "--brand", brand, "--format", f, "--out", op]
            else:
                op = os.path.join(out, f"{stem}_m{which}_{tag}.zip")
                a = ["from-md", md, "--which", str(which), "--images", img, "--brand", brand,
                     "--format", f, "--out", op]
            a.append("--keep-dir")                       # keep the .course dir for preview
            if validate:
                a.append("--validate")
            preview = os.path.join(os.path.splitext(op)[0] + ".course", "index.html")
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
        except Exception:
            pass
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
        pass

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

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            try:
                self._file(HTML)
            except OSError:
                self._json({"error": "index.html missing"}, 500)
        elif u.path == "/api/init":
            import authoring
            cfg = load_config()
            ws = cfg.get("workspace") or os.path.join(os.path.expanduser("~"), "CourseCraft Courses")
            self._json({"home": os.path.expanduser("~"), "brands": list_brands(),
                        "folders": PROJECT_FOLDERS,
                        "providers": authoring.provider_status(),
                        "archetypes": authoring.list_archetypes(),
                        "workspace": ws, "workspace_set": bool(cfg.get("workspace")),
                        "projects": list_projects(ws)})
        elif u.path == "/api/ai-status":
            import authoring
            self._json({"providers": authoring.provider_status()})
        elif u.path == "/api/ls":
            self._json(ls(q.get("path", [""])[0]))
        elif u.path == "/api/scan":
            self._json({"mls": microlearnings(q.get("md", [""])[0])})
        elif u.path == "/api/listfiles":
            ext = q.get("ext", [None])[0]
            exts = ext.split(",") if ext else None
            self._json({"files": list_files(q.get("path", [""])[0], exts)})
        elif u.path == "/api/reveal":
            self._json({"ok": reveal(q.get("path", [""])[0])})
        elif u.path == "/preview":
            # serve a file from inside a built .course dir (path-traversal guarded)
            base = os.path.abspath(q.get("dir", [""])[0])
            rel = q.get("file", ["index.html"])[0]
            target = os.path.abspath(os.path.join(base, rel))
            if target.startswith(base) and os.path.isfile(target):
                self._file(target)
            else:
                self._json({"error": "not found"}, 404)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
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
                ws = load_config().get("workspace") or os.path.join(os.path.expanduser("~"), "CourseCraft Courses")
                os.makedirs(ws, exist_ok=True)
                if not load_config().get("workspace"):
                    save_config({"workspace": ws})
                res = new_project(ws, p["name"])
                res["projects"] = list_projects(ws)
                self._json(res)
            elif u.path == "/api/project/open":
                self._json(read_project(os.path.expanduser(p["path"])))
            elif u.path == "/api/project/save":
                meta = write_project(os.path.expanduser(p["path"]), p.get("meta", {}))
                self._json({"ok": True, "meta": meta})
            elif u.path == "/api/build":
                self._json(do_build(p))
            elif u.path == "/api/review":
                self._json(do_review(p))
            elif u.path == "/api/generate":
                self._json(do_generate(p))
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
    print(f"\n  CourseCraft dashboard → {url}")
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
