"""Q6 — URL → deck/course source.

A pasted link is fetched (stdlib urllib, no metered API) and tag-stripped into a
source document alongside files. Tests use file:// URLs and a local HTTP-free
fixture so nothing touches the live network. An unreachable/oversized/binary URL
degrades to a skip-with-note rather than a silent drop or a crash.
"""
import os
import pathlib

import authoring as A

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _file_url(p):
    return pathlib.Path(p).resolve().as_uri()


# --- _read_url -------------------------------------------------------------

def test_html_url_is_tag_stripped(tmp_path):
    f = tmp_path / "page.html"
    f.write_text("<html><head><style>x{}</style></head><body>"
                 "<h1>Release Notes</h1><p>Ships Tuesday.</p>"
                 "<script>evil()</script></body></html>", encoding="utf-8")
    text = A._read_url(_file_url(f))
    assert "Release Notes" in text and "Ships Tuesday." in text
    assert "<h1>" not in text and "evil()" not in text   # tags + script dropped


def test_plain_text_url_is_verbatim(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("plain source line one\nline two", encoding="utf-8")
    text = A._read_url(_file_url(f))
    assert "plain source line one" in text and "line two" in text


def test_unreachable_url_returns_none(tmp_path):
    missing = _file_url(tmp_path / "does-not-exist.html")
    assert A._read_url(missing) is None


def test_non_url_schemes_rejected():
    for bad in ("", None, "/etc/passwd", "ftp://h/x", "javascript:alert(1)", "page.html"):
        assert A._read_url(bad) is None


def test_oversized_body_is_skipped(tmp_path, monkeypatch):
    f = tmp_path / "big.txt"
    f.write_text("x" * 5000, encoding="utf-8")
    monkeypatch.setattr(A, "_MAX_SOURCE_BYTES", 1000)
    assert A._read_url(_file_url(f)) is None            # over the cap → skip


# --- _coerce_urls ----------------------------------------------------------

def test_coerce_urls_splits_strings_and_lists():
    assert A._coerce_urls("a\nb , c") == ["a", "b", "c"]
    assert A._coerce_urls(["a", " b ", "", None]) == ["a", "b"]
    assert A._coerce_urls("") == [] and A._coerce_urls(None) == []


# --- read_sources integration ---------------------------------------------

def test_url_becomes_a_readable_source(tmp_path):
    f = tmp_path / "src.html"
    f.write_text("<body><p>policy detail alpha</p></body>", encoding="utf-8")
    url = _file_url(f)
    text, used, skipped = A.read_sources("", urls=[url])
    assert "policy detail alpha" in text
    assert url in used and "SOURCE URL:" in text
    assert not skipped


def test_url_and_files_combine(tmp_path):
    (tmp_path / "doc.txt").write_text("file body beta", encoding="utf-8")
    u = tmp_path / "page.html"
    u.write_text("<body>url body gamma</body>", encoding="utf-8")
    text, used, skipped = A.read_sources(str(tmp_path / "doc.txt"), urls=[_file_url(u)])
    assert "file body beta" in text and "url body gamma" in text
    assert any(x.endswith("doc.txt") for x in used) and _file_url(u) in used


def test_unreachable_url_yields_skip_note(tmp_path):
    bad = _file_url(tmp_path / "nope.html")
    text, used, skipped = A.read_sources("", urls=[bad])
    assert text == "" and used == []
    assert len(skipped) == 1 and bad in skipped[0] and "skipped" in skipped[0]


def test_no_urls_is_unchanged_behavior(tmp_path):
    (tmp_path / "only.txt").write_text("just a file", encoding="utf-8")
    text, used, skipped = A.read_sources(str(tmp_path))
    assert "just a file" in text and not skipped


# --- static wiring guards --------------------------------------------------

def test_server_threads_urls():
    src = open(os.path.join(REPO, "dashboard", "server.py"), encoding="utf-8").read()
    assert "def _read_sources_or_error(source, urls=" in src
    assert "read_sources(source, urls=urls)" in src
    assert 'urls=p.get("urls", "")' in src               # entry points pass it


def test_dashboard_has_url_inputs():
    html = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()
    assert 'id="src_urls"' in html and 'id="sl_urls"' in html
    assert "urls:val('src_urls')" in html and "urls:val('sl_urls')" in html
