"""Item 7 — source assurance. Both tabs show, BEFORE generating, every source that
will be ingested (folder documents split into supported/unsupported types + each
pasted link), and AFTER generating, an explicit used-vs-skipped list rather than a
bare count. Static drift guards over the dashboard wiring.
"""
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()


def _fn(name):
    return HTML.split(f"function {name}(", 1)[1].split("\n}", 1)[0]


def test_pre_generate_panel_counts_docs_and_links():
    fn = _fn("renderSrcAssure")
    assert "SRC_EXTS.includes(extOf(f))" in fn      # supported vs unsupported split
    assert "_urlList(urlsVal)" in fn                # pasted links are counted too
    assert "will be included" in fn                 # affirmative "all of these" message
    assert "Skipped" in fn                          # unsupported types are called out


def test_both_refresh_functions_use_the_panel():
    assert "renderSrcAssure('src_files'" in _fn("refreshSrc")
    assert "renderSrcAssure('sl_src_files'" in _fn("refreshSlSrc")


def test_url_textareas_refresh_live():
    assert 'id="src_urls"' in HTML and 'oninput="refreshSrc()"' in HTML
    assert 'id="sl_urls"' in HTML and 'oninput="refreshSlSrc()"' in HTML


def test_post_generate_shows_used_and_skipped():
    used = _fn("srcUsedHtml")
    assert "Sources used" in used and "Not included" in used
    # wired into every result renderer (course staged, course streamed, deck)
    assert "srcUsedHtml(plan.used_sources, plan.skipped)" in HTML
    assert "srcUsedHtml(res.used_sources, res.skipped)" in HTML
    assert HTML.count("srcUsedHtml(res.used_sources, res.skipped)") >= 2
