#!/usr/bin/env python3
"""Course Builder — CLI.

  python src/cli.py from-rise  <rise-raw.zip>           --out build/course.zip
  python src/cli.py from-docx  <course.docx> --images <dir>  --out build/course.zip
  python src/cli.py import-rise <rise-raw.zip>          --out build/course.ir.json
"""
import os, sys, json, re, argparse, zipfile

# When installed (`pip install -e .`) the engine modules import directly.
# When run as a bare script (air-gapped `python3 src/cli.py`), make sure this
# module's own directory is importable. Idempotent — a no-op once installed.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import render, scorm, cmi5, brand  # noqa: E402


def _emit(ir, asset_blobs, out_zip, keep_dir=False, validate=False, fmt="scorm",
          brand_name="_default", animate=True, lint_md=None, package=True, gate=None):
    b = brand.load_brand(brand_name)
    course_dir = os.path.splitext(out_zip)[0] + ".course"
    render.render_course(ir, course_dir, asset_blobs, brand=b, animate=animate, gate=gate)
    if not package:
        # HTML-only render (the dashboard preview): produce the learner-facing course
        # dir and STOP — no SCORM/cmi5 zip. Packaging happens only at publish, so
        # previewing a course never litters the output with packages. The build
        # report is keyed off the course dir (there's no zip to sit beside).
        print(f"✓ {ir['title']} (preview · no package)")
        _write_report(ir, course_dir, lint_md=lint_md, brand=b)
        return
    if fmt == "cmi5":
        cmi5.package(course_dir, out_zip, ir["id"], ir["title"], lang=ir.get("locale", "en"),
                     graded=ir.get("graded", False), passing=ir.get("passingScore", 80),
                     id_base=b.get("cmi5IdBase"))
    elif fmt == "scorm2004":
        scorm.package(course_dir, out_zip, ir["id"], ir["title"], version="2004")
    else:
        scorm.package(course_dir, out_zip, ir["id"], ir["title"])
    if not keep_dir:
        import shutil; shutil.rmtree(course_dir, ignore_errors=True)
    st = ir.get("_stats", {})
    print(f"✓ {ir['title']}")
    print(f"  blocks={st.get('blocks')} assets={st.get('assets')} "
          f"skipped={st.get('skipped', {})}")
    print(f"  {fmt.upper()} → {out_zip} ({os.path.getsize(out_zip)//1024} KB)")
    conf_errors, conf_warnings = ([], [])
    if validate:
        conf_errors, conf_warnings = _run_lint(out_zip)
    # Structured build report (C1): fold the §8 lint pass + conformance results +
    # the IR's import-time drop warnings into one JSON beside the artifact so the
    # dashboard can show the operator when a build degraded — not just stderr.
    _write_report(ir, out_zip, lint_md=lint_md, brand=b,
                  conformance_errors=conf_errors, conformance_warnings=conf_warnings)
    if validate and conf_errors:
        raise SystemExit(f"✗ conformance lint failed for {out_zip}")


def _md_lint_errors(lint_md):
    """Run the §8 authoring lint over a source .md at BUILD time (surfaces KC
    mis-scoring and friends even for hand-authored md that never went through
    generation). Returns a list of error strings (empty on clean / non-md)."""
    if not (lint_md and os.path.isfile(lint_md)):
        return []
    try:
        import authoring
        _ok, _n, errs = authoring.lint(open(lint_md, encoding="utf-8").read())
        return errs
    except Exception as e:                      # lint must never break a build
        return [f"lint pass could not run: {e}"]


def _brand_tokens(b):
    """Resolve a brand's tokens.css into {--brand-*: '#hex'} for the a11y contrast
    check (M2). Best-effort: no profile / unreadable tokens → {} (contrast skipped)."""
    import build_report
    try:
        tk = b.asset("tokens.css") if b is not None else None
        if tk:
            return build_report.parse_tokens_css(open(tk, encoding="utf-8").read())
    except OSError:
        pass
    return {}


def _write_report(ir, out_path, lint_md=None, dropped=None,
                  conformance_errors=None, conformance_warnings=None, brand=None,
                  consistency=None):
    import build_report
    report = build_report.assemble(
        ir, lint_errors=_md_lint_errors(lint_md), dropped=dropped,
        conformance_errors=conformance_errors, conformance_warnings=conformance_warnings,
        brand_tokens=_brand_tokens(brand), consistency=consistency)
    build_report.write(report, out_path)
    rd = [f for f in (report.get("readability") or []) if f.get("severity") == "warn"]
    cons = report.get("consistency") or []
    n = (len(report["warnings"]) + len(report["errors"]) + len(report.get("a11y") or [])
         + len(rd) + len(cons))
    if n:
        print(f"  build report: {len(report['errors'])} error(s), "
              f"{len(report['warnings'])} warning(s), "
              f"{len(report.get('a11y') or [])} a11y finding(s), "
              f"{len(rd)} readability finding(s), "
              f"{len(cons)} consistency finding(s) → {build_report.report_path(out_path)}")
    return report


def _run_lint(out_zip):
    """Run SCORM conformance lint; print results. Returns (errors, warnings).
    The caller decides whether errors are fatal (so the report is written first)."""
    import scorm_lint
    errors, warnings = scorm_lint.lint_zip(out_zip)
    for w in warnings:
        print(f"  lint warning: {w}")
    for e in errors:
        print(f"  lint ERROR: {e}")
    if not errors:
        print("  ✓ conformance lint passed")
    return errors, warnings


def cmd_from_rise(a):
    from rise_import import import_rise
    b = brand.load_brand(getattr(a, "brand", "_default"))
    ir, copy_map, src_zip = import_rise(a.zip, brand=b)
    blobs = {}
    with zipfile.ZipFile(src_zip) as zf:
        for in_path, rel in copy_map.items():
            blobs[rel] = zf.read(in_path)
    _emit(ir, blobs, a.out, a.keep_dir, getattr(a, "validate", False), getattr(a, "format", "scorm"),
          getattr(a, "brand", "_default"), animate=not getattr(a, "no_animate", False))


def cmd_from_docx(a):
    from docx_import import import_docx
    ir, used = import_docx(a.docx, a.images)
    blobs = {rel: open(src, "rb").read() for rel, src in used.items()}
    _emit(ir, blobs, a.out, a.keep_dir, getattr(a, "validate", False), getattr(a, "format", "scorm"),
          getattr(a, "brand", "_default"), animate=not getattr(a, "no_animate", False))


def cmd_from_md(a):
    from md_import import import_md
    ir, used = import_md(a.md, which=a.which, hero=a.hero, image_dir=a.images)
    blobs = {rel: open(src, "rb").read() for rel, src in used.items()}
    _emit(ir, blobs, a.out, a.keep_dir, getattr(a, "validate", False), getattr(a, "format", "scorm"),
          getattr(a, "brand", "_default"), animate=not getattr(a, "no_animate", False),
          lint_md=a.md, package=not getattr(a, "no_package", False),
          gate=(False if getattr(a, "no_gate", False) else None))


def cmd_from_md_course(a):
    """Build EVERY '## Microlearning N' in a .md into ONE multi-SCO SCORM course
    (N lessons sharing brand/+player/; the LMS shows a TOC over the lessons).

    NOTE: SCORM 1.2 has no manifest-level completion rollup, so whether finishing
    all lessons marks the COURSE complete is the LMS's default policy, not
    something this package guarantees. For real cross-lesson moveOn/rollup, build
    cmi5 (--format cmi5). The production model is one single-SCO package per unit,
    sequenced by the LMS in a Path — this multi-SCO path is not that."""
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
    b = brand.load_brand(getattr(a, "brand", "_default"))
    render.copy_shared(course_dir, b)                       # active brand + player/ once at the root
    scos, graded, passing, lang = [], False, 80, "en"
    agg_blocks, agg_assets, agg_warnings = 0, 0, []   # roll up per-unit stats for one course report
    unit_irs = []                                     # kept for the C20 cross-unit consistency sweep
    for k in range(1, n + 1):
        ir, used = import_md(a.md, which=k, image_dir=a.images)
        unit_irs.append(ir)
        blobs = {rel: open(src, "rb").read() for rel, src in used.items()}
        render.render_course(ir, os.path.join(course_dir, f"sco_{k}"), blobs,
                             asset_base="../", bundle_brand_player=False,
                             lesson_index=k, lesson_count=n, brand=b,
                             animate=not getattr(a, "no_animate", False),
                             gate=(False if getattr(a, "no_gate", False) else None))
        scos.append({"id": ir["id"], "title": ir["title"], "href": f"sco_{k}/index.html"})
        graded, passing, lang = ir.get("graded", False), ir.get("passingScore", 80), ir.get("locale", "en")
        _st = ir.get("_stats", {})
        agg_blocks += _st.get("blocks") or 0
        agg_assets += _st.get("assets") or 0
        agg_warnings += [f"unit {k}: {w}" for w in (_st.get("warnings") or [])]
    fmt = getattr(a, "format", "scorm")
    if fmt == "cmi5":
        cmi5.package_multi(course_dir, a.out, cid, title, scos, lang=lang, graded=graded, passing=passing,
                           id_base=b.get("cmi5IdBase"))
    elif fmt == "scorm2004":
        scorm.package_multi(course_dir, a.out, cid, title, scos, version="2004")
    else:
        scorm.package_multi(course_dir, a.out, cid, title, scos)
    print(f"✓ {title} — {n} lesson(s) [{fmt}]")
    for k, s in enumerate(scos, 1):
        print(f"    {k}. {s['title']}")
    print(f"  {fmt.upper()} (multi) → {a.out} ({os.path.getsize(a.out)//1024} KB)")
    if not a.keep_dir:
        shutil.rmtree(course_dir, ignore_errors=True)
    conf_errors, conf_warnings = ([], [])
    if getattr(a, "validate", False):
        conf_errors, conf_warnings = _run_lint(a.out)
    agg_ir = {"title": title, "_stats": {"blocks": agg_blocks, "assets": agg_assets,
                                         "warnings": agg_warnings}}
    import build_report
    from authoring import load_glossary
    cons = build_report.consistency_findings_course(
        unit_irs, glossary=load_glossary(getattr(a, "brand", "_default")))
    _write_report(agg_ir, a.out, lint_md=a.md, brand=b, consistency=cons,
                  conformance_errors=conf_errors, conformance_warnings=conf_warnings)
    if getattr(a, "validate", False) and conf_errors:
        raise SystemExit(f"✗ conformance lint failed for {a.out}")


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
    b = brand.load_brand(getattr(a, "brand", "_default"))
    ir, _copy, _src = import_rise(a.zip, brand=b)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(ir, f, indent=2, ensure_ascii=False)
    print(f"✓ IR → {a.out}  (blocks={ir['_stats']['blocks']}, "
          f"skipped={ir['_stats'].get('skipped')})")


def cmd_from_ir(a):
    """Rebuild a SCORM from an (edited) IR JSON + a folder of its assets."""
    ir = json.load(open(a.ir, encoding="utf-8"))
    import ir_validate
    ir = ir_validate.migrate(ir, label=ir.get("id", "course"))   # version gate + forward-compat seam
    ir_validate.validate_ir(ir, label=ir.get("id", "course"))
    blobs = {}
    if a.images and os.path.isdir(a.images):
        for n in os.listdir(a.images):
            fp = os.path.join(a.images, n)
            if os.path.isfile(fp):
                blobs["assets/" + n] = open(fp, "rb").read()
    _emit(ir, blobs, a.out, a.keep_dir, getattr(a, "validate", False), getattr(a, "format", "scorm"), getattr(a, "brand", "_default"))


def cmd_repackage(a):
    """Re-zip an (edited) course directory into SCORM — for direct HTML tweaks."""
    cid = a.id or os.path.splitext(os.path.basename(a.dir))[0]
    title = a.title or cid
    scorm.package(a.dir, a.out, cid, title)
    print(f"✓ repackaged {a.dir} → {a.out} ({os.path.getsize(a.out)//1024} KB)")


def cmd_lint(a):
    import scorm_lint
    raise SystemExit(scorm_lint.main(["scorm_lint", a.zip]))


def cmd_match_layout(a):
    """P4 'describe the slide': deterministically map a one-sentence intent to the
    best-fit deck layout(s) — no AI call. Prints the recommendation + any ranked
    alternatives; --json for machine output."""
    import authoring
    res = authoring.match_layout_from_intent(a.intent, allow_image_layouts=a.images)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    rec = res["recommended"]
    tag = "" if res["confident"] else \
        "   (low confidence — intent is vague; rephrase or let the generator choose)"
    print(f"→ {rec}: {authoring.LAYOUT_PURPOSE.get(rec, '')}{tag}")
    for r in res["ranked"][1:]:
        print(f"   · {r['layout']} (score {r['score']}: {', '.join(r['cues'])})")


def cmd_inspect_pptx(a):
    """Extract a foreign .pptx's design DNA (theme palette + fonts, slide size, layout
    inventory, per-slide shapes) to a JSON profile -- the first step of template
    ingestion. Read-only; never modifies the source."""
    import json
    import pptx_ingest
    profile = pptx_ingest.inspect_pptx(a.pptx)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(profile, fh, indent=2, ensure_ascii=False)
        pal = profile["theme"]["palette"]
        print(f"✓ inspected {os.path.basename(a.pptx)} → {a.out} "
              f"({profile['slide_count']} slides, {profile['layout_count']} layouts, "
              f"{len(pal)} theme colors)")
    else:
        print(json.dumps(profile, indent=2, ensure_ascii=False))


def cmd_roletag_pptx(a):
    """Tag one slide of a .pptx into a renderable region-spec (templates/layouts/<name>.json)
    -- template ingestion step 2c. The claude CLI classifies each shape's role; geometry
    and spec assembly are deterministic. Read-only on the source."""
    import json
    import pptx_ingest
    profile = pptx_ingest.inspect_pptx(a.pptx)
    name = a.name or profile.get("name") or "ingested"
    spec, err = pptx_ingest.roletag_slide(profile, index=a.slide, name=name,
                                          provider=a.provider,
                                          category=a.client or "default", brand=a.brand)
    if err:
        raise SystemExit(f"✗ role-tag failed: {err}")
    out = a.out
    if not out:
        layouts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   "templates", "layouts")
        os.makedirs(layouts_dir, exist_ok=True)
        out = os.path.join(layouts_dir, os.path.basename(name) + ".json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=2, ensure_ascii=False)
    print(f"✓ tagged slide {a.slide} of {os.path.basename(a.pptx)} → {out} "
          f"({len(spec['regions'])} regions)")


def cmd_translate(a):
    """Translate/localize a built course .md into a target language or locale, preserving
    the §8 block structure. One subscription-CLI pass per unit; reuses the brand glossary
    as a keep-verbatim term list; verifies the structure survived (M5)."""
    import authoring
    md = open(a.md, encoding="utf-8").read()
    res = authoring.translate_course(a.provider, md, a.target, brand=a.brand, model=a.model,
                                     use_tm=not getattr(a, "no_tm", False))
    if not res.get("ok"):
        raise SystemExit(f"✗ translate failed: {res.get('error')}")
    out = a.out
    if not out:
        base, ext = os.path.splitext(a.md)
        slug = re.sub(r"[^a-z0-9]+", "-", (a.target or "").lower()).strip("-") or "translated"
        out = f"{base}.{slug}{ext or '.md'}"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(res["out"])
    tag = "localized" if res.get("mode") == "localize" else "translated"
    print(f"✓ {tag} {res['units']} unit(s) → {out}")
    if res.get("tm_reused"):
        print(f"  ↺ {res['tm_reused']} unit(s) reused from translation memory (no re-review needed)")
    if res.get("pending_approval"):
        print(f"  ⧗ {res.get('tm_stored', 0)} new unit(s) stored PENDING approval — run "
              f"`tm approve \"{a.md}\" --target \"{a.target}\"` once reviewed to make them reusable")
    if not res.get("structure_ok", True):
        print("  ⚠ block structure drifted from the source:")
        for s in res.get("structure_issues", []):
            print(f"    - {s}")
    if not res.get("lint_ok", True):
        print("  ⚠ §8 lint issues in the output:")
        for s in res.get("lint_errors", []):
            print(f"    - {s}")


def cmd_tm(a):
    """C17 — translation-memory admin. `tm approve <src.md> --target X` runs the final
    approval step for a full translation (promotes its pending units to reusable);
    `tm list --target X` shows how many entries a target has."""
    import tm
    if a.action == "approve":
        if not a.src:
            raise SystemExit("tm approve needs a source course .md (--src or positional)")
        md = open(a.src, encoding="utf-8").read()
        n = tm.approve(a.target, md)
        print(f"✓ approved {n} pending unit(s) for “{a.target}” → now reusable from memory"
              if n else f"no pending units to approve for “{a.target}” (already approved, or none stored)")
    elif a.action == "list":
        data = tm.load(a.target)
        approved = sum(1 for e in data.values() if e.get("approved"))
        print(f"{a.target}: {len(data)} unit(s) in memory ({approved} approved, "
              f"{len(data) - approved} pending) → {tm.tm_path(a.target)}")


def cmd_captions(a):
    """M3 — generate local captions for a course's file-mode video/audio blocks.
    Transcribes each resolvable LOCAL media file with a local Whisper (faster-whisper
    or a whisper.cpp/openai-whisper binary), writes a sidecar .vtt next to it, and
    binds it onto the media line. Remote/embedded media is skipped; if no Whisper is
    installed, media is reported skipped-with-a-note (never silently dropped)."""
    import captions
    md_text = open(a.md, encoding="utf-8").read()
    base_dir = a.assets or os.path.dirname(os.path.abspath(a.md))
    new_md, report = captions.caption_markdown(md_text, base_dir, lang=a.lang,
                                               overwrite=a.overwrite)
    backend = captions.caption_backend()
    print(f"backend: {backend or 'none (skip-with-note — install faster-whisper)'}")
    for r in report:
        if r["status"] in ("written", "exists"):
            mark = "✓" if r["status"] == "written" else "•"
            print(f"  {mark} {r['src']} → {r['vtt']}")
        elif r["status"] == "bound":
            print(f"  • {r['src']} (already captioned)")
        else:
            print(f"  ⚠ {r['src']} skipped: {r.get('reason')}")
    wrote = any(r["status"] == "written" for r in report)
    binds = any(r["status"] in ("written", "exists") for r in report)
    if binds and new_md != md_text:
        with open(a.md, "w", encoding="utf-8") as fh:
            fh.write(new_md)
        print(f"✓ bound caption tracks into {a.md}")
    n_written = sum(r["status"] == "written" for r in report)
    print(f"{n_written} caption file(s) written." if wrote
          else "No new caption files written.")


def cmd_consistency(a):
    """C20 — check one appended unit against the rest of its course for term/voice
    drift. Imports the target unit and its siblings, runs the deterministic drift
    check (glossary-aware), and prints the findings. Non-blocking: this reports drift,
    it never changes the course."""
    import re as _re
    import build_report
    from md_import import import_md
    from authoring import load_glossary
    text = open(a.md, encoding="utf-8").read()
    n = len(_re.split(r'^##\s+Microlearning\s+', text, flags=_re.M)) - 1
    if n < 2:
        print(f"{a.md}: needs two or more '## Microlearning N' units to compare (found {n}).")
        return
    which = a.which or n                            # default: the last unit (the appended one)
    if which < 1 or which > n:
        raise SystemExit(f"--which {which} out of range (file has {n} unit(s))")
    new_ir, _ = import_md(a.md, which=which)
    prior = [import_md(a.md, which=k)[0] for k in range(1, n + 1) if k != which]
    findings = build_report.consistency_findings(
        new_ir, prior, glossary=load_glossary(a.brand))
    print(f"{a.md}: unit {which} of {n} vs the other {n - 1} —")
    if not findings:
        print("  ✓ no term/voice drift detected.")
        return
    for f in findings:
        print(f"  ⚠ [{f['check']}] {f['message']}")
    print(f"{len(findings)} consistency finding(s).")


def cmd_from_csv(a):
    """Bulk-generate courses from a manifest CSV (M6). One row per course; each row is an
    ordinary generate() call. --validate does a dry run (parse + per-row checks) and exits
    without generating. Continue-on-error otherwise: a bad row is reported, the batch goes on."""
    import authoring
    csv_text = open(a.csv, encoding="utf-8").read()
    rows, errors = authoring.parse_manifest(csv_text)
    if errors:
        for e in errors:
            print(f"✗ {e}")
        raise SystemExit(1)
    checks = authoring.validate_manifest(rows)
    bad = [c for c in checks if not c["ok"]]
    if a.validate:
        print(f"Manifest: {len(rows)} row(s), {len(rows) - len(bad)} ok, {len(bad)} with issues")
        for c in checks:
            mark = "✓" if c["ok"] else "✗"
            print(f"  {mark} row {c['row']}: {c['title']}"
                  + ("" if c["ok"] else "  — " + "; ".join(c["issues"])))
        raise SystemExit(1 if bad else 0)
    if bad:
        print(f"✗ {len(bad)} row(s) have issues — fix them or re-run with --validate to see all:")
        for c in bad:
            print(f"    row {c['row']}: {c['title']} — {'; '.join(c['issues'])}")
        raise SystemExit(1)
    res = authoring.generate_batch(a.provider, rows, a.out, brand=a.brand,
                                   on_row=lambda i, n, r: print(f"  [{i+1}/{n}] {r.get('title') or r.get('objective')}…"))
    print(f"✓ generated {res['ok_count']}/{res['n']} course(s) → {a.out}")
    for r in res["results"]:
        if r["ok"]:
            flag = "" if r.get("lint_ok", True) else "  ⚠ lint issues"
            print(f"  ✓ row {r['row']}: {r['title']} → {r['out']}{flag}")
        else:
            print(f"  ✗ row {r['row']}: {r['title']} — {r.get('error')}")
    if res["fail_count"]:
        raise SystemExit(1)


def cmd_to_pptx(a):
    """Render a microlearning to a STATIC PowerPoint deck.

    Reuses the from-md import path so image resolution is identical to a SCORM
    build, then walks the IR into slides. Interactive blocks are flattened or
    dropped (logged) -- see src/pptx_export.py for the mapping."""
    from md_import import import_md
    import pptx_export
    ir, used = import_md(a.md, which=a.which, hero=a.hero, image_dir=a.images)
    blobs = {rel: src for rel, src in used.items()}      # rel -> on-disk path
    b = brand.load_brand(getattr(a, "brand", "_default"))
    stats = pptx_export.export_pptx(
        ir, blobs, a.out, brand=b,
        transition=getattr(a, "transition", None),
        transition_dir=getattr(a, "transition_dir", None),
        transition_speed=getattr(a, "transition_speed", "med"))
    print(f"✓ {ir['title']}")
    print(f"  slides={stats['slides']} dropped={stats['dropped']}"
          + (f" transition={stats['transition']}" if stats.get('transition') else ""))
    print(f"  PPTX → {a.out} ({os.path.getsize(a.out)//1024} KB)")
    # build report (C1): the flatten's dropped-block set + lint + import warnings
    _write_report(ir, a.out, lint_md=a.md, dropped=stats.get("dropped"), brand=b)


def cmd_slide(a):
    """Render one standalone, on-brand slide from a JSON content file.

    A reusable slide-template target (separate from course IR), selected via
    --layout (see slide_layouts.LAYOUTS). Colors come from the active brand
    profile -- see src/slide_layouts.py for each layout's content schema."""
    import slide_layouts
    b = brand.load_brand(getattr(a, "brand", "_default"))
    stats = slide_layouts.export_slide_file(
        a.content, a.out, brand=b, layout=a.layout,
        transition=getattr(a, "transition", None),
        transition_dir=getattr(a, "transition_dir", None),
        transition_speed=getattr(a, "transition_speed", "med"),
        images_dir=getattr(a, "images", None),
        animate=getattr(a, "animate", None),
        animate_speed=getattr(a, "animate_speed", "med"))
    print(f"✓ slide ({stats['layout']}) → {a.out} ({os.path.getsize(a.out)//1024} KB)")
    extra = " ".join(f"{k}={v}" for k, v in stats.items() if k != "layout")
    if extra:
        print(f"  {extra}")


def cmd_deck(a):
    """Assemble a multi-slide, on-brand .pptx deck from a JSON deck file.

    The deck file is {"slides": [{"layout": <name>, "content": {...}}, ...]};
    each slide uses any slide_layouts layout. One transition applies deck-wide."""
    import slide_layouts, authoring
    b = brand.load_brand(getattr(a, "brand", "_default"))
    # default the image source to the brand's built-in library (on-brand template
    # imagery) when no folder is given, so `image:` slots resolve out of the box.
    images_dir = getattr(a, "images", None) or authoring.brand_image_dir(getattr(a, "brand", "_default"))
    if getattr(a, "format", "pptx") == "html":
        import json as _json, slide_svg
        with open(a.content, encoding="utf-8") as fh:
            deck = _json.load(fh)
        slides = deck.get("slides", deck) if isinstance(deck, dict) else deck
        title = getattr(a, "title", None) or os.path.splitext(os.path.basename(a.out))[0]
        html = slide_svg.render_deck_html(slides, b, images_dir=images_dir, title=title)
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(html)
        n = len(slides) if isinstance(slides, list) else 0
        print(f"✓ deck ({n} slides) → {a.out} ({os.path.getsize(a.out)//1024} KB, standalone HTML)")
        return
    stats = slide_layouts.export_deck_file(
        a.content, a.out, brand=b,
        transition=getattr(a, "transition", None),
        transition_dir=getattr(a, "transition_dir", None),
        transition_speed=getattr(a, "transition_speed", "med"),
        images_dir=images_dir,
        animate=getattr(a, "animate", None),
        animate_speed=getattr(a, "animate_speed", "med"))
    print(f"✓ deck ({stats['slides']} slides) → {a.out} ({os.path.getsize(a.out)//1024} KB)")
    print(f"  layouts: {', '.join(stats['layouts'])}")


def cmd_cover(a):
    """Composite cover/hero/mobile art (background + icon + title) for one course or a batch."""
    import cover
    from common import slugify
    b = brand.load_brand(getattr(a, "brand", "_default"))

    def resolve(folder_key, val):
        if not val:
            return None
        if os.path.isfile(val):
            return val
        d = b.asset(folder_key)                    # the brand's backgrounds/ or icons/ folder
        if d:
            for ext in ("", ".png", ".jpg", ".jpeg"):
                p = os.path.join(d, val + ext)
                if os.path.isfile(p):
                    return p
        print(f"  note: '{val}' not found as a file or in the brand's {folder_key}/ — synthesizing")
        return None

    if a.map:
        items = json.load(open(a.map, encoding="utf-8"))
    else:
        items = [{"name": a.name or slugify(a.title or "cover"), "title": a.title or "",
                  "background": a.bg, "icon": a.icon, "accent": a.accent,
                  "layout": a.layout, "subtitle": a.subtitle}]
    for it in items:
        name = it.get("name") or slugify(it.get("title") or "cover")
        out = cover.render_set(b, a.out, name, it.get("title", ""),
                               background=resolve("backgrounds", it.get("background")),
                               icon=resolve("icons", it.get("icon")), accent=it.get("accent"),
                               layout=it.get("layout"), subtitle=it.get("subtitle"))
        print(f"✓ {name}: " + " · ".join(f"{k} {os.path.basename(v)}" for k, v in out.items()))


def main():
    p = argparse.ArgumentParser(prog="course-builder")
    sub = p.add_subparsers(required=True)

    r = sub.add_parser("from-rise"); r.add_argument("zip")
    r.add_argument("--out", required=True); r.add_argument("--keep-dir", action="store_true")
    r.add_argument("--validate", action="store_true"); r.add_argument("--brand", default="_default")
    r.add_argument("--no-animate", action="store_true", help="disable entrance animations"); r.set_defaults(fn=cmd_from_rise)

    d = sub.add_parser("from-docx"); d.add_argument("docx")
    d.add_argument("--images", required=True); d.add_argument("--out", required=True)
    d.add_argument("--keep-dir", action="store_true")
    d.add_argument("--validate", action="store_true"); d.add_argument("--brand", default="_default")
    d.add_argument("--no-animate", action="store_true", help="disable entrance animations"); d.set_defaults(fn=cmd_from_docx)

    md = sub.add_parser("from-md"); md.add_argument("md")
    md.add_argument("--which", type=int, default=1); md.add_argument("--images", default=None)
    md.add_argument("--hero", default=None); md.add_argument("--out", required=True)
    md.add_argument("--keep-dir", action="store_true")
    md.add_argument("--format", choices=["scorm", "scorm2004", "cmi5"], default="scorm")
    md.add_argument("--validate", action="store_true"); md.add_argument("--brand", default="_default")
    md.add_argument("--no-animate", action="store_true", help="disable entrance animations")
    md.add_argument("--no-gate", action="store_true",
                    help="M13: don't block completion on a failing score (course completes regardless)")
    md.add_argument("--no-package", action="store_true",
                    help="render the HTML course dir only, skip the SCORM/cmi5 zip (preview)")
    md.set_defaults(fn=cmd_from_md)

    mc = sub.add_parser("from-md-course"); mc.add_argument("md")
    mc.add_argument("--images", default=None); mc.add_argument("--title", default=None)
    mc.add_argument("--out", required=True); mc.add_argument("--keep-dir", action="store_true")
    mc.add_argument("--format", choices=["scorm", "scorm2004", "cmi5"], default="scorm")
    mc.add_argument("--validate", action="store_true"); mc.add_argument("--brand", default="_default")
    mc.add_argument("--no-animate", action="store_true", help="disable entrance animations")
    mc.add_argument("--no-gate", action="store_true",
                    help="M13: don't block completion on a failing score (course completes regardless)")
    mc.set_defaults(fn=cmd_from_md_course)

    gp = sub.add_parser("gen-prompts"); gp.add_argument("md")
    gp.add_argument("--which", type=int, default=1); gp.add_argument("--hero", default=None)
    gp.add_argument("--hierarchy", default=None); gp.add_argument("--out", default=None)
    gp.add_argument("--manifest", default=None, help="also write a re-rollable image_prompts.json here")
    gp.set_defaults(fn=cmd_gen_prompts)

    i = sub.add_parser("import-rise"); i.add_argument("zip")
    i.add_argument("--out", required=True); i.add_argument("--brand", default="_default")
    i.set_defaults(fn=cmd_import_rise)

    fi = sub.add_parser("from-ir"); fi.add_argument("ir")
    fi.add_argument("--images", default=None); fi.add_argument("--out", required=True)
    fi.add_argument("--keep-dir", action="store_true")
    fi.add_argument("--format", choices=["scorm", "scorm2004", "cmi5"], default="scorm")
    fi.add_argument("--validate", action="store_true"); fi.add_argument("--brand", default="_default"); fi.set_defaults(fn=cmd_from_ir)

    rp = sub.add_parser("repackage"); rp.add_argument("dir")
    rp.add_argument("--out", required=True); rp.add_argument("--id", default=None)
    rp.add_argument("--title", default=None); rp.set_defaults(fn=cmd_repackage)

    ln = sub.add_parser("lint"); ln.add_argument("zip")
    ln.set_defaults(fn=cmd_lint)

    ip = sub.add_parser("inspect-pptx",
        help="extract a .pptx's design DNA (theme/fonts/layouts/shapes) to a JSON profile")
    ip.add_argument("pptx")
    ip.add_argument("--out", default=None, help="write the profile JSON here (default: stdout)")
    ip.set_defaults(fn=cmd_inspect_pptx)

    rt = sub.add_parser("roletag-pptx",
        help="tag one .pptx slide into a reusable region-spec (templates/layouts/<name>.json)")
    rt.add_argument("pptx")
    rt.add_argument("--slide", type=int, default=0, help="slide index to tag (default: 0)")
    rt.add_argument("--name", default=None, help="template name (default: the .pptx stem)")
    rt.add_argument("--provider", default="claude", help="AI provider for role tagging")
    rt.add_argument("--client", default=None,
        help="tag as client-specific (picker group), e.g. TeleTracking; default: generic")
    rt.add_argument("--brand", default=None,
        help="default brand for a client-specific template (auto-selected when picked)")
    rt.add_argument("--out", default=None,
        help="write the spec here (default: templates/layouts/<name>.json)")
    rt.set_defaults(fn=cmd_roletag_pptx)

    tr = sub.add_parser("translate",
        help="translate/localize a built course .md into another language or locale, preserving §8 structure")
    tr.add_argument("md")
    tr.add_argument("--target", required=True,
        help="target language or locale (e.g. Spanish, es, fr; en-GB/UK for localization)")
    tr.add_argument("--provider", default="claude", help="AI provider (subscription CLI)")
    tr.add_argument("--model", default=None)
    tr.add_argument("--brand", default=None,
        help="brand whose glossary supplies the keep-verbatim product terms")
    tr.add_argument("--out", default=None, help="output .md (default: <md>.<target>.md)")
    tr.add_argument("--no-tm", action="store_true",
        help="C17: don't reuse or write the translation memory for this run")
    tr.set_defaults(fn=cmd_translate)

    tm_p = sub.add_parser("tm",
        help="C17: translation-memory admin (approve full translations, list a target's memory)")
    tm_p.add_argument("action", choices=["approve", "list"])
    tm_p.add_argument("src", nargs="?", default=None, help="source course .md (for approve)")
    tm_p.add_argument("--target", required=True, help="target language/locale the memory is keyed to")
    tm_p.set_defaults(fn=cmd_tm)

    cp = sub.add_parser("captions",
        help="generate local captions (.vtt) for a course's file-mode video/audio via local Whisper")
    cp.add_argument("md", help="course .md whose media blocks to caption")
    cp.add_argument("--assets", default=None,
        help="base dir for resolving relative media srcs (default: the .md's folder)")
    cp.add_argument("--lang", default="en", help="caption language code (default: en)")
    cp.add_argument("--overwrite", action="store_true",
        help="re-transcribe and rebind even where a sidecar / captions opt already exists")
    cp.set_defaults(fn=cmd_captions)

    cc = sub.add_parser("consistency",
        help="C20: check an appended unit against the rest of a course for term/voice drift")
    cc.add_argument("md", help="course .md with two or more '## Microlearning N' units")
    cc.add_argument("--which", type=int, default=None,
        help="the appended unit to check (1-based; default: the last unit)")
    cc.add_argument("--brand", default="_default",
        help="brand whose glossary supplies the approved-term guard")
    cc.set_defaults(fn=cmd_consistency)

    fc = sub.add_parser("from-csv",
        help="bulk-generate courses from a manifest CSV (one row per course), reusing generate()")
    fc.add_argument("csv", help="manifest CSV: columns objective, audience, source (required) + "
                                "optional title, archetype, units, urls, preset, brand")
    fc.add_argument("--out", required=True, help="output folder for the generated <slug>.md courses")
    fc.add_argument("--provider", default="claude", help="AI provider (subscription CLI)")
    fc.add_argument("--brand", default=None, help="default brand glossary (a row's brand column overrides)")
    fc.add_argument("--validate", action="store_true",
        help="dry run: check every row (archetype, source, required fields) and report, generate nothing")
    fc.set_defaults(fn=cmd_from_csv)

    pp = sub.add_parser("to-pptx"); pp.add_argument("md")
    pp.add_argument("--which", type=int, default=1); pp.add_argument("--images", default=None)
    pp.add_argument("--hero", default=None); pp.add_argument("--out", required=True)
    pp.add_argument("--brand", default="_default")
    pp.add_argument("--transition", default=None,
        help="slide transition applied to every slide: none|fade|cut|push|wipe|split|cover")
    pp.add_argument("--transition-dir", default=None, help="direction for push/wipe/cover: l|r|u|d")
    pp.add_argument("--transition-speed", default="med", help="slow|med|fast")
    pp.set_defaults(fn=cmd_to_pptx)

    sl = sub.add_parser("slide"); sl.add_argument("--content", required=True)
    sl.add_argument("--layout", default="infographic"); sl.add_argument("--out", required=True)
    sl.add_argument("--brand", default="_default")
    sl.add_argument("--images", default=None, help="folder that holds image files referenced by `image:`")
    sl.add_argument("--transition", default=None,
        help="slide transition: none|fade|cut|push|wipe|split|cover")
    sl.add_argument("--transition-dir", default=None, help="direction for push/wipe/cover: l|r|u|d")
    sl.add_argument("--transition-speed", default="med", help="slow|med|fast")
    sl.add_argument("--animate", default=None, help="entrance animation: none|fade|rise|flyleft|flyright")
    sl.add_argument("--animate-speed", default="med", help="slow|med|fast")
    sl.set_defaults(fn=cmd_slide)

    dk = sub.add_parser("deck"); dk.add_argument("--content", required=True)
    dk.add_argument("--out", required=True); dk.add_argument("--brand", default="_default")
    dk.add_argument("--images", default=None, help="folder that holds image files referenced by `image:`")
    dk.add_argument("--transition", default=None,
        help="transition applied to every slide: none|fade|cut|push|wipe|split|cover")
    dk.add_argument("--transition-dir", default=None, help="direction for push/wipe/cover: l|r|u|d")
    dk.add_argument("--transition-speed", default="med", help="slow|med|fast")
    dk.add_argument("--animate", default=None, help="entrance animation per slide: none|fade|rise|flyleft|flyright")
    dk.add_argument("--animate-speed", default="med", help="slow|med|fast")
    dk.add_argument("--format", choices=["pptx", "html"], default="pptx",
        help="pptx = editable PowerPoint deck (default); html = standalone, self-contained interactive slideshow that opens offline")
    dk.add_argument("--title", default=None, help="presentation title shown in the html deck (defaults to the output filename)")
    dk.set_defaults(fn=cmd_deck)

    cv = sub.add_parser("cover")
    cv.add_argument("--title", default=None); cv.add_argument("--name", default=None)
    cv.add_argument("--bg", default=None); cv.add_argument("--icon", default=None)
    cv.add_argument("--accent", default=None); cv.add_argument("--map", default=None,
        help="JSON list of {name,title,subtitle,background,icon,accent,layout} for a batch")
    cv.add_argument("--layout", default=None, choices=["topic", "path"],
        help="cover layout (default: brand's cover.layout)")
    cv.add_argument("--subtitle", default=None, help="audience/subtitle line (path layout)")
    cv.add_argument("--out", required=True, help="output directory")
    cv.add_argument("--brand", default="_default"); cv.set_defaults(fn=cmd_cover)

    ml = sub.add_parser("match-layout",
        help="P4: map a one-sentence slide intent to the best-fit deck layout (deterministic, no AI)")
    ml.add_argument("intent",
        help="plain-English description of what the slide should do, e.g. \"compare the 3 deployment models\"")
    ml.add_argument("--images", action="store_true",
        help="also consider the image/imagetext layouts (an images folder is available)")
    ml.add_argument("--json", action="store_true", help="emit the full ranked result as JSON")
    ml.set_defaults(fn=cmd_match_layout)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
