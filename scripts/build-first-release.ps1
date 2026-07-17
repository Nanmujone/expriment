$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$spec = Join-Path $projectRoot "EnglishSongLearningPlayer.spec"

& $python -m PyInstaller --noconfirm --clean $spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

$output = Join-Path $projectRoot "dist\EnglishSongLearningPlayer"
$node = Get-ChildItem -LiteralPath $output -Recurse -File -Filter "node.exe"
if ($node) {
    throw "PARTIAL_OFFLINE build unexpectedly contains node.exe"
}

$bytes = (Get-ChildItem -LiteralPath $output -Recurse -File | Measure-Object Length -Sum).Sum
$mebibytes = [math]::Round($bytes / 1MB, 1)
Write-Output "Build output: $output"
Write-Output "Installed size: $mebibytes MiB"
