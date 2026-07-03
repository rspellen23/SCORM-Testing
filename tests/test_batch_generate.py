"""M6 — CSV manifest -> bulk generate.

`parse_manifest` turns a manifest CSV into normalized rows (columns matched
case/space/underscore-insensitively; unknown columns ignored). `validate_manifest`
dry-runs the rows (archetype/source/required-field checks) with no generation.
`generate_batch` runs one ordinary `generate()` per row, continue-on-error, and
de-duplicates output filenames. No metered calls — `run_cli`/`generate` are stubbed.
"""
import os

import authoring as A


# ---- parse_manifest -----------------------------------------------------------

def test_parse_basic_columns_and_row_numbers():
    csv = ("title,objective,audience,archetype,units,source,urls,preset,brand\n"
           "Intro,learn X,nurses,decision-scenario,3,/srcA,http://x,corporate,teletracking\n")
    rows, errors = A.parse_manifest(csv)
    assert errors == []
    assert len(rows) == 1
    r = rows[0]
    assert r["row"] == 2                       # header is row 1
    assert r["title"] == "Intro"
    assert r["objective"] == "learn X"
    assert r["audience"] == "nurses"
    assert r["archetype"] == "decision-scenario"
    assert r["units"] == "3"
    assert r["source"] == "/srcA"
    assert r["urls"] == "http://x"
    assert r["preset"] == "corporate"
    assert r["brand"] == "teletracking"


def test_parse_header_aliases_and_unknown_columns_ignored():
    # "Course"/"Goal"/"Learners"/"Type"/"Modules"/"Folder" are aliases; "notes" is ignored.
    csv = ("Course,Goal,Learners,Type,Modules,Folder,notes\n"
           "T,obj,aud,concept-explainer,2,/s,ignore me\n")
    rows, errors = A.parse_manifest(csv)
    assert errors == []
    assert rows[0]["title"] == "T"
    assert rows[0]["objective"] == "obj"
    assert rows[0]["audience"] == "aud"
    assert rows[0]["archetype"] == "concept-explainer"
    assert rows[0]["units"] == "2"
    assert rows[0]["source"] == "/s"


def test_parse_underscore_and_space_headers_normalized():
    csv = ("Learning_Objective, Source Folder ,audience\n"
           "obj,/s,aud\n")
    rows, errors = A.parse_manifest(csv)
    assert errors == []
    assert rows[0]["objective"] == "obj"
    assert rows[0]["source"] == "/s"
    assert rows[0]["audience"] == "aud"


def test_parse_default_archetype_when_absent():
    csv = "objective,audience,source\nobj,aud,/s\n"
    rows, _ = A.parse_manifest(csv)
    assert rows[0]["archetype"] == "concept-explainer"


def test_parse_missing_required_column_is_error():
    csv = "title,objective,audience\nT,obj,aud\n"      # no source column
    rows, errors = A.parse_manifest(csv)
    assert rows == []
    assert any("source" in e for e in errors)


def test_parse_blank_rows_skipped_and_header_only_errors():
    csv = "objective,audience,source\nobj,aud,/s\n,,\n"
    rows, errors = A.parse_manifest(csv)
    assert errors == []
    assert len(rows) == 1                              # the blank line is dropped
    rows2, errors2 = A.parse_manifest("objective,audience,source\n")
    assert rows2 == []
    assert any("no data" in e for e in errors2)


def test_parse_empty_manifest_is_error():
    rows, errors = A.parse_manifest("")
    assert rows == []
    assert errors


def test_parse_strips_bom():
    csv = "﻿objective,audience,source\nobj,aud,/s\n"
    rows, errors = A.parse_manifest(csv)
    assert errors == []
    assert rows[0]["objective"] == "obj"


# ---- validate_manifest --------------------------------------------------------

def test_validate_flags_bad_rows(tmp_path):
    good_src = tmp_path / "src"
    good_src.mkdir()
    csv = (f"title,objective,audience,archetype,source,urls\n"
           f"Good,obj,aud,concept-explainer,{good_src},\n"
           f"NoObj,,aud,concept-explainer,{good_src},\n"
           f"BadArch,obj,aud,nope,{good_src},\n"
           f"NoSrc,obj,aud,concept-explainer,/does/not/exist,\n"
           f"UrlsOnly,obj,aud,concept-explainer,,http://example.com\n")
    rows, _ = A.parse_manifest(csv)
    checks = A.validate_manifest(rows)
    by_title = {c["title"]: c for c in checks}
    assert by_title["Good"]["ok"]
    assert not by_title["NoObj"]["ok"] and any("objective" in i for i in by_title["NoObj"]["issues"])
    assert not by_title["BadArch"]["ok"] and any("archetype" in i for i in by_title["BadArch"]["issues"])
    assert not by_title["NoSrc"]["ok"] and any("source" in i for i in by_title["NoSrc"]["issues"])
    assert by_title["UrlsOnly"]["ok"]                 # urls stand in for a source folder


def test_validate_flags_non_numeric_units(tmp_path):
    src = tmp_path / "s"; src.mkdir()
    csv = f"objective,audience,source,units\nobj,aud,{src},lots\n"
    rows, _ = A.parse_manifest(csv)
    checks = A.validate_manifest(rows)
    assert not checks[0]["ok"] and any("units" in i for i in checks[0]["issues"])


# ---- generate_batch -----------------------------------------------------------

VALID_MD = """# Course

**Curriculum Rationale:** teach it.

## Microlearning 1: One

**Slide 1 — Learning Objectives**
*Visual:* graphic · overview
*Objectives:* After this lesson, you will be able to:
- Do the thing

**Slide 2 — Body**
Some content here.
"""


def _mk_source(tmp_path, name):
    d = tmp_path / name
    d.mkdir()
    (d / "src.txt").write_text("Some source material about the topic.", encoding="utf-8")
    return str(d)


def test_generate_batch_two_rows_two_courses(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "run_cli", lambda prov, prompt, **k: (True, VALID_MD, ""))
    monkeypatch.setattr(A, "load_glossary", lambda b=None: {"preferred": [], "banned": []})
    s1 = _mk_source(tmp_path, "s1"); s2 = _mk_source(tmp_path, "s2")
    out = tmp_path / "out"
    csv = (f"title,objective,audience,source\n"
           f"Alpha,obj a,aud a,{s1}\n"
           f"Beta,obj b,aud b,{s2}\n")
    rows, _ = A.parse_manifest(csv)
    res = A.generate_batch("claude", rows, str(out))
    assert res["ok"] and res["n"] == 2 and res["ok_count"] == 2 and res["fail_count"] == 0
    assert os.path.isfile(out / "alpha.md")
    assert os.path.isfile(out / "beta.md")


def test_generate_batch_forwards_per_row_params(tmp_path, monkeypatch):
    calls = []

    def fake_generate(provider, **kw):
        calls.append(kw)
        with open(kw["out_path"], "w", encoding="utf-8") as fh:
            fh.write("x")
        return {"ok": True, "out": kw["out_path"], "units": 1, "lint_ok": True}

    monkeypatch.setattr(A, "generate", fake_generate)
    monkeypatch.setattr(A, "load_glossary", lambda b=None: {"preferred": [], "banned": []})
    csv = ("title,objective,audience,archetype,units,source,urls,preset\n"
           "Alpha,obj a,aud a,decision-scenario,4,/sa,http://a,corporate\n")
    rows, _ = A.parse_manifest(csv)
    A.generate_batch("claude", rows, str(tmp_path / "out"))
    assert len(calls) == 1
    c = calls[0]
    assert c["objective"] == "obj a" and c["audience"] == "aud a"
    assert c["archetype"] == "decision-scenario"
    assert c["n_units"] == 4                          # parsed to int
    assert c["source_folder"] == "/sa"
    assert c["urls"] == "http://a"
    assert c["preset"] == "corporate"
    assert c["course_title"] == "Alpha"


def test_generate_batch_dedups_repeated_titles(tmp_path, monkeypatch):
    def fake_generate(provider, **kw):
        with open(kw["out_path"], "w", encoding="utf-8") as fh:
            fh.write("x")
        return {"ok": True, "out": kw["out_path"], "units": 1, "lint_ok": True}

    monkeypatch.setattr(A, "generate", fake_generate)
    monkeypatch.setattr(A, "load_glossary", lambda b=None: {"preferred": [], "banned": []})
    csv = ("title,objective,audience,source\n"
           "Same,obj1,aud,/s1\n"
           "Same,obj2,aud,/s2\n")
    rows, _ = A.parse_manifest(csv)
    res = A.generate_batch("claude", rows, str(tmp_path / "out"))
    outs = [r["out"] for r in res["results"]]
    assert len(set(outs)) == 2                        # distinct files despite identical title
    assert outs[0].endswith("same.md")
    assert outs[1].endswith("same-2.md")


def test_generate_batch_continues_on_error(tmp_path, monkeypatch):
    def fake_generate(provider, **kw):
        if kw["objective"] == "boom":
            return {"ok": False, "error": "no readable sources"}
        with open(kw["out_path"], "w", encoding="utf-8") as fh:
            fh.write("x")
        return {"ok": True, "out": kw["out_path"], "units": 1, "lint_ok": True}

    monkeypatch.setattr(A, "generate", fake_generate)
    monkeypatch.setattr(A, "load_glossary", lambda b=None: {"preferred": [], "banned": []})
    csv = ("title,objective,audience,source\n"
           "Bad,boom,aud,/s1\n"
           "Good,fine,aud,/s2\n")
    rows, _ = A.parse_manifest(csv)
    res = A.generate_batch("claude", rows, str(tmp_path / "out"))
    assert res["n"] == 2 and res["ok_count"] == 1 and res["fail_count"] == 1
    assert res["ok"]                                  # ok is True while any row succeeded
    bad = next(r for r in res["results"] if r["title"] == "Bad")
    good = next(r for r in res["results"] if r["title"] == "Good")
    assert not bad["ok"] and bad["error"] == "no readable sources"
    assert good["ok"]


def test_generate_batch_per_row_brand_override(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(A, "load_glossary", lambda b=None: seen.append(b) or {"preferred": [], "banned": []})

    def fake_generate(provider, **kw):
        with open(kw["out_path"], "w", encoding="utf-8") as fh:
            fh.write("x")
        return {"ok": True, "out": kw["out_path"], "units": 1, "lint_ok": True}

    monkeypatch.setattr(A, "generate", fake_generate)
    csv = ("title,objective,audience,source,brand\n"
           "A,obj,aud,/s,teletracking\n")
    rows, _ = A.parse_manifest(csv)
    A.generate_batch("claude", rows, str(tmp_path / "out"), brand="_default")
    assert "teletracking" in seen                     # the row's brand column wins
