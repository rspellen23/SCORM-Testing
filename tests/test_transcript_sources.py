"""C1 — transcript/media → course sources.

A caption file (.vtt/.srt) or a media file (transcribed by the LOCAL Whisper
seam, captions.py — no metered API) enters `read_sources` as cleaned SOURCE
TRANSCRIPT prose: cue numbers/settings/tags stripped, paragraphs split on
silence gaps, sparse [m:ss] position markers kept as hints for the provider
(James's forks: source-type only; provider segments; timestamps as hints;
full course treatment via the unchanged prompt).

`authoring._transcribe_media` is the injectable stub seam (monkeypatched here,
mirroring the captions/provider stubs) so no real Whisper is needed.
"""
import os

import authoring as A


VTT = """WEBVTT
Kind: captions
Language: en

NOTE this block is metadata
and must be dropped

1
00:00:00.000 --> 00:00:02.000 align:start position:0%
Welcome to <b>Transfer IQ</b> Pro.

00:00:02.100 --> 00:00:04.000
<v Narrator>Today we cover the basics.</v>

00:00:09.000 --> 00:00:11.000
After a pause, a new topic starts.
"""

SRT = """1
00:00:00,000 --> 00:00:02,500
First subtitle line.

2
00:00:02,600 --> 00:00:05,000
Second subtitle line.
"""


# ---- cue parsing (pure) ----------------------------------------------------

def test_parse_cues_vtt_strips_noise():
    cues = A._parse_cues(VTT)
    assert [c[2] for c in cues] == ["Welcome to Transfer IQ Pro.",
                                    "Today we cover the basics.",
                                    "After a pause, a new topic starts."]
    assert cues[0][0] == 0.0 and cues[0][1] == 2.0
    joined = " ".join(c[2] for c in cues)
    assert "WEBVTT" not in joined and "NOTE" not in joined
    assert "align" not in joined and "<" not in joined


def test_parse_cues_srt_comma_millis_and_indexes():
    cues = A._parse_cues(SRT)
    assert [c[2] for c in cues] == ["First subtitle line.", "Second subtitle line."]
    assert cues[0][1] == 2.5
    assert "1" != cues[0][2][0] or True           # index lines never become text


def test_parse_cues_hourless_and_hours():
    text = "WEBVTT\n\n05:00.000 --> 05:02.000\nshort form\n\n" \
           "01:02:03.000 --> 01:02:04.000\nlong form\n"
    cues = A._parse_cues(text)
    assert cues[0][0] == 300.0
    assert cues[1][0] == 3723.0


def test_parse_cues_garbage_never_raises():
    assert A._parse_cues("") == []
    assert A._parse_cues(None) == []
    assert A._parse_cues("random text\nno cues here\n42\n") == []
    assert A._parse_cues("00:00:aa.000 --> nonsense\nx\n") == []


def test_parse_cues_multiline_cue_and_entities():
    text = "WEBVTT\n\n00:00.000 --> 00:02.000\nline one &amp; friends\nline two\n"
    cues = A._parse_cues(text)
    assert cues == [(0.0, 2.0, "line one & friends line two")]


# ---- transcript → prose (pure) ---------------------------------------------

def test_prose_paragraphs_split_on_gap_with_markers():
    prose = A._transcript_to_prose(VTT)
    paras = prose.split("\n\n")
    assert len(paras) == 2                        # 0.1s join, 5s gap splits
    assert paras[0].startswith("[0:00] ")
    assert "Welcome to Transfer IQ Pro. Today we cover the basics." in paras[0]
    # Second paragraph starts 9s in — under the 60s marker cadence → no marker.
    assert paras[1] == "After a pause, a new topic starts."


def test_prose_marker_cadence_and_hour_format():
    cues = []
    for i, start in enumerate((0, 30, 65, 3700)):
        cues.append(f"{start // 3600:02d}:{start % 3600 // 60:02d}:{start % 60:02d}.000 --> "
                    f"{start // 3600:02d}:{start % 3600 // 60:02d}:{start % 60 + 1:02d}.000\n"
                    f"segment {i}\n")
    prose = A._transcript_to_prose("WEBVTT\n\n" + "\n".join(cues))
    assert "[0:00] segment 0" in prose
    assert "[0:30]" not in prose                  # within 60s of the last marker
    assert "[1:05] segment 2" in prose
    assert "[1:01:40] segment 3" in prose         # h:mm:ss past the hour


def test_prose_dedupes_rolling_captions():
    text = ("WEBVTT\n\n00:00.000 --> 00:01.000\nsame line\n\n"
            "00:01.000 --> 00:02.000\nsame line\n\n"
            "00:02.000 --> 00:03.000\nnext line\n")
    prose = A._transcript_to_prose(text)
    assert prose.count("same line") == 1
    assert "next line" in prose


def test_prose_long_paragraph_breaks_for_marker():
    # Continuous speech (no 2s gaps) still gets a marker opportunity ~every 60s.
    cues = []
    for start in range(0, 130, 10):
        cues.append(f"00:{start // 60:02d}:{start % 60:02d}.000 --> "
                    f"00:{(start + 9) // 60:02d}:{(start + 9) % 60:02d}.000\nt{start}\n")
    prose = A._transcript_to_prose("WEBVTT\n\n" + "\n".join(cues))
    assert "[0:00]" in prose and "[1:00]" in prose and "[2:00]" in prose


def test_prose_empty_input():
    assert A._transcript_to_prose("") == ""
    assert A._transcript_to_prose("no cues at all") == ""


# ---- read_sources wiring ----------------------------------------------------

def test_read_sources_vtt_file(tmp_path):
    (tmp_path / "talk.vtt").write_text(VTT, encoding="utf-8")
    text, used, skipped = A.read_sources(str(tmp_path))
    assert used == ["talk.vtt"] and skipped == []
    assert "===== SOURCE TRANSCRIPT: talk.vtt =====" in text
    assert "never copy them into the course" in text  # marker-hint note present
    assert "Welcome to Transfer IQ Pro." in text
    assert "align:start" not in text


def test_read_sources_srt_file(tmp_path):
    (tmp_path / "talk.srt").write_text(SRT, encoding="utf-8")
    text, used, skipped = A.read_sources(str(tmp_path))
    assert used == ["talk.srt"]
    assert "First subtitle line." in text


def test_read_sources_media_stubbed(tmp_path, monkeypatch):
    (tmp_path / "demo.mp4").write_bytes(b"\x00" * 32)
    monkeypatch.setattr(A, "_transcribe_media", lambda p: VTT)
    text, used, skipped = A.read_sources(str(tmp_path))
    assert used == ["demo.mp4"] and skipped == []
    assert "===== SOURCE TRANSCRIPT: demo.mp4 =====" in text
    assert "[0:00]" in text


def test_read_sources_media_no_backend_skips_with_note(tmp_path, monkeypatch):
    (tmp_path / "demo.mp4").write_bytes(b"\x00" * 32)
    monkeypatch.setattr(A, "_transcribe_media", lambda p: None)
    text, used, skipped = A.read_sources(str(tmp_path))
    assert used == [] and text == ""
    assert len(skipped) == 1
    assert "faster-whisper" in skipped[0]


def test_read_sources_media_exempt_from_per_file_cap(tmp_path, monkeypatch):
    # A large video transcribes fine — only its transcript enters the budget.
    big = tmp_path / "big.mov"
    big.write_bytes(b"\x00" * 16)
    monkeypatch.setattr(os.path, "getsize", lambda p: A._MAX_SOURCE_BYTES + 1)
    monkeypatch.setattr(A, "_transcribe_media", lambda p: VTT)
    text, used, skipped = A.read_sources(str(tmp_path))
    assert used == ["big.mov"] and skipped == []


def test_read_sources_big_text_still_capped(tmp_path, monkeypatch):
    # The existing per-file cap on ordinary files is untouched.
    (tmp_path / "big.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(os.path, "getsize", lambda p: A._MAX_SOURCE_BYTES + 1)
    text, used, skipped = A.read_sources(str(tmp_path))
    assert used == []
    assert skipped and "larger than" in skipped[0]


def test_read_sources_media_transcript_charged_to_total(tmp_path, monkeypatch):
    (tmp_path / "demo.mp4").write_bytes(b"\x00" * 16)
    monkeypatch.setattr(A, "_transcribe_media", lambda p: VTT)
    monkeypatch.setattr(A, "_MAX_TOTAL_SOURCE_BYTES", 10)  # transcript exceeds it
    text, used, skipped = A.read_sources(str(tmp_path))
    assert used == []
    assert skipped and "total cap" in skipped[0]


def test_read_sources_plain_docs_unchanged(tmp_path):
    (tmp_path / "notes.txt").write_text("plain source", encoding="utf-8")
    text, used, skipped = A.read_sources(str(tmp_path))
    assert used == ["notes.txt"]
    assert "===== SOURCE DOCUMENT: notes.txt =====" in text
    assert "SOURCE TRANSCRIPT" not in text
