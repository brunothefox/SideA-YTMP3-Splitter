param([switch]$HighAccuracy)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
New-Item -ItemType Directory -Force tools/whisper, tools/models | Out-Null
$enginePath = Join-Path $PSScriptRoot 'tools/whisper/Release/whisper-cli.exe'
if (-not (Test-Path -LiteralPath $enginePath)) {
    Write-Host 'Downloading the official Whisper CPU engine...'
    Invoke-WebRequest 'https://github.com/ggml-org/whisper.cpp/releases/download/v1.9.2/whisper-bin-x64.zip' -OutFile 'tools/whisper.zip'
    $binaryHash = (Get-FileHash -LiteralPath 'tools/whisper.zip' -Algorithm SHA256).Hash.ToLower()
    if ($binaryHash -ne '49dcc16de826f20bd53d44f947a1ae49dfa81f86cad67a64d80820cb192d674a') { throw 'Whisper download checksum mismatch.' }
    Expand-Archive -LiteralPath 'tools/whisper.zip' -DestinationPath 'tools/whisper' -Force
    Remove-Item -LiteralPath 'tools/whisper.zip'
}
$modelPath = Join-Path $PSScriptRoot 'tools/models/ggml-base.bin'
if (-not (Test-Path -LiteralPath $modelPath)) {
    Write-Host 'Downloading the multilingual speech model (148 MB)...'
    Invoke-WebRequest 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin' -OutFile 'tools/models/ggml-base.bin.part'
    $modelHash = (Get-FileHash -LiteralPath 'tools/models/ggml-base.bin.part' -Algorithm SHA256).Hash.ToLower()
    if ($modelHash -ne '60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe') { throw 'Model download checksum mismatch.' }
    Move-Item -LiteralPath 'tools/models/ggml-base.bin.part' -Destination $modelPath
}
if ($HighAccuracy -and -not (Test-Path -LiteralPath 'tools/models/ggml-small.bin')) {
    Write-Host 'Downloading the higher-accuracy multilingual model (488 MB)...'
    Invoke-WebRequest 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin' -OutFile 'tools/models/ggml-small.bin.part'
    if ((Get-FileHash -LiteralPath 'tools/models/ggml-small.bin.part' -Algorithm SHA256).Hash.ToLower() -ne '1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b') { throw 'Higher-accuracy model checksum mismatch.' }
    Move-Item -LiteralPath 'tools/models/ggml-small.bin.part' -Destination 'tools/models/ggml-small.bin'
}
Write-Host 'Offline content cleanup is ready. Refresh the site.'
