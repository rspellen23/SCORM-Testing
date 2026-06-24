"""Block-registry drift test (audit item 2.2).

`src/blocks.py` is the single source of truth for the block vocabulary. This
test re-derives the type set from each of the four real wiring sites and asserts
they all agree with the registry, so adding a block to one site without the
others fails CI:

    1. schema enum       schema/ir.schema.json
    2. HTML renderer     src/render.py            (the `t == "..."` dispatch)
    3. PPTX exporter     src/pptx_export.py        (the importable `_DROP` set)
    4. markdown parser   src/md_import.py          (literal producers + `*_RE`)

It also enforces the 'coming-soon' invariant: stubbed types (scenario / continue
/ headingParagraph) must stay importer-only — no authoring grammar — so the AI
author can never emit a half-wired block.
"""
import json
import os
import re

import blocks
import pptx_export

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "src")
SCHEMA = os.path.join(os.path.dirname(HERE), "schema", "ir.schema.json")
SCHEMA_DOC = os.path.join(os.path.dirname(HERE), "schema", "IR_SCHEMA.md")


def _read(rel):
    with open(os.path.join(SRC, rel), encoding="utf-8") as fh:
        return fh.read()


def _schema_enum():
    with open(SCHEMA, encoding="utf-8") as fh:
        s = json.load(fh)
    return set(s["definitions"]["block"]["properties"]["type"]["enum"])


def _render_handled():
    """Types the HTML renderer dispatches on: `if t == "x"` in render_block plus
    the `b.get("type") == "x"` section markers in the page assembler."""
    src = _read("render.py")
    got = set(re.findall(r'\bt == "([a-zA-Z]+)"', src))
    got |= set(re.findall(r'type"\)\s*==\s*"([a-zA-Z]+)"', src))
    return got


def _md_producible():
    """Types the markdown parser can emit: literal `"type": "x"` producers plus
    every dedicated `<TYPE>_RE` authoring marker (covers the dynamic accordion/
    process producers, which share `_parse_accordion(kind=...)`)."""
    src = _read("md_import.py")
    got = set(re.findall(r'["\']type["\']:\s*["\']([a-zA-Z]+)["\']', src))
    for t in blocks.all_types():
        if re.search(rf'\b{t.upper()}_RE\s*=\s*re\.compile', src, re.I):
            got.add(t)
    # the modal media `{'type': 'image'/'video'/'embed'}` are sub-objects, not
    # top-level blocks; they happen to coincide with real block types so they're
    # harmless here, but guard against a stray sub-object type leaking in.
    return got & blocks.all_types()


def test_registry_covers_schema_enum():
    assert blocks.all_types() == _schema_enum(), (
        "blocks.BLOCKS and the schema enum disagree — add the type to both."
    )


def test_registry_matches_renderer():
    assert _render_handled() == blocks.all_types(), (
        "render.py and blocks.BLOCKS disagree — every block needs a renderer "
        "branch and a registry entry."
    )


def test_registry_matches_pptx_drop():
    # _DROP is the authoritative flatten-disposition fact; the registry mirrors it.
    assert set(pptx_export._DROP) == blocks.pptx_drop_types(), (
        "pptx_export._DROP and blocks.BLOCKS disagree on what the flatten drops."
    )
    # render vs drop must partition the whole vocabulary (no type unaccounted for).
    assert blocks.pptx_render_types().isdisjoint(blocks.pptx_drop_types())
    assert blocks.pptx_render_types() | blocks.pptx_drop_types() == blocks.all_types()


def test_stable_types_are_parser_producible():
    producible = _md_producible()
    missing = blocks.authorable_types() - producible
    assert not missing, (
        f"these stable types have no markdown parser producer: {sorted(missing)} "
        f"— add a parser or mark them coming-soon."
    )


def test_schema_doc_covers_every_type():
    """Every block type has a row in the human-facing schema/IR_SCHEMA.md table."""
    with open(SCHEMA_DOC, encoding="utf-8") as fh:
        doc = fh.read()
    documented = set(re.findall(r'^\|\s*`([a-zA-Z]+)`\s*\|', doc, re.M))
    missing = blocks.all_types() - documented
    assert not missing, f"IR_SCHEMA.md table is missing rows for: {sorted(missing)}"


def test_coming_soon_types_are_importer_only():
    """The stubbed types must NOT be markdown-authorable, or the AI could emit a
    half-wired block (the silent-degradation bug this registry closes)."""
    leaked = blocks.coming_soon_types() & _md_producible()
    assert not leaked, (
        f"coming-soon types leaked into the authoring grammar: {sorted(leaked)}"
    )
    # and they must still be real, rendered types (stub, not deleted)
    assert blocks.coming_soon_types() <= _render_handled()
    assert blocks.coming_soon_types() <= _schema_enum()
