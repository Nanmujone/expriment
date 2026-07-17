$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$executable = Join-Path $projectRoot "dist\EnglishSongLearningPlayer\EnglishSongLearningPlayer.exe"
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw "Packaged executable not found: $executable"
}

$process = $null
try {
    $process = Start-Process -FilePath $executable -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 3
    $process.Refresh()
    if ($process.HasExited) {
        throw "Packaged app exited early with code $($process.ExitCode)"
    }
    Write-Output "Packaged app stayed running for the smoke-test window."
}
finally {
    if ($null -ne $process -and -not $process.HasExited) {
        if (-not $process.CloseMainWindow()) {
            Stop-Process -Id $process.Id
        }
    }
}
