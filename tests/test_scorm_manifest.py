"""(d) SCORM manifest validity via scorm_lint.lint_zip.

Builds the showcase to a real SCORM 1.2 package and runs the conformance lint.
A malformed manifest / packaging regression fails here. Run for both the
neutral and TeleTracking brands so a brand-file regression is also caught.
"""
import os
import zipfile

import pytest

import brand
import md_import
import render
import scorm
import scorm_lint


def _build_scorm(showcase_md, tmp_path, brand_name):
    ir, used = md_import.import_md(showcase_md, which=1)
    b = brand.load_brand(brand_name)
    course_dir = str(tmp_path / f"{brand_name}.course")
    render.render_course(ir, course_dir, {}, brand=b)
    out_zip = str(tmp_path / f"{brand_name}.zip")
    scorm.package(course_dir, out_zip, ir["id"], ir["title"])
    return out_zip


@pytest.mark.parametrize("brand_name", ["_default", "teletracking"])
def test_scorm_lint_passes(showcase_md, tmp_path, brand_name):
    out_zip = _build_scorm(showcase_md, tmp_path, brand_name)
    assert os.path.exists(out_zip)
    errors, warnings = scorm_lint.lint_zip(out_zip)
    assert errors == [], f"{brand_name} SCORM lint errors: {errors}"


def test_manifest_present(showcase_md, tmp_path):
    out_zip = _build_scorm(showcase_md, tmp_path, "_default")
    with zipfile.ZipFile(out_zip) as z:
        names = z.namelist()
    assert "imsmanifest.xml" in names
    assert "index.html" in names
