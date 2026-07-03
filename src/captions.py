"""M3 — Local captions for self-hosted media (video/audio) via a LOCAL Whisper.

No metered API: transcription runs entirely on the operator's machine. Two
backends are auto-detected, preferred in this order:

  1. `faster-whisper` (a MIT Python package — easiest to install, in-process).
  2. a whisper.cpp / openai-whisper BINARY on PATH (subprocess), for operators
     who already have one — mirrors the Tesseract skip-with-note pattern.

If NEITHER is present, transcription returns None and the caller reports the
media as skipped-with-a-note (an install hint), never a silent drop — exactly
like the OCR path in `authoring._ocr_image`.

The loop-closer is `caption_markdown`: it scans a course .md for file-mode
`*Video:*` / `*Audio:*` blocks with a resolvable LOCAL source, writes a sidecar
WebVTT next to each media file, and binds it onto the block by appending a
`· captions: <file>` segment to the media line. The next build then renders a
`<track kind="captions">` (see render.py). Remote/embedded media is skipped.

The scanning/binding logic takes an injectable `transcribe=` callable so tests
can exercise the wiring without a real Whisper installed (mirrors how the
generate/translate tests inject a stub provider)."""

import os
import re
import shutil
import subprocess
import tempfile

from md_import import VIDEO_RE, AUDIO_RE, _video_block, _audio_block


# ---- backend detection ---------------------------------------------------

# whisper.cpp ships `whisper-cli` (current) / `main` (old); openai-whisper
# installs `whisper`. `main` is too generic to probe safely, so we don't.
_WHISPER_BINS = ("whisper-cli", "whisper-cpp", "whisper")


def _faster_whisper_available():
    """True if the faster-whisper Python package can be imported."""
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def _whisper_bin():
    """Locate a whisper.cpp / openai-whisper binary on PATH, else None.
    Cross-platform like `authoring._tesseract_cmd`: on Windows also probe the
    default install dir (installers often skip PATH)."""
    for name in _WHISPER_BINS:
        found = shutil.which(name)
        if found:
            return found
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            for name in _WHISPER_BINS:
                cand = os.path.join(base, "whisper", name + ".exe")
                if os.path.isfile(cand):
                    return cand
    return None


def caption_backend():
    """Return the label of the backend that WOULD be used ("faster-whisper" or
    "whisper-binary"), or None when captioning is unavailable. Cheap to call —
    used by the dashboard/report to explain a skip."""
    if _faster_whisper_available():
        return "faster-whisper"
    if _whisper_bin():
        return "whisper-binary"
    return None


# ---- WebVTT formatting (pure) --------------------------------------------

def _format_ts(seconds):
    """Seconds (float) -> WebVTT timestamp `HH:MM:SS.mmm`."""
    if seconds is None or seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def segments_to_vtt(segments):
    """Build a WebVTT document from `[(start, end, text), ...]` cues. Pure —
    the shared serializer for every backend. Empty/whitespace cues are dropped;
    an empty input still yields a valid one-line `WEBVTT` file."""
    lines = ["WEBVTT", ""]
    for start, end, text in segments:
        text = (text or "").strip()
        if not text:
            continue
        lines.append(f"{_format_ts(start)} --> {_format_ts(end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---- transcription -------------------------------------------------------

def _transcribe_faster_whisper(path, lang=None, model_size=None):
    """Transcribe with faster-whisper. Returns VTT text, or None on any failure."""
    try:
        from faster_whisper import WhisperModel
    except Exception:
        return None
    size = model_size or os.environ.get("WHISPER_MODEL", "base")
    try:
        model = WhisperModel(size)
        segments, _info = model.transcribe(path, language=lang or None)
        cues = [(seg.start, seg.end, seg.text) for seg in segments]
    except Exception:
        return None
    return segments_to_vtt(cues)


def _transcribe_binary(path, lang=None, model_size=None):
    """Transcribe via a whisper.cpp / openai-whisper binary. Returns VTT text,
    or None when the binary is absent or the run fails. openai-whisper writes a
    sidecar VTT in an output dir; whisper.cpp needs a model file (probed from
    $WHISPER_CPP_MODEL) and writes `<-of>.vtt`."""
    binpath = _whisper_bin()
    if not binpath:
        return None
    name = os.path.basename(binpath).lower()
    with tempfile.TemporaryDirectory() as td:
        try:
            if name.startswith("whisper-cli") or name.startswith("whisper-cpp"):
                model = os.environ.get("WHISPER_CPP_MODEL")
                if not model or not os.path.isfile(model):
                    return None                       # no model → treat as unavailable
                of = os.path.join(td, "out")
                cmd = [binpath, "-m", model, "-f", path, "-ovtt", "-of", of]
                if lang:
                    cmd += ["-l", lang]
                subprocess.run(cmd, check=True, capture_output=True, timeout=1800)
                vtt = of + ".vtt"
            else:                                     # openai-whisper CLI
                size = model_size or os.environ.get("WHISPER_MODEL", "base")
                cmd = [binpath, path, "--model", size, "--output_format", "vtt",
                       "--output_dir", td]
                if lang:
                    cmd += ["--language", lang]
                subprocess.run(cmd, check=True, capture_output=True, timeout=1800)
                stem = os.path.splitext(os.path.basename(path))[0]
                vtt = os.path.join(td, stem + ".vtt")
            if os.path.isfile(vtt):
                return open(vtt, encoding="utf-8", errors="replace").read()
        except Exception:
            return None
    return None


def transcribe_to_vtt(path, lang=None, model_size=None):
    """Transcribe a media file to WebVTT using the best available local backend.
    Returns the VTT text, or None when no backend is installed / the run fails
    (so the caller reports skip-with-note). Never raises."""
    if not path or not os.path.isfile(path):
        return None
    vtt = _transcribe_faster_whisper(path, lang=lang, model_size=model_size)
    if vtt is not None:
        return vtt
    return _transcribe_binary(path, lang=lang, model_size=model_size)


# ---- source resolution ---------------------------------------------------

def _is_remote(src):
    return bool(re.match(r'^(https?:)?//', (src or "").strip(), re.I))


def _resolve(src, base_dir):
    """Resolve a media src to an absolute local path (or None for remote)."""
    if not src or _is_remote(src):
        return None
    if os.path.isabs(src):
        return os.path.normpath(src)
    return os.path.normpath(os.path.join(base_dir, src))


def _sidecar(src):
    """Sidecar VTT path for a media src: `media/clip.mp4` -> `media/clip.vtt`."""
    return os.path.splitext(src)[0] + ".vtt"


# ---- the loop-closer: caption a course markdown --------------------------

def caption_markdown(md_text, base_dir, *, transcribe=transcribe_to_vtt,
                     lang="en", overwrite=False):
    """Scan a course .md for file-mode video/audio blocks, generate a sidecar
    WebVTT for each resolvable LOCAL source, and BIND it by appending
    `· captions: <sidecar> · lang: <lang>` to the media line.

    Returns `(new_md_text, report)`. `report` is a per-media list of
    `{"src", "status", ...}` where status is one of:
      written  — transcribed a new sidecar and bound it
      exists   — a sidecar already existed on disk; bound it (no transcription)
      bound    — the line already carried a `captions:` opt (left as-is)
      skip     — not captioned; `reason` ∈ remote|missing|no-backend|failed

    `transcribe` is injectable so tests exercise the wiring without Whisper.
    Non-destructive to media; only the .md text and new .vtt sidecars change."""
    report = []
    out_lines = []
    for raw in md_text.splitlines():
        m = VIDEO_RE.match(raw.strip()) or AUDIO_RE.match(raw.strip())
        if not m:
            out_lines.append(raw)
            continue
        is_video = bool(VIDEO_RE.match(raw.strip()))
        block = _video_block(m.group(1)) if is_video else _audio_block(m.group(1))
        src = block.get("src", "")
        # already bound in the grammar → leave the line untouched
        if block.get("captions") and not overwrite:
            report.append({"src": src, "status": "bound"})
            out_lines.append(raw)
            continue
        # embed-mode video / remote src → nothing local to transcribe
        if block.get("mode") == "embed" or _is_remote(src):
            report.append({"src": src, "status": "skip", "reason": "remote"})
            out_lines.append(raw)
            continue
        resolved = _resolve(src, base_dir)
        if not resolved or not os.path.isfile(resolved):
            report.append({"src": src, "status": "skip", "reason": "missing"})
            out_lines.append(raw)
            continue
        side_src = _sidecar(src)
        side_abs = _resolve(side_src, base_dir)
        if os.path.isfile(side_abs) and not overwrite:
            report.append({"src": src, "status": "exists", "vtt": side_src})
            out_lines.append(_bind(raw, side_src, lang))
            continue
        vtt = transcribe(resolved, lang=lang)
        if vtt is None:
            reason = "no-backend" if caption_backend() is None else "failed"
            report.append({"src": src, "status": "skip", "reason": reason})
            out_lines.append(raw)
            continue
        with open(side_abs, "w", encoding="utf-8") as fh:
            fh.write(vtt)
        report.append({"src": src, "status": "written", "vtt": side_src})
        out_lines.append(_bind(raw, side_src, lang))
    trailing = "\n" if md_text.endswith("\n") else ""
    return "\n".join(out_lines) + trailing, report


def _bind(line, vtt_rel, lang):
    """Append `· captions: <vtt> · lang: <lang>` to a media line (idempotent)."""
    if re.search(r'·\s*captions\s*:', line, re.I):
        return line
    extra = f" · captions: {vtt_rel}"
    if lang:
        extra += f" · lang: {lang}"
    return line.rstrip() + extra
