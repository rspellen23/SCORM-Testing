"""Course wizard: the standalone "Generate scripts" stage was dissolved. The
course-definition questions (title, objectives, audience, teaching pattern,
purpose, unit count) moved UP into the Project step; the Generate button moved
to the END of the Source materials step. These static drift guards fail if a
future edit re-introduces the separate stage or splits those fields back out.
"""
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()


def _stage(stage_id):
    # the chunk of a stage div, from its id to the next stage comment
    body = HTML.split(f'id="{stage_id}"', 1)[1]
    return body.split("<!-- STEP", 1)[0]


def test_no_standalone_generate_stage():
    line = re.search(r"const COURSE_STEPS=\[(.*?)\];", HTML).group(1)
    steps = [s.strip().strip("'\"") for s in line.split(",")]
    assert "Generate scripts" not in steps
    assert steps[:2] == ["Project", "Source materials"]


def test_course_definition_fields_live_in_project_step():
    s1 = _stage("s1")
    for fid in ("gen_title", "gen_obj", "gen_aud", "gen_arch", "gen_preset", "gen_units"):
        assert f'id="{fid}"' in s1, fid
    # exactly one of each across the whole page (no leftover duplicate in a dead stage)
    for fid in ("gen_title", "gen_obj", "gen_aud"):
        assert HTML.count(f'id="{fid}"') == 1, fid


def test_generate_button_lives_in_source_step():
    s3 = _stage("s3")
    assert 'id="gen_go"' in s3 and 'onclick="generate()"' in s3
    assert 'name="gen_mode"' in s3            # the staged/stream mode moved with it
    assert 'id="gen_results"' in s3 and 'id="script_modules"' in s3
