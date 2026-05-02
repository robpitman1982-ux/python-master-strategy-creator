param(
    [Parameter(Mandatory=$true)]
    [string]$RunId,

    [Parameter(Mandatory=$true)]
    [string]$PlanPath,

    [Parameter(Mandatory=$true)]
    [string]$RemoteRoot,

    [string]$BackupRoot = "G:\My Drive\strategy-data-backup",
    [int]$PollSeconds = 300,
    [string]$LogPrefix = "auto_ingest"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$logsDir = Join-Path $repoRoot "logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

$safeRunId = $RunId -replace '[^A-Za-z0-9_.-]', '_'
$stdoutLog = Join-Path $logsDir "$LogPrefix`_$safeRunId.out.log"
$stderrLog = Join-Path $logsDir "$LogPrefix`_$safeRunId.err.log"
$statePath = ".tmp_auto_ingest_$safeRunId.json"
$pidPath = Join-Path $repoRoot ".tmp_auto_ingest_$safeRunId.pid"

$argLine = @(
    '-u',
    '"scripts\auto_ingest_distributed_run.py"',
    '--run-id', $RunId,
    '--plan', "`"$PlanPath`"",
    '--remote-root', $RemoteRoot,
    '--backup-root', "`"$BackupRoot`"",
    '--state-path', $statePath,
    '--poll-seconds', $PollSeconds
) -join ' '

$process = Start-Process `
    -FilePath "python" `
    -ArgumentList $argLine `
    -WorkingDirectory $repoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru

Set-Content -Path $pidPath -Value $process.Id -Encoding ASCII

Write-Output "Started auto-ingest watcher"
Write-Output "PID: $($process.Id)"
Write-Output "stdout: $stdoutLog"
Write-Output "stderr: $stderrLog"
Write-Output "state: $statePath"
