"""Multi-select knowledge checks ('choose all that apply').

`multi` is auto-derived: more than one letter on the `*Correct Answer:*` line makes
the KC multi-select (toggle options + Submit, scored all-correct/none-wrong). One
letter stays single-select with byte-identical markup. The lint requires a multi KC
to mark >=2 correct and leave >=1 wrong (else it isn't a real 'select all').
"""
import os
import tempfile

import authoring
import md_import
import render


def _kc(answer, n=4):
    letters = "ABCDEF"[:n]
    body = "*Question:* Q\n" + "".join(f"- {l}) opt {l}\n" for l in letters) + f"*Correct Answer:* {answer}\n"
    return md_import._knowledge_check(body)


def test_single_letter_is_single_select():
    kc = _kc("B")
    assert kc["multi"] is False
    assert [i for i, o in enumerate(kc["options"]) if o["correct"]] == [1]


def test_multiple_letters_make_it_multi():
    kc = _kc("A, C")
    assert kc["multi"] is True
    assert [i for i, o in enumerate(kc["options"]) if o["correct"]] == [0, 2]


def test_answer_format_variants():
    for spec in ("A, C", "A and C", "A/C", "A & C", "A C"):
        kc = _kc(spec)
        assert kc["multi"] is True, spec
        assert [i for i, o in enumerate(kc["options"]) if o["correct"]] == [0, 2], spec


def test_trailing_prose_does_not_leak_letters():
    # the answer line tokenizer keeps only single A-Z labels
    kc = md_import._knowledge_check("*Question:* Q\n- A) a\n- B) b\n*Correct Answer:* B is the right one\n")
    assert kc["multi"] is False
    assert [i for i, o in enumerate(kc["options"]) if o["correct"]] == [1]


def test_single_render_unchanged():
    h = render.render_block(_kc("B"))
    assert "nv-kc--multi" not in h and "nv-kc-submit" not in h and "aria-pressed" not in h


def test_multi_render_has_toggles_and_submit():
    h = render.render_block(_kc("A, C"))
    assert "nv-kc--multi" in h
    assert "nv-kc-submit" in h
    assert 'aria-pressed="false"' in h
    assert "Select all that apply" in h


# --- lint ------------------------------------------------------------------

_HEAD = ("## Microlearning 1: KC Test\n\n"
         "**Slide 1 — Learning Objectives**\n*Visual:* graphic · obj · slot: `obj`\n- Learn\n\n"
         "**Slide 2 — Check**\n")


def test_multi_good_passes_lint():
    md = _HEAD + "*Question:* Pick the two\n- A) a\n- B) b\n- C) c\n- D) d\n*Correct Answer:* A, C\n"
    ok, _, errs = authoring.lint(md)
    assert ok, errs


def test_multi_all_correct_is_flagged():
    md = _HEAD + "*Question:* Pick\n- A) a\n- B) b\n- C) c\n*Correct Answer:* A, B, C\n"
    ok, _, errs = authoring.lint(md)
    assert not ok and any("multi-select" in e for e in errs), errs


def test_label_after_prose_does_not_leak_as_answer():
    # A1: a stray letter AFTER prose must NOT become a third correct answer.
    kc = _kc("A, C and also note B")
    assert [i for i, o in enumerate(kc["options"]) if o["correct"]] == [0, 2]


def test_label_after_prose_is_flagged_by_lint():
    # A1: the parser drops the leaked letter AND lint raises the malformed line.
    md = _HEAD + "*Question:* Pick\n- A) a\n- B) b\n- C) c\n- D) d\n*Correct Answer:* A, C and also note B\n"
    ok, _, errs = authoring.lint(md)
    assert not ok and any("mixes answer" in e for e in errs), errs


def test_benign_trailing_prose_still_passes_lint():
    # A1 guard: `B is the right one` (prose after, no later label) is NOT a leak.
    md = _HEAD + "*Question:* Pick\n- A) a\n- B) b\n*Correct Answer:* B is the right one\n"
    ok, _, errs = authoring.lint(md)
    assert ok, errs


def test_duplicate_option_labels_fail_lint():
    # A2: two `- B)` choices — the correct-answer letter maps to the first only.
    md = _HEAD + "*Question:* Pick\n- A) a\n- B) b\n- B) b2\n- C) c\n*Correct Answer:* B\n"
    ok, _, errs = authoring.lint(md)
    assert not ok and any("repeats option label" in e for e in errs), errs


def test_unique_labels_pass_lint():
    md = _HEAD + "*Question:* Pick\n- A) a\n- B) b\n- C) c\n*Correct Answer:* B\n"
    ok, _, errs = authoring.lint(md)
    assert ok, errs


def test_multi_scores_all_correct_none_wrong_shape():
    # IR exposes exactly the correct set the player scores against
    md = _HEAD + "*Question:* Pick the two\n- A) a\n- B) b\n- C) c\n- D) d\n*Correct Answer:* B, D\n"
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    f.write(md); f.close()
    try:
        ir, _ = md_import.import_md(f.name, which=1)
    finally:
        os.unlink(f.name)
    kc = next(b for b in ir["blocks"] if b["type"] == "knowledgeCheck")
    assert kc["multi"] is True
    assert [o["correct"] for o in kc["options"]] == [False, True, False, True]
