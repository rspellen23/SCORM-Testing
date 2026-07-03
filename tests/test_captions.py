"""M3 — local captions for media.

captions.py transcribes file-mode video/audio with a LOCAL Whisper and binds a
sidecar WebVTT onto the media line so the build renders a <track kind=captions>.
No metered API: the `transcribe` callable is the injectable stub seam (like the
generate/translate provider stub), and the degrade path (no Whisper installed →
skip-with-note, never a silent drop) is covered here too.
"""
import os

import captions as C
import md_import as M
import render as R


# ---- WebVTT formatting (pure) --------------------------------------------

def test_format_ts_basic():
    assert C._format_ts(0) == "00:00:00.000"
    assert C._format_ts(1.5) == "00:00:01.500"
    assert C._format_ts(3661.25) == "01:01:01.250"
    assert C._format_ts(-3) == "00:00:00.000"     # clamp negatives


def test_segments_to_vtt():
    vtt = C.segments_to_vtt([(0, 1.5, "Hello"), (1.5, 3, "world")])
    assert vtt.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:01.500" in vtt
    assert "Hello" in vtt and "world" in vtt
    assert vtt.endswith("\n")


def test_segments_to_vtt_drops_blank_cues():
    vtt = C.segments_to_vtt([(0, 1, "  "), (1, 2, "kept")])
    assert "kept" in vtt
    assert vtt.count("-->") == 1                    # blank cue skipped


def test_segments_to_vtt_empty_is_valid():
    assert C.segments_to_vtt([]).strip() == "WEBVTT"


# ---- source resolution ---------------------------------------------------

def test_is_remote():
    assert C._is_remote("https://x.com/a.mp4")
    assert C._is_remote("//cdn/a.mp4")
    assert not C._is_remote("media/a.mp4")
    assert not C._is_remote("/abs/a.mp4")


def test_sidecar_swaps_extension():
    assert C._sidecar("media/clip.mp4") == "media/clip.vtt"
    assert C._sidecar("a.mp3") == "a.vtt"


# ---- the wiring: caption_markdown (stub transcriber) ---------------------

def _stub(_path, lang=None):
    return C.segments_to_vtt([(0, 1, "stub caption")])


_OBJ = ("## Microlearning 1: Captions Test\n\n"
        "**Slide 1 — Learning Objectives**\n"
        "*Visual:* graphic · obj · slot: `obj`\n"
        "- Watch a clip\n\n")


def _md(src):
    return _OBJ + f"**Slide 2 — Clip**\n\n*Video:* file · {src}\n"


def test_caption_markdown_writes_sidecar_and_binds(tmp_path):
    (tmp_path / "clip.mp4").write_bytes(b"\x00")
    md = _md("clip.mp4")
    new_md, report = C.caption_markdown(md, str(tmp_path), transcribe=_stub)
    assert (tmp_path / "clip.vtt").is_file()
    assert report[0]["status"] == "written"
    assert report[0]["vtt"] == "clip.vtt"
    assert "· captions: clip.vtt · lang: en" in new_md


def test_caption_markdown_binding_renders_track(tmp_path):
    """End-to-end: caption → md re-parses to an IR with the track → render emits it."""
    (tmp_path / "clip.mp4").write_bytes(b"\x00")
    new_md, _ = C.caption_markdown(_md("clip.mp4"), str(tmp_path), transcribe=_stub)
    p = tmp_path / "c.md"
    p.write_text(new_md, encoding="utf-8")
    ir, _u = M.import_md(str(p))
    vid = next(b for b in ir["blocks"] if b.get("type") == "video")
    assert vid["captions"] == "clip.vtt"
    assert vid.get("captionsLang") == "en"
    html = R.render_block(vid)
    assert '<track kind="captions"' in html
    assert 'src="clip.vtt"' in html


def test_caption_markdown_audio_gets_track(tmp_path):
    (tmp_path / "a.mp3").write_bytes(b"\x00")
    md = _OBJ + "**Slide 2 — Clip**\n\n*Audio:* a.mp3\n"
    new_md, report = C.caption_markdown(md, str(tmp_path), transcribe=_stub)
    assert report[0]["status"] == "written"
    assert "· captions: a.vtt" in new_md


def test_caption_markdown_skips_remote(tmp_path):
    md = _md("https://cdn.example.com/v.mp4")
    new_md, report = C.caption_markdown(md, str(tmp_path), transcribe=_stub)
    assert report[0]["status"] == "skip" and report[0]["reason"] == "remote"
    assert new_md == md                             # untouched


def test_caption_markdown_skips_embed(tmp_path):
    md = "# C\n\n**Slide 1**\n\n*Video:* embed · https://youtu.be/x\n"
    _new, report = C.caption_markdown(md, str(tmp_path), transcribe=_stub)
    assert report[0]["status"] == "skip" and report[0]["reason"] == "remote"


def test_caption_markdown_skips_missing_file(tmp_path):
    md = _md("gone.mp4")
    _new, report = C.caption_markdown(md, str(tmp_path), transcribe=_stub)
    assert report[0]["status"] == "skip" and report[0]["reason"] == "missing"


def test_caption_markdown_degrades_when_no_backend(tmp_path):
    """The degrade path: transcribe returns None (no Whisper) → skip-with-note,
    no sidecar written, the md is left untouched."""
    (tmp_path / "clip.mp4").write_bytes(b"\x00")
    _new, report = C.caption_markdown(_md("clip.mp4"), str(tmp_path),
                                      transcribe=lambda *_a, **_k: None)
    assert report[0]["status"] == "skip"
    assert report[0]["reason"] in ("no-backend", "failed")
    assert not (tmp_path / "clip.vtt").exists()


def test_caption_markdown_binds_existing_sidecar_without_transcribing(tmp_path):
    (tmp_path / "clip.mp4").write_bytes(b"\x00")
    (tmp_path / "clip.vtt").write_text("WEBVTT\n", encoding="utf-8")
    called = []
    new_md, report = C.caption_markdown(
        _md("clip.mp4"), str(tmp_path),
        transcribe=lambda *a, **k: called.append(1) or _stub(*a, **k))
    assert report[0]["status"] == "exists"
    assert not called                               # never transcribed
    assert "· captions: clip.vtt" in new_md


def test_caption_markdown_leaves_already_bound_line(tmp_path):
    (tmp_path / "clip.mp4").write_bytes(b"\x00")
    md = "# C\n\n**Slide 1**\n\n*Video:* file · clip.mp4 · captions: hand.vtt\n"
    new_md, report = C.caption_markdown(md, str(tmp_path), transcribe=_stub)
    assert report[0]["status"] == "bound"
    assert new_md == md


def test_caption_markdown_overwrite_retranscribes(tmp_path):
    (tmp_path / "clip.mp4").write_bytes(b"\x00")
    (tmp_path / "clip.vtt").write_text("WEBVTT\nold\n", encoding="utf-8")
    _new, report = C.caption_markdown(_md("clip.mp4"), str(tmp_path),
                                      transcribe=_stub, overwrite=True)
    assert report[0]["status"] == "written"
    assert "stub caption" in (tmp_path / "clip.vtt").read_text()


# ---- md grammar: captions/lang opt round-trips ---------------------------

def test_video_block_parses_captions_opt():
    b = M._video_block("file · media/clip.mp4 · captions: clip.vtt · lang: es")
    assert b["captions"] == "clip.vtt"
    assert b["captionsLang"] == "es"


def test_media_ir_byte_identical_without_captions():
    """No captions opt → the IR carries no captions key (un-captioned media is
    unchanged)."""
    b = M._video_block("file · media/clip.mp4")
    assert "captions" not in b
    ba = M._audio_block("a.mp3")
    assert "captions" not in ba


# ---- backend detection degrades cleanly ----------------------------------

def test_caption_backend_returns_none_or_label():
    # In CI no Whisper is installed → None; the contract is "None or a str label".
    assert C.caption_backend() in (None, "faster-whisper", "whisper-binary")


def test_transcribe_to_vtt_missing_file_is_none():
    assert C.transcribe_to_vtt("/no/such/file.mp4") is None


def test_audio_track_renders():
    html = R.render_block({"type": "audio", "src": "a.mp3",
                           "captions": "a.vtt", "captionsLang": "en"})
    assert '<track kind="captions"' in html and 'src="a.vtt"' in html


def test_audio_without_captions_has_no_track():
    html = R.render_block({"type": "audio", "src": "a.mp3"})
    assert "<track" not in html
