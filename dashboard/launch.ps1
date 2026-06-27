# Launch the course-builder dashboard on Windows (PowerShell).
# Right-click this file > "Run with PowerShell", or from a terminal:
#   powershell -ExecutionPolicy Bypass -File dashboard\launch.ps1
# (PowerShell equivalent of dashboard/launch.command / launch.bat.)
Set-Location (Join-Path $PSScriptRoot '..')
Write-Host 'Starting course-builder dashboard...'
$py = if (Get-Command python -ErrorAction SilentlyContinue) { 'python' } else { 'py' }
& $py dashboard/server.py
if ($LASTEXITCODE -ne 0) {
    Write-Host ''
    Write-Host 'Could not start. Make sure Python 3 is installed and on PATH'
    Write-Host '(download from python.org and tick "Add python.exe to PATH").'
    Read-Host 'Press Enter to close'
}
