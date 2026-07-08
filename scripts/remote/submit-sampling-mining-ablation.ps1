param(
    [Parameter(Mandatory = $true)]
    [string] $ExperimentId,
    [ValidateSet("inspect", "apply", "smoke", "apply-smoke", "overnight", "summarize", "status", "collect", "archive", "commit", "audit", "cleanup", "push")]
    [string] $Mode = "inspect",
    [string] $TrialConfigPath = "",
    [string] $ProjectRootPath = "",
    [string] $PythonBin = "",
    [string] $DataRoot = "",
    [string] $Pretrained = "",
    [string] $Gpu = "",
    [string] $Gpus = "",
    [int] $MaxParallel = 4,
    [int] $MaxMem = 2000,
    [int] $MaxUtil = 20,
    [switch] $RerunFailed,
    [string] $RemoteHost = "",
    [string] $SshConfigPath = "",
    [switch] $Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$remoteScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $remoteScriptRoot "lib\common.ps1")
. (Join-Path $remoteScriptRoot "lib\ssh.ps1")
. (Join-Path $remoteScriptRoot "lib\paths.ps1")
. (Join-Path $remoteScriptRoot "lib\result.ps1")
. (Join-Path $remoteScriptRoot "lib\training.ps1")

Assert-ExperimentId -ExperimentId $ExperimentId
$projectRoot = Get-ProjectRoot -RemoteScriptRoot $remoteScriptRoot
$config = Get-RemoteConfig -ProjectRoot $projectRoot
if (-not [string]::IsNullOrWhiteSpace($RemoteHost)) { $config.RemoteHost = $RemoteHost }
if (-not [string]::IsNullOrWhiteSpace($SshConfigPath)) { $config.SshConfigPath = $SshConfigPath }

$training = Get-TrainingConfig -ProjectRoot $projectRoot -Path $TrialConfigPath
if (-not [string]::IsNullOrWhiteSpace($ProjectRootPath)) { $training["RemoteProjectRoot"] = $ProjectRootPath }
if (-not [string]::IsNullOrWhiteSpace($PythonBin)) { $training["PythonBin"] = $PythonBin }
if (-not [string]::IsNullOrWhiteSpace($DataRoot)) { $training["DataRoot"] = $DataRoot }
if (-not [string]::IsNullOrWhiteSpace($Pretrained)) { $training["Pretrained"] = $Pretrained }
if (-not [string]::IsNullOrWhiteSpace($Gpu)) { $training["Gpu"] = $Gpu }

Assert-TrainingRemotePaths -Training $training
Assert-TrainingGpu -Training $training
if ($MaxParallel -lt 1 -or $MaxParallel -gt 16) {
    throw "MaxParallel must be between 1 and 16."
}
if ($MaxMem -lt 1) {
    throw "MaxMem must be positive."
}
if ($MaxUtil -lt 0 -or $MaxUtil -gt 100) {
    throw "MaxUtil must be between 0 and 100."
}
if ((-not [string]::IsNullOrWhiteSpace($Gpus)) -and ($Gpus -notmatch '^[0-9,]+$')) {
    throw "Gpus must contain only digits and commas."
}

$entry = Join-RemotePath -Left ([string] $config.RemoteWorkspaceRoot) -Right "bin/run_sampling_mining_ablation_bridge.sh"
Assert-RemotePath -Path $entry -Name "SamplingMiningEntry"

$cmdText = "test -x " + (Quote-PosixSingle $entry) + " && " + (Quote-PosixSingle $entry) + " --experiment-id " + (Quote-PosixSingle $ExperimentId)
$cmdText = Add-RemoteArg -CommandText $cmdText -Name "project-root" -Value ([string] $training["RemoteProjectRoot"])
$cmdText = Add-RemoteArg -CommandText $cmdText -Name "python" -Value ([string] $training["PythonBin"])
$cmdText = Add-RemoteArg -CommandText $cmdText -Name "data-root" -Value ([string] $training["DataRoot"])
$cmdText = Add-RemoteArg -CommandText $cmdText -Name "pretrained" -Value ([string] $training["Pretrained"])
$cmdText = Add-RemoteArg -CommandText $cmdText -Name "gpu" -Value ([string] $training["Gpu"])
$cmdText = Add-RemoteArg -CommandText $cmdText -Name "mode" -Value $Mode
$cmdText += " --max-parallel " + $MaxParallel
$cmdText += " --max-mem " + $MaxMem
$cmdText += " --max-util " + $MaxUtil
if (-not [string]::IsNullOrWhiteSpace($Gpus)) {
    $cmdText = Add-RemoteArg -CommandText $cmdText -Name "gpus" -Value $Gpus
}
if ($RerunFailed) {
    $cmdText += " --rerun-failed"
}
$cmdText = Add-RemoteRootExport -CommandText $cmdText -RemoteWorkspaceRoot ([string] $config.RemoteWorkspaceRoot)
$remoteCommand = "bash -lc " + (Quote-PosixSingle $cmdText)

$result = Invoke-RemoteSsh `
    -RemoteHost ([string] $config.RemoteHost) `
    -SshConfigPath ([string] $config.SshConfigPath) `
    -ConnectTimeoutSec ([int] $config.ConnectTimeoutSec) `
    -RemoteCommand $remoteCommand `
    -AllowFailure

$ok = ($result.exit_code -eq 0)
$status = New-StatusObject -ScriptName "submit-sampling-mining-ablation.ps1" -Ok $ok -ExperimentId $ExperimentId -Details @{
    mode = $Mode
    remote_entry = $entry
    project_root = [string] $training["RemoteProjectRoot"]
    python_bin = [string] $training["PythonBin"]
    data_root = [string] $training["DataRoot"]
    pretrained = [string] $training["Pretrained"]
    gpu = [string] $training["Gpu"]
    gpus = $Gpus
    max_parallel = $MaxParallel
    max_mem = $MaxMem
    max_util = $MaxUtil
    rerun_failed = [bool] $RerunFailed
    exit_code = $result.exit_code
    output = $result.output
}

$outPath = Get-StatusFilePath -ProjectRoot $projectRoot -ExperimentId $ExperimentId -Name ("sampling-mining-" + $Mode)
Write-StatusJson -Data $status -Path $outPath -Json:$Json

if (-not $ok) {
    exit 1
}
