"""(b) Schema validation of importer output.

Every importer's output must validate STRICTLY against schema/ir.schema.json.
This is the drift gate: a schema/importer/renderer divergence (the class of bug
that shipped silently before the audit) fails here.

No golden files -> robust to legitimate template content edits; it only checks
that whatever the importer produces conforms to the schema.
"""
import os

import pytest

import ir_validate
import md_import
from conftest import ARCHETYPE_TEMPLATES, TEMPLATES


def test_jsonschema_available():
    # The suite is meaningless without it; [dev] installs jsonschema.
    assert ir_validate.have_jsonschema(), "install with: pip install -e .[dev]"


def test_schema_is_self_valid():
    import jsonschema
    schema = ir_validate.load_schema()
    cls = jsonschema.validators.validator_for(schema)
    cls.check_schema(schema)  # raises if the schema itself is malformed


def test_showcase_validates(showcase_ir):
    errors = ir_validate.validate_ir(showcase_ir, strict=False, label="showcase")
    assert errors == []


@pytest.mark.parametrize("template", ARCHETYPE_TEMPLATES)
def test_archetype_templates_validate(template):
    path = os.path.join(TEMPLATES, template)
    ir, _ = md_import.import_md(path, which=1)
    errors = ir_validate.validate_ir(ir, strict=False, label=template)
    assert errors == [], f"{template}: {errors}"


def test_strict_mode_rejects_unknown_block_type():
    bad = {
        "schema": "course-ir/v1", "id": "x", "title": "X", "locale": "en",
        "blocks": [{"type": "definitelyNotARealBlock", "html": "hi"}],
    }
    with pytest.raises(ValueError):
        ir_validate.validate_ir(bad, strict=True)
