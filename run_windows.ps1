$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv .venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    } else {
        throw "Python 3.12 was not found. Install 64-bit Python 3.12 first."
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) {
        throw "Failed to create .venv. Confirm that 64-bit Python 3.12 is installed."
    }
}

& $VenvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Failed to install requirements.txt." }
& $VenvPython scripts\download_demo_assets.py
if ($LASTEXITCODE -ne 0) { throw "Failed to download demo assets." }
& $VenvPython show.py
