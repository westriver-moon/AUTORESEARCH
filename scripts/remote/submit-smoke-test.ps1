param(
    [Parameter(Mandatory = $true)]
    [string] $ExperimentId,
    [string] $RemoteConfigPath = "",
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

Assert-ExperimentId -ExperimentId $ExperimentId
$projectRoot = Get-ProjectRoot -RemoteScriptRoot $remoteScriptRoot
$config = Get-RemoteConfig -ProjectRoot $projectRoot
if (-not [string]::IsNullOrWhiteSpace($RemoteHost)) { $config.RemoteHost = $RemoteHost }
if (-not [string]::IsNullOrWhiteSpace($SshConfigPath)) { $config.SshConfigPath = $SshConfigPath }

$entry = [string] $config.RemoteSmokeEntry
Assert-RemotePath -Path $entry -Name "RemoteSmokeEntry"

$remoteExperimentRoot = Get-RemoteExperimentRoot -Config $config -ExperimentId $ExperimentId
if ([string]::IsNullOrWhiteSpace($RemoteConfigPath)) {
    $RemoteConfigPath = Join-RemotePath -Left $remoteExperimentRoot -Right "experiment-contract.yaml"
}
Assert-RemotePath -Path $RemoteConfigPath -Name "RemoteConfigPath"

$cmdText = "test -x '$entry' && '$entry' --experiment-id '$ExperimentId' --config '$RemoteConfigPath'"
$remoteCommand = "bash -lc " + (Quote-PosixSingle $cmdText)
$result = Invoke-RemoteSsh `
    -RemoteHost ([string] $config.RemoteHost) `
    -SshConfigPath ([string] $config.SshConfigPath) `
    -ConnectTimeoutSec ([int] $config.ConnectTimeoutSec) `
    -RemoteCommand $remoteCommand `
    -AllowFailure

$ok = ($result.exit_code -eq 0)
$status = New-StatusObject -ScriptName "submit-smoke-test.ps1" -Ok $ok -ExperimentId $ExperimentId -Details @{
    remote_entry = $entry
    remote_config = $RemoteConfigPath
    exit_code = $result.exit_code
    output = $result.output
}

$outPath = Get-StatusFilePath -ProjectRoot $projectRoot -ExperimentId $ExperimentId -Name "submit-smoke-test"
Write-StatusJson -Data $status -Path $outPath -Json:$Json

if (-not $ok) {
    exit 1
}

