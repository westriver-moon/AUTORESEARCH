param(
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

$projectRoot = Get-ProjectRoot -RemoteScriptRoot $remoteScriptRoot
$config = Get-RemoteConfig -ProjectRoot $projectRoot
if (-not [string]::IsNullOrWhiteSpace($RemoteHost)) { $config.RemoteHost = $RemoteHost }
if (-not [string]::IsNullOrWhiteSpace($SshConfigPath)) { $config.SshConfigPath = $SshConfigPath }

$localRemoteBin = Join-Path $remoteScriptRoot "remote-bin"
if (-not (Test-Path -LiteralPath $localRemoteBin)) {
    throw "Local remote-bin directory was not found: $localRemoteBin"
}

$remoteBin = Join-RemotePath -Left ([string] $config.RemoteWorkspaceRoot) -Right "bin"
Assert-RemotePath -Path $remoteBin -Name "remoteBin"

$mkdirCommand = "bash -lc " + (Quote-PosixSingle ("mkdir -p " + (Quote-PosixSingle $remoteBin)))
Invoke-RemoteSsh `
    -RemoteHost ([string] $config.RemoteHost) `
    -SshConfigPath ([string] $config.SshConfigPath) `
    -ConnectTimeoutSec ([int] $config.ConnectTimeoutSec) `
    -RemoteCommand $mkdirCommand | Out-Null

$uploaded = @()
$chmodTargets = @()
Get-ChildItem -LiteralPath $localRemoteBin -Filter "*.sh" -File | ForEach-Object {
    $remotePath = Join-RemotePath -Left $remoteBin -Right $_.Name
    Assert-RemotePath -Path $remotePath -Name "remotePath"
    Invoke-RemoteScpTo `
        -RemoteHost ([string] $config.RemoteHost) `
        -SshConfigPath ([string] $config.SshConfigPath) `
        -LocalPath $_.FullName `
        -RemotePath $remotePath | Out-Null
    $uploaded += $_.Name
    $chmodTargets += (Quote-PosixSingle $remotePath)
}

if ($chmodTargets.Count -gt 0) {
    $chmodCommand = "bash -lc " + (Quote-PosixSingle ("chmod 700 " + ($chmodTargets -join " ")))
    Invoke-RemoteSsh `
        -RemoteHost ([string] $config.RemoteHost) `
        -SshConfigPath ([string] $config.SshConfigPath) `
        -ConnectTimeoutSec ([int] $config.ConnectTimeoutSec) `
        -RemoteCommand $chmodCommand | Out-Null
}

$status = New-StatusObject -ScriptName "deploy-remote-bin.ps1" -Ok $true -Details @{
    remote_bin = $remoteBin
    uploaded = $uploaded
}

Write-StatusJson -Data $status -Json:$Json
