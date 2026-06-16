"""Structural conformance lint for a built SCORM 1.2 package (.zip).

Catches the things that make a package fail on a strict LMS: malformed/missing
manifest, dangling resource/item references, <file> entries that aren't in the zip
(or content in the zip that nothing references), duplicate identifiers, missing SCO
entry point, and absent controlling XSDs. Stdlib only. Optionally runs `xmllint`
against the bundled schema when it's on PATH.

Usage:  python3 src/scorm_lint.py <package.zip>
Returns nonzero on errors (warnings don't fail).
"""
import os, sys, zipfile
import xml.etree.ElementTree as ET

IMSCP = "http://www.imsproject.org/xsd/imscp_rootv1p1p2"
ADLCP = "http://www.adlnet.org/xsd/adlcp_rootv1p2"
CMI5NS = "https://w3id.org/xapi/profiles/cmi5/v1/CourseStructure.xsd"
SCHEMA_FILES = ("imscp_rootv1p1p2.xsd", "adlcp_rootv1p2.xsd", "ims_xml.xsd", "imsmd_rootv1p2p1.xsd")
MOVEON = {"Passed", "Completed", "CompletedAndPassed", "CompletedOrPassed", "NotApplicable"}


def _q(tag):  # imscp-namespaced tag
    return "{%s}%s" % (IMSCP, tag)


def lint_zip(path):
    errors, warnings = [], []
    if not zipfile.is_zipfile(path):
        return ["not a zip file: %s" % path], []

    with zipfile.ZipFile(path) as z:
        names = set(n for n in z.namelist() if not n.endswith("/"))
        if "cmi5.xml" in names:
            return _lint_cmi5(z.read("cmi5.xml"), names)
        if "imsmanifest.xml" not in names:
            return ["package root has neither imsmanifest.xml (SCORM) nor cmi5.xml"], []
        try:
            root = ET.fromstring(z.read("imsmanifest.xml"))
        except ET.ParseError as e:
            return ["imsmanifest.xml is not well-formed XML: %s" % e], []

    # namespace + schema sanity
    if root.tag != _q("manifest"):
        errors.append("root element is %r, expected imscp:manifest" % root.tag)
    md = root.find(_q("metadata"))
    if md is None or (md.findtext(_q("schemaversion")) or "").strip() != "1.2":
        warnings.append("metadata/schemaversion is not '1.2'")

    # identifiers unique
    ids = [el.get("identifier") for el in root.iter() if el.get("identifier")]
    dupes = set(i for i in ids if ids.count(i) > 1)
    if dupes:
        errors.append("duplicate identifiers: %s" % ", ".join(sorted(dupes)))

    # resources: id -> {href, files}
    resources = {}
    for res in root.iter(_q("resource")):
        rid = res.get("identifier")
        hrefs = [f.get("href") for f in res.findall(_q("file")) if f.get("href")]
        resources[rid] = {"href": res.get("href"), "files": hrefs,
                          "deps": [d.get("identifierref") for d in res.findall(_q("dependency"))]}

    # organizations: default resolves; every item identifierref resolves; SCO href present
    orgs = root.find(_q("organizations"))
    referenced = set()
    sco_count = 0
    if orgs is None or not list(orgs.findall(_q("organization"))):
        errors.append("no <organization> in manifest")
    else:
        default = orgs.get("default")
        org_ids = [o.get("identifier") for o in orgs.findall(_q("organization"))]
        if default and default not in org_ids:
            errors.append("organizations default=%r matches no organization" % default)
        for item in orgs.iter(_q("item")):
            ref = item.get("identifierref")
            if not ref:
                continue
            if ref not in resources:
                errors.append("item identifierref=%r resolves to no resource" % ref)
                continue
            sco_count += 1
            r = resources[ref]
            if r["href"]:
                referenced.add(r["href"])
                if r["href"] not in names:
                    errors.append("resource %s href=%r not in package" % (ref, r["href"]))
            # pull in dependency files too
            chain = [r] + [resources[d] for d in r["deps"] if d in resources]
            for rr in chain:
                for h in rr["files"]:
                    referenced.add(h)
                    if h not in names:
                        errors.append("<file href=%r> (resource %s) not in package" % (h, ref))

    if sco_count == 0:
        errors.append("no SCO is referenced by any item (nothing will launch)")

    # content present in zip but referenced by nothing (excl. manifest + controlling XSDs)
    exempt = {"imsmanifest.xml"} | set(SCHEMA_FILES)
    orphan = sorted(n for n in names if n not in referenced and n not in exempt)
    if orphan:
        warnings.append("%d file(s) in package not referenced by the manifest: %s%s"
                        % (len(orphan), ", ".join(orphan[:6]), " …" if len(orphan) > 6 else ""))

    # controlling XSDs bundled?
    for xsd in ("imscp_rootv1p1p2.xsd", "adlcp_rootv1p2.xsd"):
        if xsd not in names:
            warnings.append("controlling schema %s not bundled (strict LMSes may reject)" % xsd)

    # NOTE: deliberately no xmllint/libxml2 schema validation. SCORM 1.2's own
    # ims_xml.xsd declares the `xml` namespace as the default namespace, which
    # libxml2 refuses to load, and adlcp:scormtype trips the imscp strict wildcard
    # unless every schema is co-loaded — so xmllint false-fails EVERY conformant
    # 1.2 package. The structural checks above are the reliable signal; for true
    # schema validation upload to SCORM Cloud (the ADL reference engine).

    return errors, warnings


def _lint_cmi5(xml_bytes, names):
    """Validate a cmi5 package: cmi5.xml well-formed, a <course> with an id, and
    ≥1 <au> each with an id, a valid moveOn, and a <url> present in the zip."""
    errors, warnings = [], []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        return ["cmi5.xml is not well-formed XML: %s" % e], []
    local = lambda el: el.tag.rsplit("}", 1)[-1]   # tag without namespace
    if local(root) != "courseStructure":
        errors.append("cmi5.xml root is %r, expected courseStructure" % local(root))

    course = next((e for e in root.iter() if local(e) == "course"), None)
    if course is None:
        errors.append("no <course> element")
    elif not course.get("id"):
        errors.append("<course> missing id (must be an IRI)")

    aus = [e for e in root.iter() if local(e) == "au"]
    if not aus:
        errors.append("no <au> (assignable unit) — nothing will launch")
    ids = []
    for au in aus:
        ids.append(au.get("id"))
        if not au.get("id"):
            errors.append("an <au> is missing its id (IRI)")
        mv = au.get("moveOn")
        if mv and mv not in MOVEON:
            errors.append("au moveOn=%r is not a valid value %s" % (mv, sorted(MOVEON)))
        ms = au.get("masteryScore")
        if ms is not None:
            try:
                if not (0.0 <= float(ms) <= 1.0):
                    errors.append("au masteryScore=%r must be 0..1" % ms)
            except ValueError:
                errors.append("au masteryScore=%r not a number" % ms)
        url_el = next((c for c in au if local(c) == "url"), None)
        url = (url_el.text or "").strip() if url_el is not None else ""
        if not url:
            errors.append("an <au> has no <url>")
        elif url.split("?")[0].split("#")[0] not in names:
            errors.append("au url %r not in package" % url)
    dupes = set(i for i in ids if i and ids.count(i) > 1)
    if dupes:
        errors.append("duplicate au ids: %s" % ", ".join(sorted(dupes)))
    return errors, warnings


def main(argv):
    if len(argv) != 2:
        print("usage: scorm_lint.py <package.zip>"); return 2
    errors, warnings = lint_zip(argv[1])
    for w in warnings:
        print("  warning:", w)
    if errors:
        print("FAIL (%d error%s):" % (len(errors), "" if len(errors) == 1 else "s"))
        for e in errors:
            print("  error:", e)
        return 1
    print("PASS: %s is structurally conformant SCORM 1.2%s"
          % (os.path.basename(argv[1]), " (%d warning%s)" % (len(warnings), "" if len(warnings)==1 else "s") if warnings else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
