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

$entry = [string] $config.RemoteStatusEntry
Assert-RemotePath -Path $entry -Name "RemoteStatusEntry"

$cmdText = "test -x " + (Quote-PosixSingle $entry) + " && " + (Quote-PosixSingle $entry) + " --experiment-id " + (Quote-PosixSingle $ExperimentId)
$cmdText = Add-RemoteRootExport -CommandText $cmdText -RemoteWorkspaceRoot ([string] $config.RemoteWorkspaceRoot)
$remoteCommand = "bash -lc " + (Quote-PosixSingle $cmdText)
$result = Invoke-RemoteSsh `
    -RemoteHost ([string] $config.RemoteHost) `
    -SshConfigPath ([string] $config.SshConfigPath) `
    -ConnectTimeoutSec ([int] $config.ConnectTimeoutSec) `
    -RemoteCommand $remoteCommand `
    -AllowFailure
$remoteState = ""
if (-not [string]::IsNullOrWhiteSpace($result.output)) {
    try {
        $remoteStatus = $result.output | ConvertFrom-Json
        if ($null -ne $remoteStatus.PSObject.Properties["state"]) {
            $remoteState = [string] $remoteStatus.state
        }
    } catch {
        $remoteState = ""
    }
}

$ok = (($result.exit_code -eq 0) -and ($remoteState -ne "not_found"))
$status = New-StatusObject -ScriptName "check-job.ps1" -Ok $ok -ExperimentId $ExperimentId -Details @{
    remote_entry = $entry
    exit_code = $result.exit_code
    remote_state = $remoteState
    output = $result.output
}

$outPath = Get-StatusFilePath -ProjectRoot $projectRoot -ExperimentId $ExperimentId -Name "status"
Write-StatusJson -Data $status -Path $outPath -Json:$Json

if (-not $ok) {
    exit 1
}
