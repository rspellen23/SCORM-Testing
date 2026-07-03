"""Template ingestion step 2d — data-driven template layouts pickable in the dashboard.

Ingested region-specs (templates/layouts/*.json) appear in the slide-layout picker as
named entries, grouped: generic ones under "Templates", client-specific ones under
"<Client> templates". Picking a template builds a {layout:"template"} slide from its
starter content; a client-specific template auto-defaults its brand. Static drift guards
over dashboard/index.html.
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()


def _fn(name):
    return HTML.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


def test_templates_state_declared_and_loaded():
    assert "TEMPLATES=[], TEMPLATE_MAP={}" in HTML
    assert "TEMPLATES = r.templates||[]" in HTML
    assert "TEMPLATE_MAP[t.name]=t" in HTML


def test_picker_options_helper_groups_templates():
    fn = _fn("layoutOptionsHtml")
    assert "LAYOUTS.map" in fn                              # built-in layouts first
    assert "optgroup" in fn                                 # templates grouped
    assert "'Templates'" in fn                              # generic group label
    assert "templates'" in fn or "+' templates'" in fn      # client-specific group label
    assert "'template:'+t.name" in fn                       # template option value form


def test_both_pickers_use_the_helper():
    # the add-slide picker and the per-slide select both call the grouped helper
    assert "layoutOptionsHtml('')" in HTML
    assert "layoutOptionsHtml(slidePickerValue(d))" in HTML


def test_slide_picker_value_maps_template_slide():
    fn = _fn("slidePickerValue")
    assert "d.layout==='template'" in fn
    assert "'template:'+c.template" in fn


def test_deckadd_builds_template_slide():
    fn = _fn("deckAdd")
    assert "isTemplateVal(sel)" in fn
    assert "layout:'template'" in fn
    assert "autoBrandForTemplate(t)" in fn


def test_decksetlayout_handles_template_and_keeps_text():
    fn = _fn("deckSetLayout")
    assert "isTemplateVal(sel)" in fn
    assert "toTemplateContent(t, DECK[i].content)" in fn    # cancel path keeps user text
    assert "autoBrandForTemplate(t)" in fn


def test_auto_brand_is_a_default_not_a_lock():
    fn = _fn("autoBrandForTemplate")
    assert "if(!t || !t.brand) return" in fn                # no brand -> no-op
    assert "b.value=t.brand" in fn
    # it only sets when the option exists and differs; it never disables the selector
    assert "disabled" not in fn


def test_to_template_content_preserves_binds():
    fn = _fn("toTemplateContent")
    assert "c.template=t.name" in fn
    assert "t.starter" in fn                                # seed starter when empty


def test_isanyexample_recognizes_template_starters():
    fn = _fn("isAnyExample")
    assert "TEMPLATES.some" in fn
