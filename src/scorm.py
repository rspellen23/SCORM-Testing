"""Wrap a rendered course directory into a SCORM 1.2 package (.zip).

Runtime supports both SCORM 1.2 and 2004 (player.js detects API/API_1484_11);
the manifest declares 1.2, which is the broadly-accepted, widely-validated target.
"""
import os, zipfile
from xml.sax.saxutils import escape

SCHEMA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scorm_schema")
# Controlling documents bundled at the PIF root for strict-conformance LMSes / the ADL test suite.
SCHEMA_FILES = ("imscp_rootv1p1p2.xsd", "adlcp_rootv1p2.xsd", "ims_xml.xsd", "imsmd_rootv1p2p1.xsd")

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


def _write_pif(course_dir, out_zip, manifest, files):
    """Write the manifest into the dir, then zip manifest + files + controlling XSDs."""
    with open(os.path.join(course_dir, "imsmanifest.xml"), "w", encoding="utf-8") as f:
        f.write(manifest)
    os.makedirs(os.path.dirname(os.path.abspath(out_zip)), exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(course_dir, "imsmanifest.xml"), "imsmanifest.xml")
        for full, rel in files:
            z.write(full, rel)
        for xsd in SCHEMA_FILES:                       # controlling documents at PIF root
            src = os.path.join(SCHEMA_DIR, xsd)
            if os.path.exists(src):
                z.write(src, xsd)
    return out_zip


def package(course_dir, out_zip, course_id, title):
    """Single-SCO package: one organization, one item, one SCO at index.html."""
    files = list(_all_files(course_dir))
    manifest = MANIFEST.format(id=escape(course_id), title=escape(title),
                               files=_file_tags(rel for _f, rel in files))
    return _write_pif(course_dir, out_zip, manifest, files)


def package_multi(course_dir, out_zip, course_id, title, scos):
    """Multi-SCO package: N lessons as N items/SCOs that share one asset resource
    (brand/ + player/ at the root). scos = [{id, title, href}], href like
    'sco_1/index.html'. Each SCO's local files (its index.html + assets/) ride on
    its own resource; the shared brand/player ride on RES-SHARED via <dependency>."""
    cid = escape(course_id)
    files = list(_all_files(course_dir))
    shared = [rel for _f, rel in files if rel.startswith(("brand/", "player/"))]

    items, resources = [], []
    for k, sco in enumerate(scos, 1):
        folder = sco["href"].rsplit("/", 1)[0] + "/"            # e.g. "sco_1/"
        local = [rel for _f, rel in files if rel.startswith(folder)]
        rid = f"RES-{cid}-{k}"
        items.append(f'      <item identifier="ITEM-{cid}-{k}" identifierref="{rid}" isvisible="true">'
                     f'<title>{escape(sco["title"])}</title></item>')
        resources.append(
            f'    <resource identifier="{rid}" type="webcontent" adlcp:scormtype="sco" href="{escape(sco["href"])}">\n'
            f'{_file_tags(local)}\n'
            f'      <dependency identifierref="RES-{cid}-SHARED"/>\n'
            f'    </resource>')
    resources.append(
        f'    <resource identifier="RES-{cid}-SHARED" type="webcontent" adlcp:scormtype="asset">\n'
        f'{_file_tags(shared)}\n'
        f'    </resource>')

    manifest = MANIFEST_MULTI.format(id=cid, title=escape(title),
                                     items="\n".join(items), resources="\n".join(resources))
    return _write_pif(course_dir, out_zip, manifest, files)
