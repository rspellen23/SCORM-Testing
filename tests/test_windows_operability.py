"""Phase W — Windows / cross-platform operability regression tests.

Covers the three code-doable items from AUDIT_AND_REMEDIATION_PLAN_2026-06-26:
  * W1 — the Windows launchers (launch.bat / launch.ps1 / build.bat) exist and
    invoke the right entrypoints, so a PC operator can double-click in.
  * W2 — Tesseract detection finds the UB-Mannheim Windows install even when it's
    off PATH (the installer does not add it), instead of a false "OCR unavailable".
  * W3 — the file-endpoint allowlist gains a Windows drive-letter analogue to the
    macOS /Volumes root, so a source on a second/external drive isn't clamped home.

W4 (a real end-to-end Windows smoke pass) is the human-gated oracle and is not
something a test on this machine can close — these guard the code paths W4 exercises.

server.py lives in dashboard/, off the pyproject pythonpath=src, so we add it.
"""
import os
import sys

import authoring  # on pythonpath=src

_DASH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard")
if _DASH not in sys.path:
    sys.path.insert(0, _DASH)
import server  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- W1: Windows launchers exist and call the right entrypoints --------------

def test_launch_bat_exists_and_runs_server():
    p = os.path.join(_REPO, "dashboard", "launch.bat")
    assert os.path.isfile(p), "dashboard/launch.bat is missing (W1)"
    body = open(p, encoding="utf-8").read()
    assert "dashboard\\server.py" in body
    assert body.lstrip().startswith("@echo off")


def test_launch_ps1_exists_and_runs_server():
    p = os.path.join(_REPO, "dashboard", "launch.ps1")
    assert os.path.isfile(p), "dashboard/launch.ps1 is missing (W1)"
    body = open(p, encoding="utf-8").read()
    assert "dashboard/server.py" in body


def test_build_bat_exists_and_wraps_the_cli():
    p = os.path.join(_REPO, "build.bat")
    assert os.path.isfile(p), "build.bat is missing (W1)"
    body = open(p, encoding="utf-8").read()
    assert "src\\cli.py" in body
    assert "%*" in body                       # passes args through to the engine


# --- W2: Tesseract detection on Windows (off-PATH UB-Mannheim install) -------

def test_tesseract_cmd_uses_path_when_present(monkeypatch):
    monkeypatch.setattr(authoring.shutil, "which", lambda _n: "/usr/bin/tesseract")
    assert authoring._tesseract_cmd() == "/usr/bin/tesseract"


def test_tesseract_cmd_probes_windows_install_when_off_path(monkeypatch):
    monkeypatch.setattr(authoring.shutil, "which", lambda _n: None)
    monkeypatch.setattr(authoring.os, "name", "nt")
    monkeypatch.setenv("ProgramFiles", r"C:\Program Files")
    # the UB-Mannheim default: <ProgramFiles>\Tesseract-OCR\tesseract.exe
    monkeypatch.setattr(authoring.os.path, "isfile",
                        lambda p: p.endswith("tesseract.exe"))
    cmd = authoring._tesseract_cmd()
    assert cmd is not None and cmd.endswith("tesseract.exe")
    assert "Tesseract-OCR" in cmd


def test_tesseract_cmd_none_when_absent_on_windows(monkeypatch):
    monkeypatch.setattr(authoring.shutil, "which", lambda _n: None)
    monkeypatch.setattr(authoring.os, "name", "nt")
    monkeypatch.setattr(authoring.os.path, "isfile", lambda _p: False)
    assert authoring._tesseract_cmd() is None


def test_tesseract_cmd_none_when_absent_off_windows(monkeypatch):
    monkeypatch.setattr(authoring.shutil, "which", lambda _n: None)
    monkeypatch.setattr(authoring.os, "name", "posix")
    assert authoring._tesseract_cmd() is None


def test_ocr_image_returns_none_without_engine(monkeypatch):
    # Whole-pipeline contract: no engine -> None (caller skips with a hint), no crash.
    monkeypatch.setattr(authoring, "_tesseract_cmd", lambda: None)
    assert authoring._ocr_image("anything.png") is None


# --- W3: Windows drive-letter roots (the /Volumes analogue) ------------------

def test_platform_drive_roots_windows_lists_accessible_drives(monkeypatch):
    monkeypatch.setattr(server.os, "name", "nt")
    monkeypatch.setattr(server.os.path, "isdir", lambda p: p in ("C:\\", "D:\\"))
    roots = server._platform_drive_roots()
    assert roots == ["C:\\", "D:\\"]          # C: (home) AND D: (second drive)


def test_platform_drive_roots_macos_is_volumes(monkeypatch):
    monkeypatch.setattr(server.os, "name", "posix")
    monkeypatch.setattr(server.os.path, "isdir", lambda p: p == "/Volumes")
    assert server._platform_drive_roots() == ["/Volumes"]


def test_platform_drive_roots_linux_is_empty(monkeypatch):
    monkeypatch.setattr(server.os, "name", "posix")
    monkeypatch.setattr(server.os.path, "isdir", lambda _p: False)
    assert server._platform_drive_roots() == []


def test_allow_roots_includes_platform_drives(monkeypatch):
    # _allow_roots folds the platform drives in (realpath'd) alongside home/repo/temp.
    monkeypatch.setattr(server, "_platform_drive_roots", lambda: [server.ROOT])
    roots = server._allow_roots()
    assert os.path.realpath(server.ROOT) in roots
