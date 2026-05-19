param(
    [string]$RunName = "pi_1m_hold2_release1",
    [string]$Digits = "data\pi_10m_digits.txt",
    [int]$MaxDigits = 0,
    [string]$Checkpoint = "latest",
    [int]$Speed = 1,
    [int]$HoldFrames = 2,
    [int]$ReleaseFrames = 1,
    [int]$SoundVolume = 100,
    [int]$SoundSampleRate = 48000,
    [int]$Scale = 4
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

Get-CimInstance Win32_Process |
    Where-Object {
        ($_.Name -in @("py.exe", "python.exe", "pythonw.exe")) -and
        (($_.CommandLine -match "review_pi_checkpoint\.py") -or ($_.CommandLine -match "review_web\.py"))
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force
    }

$arguments = @(
    "scripts\review_web.py",
    "--run-name", $RunName,
    "--digits", $Digits,
    "--checkpoint", $Checkpoint,
    "--speed", "$Speed",
    "--hold-frames", "$HoldFrames",
    "--release-frames", "$ReleaseFrames",
    "--sound-volume", "$SoundVolume",
    "--sound-sample-rate", "$SoundSampleRate",
    "--scale", "$Scale",
    "--open-browser"
)

if ($MaxDigits -gt 0) {
    $arguments += @("--max-digits", "$MaxDigits")
}

$process = Start-Process -FilePath "py" -ArgumentList $arguments -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru
Write-Host "Started review process PID=$($process.Id)"
