"""Q4 — SCORM 2004 4th Edition packaging.

Mirrors test_scorm_manifest.py but exercises the new `version="2004"` path on
scorm.package / scorm.package_multi: the 2004 manifest namespaces + scormType,
that scorm_lint accepts it, and — critically — that the default 1.2 path is
UNCHANGED (same namespace, lowercase scormtype, schemaversion 1.2).
"""
import os
import zipfile
import xml.etree.ElementTree as ET

import pytest

import brand
import md_import
import render
import scorm
import scorm_lint

IMSCP_12 = "http://www.imsproject.org/xsd/imscp_rootv1p1p2"
IMSCP_2004 = "http://www.imsglobal.org/xsd/imscp_v1p1"


def _build_single(showcase_md, tmp_path, brand_name, version):
    ir, _used = md_import.import_md(showcase_md, which=1)
    b = brand.load_brand(brand_name)
    course_dir = str(tmp_path / f"{brand_name}-{version}.course")
    render.render_course(ir, course_dir, {}, brand=b)
    out_zip = str(tmp_path / f"{brand_name}-{version}.zip")
    scorm.package(course_dir, out_zip, ir["id"], ir["title"], version=version)
    return out_zip


def _manifest_xml(out_zip):
    with zipfile.ZipFile(out_zip) as z:
        return z.read("imsmanifest.xml").decode("utf-8")


# --- 2004 single-SCO ---------------------------------------------------------

@pytest.mark.parametrize("brand_name", ["_default", "teletracking"])
def test_scorm2004_lint_passes(showcase_md, tmp_path, brand_name):
    out_zip = _build_single(showcase_md, tmp_path, brand_name, "2004")
    assert os.path.exists(out_zip)
    errors, _warnings = scorm_lint.lint_zip(out_zip)
    assert errors == [], f"{brand_name} 2004 lint errors: {errors}"


def test_scorm2004_manifest_shape(showcase_md, tmp_path):
    out_zip = _build_single(showcase_md, tmp_path, "_default", "2004")
    xml = _manifest_xml(out_zip)
    root = ET.fromstring(xml)
    # 2004 content-packaging namespace on the root element
    assert root.tag == "{%s}manifest" % IMSCP_2004
    # schemaversion is a 2004 value
    md = root.find("{%s}metadata" % IMSCP_2004)
    assert (md.findtext("{%s}schemaversion" % IMSCP_2004) or "").startswith("2004")
    # the 2004 sequencing/navigation namespaces are declared
    assert 'xmlns:imsss="http://www.imsglobal.org/xsd/imsss"' in xml
    assert 'xmlns:adlseq="http://www.adlnet.org/xsd/adlseq_v1p3"' in xml
    assert 'xmlns:adlnav="http://www.adlnet.org/xsd/adlnav_v1p3"' in xml
    # the SCO marker is the 2004 capital-T scormType (NOT 1.2's scormtype)
    assert 'adlcp:scormType="sco"' in xml
    assert "scormtype=" not in xml


# --- 2004 multi-SCO ----------------------------------------------------------

def _build_multi(showcase_md, tmp_path, version, n=2):
    b = brand.load_brand("_default")
    ir, _used = md_import.import_md(showcase_md, which=1)
    course_dir = str(tmp_path / f"multi-{version}.course")
    os.makedirs(course_dir)
    render.copy_shared(course_dir, b)
    scos = []
    for k in range(1, n + 1):
        render.render_course(ir, os.path.join(course_dir, f"sco_{k}"), {},
                             asset_base="../", bundle_brand_player=False,
                             lesson_index=k, lesson_count=n, brand=b)
        scos.append({"id": f"{ir['id']}-{k}", "title": f"Lesson {k}",
                     "href": f"sco_{k}/index.html"})
    out_zip = str(tmp_path / f"multi-{version}.zip")
    scorm.package_multi(course_dir, out_zip, ir["id"], ir["title"], scos, version=version)
    return out_zip


def test_scorm2004_multi_lint_passes(showcase_md, tmp_path):
    out_zip = _build_multi(showcase_md, tmp_path, "2004")
    errors, _warnings = scorm_lint.lint_zip(out_zip)
    assert errors == [], f"2004 multi lint errors: {errors}"
    xml = _manifest_xml(out_zip)
    # per-lesson SCO resources + the shared asset resource all use capital-T
    assert 'adlcp:scormType="sco"' in xml
    assert 'adlcp:scormType="asset"' in xml
    assert "scormtype=" not in xml
    root = ET.fromstring(xml)
    assert root.tag == "{%s}manifest" % IMSCP_2004


# --- 1.2 path must be UNCHANGED ---------------------------------------------

def test_scorm12_default_unchanged(showcase_md, tmp_path):
    """Default version stays 1.2: original namespace, lowercase scormtype,
    schemaversion 1.2 — a 2004 regression that bled into 1.2 fails here."""
    out_zip = _build_single(showcase_md, tmp_path, "_default", "1.2")
    errors, _warnings = scorm_lint.lint_zip(out_zip)
    assert errors == [], f"1.2 lint errors: {errors}"
    xml = _manifest_xml(out_zip)
    root = ET.fromstring(xml)
    assert root.tag == "{%s}manifest" % IMSCP_12
    md = root.find("{%s}metadata" % IMSCP_12)
    assert (md.findtext("{%s}schemaversion" % IMSCP_12) or "").strip() == "1.2"
    assert 'adlcp:scormtype="sco"' in xml          # lowercase = 1.2
    assert "scormType=" not in xml                 # no 2004 capital-T leak


def test_package_default_version_is_12(showcase_md, tmp_path):
    """scorm.package() with no version arg == the 1.2 manifest byte-for-byte."""
    ir, _used = md_import.import_md(showcase_md, which=1)
    b = brand.load_brand("_default")
    cdir = str(tmp_path / "x.course")
    render.render_course(ir, cdir, {}, brand=b)
    z_default = str(tmp_path / "default.zip")
    z_explicit = str(tmp_path / "explicit.zip")
    scorm.package(cdir, z_default, ir["id"], ir["title"])
    scorm.package(cdir, z_explicit, ir["id"], ir["title"], version="1.2")
    assert _manifest_xml(z_default) == _manifest_xml(z_explicit)
