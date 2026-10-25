# Pull the latest code and run the app from source (only needed if you want to
# edit code yourself; for testing updates, use the PR test builds instead).
# Usage, from the repo root in PowerShell:
#   .\scripts\run_from_source.ps1            # current branch
#   .\scripts\run_from_source.ps1 my-branch  # check out a branch first
param([string]$Branch = "")
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if ($Branch) { git fetch origin $Branch; git checkout $Branch }
git pull --ff-only

if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install -q -e ".[dev]"

Push-Location frontend
npm ci --silent
npm run build
Pop-Location

& .\.venv\Scripts\python.exe -m ankigen
