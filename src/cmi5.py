"""Wrap a rendered course directory into a cmi5 package (.zip).

cmi5 is the modern, xAPI-based successor to SCORM for LMS-launched courses. The
runtime (player.js) detects a cmi5 launch and reports via xAPI statements to the
LRS; here we only emit the `cmi5.xml` course structure and zip the content.
Mirrors scorm.py's single (`package`) / multi-AU (`package_multi`) split and the
same shared-asset directory layout (brand/+player/ at the root, sco_k/ per lesson).
"""
import os, zipfile
from xml.sax.saxutils import escape, quoteattr

ID_BASE = "https://teletracking.example/cmi5"   # identifier IRIs (not resolvable URLs)
MOVEON = {True: "CompletedAndPassed", False: "Completed"}

COURSE_TMPL = """<?xml version="1.0" encoding="UTF-8"?>
<courseStructure xmlns="https://w3id.org/xapi/profiles/cmi5/v1/CourseStructure.xsd"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <course id={cid}>
    <title><langstring lang="{lang}">{title}</langstring></title>
    <description><langstring lang="{lang}">{title}</langstring></description>
  </course>
{aus}
</courseStructure>
"""

AU_TMPL = """  <au id={au} moveOn="{moveon}"{mastery}>
    <title><langstring lang="{lang}">{title}</langstring></title>
    <description><langstring lang="{lang}">{title}</langstring></description>
    <url>{url}</url>
  </au>"""


def _au(course_id, k, title, url, lang, graded, passing):
    mastery = ' masteryScore="%.4f"' % (max(0, min(100, passing)) / 100.0) if graded else ""
    return AU_TMPL.format(au=quoteattr("%s/%s/au/%d" % (ID_BASE, course_id, k)),
                          moveon=MOVEON[graded], mastery=mastery,
                          lang=lang, title=escape(title), url=escape(url))


def _all_files(course_dir):
    for base, _dirs, names in os.walk(course_dir):
        for n in names:
            full = os.path.join(base, n)
            rel = os.path.relpath(full, course_dir).replace(os.sep, "/")
            if rel == "cmi5.xml":          # we (re)write our own; never double-add
                continue
            yield full, rel


def _write_pif(course_dir, out_zip, xml, files):
    with open(os.path.join(course_dir, "cmi5.xml"), "w", encoding="utf-8") as f:
        f.write(xml)
    os.makedirs(os.path.dirname(os.path.abspath(out_zip)), exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(course_dir, "cmi5.xml"), "cmi5.xml")
        for full, rel in files:
            z.write(full, rel)
    return out_zip


def package(course_dir, out_zip, course_id, title, lang="en", graded=False, passing=80):
    """Single-AU cmi5 package (one lesson at index.html)."""
    files = list(_all_files(course_dir))
    aus = _au(course_id, 1, title, "index.html", lang, graded, passing)
    xml = COURSE_TMPL.format(cid=quoteattr("%s/%s" % (ID_BASE, course_id)),
                             lang=lang, title=escape(title), aus=aus)
    return _write_pif(course_dir, out_zip, xml, files)


def package_multi(course_dir, out_zip, course_id, title, aus, lang="en", graded=False, passing=80):
    """Multi-AU cmi5 package. aus = [{title, href}] (href like 'sco_1/index.html')."""
    files = list(_all_files(course_dir))
    au_xml = "\n".join(_au(course_id, k, a["title"], a["href"], lang, graded, passing)
                       for k, a in enumerate(aus, 1))
    xml = COURSE_TMPL.format(cid=quoteattr("%s/%s" % (ID_BASE, course_id)),
                             lang=lang, title=escape(title), aus=au_xml)
    return _write_pif(course_dir, out_zip, xml, files)
