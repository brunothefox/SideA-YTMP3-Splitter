$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required.' }
}
& ./.venv/Scripts/python.exe -c 'import fastapi, uvicorn, multipart, yt_dlp, mutagen, imageio_ffmpeg' 2>$null
if ($LASTEXITCODE -ne 0) {
    & ./.venv/Scripts/python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your internet connection.' }
}
& ./.venv/Scripts/python.exe launcher.py
