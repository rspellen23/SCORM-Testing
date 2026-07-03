"""Q7 — image/screenshot → deck.

Images dropped in a DECK source folder are OCR'd (via Tesseract) and their text
flows into the deck-generation prompt — the deck reuses the same OCR-aware
`read_sources` the course side does. Missing Tesseract degrades with the existing
skip-with-hint, never a crash. These tests pin the deck wiring (the DoD's ask);
OCR itself is stubbed so no Tesseract binary is needed.
"""
import os

import authoring as A

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_VALID_DECK = '{"slides":[{"layout":"infographic","content":{"title":"T"}}]}'


def test_image_source_text_reaches_the_deck_prompt(tmp_path, monkeypatch):
    (tmp_path / "screenshot.png").write_bytes(b"\x89PNG\r\n")   # bytes never read (OCR stubbed)
    monkeypatch.setattr(A, "_ocr_image", lambda p: "OCRED_SCREEN_TEXT_42")
    captured = {}

    def fake_run_cli(provider, prompt, **k):
        captured["p"] = prompt
        return (True, _VALID_DECK, "")
    monkeypatch.setattr(A, "run_cli", fake_run_cli)
    res = A.generate_deck("claude", str(tmp_path), title="D")
    assert res.get("ok"), res
    assert "OCRED_SCREEN_TEXT_42" in captured["p"]              # OCR text is in the deck prompt
    assert "screenshot.png" in res.get("used_sources", [])


def test_missing_tesseract_degrades_with_hint(tmp_path, monkeypatch):
    (tmp_path / "shot.png").write_bytes(b"\x89PNG\r\n")
    monkeypatch.setattr(A, "_tesseract_cmd", lambda: None)      # OCR engine absent
    res = A.generate_deck("claude", str(tmp_path), title="D")
    # nothing readable -> generate_deck returns the no-source error WITH the skip note
    assert res.get("ok") is False
    assert any("shot.png" in s and "Tesseract" in s for s in res.get("skipped", []))


def test_deck_picker_accepts_images_and_advertises_ocr():
    html = open(os.path.join(REPO, "dashboard", "index.html"), encoding="utf-8").read()
    picker = html[html.index("pick('both','sl_src'"):].split(")", 1)[0]
    for ext in ("png", "jpg", "jpeg", "tif", "bmp", "gif", "webp"):
        assert f"'{ext}'" in picker                              # image exts selectable in the deck picker
    # the deck source label tells the operator images are OCR'd
    assert "images via OCR" in html
