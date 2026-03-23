param(
    [string]$ConfigFile = "cloud/config_es_all_timeframes_gcp96.yaml",
    [string]$InstanceName = "strategy-sweep",
    [string]$Zone = "australia-southeast2-a",
    [string]$MachineType = "n2-highcpu-96",
    [switch]$SkipDestroy = $false
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
Push-Location $ProjectDir

try {
    $ArgsList = @(
        "cloud/launch_gcp_run.py",
        "--config", $ConfigFile,
        "--instance-name", $InstanceName,
        "--zone", $Zone,
        "--machine-type", $MachineType
    )
    if ($SkipDestroy) {
        $ArgsList += "--keep-vm"
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 @ArgsList
    }
    else {
        & python @ArgsList
    }
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
