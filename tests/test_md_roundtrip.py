"""(a) Parser round-trip: .md -> golden IR JSON.

A parser regression that changes the produced IR (silently shipping wrong
content) fails against the committed golden. The golden excludes _stats, whose
counts are derived and already asserted separately, to keep the diff about
structure.
"""
import md_import
from conftest import assert_golden, canonical_json


def _ir_for_golden(ir):
    ir = dict(ir)
    ir.pop("_stats", None)  # derived; compared via counts below, not the golden
    return ir


def test_showcase_roundtrip(showcase_md):
    ir, _ = md_import.import_md(showcase_md, which=1)
    assert_golden("showcase.ir.json", canonical_json(_ir_for_golden(ir)))


def test_showcase_block_count_stable(showcase_ir):
    # Guards the headline number independently of the golden text.
    assert showcase_ir["_stats"]["blocks"] == len(showcase_ir["blocks"])
    assert len(showcase_ir["blocks"]) >= 50
    # The showcase deliberately exercises a broad vocabulary.
    assert len({b["type"] for b in showcase_ir["blocks"]}) >= 20
