"""Wrap a rendered course directory into a SCORM package (.zip).

Two packaging targets, selected by `version`:
  - "1.2"  (default) — the broadly-accepted, widely-validated 1.2 manifest.
  - "2004" — SCORM 2004 4th Edition (imscp_v1p1 + adlcp/adlseq/adlnav/imsss).

The player runtime has always been 2004-ready (player.js detects
API_1484_11); this module now emits a matching 2004 PIF when asked. The 1.2
path is unchanged — a 1.2 build is byte-for-byte what it was before.
"""
import os, zipfile
from xml.sax.saxutils import escape

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_DIR = os.path.join(_ROOT, "scorm_schema")
# Controlling documents bundled at the PIF root for strict-conformance LMSes / the ADL test suite.
SCHEMA_FILES = ("imscp_rootv1p1p2.xsd", "adlcp_rootv1p2.xsd", "ims_xml.xsd", "imsmd_rootv1p2p1.xsd")

# SCORM 2004 4th Edition controlling documents. Bundled IF present (mirrors the
# 1.2 present-or-skip rule): drop the ADL CAM/SN/RTE .xsd set into scorm2004_schema/
# to satisfy strict LMSes — an absent bundle still produces a lint-PASS package
# (with a "controlling schema not bundled" warning), same as 1.2.
SCHEMA_DIR_2004 = os.path.join(_ROOT, "scorm2004_schema")
SCHEMA_FILES_2004 = ("imscp_v1p1.xsd", "adlcp_v1p3.xsd", "adlseq_v1p3.xsd",
                     "adlnav_v1p3.xsd", "imsss_v1p0.xsd")

MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="MANIFEST-{id}" version="1.2"
  xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.imsproject.org/xsd/imscp_rootv1p1p2 imscp_rootv1p1p2.xsd
                      http://www.adlnet.org/xsd/adlcp_rootv1p2 adlcp_rootv1p2.xsd">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>1.2</schemaversion>
  </metadata>
  <organizations default="ORG-{id}">
    <organization identifier="ORG-{id}">
      <title>{title}</title>
      <item identifier="ITEM-{id}" identifierref="RES-{id}" isvisible="true">
        <title>{title}</title>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="RES-{id}" type="webcontent" adlcp:scormtype="sco" href="index.html">
{files}
    </resource>
  </resources>
</manifest>
"""

MANIFEST_MULTI = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="MANIFEST-{id}" version="1.2"
  xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.imsproject.org/xsd/imscp_rootv1p1p2 imscp_rootv1p1p2.xsd
                      http://www.adlnet.org/xsd/adlcp_rootv1p2 adlcp_rootv1p2.xsd">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>1.2</schemaversion>
  </metadata>
  <organizations default="ORG-{id}">
    <organization identifier="ORG-{id}">
      <title>{title}</title>
{items}
    </organization>
  </organizations>
  <resources>
{resources}
  </resources>
</manifest>
"""

# --- SCORM 2004 4th Edition ---------------------------------------------------
# Differences from 1.2 that matter for an LMS: the default namespace is
# imscp_v1p1 (not imsproject imscp_rootv1p1p2); adlcp is v1p3; the SCO marker is
# adlcp:scormType with a CAPITAL T (1.2 uses lowercase scormtype); and the
# adlseq/adlnav/imsss sequencing namespaces are declared (we emit no sequencing
# rules, which is valid — the LMS applies its default rollup).
MANIFEST_2004 = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="MANIFEST-{id}" version="1"
  xmlns="http://www.imsglobal.org/xsd/imscp_v1p1"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_v1p3"
  xmlns:adlseq="http://www.adlnet.org/xsd/adlseq_v1p3"
  xmlns:adlnav="http://www.adlnet.org/xsd/adlnav_v1p3"
  xmlns:imsss="http://www.imsglobal.org/xsd/imsss"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.imsglobal.org/xsd/imscp_v1p1 imscp_v1p1.xsd
                      http://www.adlnet.org/xsd/adlcp_v1p3 adlcp_v1p3.xsd
                      http://www.adlnet.org/xsd/adlseq_v1p3 adlseq_v1p3.xsd
                      http://www.adlnet.org/xsd/adlnav_v1p3 adlnav_v1p3.xsd
                      http://www.imsglobal.org/xsd/imsss imsss_v1p0.xsd">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>2004 4th Edition</schemaversion>
  </metadata>
  <organizations default="ORG-{id}">
    <organization identifier="ORG-{id}">
      <title>{title}</title>
      <item identifier="ITEM-{id}" identifierref="RES-{id}">
        <title>{title}</title>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="RES-{id}" type="webcontent" adlcp:scormType="sco" href="index.html">
{files}
    </resource>
  </resources>
</manifest>
"""

MANIFEST_MULTI_2004 = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="MANIFEST-{id}" version="1"
  xmlns="http://www.imsglobal.org/xsd/imscp_v1p1"
  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_v1p3"
  xmlns:adlseq="http://www.adlnet.org/xsd/adlseq_v1p3"
  xmlns:adlnav="http://www.adlnet.org/xsd/adlnav_v1p3"
  xmlns:imsss="http://www.imsglobal.org/xsd/imsss"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.imsglobal.org/xsd/imscp_v1p1 imscp_v1p1.xsd
                      http://www.adlnet.org/xsd/adlcp_v1p3 adlcp_v1p3.xsd
                      http://www.adlnet.org/xsd/adlseq_v1p3 adlseq_v1p3.xsd
                      http://www.adlnet.org/xsd/adlnav_v1p3 adlnav_v1p3.xsd
                      http://www.imsglobal.org/xsd/imsss imsss_v1p0.xsd">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>2004 4th Edition</schemaversion>
  </metadata>
  <organizations default="ORG-{id}">
    <organization identifier="ORG-{id}">
      <title>{title}</title>
{items}
    </organization>
  </organizations>
  <resources>
{resources}
  </resources>
</manifest>
"""


def _all_files(course_dir):
    for base, _dirs, names in os.walk(course_dir):
        for n in names:
            full = os.path.join(base, n)
            rel = os.path.relpath(full, course_dir).replace(os.sep, "/")
            if rel == "imsmanifest.xml":   # we (re)write our own; never double-add
                continue
            yield full, rel


def _file_tags(rels, indent="      "):
    return "\n".join('%s<file href="%s"/>' % (indent, escape(rel)) for rel in rels)


def _schema_set(version):
    """(schema_dir, schema_files) for the requested SCORM version."""
    if version == "2004":
        return SCHEMA_DIR_2004, SCHEMA_FILES_2004
    return SCHEMA_DIR, SCHEMA_FILES


def _write_pif(course_dir, out_zip, manifest, files, version="1.2"):
    """Write the manifest into the dir, then zip manifest + files + controlling XSDs."""
    schema_dir, schema_files = _schema_set(version)
    with open(os.path.join(course_dir, "imsmanifest.xml"), "w", encoding="utf-8") as f:
        f.write(manifest)
    os.makedirs(os.path.dirname(os.path.abspath(out_zip)), exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(course_dir, "imsmanifest.xml"), "imsmanifest.xml")
        for full, rel in files:
            z.write(full, rel)
        for xsd in schema_files:                       # controlling documents at PIF root
            src = os.path.join(schema_dir, xsd)
            if os.path.exists(src):
                z.write(src, xsd)
    return out_zip


def package(course_dir, out_zip, course_id, title, version="1.2"):
    """Single-SCO package: one organization, one item, one SCO at index.html.
    version="1.2" (default) or "2004" (SCORM 2004 4th Edition)."""
    files = list(_all_files(course_dir))
    template = MANIFEST_2004 if version == "2004" else MANIFEST
    manifest = template.format(id=escape(course_id), title=escape(title),
                               files=_file_tags(rel for _f, rel in files))
    return _write_pif(course_dir, out_zip, manifest, files, version)


def package_multi(course_dir, out_zip, course_id, title, scos, version="1.2"):
    """Multi-SCO package: N lessons as N items/SCOs that share one asset resource
    (brand/ + player/ at the root). scos = [{id, title, href}], href like
    'sco_1/index.html'. Each SCO's local files (its index.html + assets/) ride on
    its own resource; the shared brand/player ride on RES-SHARED via <dependency>.
    version="1.2" (default) or "2004" (SCORM 2004 4th Edition)."""
    cid = escape(course_id)
    files = list(_all_files(course_dir))
    shared = [rel for _f, rel in files if rel.startswith(("brand/", "player/"))]
    # 2004 uses adlcp:scormType (capital T); 1.2 uses scormtype.
    stype = "scormType" if version == "2004" else "scormtype"

    items, resources = [], []
    for k, sco in enumerate(scos, 1):
        folder = sco["href"].rsplit("/", 1)[0] + "/"            # e.g. "sco_1/"
        local = [rel for _f, rel in files if rel.startswith(folder)]
        rid = f"RES-{cid}-{k}"
        items.append(f'      <item identifier="ITEM-{cid}-{k}" identifierref="{rid}" isvisible="true">'
                     f'<title>{escape(sco["title"])}</title></item>')
        resources.append(
            f'    <resource identifier="{rid}" type="webcontent" adlcp:{stype}="sco" href="{escape(sco["href"])}">\n'
            f'{_file_tags(local)}\n'
            f'      <dependency identifierref="RES-{cid}-SHARED"/>\n'
            f'    </resource>')
    resources.append(
        f'    <resource identifier="RES-{cid}-SHARED" type="webcontent" adlcp:{stype}="asset">\n'
        f'{_file_tags(shared)}\n'
        f'    </resource>')

    template = MANIFEST_MULTI_2004 if version == "2004" else MANIFEST_MULTI
    manifest = template.format(id=cid, title=escape(title),
                               items="\n".join(items), resources="\n".join(resources))
    return _write_pif(course_dir, out_zip, manifest, files, version)
