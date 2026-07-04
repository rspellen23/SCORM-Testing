"""PDF OCR — tier-2 scanned-PDF reader.

_ocr_pdf renders each page via pymupdf and passes the bitmap to Tesseract.
It follows the same skip-with-note contract as _ocr_image: returns None when
a required backend is absent so the caller surfaces an actionable install hint,
never silently drops the file.

All IO is stubbed — no real PDF, no real Tesseract, no real pymupdf needed.
"""
import sys
import types
import authoring


# ── helpers ───────────────────────────────────────────────────────────────────

def _stub_fitz(pages_text):
    """Return a minimal fitz-look-alike whose open() yields page stubs that
    produce PNG bytes (a 1×1 white PNG) when get_pixmap() is called."""
    import io
    try:
        from PIL import Image as _PILImage
        buf = io.BytesIO()
        _PILImage.new("RGB", (1, 1), (255, 255, 255)).save(buf, "PNG")
        png_bytes = buf.getvalue()
    except Exception:
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20   # minimal header stub

    class _Pix:
        def tobytes(self, fmt):
            return png_bytes

    class _Page:
        def __init__(self, text):
            self._text = text
        def get_pixmap(self, matrix=None):
            return _Pix()

    class _Doc:
        def __init__(self):
            self._pages = [_Page(t) for t in pages_text]
        def __iter__(self):
            return iter(self._pages)
        def close(self):
            pass

    mod = types.ModuleType("fitz")
    mod.open = lambda path: _Doc()

    class _Matrix:
        def __init__(self, *a):
            pass
    mod.Matrix = _Matrix
    return mod


def _stub_pytesseract(page_texts):
    """pytesseract stub: image_to_string returns page_texts in order."""
    idx = [0]
    mod = types.ModuleType("pytesseract")
    mod.pytesseract = types.SimpleNamespace(tesseract_cmd="")

    def _image_to_string(img):
        i = idx[0]
        idx[0] += 1
        return page_texts[i] if i < len(page_texts) else ""

    mod.image_to_string = _image_to_string
    return mod


# ── _ocr_pdf unit tests ────────────────────────────────────────────────────────

def test_ocr_pdf_returns_none_when_tesseract_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(authoring, "_tesseract_cmd", lambda: None)
    p = tmp_path / "scan.pdf"
    p.write_bytes(b"%PDF-1.4")
    assert authoring._ocr_pdf(str(p)) is None


def test_ocr_pdf_returns_none_when_pymupdf_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(authoring, "_tesseract_cmd", lambda: "/usr/bin/tesseract")
    # hide fitz so the import inside _ocr_pdf fails
    monkeypatch.setitem(sys.modules, "fitz", None)
    p = tmp_path / "scan.pdf"
    p.write_bytes(b"%PDF-1.4")
    assert authoring._ocr_pdf(str(p)) is None


def test_ocr_pdf_ocrs_each_page(monkeypatch, tmp_path):
    monkeypatch.setattr(authoring, "_tesseract_cmd", lambda: "/usr/bin/tesseract")
    page_texts = ["Page one text.", "Page two text."]
    monkeypatch.setitem(sys.modules, "fitz", _stub_fitz(page_texts))
    monkeypatch.setitem(sys.modules, "pytesseract", _stub_pytesseract(page_texts))
    # PIL is already installed; Image import inside _ocr_pdf must succeed
    p = tmp_path / "scan.pdf"
    p.write_bytes(b"%PDF-1.4")
    result = authoring._ocr_pdf(str(p))
    assert result is not None
    assert "Page one text." in result
    assert "Page two text." in result


def test_ocr_pdf_returns_empty_string_when_pages_have_no_text(monkeypatch, tmp_path):
    monkeypatch.setattr(authoring, "_tesseract_cmd", lambda: "/usr/bin/tesseract")
    monkeypatch.setitem(sys.modules, "fitz", _stub_fitz(["", ""]))
    monkeypatch.setitem(sys.modules, "pytesseract", _stub_pytesseract(["", ""]))
    p = tmp_path / "blank.pdf"
    p.write_bytes(b"%PDF-1.4")
    assert authoring._ocr_pdf(str(p)) == "\n"   # two empty pages joined


# ── _read_one / read_sources integration ──────────────────────────────────────

def test_read_source_uses_tier1_when_pypdf_extracts_text(monkeypatch, tmp_path):
    """pypdf returns real text → _ocr_pdf is never called."""
    called = []
    monkeypatch.setattr(authoring, "_ocr_pdf", lambda p: called.append(p) or "SHOULD_NOT_APPEAR")

    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-1.4")

    # stub pypdf so it returns real text
    import types as _types
    fake_page = _types.SimpleNamespace(extract_text=lambda: "Real extracted text from PDF.")
    fake_reader = _types.SimpleNamespace(pages=[fake_page])
    fake_pypdf = _types.ModuleType("pypdf")
    fake_pypdf.PdfReader = lambda path: fake_reader
    monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)

    text = authoring._read_one(str(p))
    assert text == "Real extracted text from PDF."
    assert called == []   # _ocr_pdf was NOT invoked


def test_read_source_falls_back_to_ocr_when_pypdf_returns_empty(monkeypatch, tmp_path):
    """pypdf returns empty → _ocr_pdf is called and its text surfaces."""
    monkeypatch.setattr(authoring, "_ocr_pdf", lambda p: "OCR_EXTRACTED_TEXT")

    p = tmp_path / "scanned.pdf"
    p.write_bytes(b"%PDF-1.4")

    import types as _types
    fake_page = _types.SimpleNamespace(extract_text=lambda: "")
    fake_reader = _types.SimpleNamespace(pages=[fake_page])
    fake_pypdf = _types.ModuleType("pypdf")
    fake_pypdf.PdfReader = lambda path: fake_reader
    monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)

    text = authoring._read_one(str(p))
    assert text == "OCR_EXTRACTED_TEXT"


def test_read_sources_reports_skip_hint_for_scanned_pdf_without_backends(
        monkeypatch, tmp_path):
    """When both backends are absent, read_sources puts an actionable note in
    skipped (not used), never raises."""
    monkeypatch.setattr(authoring, "_tesseract_cmd", lambda: None)
    monkeypatch.setitem(sys.modules, "fitz", None)

    p = tmp_path / "report.pdf"
    p.write_bytes(b"%PDF-1.4")

    import types as _types
    fake_page = _types.SimpleNamespace(extract_text=lambda: "")
    fake_reader = _types.SimpleNamespace(pages=[fake_page])
    fake_pypdf = _types.ModuleType("pypdf")
    fake_pypdf.PdfReader = lambda path: fake_reader
    monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)

    _text, used, skipped = authoring.read_sources(str(tmp_path))
    assert "report.pdf" not in " ".join(used)
    assert any("report.pdf" in s and "scanned PDF" in s for s in skipped)
    assert any("Tesseract" in s for s in skipped)
