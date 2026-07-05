param(
    [Parameter(Mandatory = $true)]
    [string] $ExperimentId,
    [Parameter(Mandatory = $true)]
    [string] $SourcePath,
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

$resolvedSource = (Resolve-Path -LiteralPath $SourcePath).Path
$resolvedProject = (Resolve-Path -LiteralPath $projectRoot).Path
if (-not $resolvedSource.StartsWith($resolvedProject, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "SourcePath must stay inside project root."
}

$remoteExperimentRoot = Get-RemoteExperimentRoot -Config $config -ExperimentId $ExperimentId
$remoteWorkspace = Join-RemotePath -Left $remoteExperimentRoot -Right "workspace"
Assert-RemotePath -Path $remoteWorkspace -Name "remoteWorkspace"

$mkdirCommand = "bash -lc " + (Quote-PosixSingle "mkdir -p '$remoteWorkspace'")
Invoke-RemoteSsh `
    -RemoteHost ([string] $config.RemoteHost) `
    -SshConfigPath ([string] $config.SshConfigPath) `
    -ConnectTimeoutSec ([int] $config.ConnectTimeoutSec) `
    -RemoteCommand $mkdirCommand | Out-Null

$isDir = (Get-Item -LiteralPath $resolvedSource).PSIsContainer
Invoke-RemoteScpTo `
    -RemoteHost ([string] $config.RemoteHost) `
    -SshConfigPath ([string] $config.SshConfigPath) `
    -LocalPath $resolvedSource `
    -RemotePath ($remoteWorkspace + "/") `
    -Recurse:$isDir | Out-Null

$status = New-StatusObject -ScriptName "sync-code.ps1" -Ok $true -ExperimentId $ExperimentId -Details @{
    source = $resolvedSource
    remote_workspace = $remoteWorkspace
}

$outPath = Get-StatusFilePath -ProjectRoot $projectRoot -ExperimentId $ExperimentId -Name "sync"
Write-StatusJson -Data $status -Path $outPath -Json:$Json

