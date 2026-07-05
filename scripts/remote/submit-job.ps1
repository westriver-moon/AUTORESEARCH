param(
    [Parameter(Mandatory = $true)]
    [string] $ExperimentId,
    [string] $TrialConfigPath = "",
    [string] $RemoteConfigPath = "",
    [string] $ProjectRootPath = "",
    [string] $PythonBin = "",
    [string] $DataRoot = "",
    [string] $Pretrained = "",
    [string] $Gpu = "",
    [string] $RemoteHost = "",
    [string] $SshConfigPath = "",
    [switch] $ConfirmFullTraining,
    [switch] $Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $ConfirmFullTraining) {
    throw "Full training requires -ConfirmFullTraining."
}

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
if (-not [string]::IsNullOrWhiteSpace($RemoteConfigPath)) { $training["PmtConfig"] = $RemoteConfigPath }
if (-not [string]::IsNullOrWhiteSpace($Pretrained)) { $training["Pretrained"] = $Pretrained }
if (-not [string]::IsNullOrWhiteSpace($Gpu)) { $training["Gpu"] = $Gpu }

$entry = [string] $config.RemoteTrainEntry
Assert-RemotePath -Path $entry -Name "RemoteTrainEntry"
Assert-TrainingRemotePaths -Training $training
Assert-TrainingGpu -Training $training

$cmdText = "test -x " + (Quote-PosixSingle $entry) + " && " + (Quote-PosixSingle $entry) + " --experiment-id " + (Quote-PosixSingle $ExperimentId)
$cmdText = Add-TrainingRemoteArgs -CommandText $cmdText -Training $training
$cmdText += " --confirm-full-training"
$cmdText = Add-RemoteRootExport -CommandText $cmdText -RemoteWorkspaceRoot ([string] $config.RemoteWorkspaceRoot)
$remoteCommand = "bash -lc " + (Quote-PosixSingle $cmdText)
$result = Invoke-RemoteSsh `
    -RemoteHost ([string] $config.RemoteHost) `
    -SshConfigPath ([string] $config.SshConfigPath) `
    -ConnectTimeoutSec ([int] $config.ConnectTimeoutSec) `
    -RemoteCommand $remoteCommand `
    -AllowFailure

$ok = ($result.exit_code -eq 0)
$status = New-StatusObject -ScriptName "submit-job.ps1" -Ok $ok -ExperimentId $ExperimentId -Details @{
    remote_entry = $entry
    remote_config = [string] $training["PmtConfig"]
    project_root = [string] $training["RemoteProjectRoot"]
    python_bin = [string] $training["PythonBin"]
    data_root = [string] $training["DataRoot"]
    pmt_config = [string] $training["PmtConfig"]
    pretrained = [string] $training["Pretrained"]
    gpu = [string] $training["Gpu"]
    exit_code = $result.exit_code
    output = $result.output
}

$outPath = Get-StatusFilePath -ProjectRoot $projectRoot -ExperimentId $ExperimentId -Name "submit-job"
Write-StatusJson -Data $status -Path $outPath -Json:$Json

if (-not $ok) {
    exit 1
}
