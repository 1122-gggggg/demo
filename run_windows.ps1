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
        throw "找不到 Python 3.12。請先安裝 64 位元 Python 3.12。"
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) {
        throw "建立 .venv 失敗；請確認已安裝 64 位元 Python 3.12。"
    }
}

& $VenvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "安裝 requirements.txt 失敗。" }
& $VenvPython scripts\download_demo_assets.py
if ($LASTEXITCODE -ne 0) { throw "下載展示資產失敗。" }
& $VenvPython show.py
