param(
    [string]$RunName = "pi_1m_hold2_release1",
    [string]$Digits = "data\pi_10m_digits.txt",
    [int]$MaxDigits = 1000000,
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
        ($_.CommandLine -match "review_pi_checkpoint\.py")
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force
    }

$arguments = @(
    "scripts\review_pi_checkpoint.py",
    "--run-name", $RunName,
    "--digits", $Digits,
    "--max-digits", "$MaxDigits",
    "--checkpoint", $Checkpoint,
    "--speed", "$Speed",
    "--hold-frames", "$HoldFrames",
    "--release-frames", "$ReleaseFrames",
    "--sound-volume", "$SoundVolume",
    "--sound-sample-rate", "$SoundSampleRate",
    "--scale", "$Scale"
)

$process = Start-Process -FilePath "py" -ArgumentList $arguments -WorkingDirectory $repoRoot -PassThru
Write-Host "Started review process PID=$($process.Id)"
