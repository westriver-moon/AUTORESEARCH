param(
    [Parameter(Mandatory = $true)]
    [string] $ExperimentId,
    [string] $RemoteHost = "",
    [string] $SshConfigPath = "",
    [switch] $Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$remoteScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $remoteScriptRoot "lib\common.ps1")
. (Join-Path $remoteScriptRoot "lib\ssh.ps1")
. (Join-Path $remoteScriptRoot "lib\result.ps1")
. (Join-Path $remoteScriptRoot "lib\training.ps1")

Assert-ExperimentId -ExperimentId $ExperimentId
$projectRoot = Get-ProjectRoot -RemoteScriptRoot $remoteScriptRoot
$config = Get-RemoteConfig -ProjectRoot $projectRoot
if (-not [string]::IsNullOrWhiteSpace($RemoteHost)) { $config.RemoteHost = $RemoteHost }
if (-not [string]::IsNullOrWhiteSpace($SshConfigPath)) { $config.SshConfigPath = $SshConfigPath }

$entry = [string] $config.RemoteCancelEntry
Assert-RemotePath -Path $entry -Name "RemoteCancelEntry"

$cmdText = "test -x " + (Quote-PosixSingle $entry) + " && " + (Quote-PosixSingle $entry) + " --experiment-id " + (Quote-PosixSingle $ExperimentId)
$cmdText = Add-RemoteRootExport -CommandText $cmdText -RemoteWorkspaceRoot ([string] $config.RemoteWorkspaceRoot)
$remoteCommand = "bash -lc " + (Quote-PosixSingle $cmdText)
$result = Invoke-RemoteSsh `
    -RemoteHost ([string] $config.RemoteHost) `
    -SshConfigPath ([string] $config.SshConfigPath) `
    -ConnectTimeoutSec ([int] $config.ConnectTimeoutSec) `
    -RemoteCommand $remoteCommand `
    -AllowFailure

$ok = ($result.exit_code -eq 0)
$status = New-StatusObject -ScriptName "cancel-own-job.ps1" -Ok $ok -ExperimentId $ExperimentId -Details @{
    remote_entry = $entry
    exit_code = $result.exit_code
    output = $result.output
}

$outPath = Get-StatusFilePath -ProjectRoot $projectRoot -ExperimentId $ExperimentId -Name "cancel-own-job"
Write-StatusJson -Data $status -Path $outPath -Json:$Json

if (-not $ok) {
    exit 1
}
