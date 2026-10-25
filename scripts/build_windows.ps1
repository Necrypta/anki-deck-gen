# Build dist\AnkiDeckGenerator.exe on Windows.
# Usage (from the repo root, in PowerShell):  .\scripts\build_windows.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e ".[dev]"

Push-Location frontend
npm ci
npm run build
Pop-Location

& .\.venv\Scripts\python.exe -m pytest -q
& .\.venv\Scripts\pyinstaller.exe --noconfirm --clean ankigen.spec

Write-Host "`nBuilt dist\AnkiDeckGenerator.exe" -ForegroundColor Green
