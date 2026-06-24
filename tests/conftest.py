"""Shared test fixtures and helpers for the Course Builder suite.

pytest is configured (pyproject.toml: tool.pytest.ini_options pythonpath=src)
to put ./src on sys.path, so engine modules import as `import md_import` etc.
without installing the package.

The golden corpus lives in tests/golden/. Regenerate it after an INTENTIONAL
parser/renderer change with:

    UPDATE_GOLDENS=1 python -m pytest tests/

CI never sets UPDATE_GOLDENS, so unintended changes fail the gate.
"""
import json
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")
TEMPLATES = os.path.join(REPO, "templates")

UPDATE = os.environ.get("UPDATE_GOLDENS") == "1"

# Archetype templates that import as a single microlearning unit (which=1).
# Used for breadth in schema validation (no golden file -> robust to content
# edits; still catches schema/importer drift).
ARCHETYPE_TEMPLATES = [
    "concept-explainer.md",
    "software-procedure.md",
    "policy-acceptable-use.md",
    "onboarding-company.md",
    "onboarding-role.md",
    "decision-scenario.md",
]


def golden_path(name):
    return os.path.join(GOLDEN, name)


def assert_golden(name, actual_text):
    """Compare actual_text to tests/golden/<name>; regenerate when UPDATE=1."""
    path = golden_path(name)
    if UPDATE or not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(actual_text)
        if not UPDATE:
            pytest.skip(f"golden {name} created; re-run to compare")
        return
    with open(path, encoding="utf-8") as fh:
        expected = fh.read()
    assert actual_text == expected, (
        f"{name} differs from golden. If this change is intentional, "
        f"regenerate with UPDATE_GOLDENS=1 python -m pytest."
    )


@pytest.fixture
def showcase_md():
    return os.path.join(FIXTURES, "showcase.md")


@pytest.fixture
def showcase_ir(showcase_md):
    import md_import
    ir, _ = md_import.import_md(showcase_md, which=1)
    return ir


def canonical_json(obj):
    """Stable JSON text for golden comparison."""
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
