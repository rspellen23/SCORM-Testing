@echo off
REM course-builder build CLI for Windows. Mirrors ./build (the Unix sh wrapper).
REM The full engine lives in .\src. The system carries NO company branding;
REM all branding loads from an external brand profile under .\brands:
REM   - default (no --brand)       -> brands\_default   (neutral)
REM   - --brand teletracking       -> brands\teletracking
REM   - --brand C:\path\to\brand   -> any external brand profile
setlocal
set "ENGINE=%~dp0src\cli.py"
set "PY=python"
where python >nul 2>nul || set "PY=py"

if "%~1"=="" goto :help
if /i "%~1"=="-h" goto :help
if /i "%~1"=="--help" goto :help

REM Pass everything through to the engine. The engine defaults --brand to the
REM neutral _default profile; pass --brand <name> to apply external branding.
%PY% "%ENGINE%" %*
exit /b %errorlevel%

:help
echo course-builder - agnostic course system (engine in .\src; branding via --brand).
echo   build.bat from-md-course ^<script.md^> --images ^<dir^> --out ^<out.zip^> [--format cmi5] [--brand ^<name^>]
echo   build.bat from-md ^<script.md^> --which N --images ^<dir^> --out ^<out.zip^> [--brand ^<name^>]
echo   build.bat from-docx ^<doc.docx^> --images ^<dir^> --out ^<out.zip^> [--brand ^<name^>]
echo   build.bat from-rise ^<raw.zip^> --out ^<out.zip^> [--brand ^<name^>]
echo   build.bat from-ir ^<course.ir.json^> --out ^<out.zip^> [--brand ^<name^>]
echo   build.bat to-pptx ^<script.md^> --images ^<dir^> --out ^<deck.pptx^> [--brand ^<name^>]   ^(course -^> PowerPoint^)
echo   build.bat slide --content ^<data.json^> --out ^<slide.pptx^> [--brand ^<name^>]         ^(infographic slide template^)
echo   build.bat cover --title "..." --out ^<dir^> [--brand ^<name^>]
echo.
echo   Branding: omit --brand for the neutral default; --brand teletracking for the TeleTracking profile.
echo   ^(lint / repackage: run python .\src\cli.py directly^)
echo   Dashboard ^(GUI^):  dashboard\launch.bat   ^(or: python dashboard\server.py^)
echo   Requires: python, python-pptx ^(PowerPoint^), python-docx ^(SME .docx review^).
exit /b 0
