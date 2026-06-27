@echo off
REM Double-click this file to launch the course-builder dashboard on Windows.
REM It starts the local helper and opens the app in your browser.
REM (Windows equivalent of dashboard/launch.command.)
cd /d "%~dp0.."
echo Starting course-builder dashboard...
where python >nul 2>nul
if %errorlevel%==0 (
  python dashboard\server.py
) else (
  py dashboard\server.py
)
if errorlevel 1 (
  echo.
  echo Could not start. Make sure Python 3 is installed and on PATH
  echo ^(download from python.org and tick "Add python.exe to PATH"^).
  pause
)
