#!/usr/bin/env python3
"""Nova Course Builder — CLI.

  python src/cli.py from-rise  <rise-raw.zip>           --out build/course.zip
  python src/cli.py from-docx  <course.docx> --images <dir>  --out build/course.zip
  python src/cli.py import-rise <rise-raw.zip>          --out build/course.ir.json
"""
import os, sys, json, argparse, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render, scorm, cmi5  # noqa: E402


def _emit(ir, asset_blobs, out_zip, keep_dir=False, validate=False, fmt="scorm"):
    course_dir = os.path.splitext(out_zip)[0] + ".course"
    render.render_course(ir, course_dir, asset_blobs)
    if fmt == "cmi5":
        cmi5.package(course_dir, out_zip, ir["id"], ir["title"], lang=ir.get("locale", "en"),
                     graded=ir.get("graded", False), passing=ir.get("passingScore", 80))
    else:
        scorm.package(course_dir, out_zip, ir["id"], ir["title"])
    if not keep_dir:
        import shutil; shutil.rmtree(course_dir, ignore_errors=True)
    st = ir.get("_stats", {})
    print(f"✓ {ir['title']}")
    print(f"  blocks={st.get('blocks')} assets={st.get('assets')} "
          f"skipped={st.get('skipped', {})}")
    print(f"  {fmt.upper()} → {out_zip} ({os.path.getsize(out_zip)//1024} KB)")
    if validate:
        _run_lint(out_zip)


def _run_lint(out_zip):
    import scorm_lint
    errors, warnings = scorm_lint.lint_zip(out_zip)
    for w in warnings:
        print(f"  lint warning: {w}")
    if errors:
        for e in errors:
            print(f"  lint ERROR: {e}")
        raise SystemExit(f"✗ conformance lint failed for {out_zip}")
    print("  ✓ conformance lint passed")


def cmd_from_rise(a):
    from rise_import import import_rise
    ir, copy_map, src_zip = import_rise(a.zip)
    blobs = {}
    with zipfile.ZipFile(src_zip) as zf:
        for in_path, rel in copy_map.items():
            blobs[rel] = zf.read(in_path)
    _emit(ir, blobs, a.out, a.keep_dir, getattr(a, "validate", False), getattr(a, "format", "scorm"))


def cmd_from_docx(a):
    from docx_import import import_docx
    ir, used = import_docx(a.docx, a.images)
    blobs = {rel: open(src, "rb").read() for rel, src in used.items()}
    _emit(ir, blobs, a.out, a.keep_dir, getattr(a, "validate", False), getattr(a, "format", "scorm"))


def cmd_from_md(a):
    from md_import import import_md
    ir, used = import_md(a.md, which=a.which, hero=a.hero, image_dir=a.images)
    blobs = {rel: open(src, "rb").read() for rel, src in used.items()}
    _emit(ir, blobs, a.out, a.keep_dir, getattr(a, "validate", False), getattr(a, "format", "scorm"))


def cmd_from_md_course(a):
    """Build EVERY '## Microlearning N' in a .md into ONE multi-SCO SCORM course
    (N lessons sharing brand/+player/; the LMS shows a TOC and rolls up completion)."""
    import re, shutil
    from md_import import import_md
    from common import slugify
    text = open(a.md, encoding="utf-8").read()
    n = len(re.split(r'^##\s+Microlearning\s+', text, flags=re.M)) - 1
    if n < 1:
        raise SystemExit(f"no '## Microlearning N:' sections found in {a.md}")
    mt = re.search(r'^#\s+(.+)$', text, flags=re.M)
    title = a.title or (mt.group(1).strip() if mt else os.path.splitext(os.path.basename(a.md))[0])
    cid = slugify(title)
    course_dir = os.path.splitext(a.out)[0] + ".course"
    if os.path.exists(course_dir):
        shutil.rmtree(course_dir)
    os.makedirs(course_dir)
    render.copy_shared(course_dir)                          # brand/ + player/ once at the root
    scos, graded, passing, lang = [], False, 80, "en"
    for k in range(1, n + 1):
        ir, used = import_md(a.md, which=k, image_dir=a.images)
        blobs = {rel: open(src, "rb").read() for rel, src in used.items()}
        render.render_course(ir, os.path.join(course_dir, f"sco_{k}"), blobs,
                             asset_base="../", bundle_brand_player=False,
                             lesson_index=k, lesson_count=n)
        scos.append({"id": ir["id"], "title": ir["title"], "href": f"sco_{k}/index.html"})
        graded, passing, lang = ir.get("graded", False), ir.get("passingScore", 80), ir.get("locale", "en")
    fmt = getattr(a, "format", "scorm")
    if fmt == "cmi5":
        cmi5.package_multi(course_dir, a.out, cid, title, scos, lang=lang, graded=graded, passing=passing)
    else:
        scorm.package_multi(course_dir, a.out, cid, title, scos)
    print(f"✓ {title} — {n} lesson(s) [{fmt}]")
    for k, s in enumerate(scos, 1):
        print(f"    {k}. {s['title']}")
    print(f"  {fmt.upper()} (multi) → {a.out} ({os.path.getsize(a.out)//1024} KB)")
    if not a.keep_dir:
        shutil.rmtree(course_dir, ignore_errors=True)
    if getattr(a, "validate", False):
        _run_lint(a.out)


def cmd_gen_prompts(a):
    """Emit a ready-to-use ChatGPT image prompt for every generatable asset a course needs.

    All assets share ONE deck-wide lock (rendering + palette usage) so a course's images cohere
    (harvested from ppt-master). --manifest also writes a re-rollable image_prompts.json.
    """
    from md_import import collect_assets
    import prompts as P
    title, assets = collect_assets(a.md, which=a.which, hero=a.hero)
    lock = P.make_lock(hierarchy=a.hierarchy, title=title)   # deck-wide: built once, used for every asset
    lines = [f"# Image prompts — {title}", ""]
    mitems, n = [], 0
    for asset in assets:
        orient = asset["orientation"] or P.ROLE_DEFAULT_ORIENT.get(asset["role"], "landscape")
        if not asset["generatable"]:
            lines += [f"## {asset['slot']}  ·  role: {asset['role']}  ·  (screenshot — capture, no prompt)", ""]
            mitems.append(P.manifest_item(asset["slot"], asset["role"], orient, None, generatable=False))
            continue
        n += 1
        prompt = P.build_prompt_locked(lock, asset["description"],
                                       role=asset["role"], orientation=asset["orientation"])
        lines += [f"## {asset['slot'] or '(unnamed)'}  ·  role: {asset['role']}  ·  orientation: {orient}",
                  "", prompt, ""]
        mitems.append(P.manifest_item(asset["slot"], asset["role"], orient, prompt, generatable=True))
    out = "\n".join(lines)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(out)
        print(f"✓ {n} prompt(s) → {a.out}")
    else:
        print(out)
    if a.manifest:
        with open(a.manifest, "w", encoding="utf-8") as f:
            json.dump(P.build_manifest(title, mitems, lock), f, indent=2, ensure_ascii=False)
        print(f"✓ manifest ({len(mitems)} items) → {a.manifest}")


def cmd_import_rise(a):
    from rise_import import import_rise
    ir, _copy, _src = import_rise(a.zip)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(ir, f, indent=2, ensure_ascii=False)
    print(f"✓ IR → {a.out}  (blocks={ir['_stats']['blocks']}, "
          f"skipped={ir['_stats'].get('skipped')})")


def cmd_from_ir(a):
    """Rebuild a SCORM from an (edited) IR JSON + a folder of its assets."""
    ir = json.load(open(a.ir, encoding="utf-8"))
    blobs = {}
    if a.images and os.path.isdir(a.images):
        for n in os.listdir(a.images):
            fp = os.path.join(a.images, n)
            if os.path.isfile(fp):
                blobs["assets/" + n] = open(fp, "rb").read()
    _emit(ir, blobs, a.out, a.keep_dir, getattr(a, "validate", False), getattr(a, "format", "scorm"))


def cmd_repackage(a):
    """Re-zip an (edited) course directory into SCORM — for direct HTML tweaks."""
    cid = a.id or os.path.splitext(os.path.basename(a.dir))[0]
    title = a.title or cid
    scorm.package(a.dir, a.out, cid, title)
    print(f"✓ repackaged {a.dir} → {a.out} ({os.path.getsize(a.out)//1024} KB)")


def cmd_lint(a):
    import scorm_lint
    raise SystemExit(scorm_lint.main(["scorm_lint", a.zip]))


def main():
    p = argparse.ArgumentParser(prog="nova-course-builder")
    sub = p.add_subparsers(required=True)

    r = sub.add_parser("from-rise"); r.add_argument("zip")
    r.add_argument("--out", required=True); r.add_argument("--keep-dir", action="store_true")
    r.add_argument("--validate", action="store_true"); r.set_defaults(fn=cmd_from_rise)

    d = sub.add_parser("from-docx"); d.add_argument("docx")
    d.add_argument("--images", required=True); d.add_argument("--out", required=True)
    d.add_argument("--keep-dir", action="store_true")
    d.add_argument("--validate", action="store_true"); d.set_defaults(fn=cmd_from_docx)

    md = sub.add_parser("from-md"); md.add_argument("md")
    md.add_argument("--which", type=int, default=1); md.add_argument("--images", default=None)
    md.add_argument("--hero", default=None); md.add_argument("--out", required=True)
    md.add_argument("--keep-dir", action="store_true")
    md.add_argument("--format", choices=["scorm", "cmi5"], default="scorm")
    md.add_argument("--validate", action="store_true"); md.set_defaults(fn=cmd_from_md)

    mc = sub.add_parser("from-md-course"); mc.add_argument("md")
    mc.add_argument("--images", default=None); mc.add_argument("--title", default=None)
    mc.add_argument("--out", required=True); mc.add_argument("--keep-dir", action="store_true")
    mc.add_argument("--format", choices=["scorm", "cmi5"], default="scorm")
    mc.add_argument("--validate", action="store_true"); mc.set_defaults(fn=cmd_from_md_course)

    gp = sub.add_parser("gen-prompts"); gp.add_argument("md")
    gp.add_argument("--which", type=int, default=1); gp.add_argument("--hero", default=None)
    gp.add_argument("--hierarchy", default=None); gp.add_argument("--out", default=None)
    gp.add_argument("--manifest", default=None, help="also write a re-rollable image_prompts.json here")
    gp.set_defaults(fn=cmd_gen_prompts)

    i = sub.add_parser("import-rise"); i.add_argument("zip")
    i.add_argument("--out", required=True); i.set_defaults(fn=cmd_import_rise)

    fi = sub.add_parser("from-ir"); fi.add_argument("ir")
    fi.add_argument("--images", default=None); fi.add_argument("--out", required=True)
    fi.add_argument("--keep-dir", action="store_true")
    fi.add_argument("--format", choices=["scorm", "cmi5"], default="scorm")
    fi.add_argument("--validate", action="store_true"); fi.set_defaults(fn=cmd_from_ir)

    rp = sub.add_parser("repackage"); rp.add_argument("dir")
    rp.add_argument("--out", required=True); rp.add_argument("--id", default=None)
    rp.add_argument("--title", default=None); rp.set_defaults(fn=cmd_repackage)

    ln = sub.add_parser("lint"); ln.add_argument("zip")
    ln.set_defaults(fn=cmd_lint)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
