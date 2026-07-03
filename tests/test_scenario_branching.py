"""M14 — scenario TRUE branching in the player.

The linear scenario (no `· goto:` targets) is unchanged — same IR, byte-identical
render, still lint-valid. Branching kicks in ONLY when a choice carries a `goto`
target: scenes gain stable ids, each scene renders as a one-at-a-time panel with a
`data-goto` on each choice button, and lint flags a goto that names no scene.

The player-side routing itself is pinned in tests/test_player.js (node --test).
"""
import os
import re
import tempfile

import authoring
import md_import
import render


def _import(md):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    f.write(md)
    f.close()
    try:
        ir, _ = md_import.import_md(f.name, which=1)
    finally:
        os.unlink(f.name)
    return ir


_OBJ = ("## Microlearning 1: Branching Test\n\n"
        "**Slide 1 — Learning Objectives**\n"
        "*Visual:* graphic · obj · slot: `obj`\n"
        "- Practice a decision\n\n")

# a linear scenario (no targets) — must stay byte-identical
_LINEAR = (
    "**Slide 2 — What would you do?**\n"
    "*Scenario:*\n"
    "::: scene\n"
    "title: Urgent transfer\n"
    "A nurse calls about an urgent transfer. What first?\n"
    "- Accept and secure the bed · preferred · feedback: Right.\n"
    "- Ask for a written request · feedback: Too slow.\n"
    ":::\n"
)

# a branching scenario — a choice routes to a named scene
_BRANCH = (
    "**Slide 2 — Escalate?**\n"
    "*Scenario:*\n"
    "::: scene\n"
    "id: start\n"
    "title: The call\n"
    "A patient is deteriorating. What do you do first?\n"
    "- Escalate to the attending · goto: escalated · feedback: Good — escalate fast.\n"
    "- Wait and monitor · goto: waited · feedback: Risky.\n"
    "::: scene\n"
    "id: escalated\n"
    "title: Escalated\n"
    "The attending responds. The patient stabilizes.\n"
    "- Document the escalation · preferred · feedback: Done.\n"
    "::: scene\n"
    "id: waited\n"
    "title: Waited\n"
    "The patient worsens.\n"
    "- Escalate now · goto: escalated · feedback: Better late than never.\n"
    ":::\n"
)


# --------------------------------------------------------------- grammar

def test_scene_id_and_goto_parse():
    ir = _import(_OBJ + _BRANCH)
    scn = next(b for b in ir["blocks"] if b["type"] == "scenario")
    ids = [s.get("id") for s in scn["scenes"]]
    assert ids == ["start", "escalated", "waited"]
    start = scn["scenes"][0]
    gotos = [r.get("goto") for r in start["responses"]]
    assert gotos == ["escalated", "waited"]
    # goto coexists with feedback + doesn't leak into the feedback text
    assert "escalate fast" in start["responses"][0]["feedback"].lower()
    assert "goto" not in start["responses"][0]["feedback"].lower()


def test_goto_and_id_are_slugged():
    md = (_OBJ + "**Slide 2 — S**\n*Scenario:*\n"
          "::: scene\ntitle: A\nGo?\n- Yes · goto: The Next Scene\n"
          "::: scene\nid: The Next Scene\nThere.\n- Done · preferred\n:::\n")
    scn = next(b for b in _import(md)["blocks"] if b["type"] == "scenario")
    assert scn["scenes"][0]["responses"][0]["goto"] == "the-next-scene"
    assert scn["scenes"][1]["id"] == "the-next-scene"


def test_linear_scenario_ir_has_no_id_key():
    # no id: / goto: authored → the scene dict must not gain an `id` key (byte-identical IR)
    scn = next(b for b in _import(_OBJ + _LINEAR)["blocks"] if b["type"] == "scenario")
    assert all("id" not in s for s in scn["scenes"])
    assert all("goto" not in r for s in scn["scenes"] for r in s["responses"])


# --------------------------------------------------------------- render

def test_linear_scenario_render_is_static_and_unchanged():
    scn = next(b for b in _import(_OBJ + _LINEAR)["blocks"] if b["type"] == "scenario")
    html = render.render_block(scn)
    assert "data-branching" not in html
    assert "data-goto" not in html
    assert "<button" not in html            # linear choices stay <div>, not buttons
    assert 'class="nv-scn-choice"' in html
    assert "is-preferred" in html


def test_branching_scenario_render_has_nav_scaffold():
    scn = next(b for b in _import(_OBJ + _BRANCH)["blocks"] if b["type"] == "scenario")
    html = render.render_block(scn)
    assert "data-branching" in html
    # each scene panel carries its id and starts hidden
    assert 'data-scene-id="start"' in html
    assert 'data-scene-id="escalated"' in html
    assert html.count("nv-scn-scene") == 3
    # choices are buttons carrying their goto target
    assert '<button type="button" class="nv-scn-choice" data-goto="escalated"' in html
    assert '<button type="button" class="nv-scn-choice" data-goto="waited"' in html
    # a Continue per scene + one Start-over + the terminal scene flagged
    assert html.count("nv-scn-continue") == 3
    assert "nv-scn-restart" in html
    assert "data-terminal" in html          # the `escalated` scene has no onward goto
    # feedback is present but starts hidden (revealed on click)
    assert re.search(r'class="nv-scn-fb" hidden', html)


def test_default_scene_ids_when_id_absent():
    # branching present (goto) but a target scene has no explicit id → falls back to scene-N
    md = (_OBJ + "**Slide 2 — S**\n*Scenario:*\n"
          "::: scene\nStart.\n- Go · goto: scene-2\n"
          "::: scene\nEnd.\n- Done · preferred\n:::\n")
    scn = next(b for b in _import(md)["blocks"] if b["type"] == "scenario")
    html = render.render_block(scn)
    assert 'data-scene-id="scene-1"' in html
    assert 'data-scene-id="scene-2"' in html
    assert 'data-goto="scene-2"' in html


# --------------------------------------------------------------- lint

def test_branching_scenario_passes_lint():
    ok, _, errs = authoring.lint(_OBJ + _BRANCH)
    assert ok, errs


def test_dangling_goto_target_flagged():
    md = (_OBJ + "**Slide 2 — S**\n*Scenario:*\n"
          "::: scene\nid: start\nGo?\n- Yes · goto: nowhere · preferred\n:::\n")
    ok, _, errs = authoring.lint(md)
    assert not ok
    assert any("goto: nowhere" in e for e in errs), errs


def test_linear_scenario_still_passes_lint():
    ok, _, errs = authoring.lint(_OBJ + _LINEAR)
    assert ok, errs
