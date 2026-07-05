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
. (Join-Path $remoteScriptRoot "lib\paths.ps1")
. (Join-Path $remoteScriptRoot "lib\result.ps1")

Assert-ExperimentId -ExperimentId $ExperimentId
$projectRoot = Get-ProjectRoot -RemoteScriptRoot $remoteScriptRoot
$config = Get-RemoteConfig -ProjectRoot $projectRoot
if (-not [string]::IsNullOrWhiteSpace($RemoteHost)) { $config.RemoteHost = $RemoteHost }
if (-not [string]::IsNullOrWhiteSpace($SshConfigPath)) { $config.SshConfigPath = $SshConfigPath }

$localDir = New-ExperimentRemoteDir -ProjectRoot $projectRoot -ExperimentId $ExperimentId
$remoteExperimentRoot = Get-RemoteExperimentRoot -Config $config -ExperimentId $ExperimentId
$remoteResults = Join-RemotePath -Left $remoteExperimentRoot -Right "results"
Assert-RemotePath -Path $remoteResults -Name "remoteResults"

$fetched = @()
$targets = @(
    @{ Name = "metrics.json"; Recurse = $false },
    @{ Name = "summary.json"; Recurse = $false },
    @{ Name = "config_used.yaml"; Recurse = $false },
    @{ Name = "logs"; Recurse = $true },
    @{ Name = "error_samples"; Recurse = $true }
)
foreach ($targetSpec in $targets) {
    $target = [string] $targetSpec.Name
    $remotePath = Join-RemotePath -Left $remoteResults -Right $target
    $existsCommand = "bash -lc " + (Quote-PosixSingle "test -e '$remotePath'")
    $exists = Invoke-RemoteSsh `
        -RemoteHost ([string] $config.RemoteHost) `
        -SshConfigPath ([string] $config.SshConfigPath) `
        -ConnectTimeoutSec ([int] $config.ConnectTimeoutSec) `
        -RemoteCommand $existsCommand `
        -AllowFailure

    if ($exists.exit_code -eq 0) {
        $localTarget = Join-Path $localDir $target
        $recurse = [bool] $targetSpec.Recurse
        Invoke-RemoteScpFrom `
            -RemoteHost ([string] $config.RemoteHost) `
            -SshConfigPath ([string] $config.SshConfigPath) `
            -RemotePath $remotePath `
            -LocalPath $localTarget `
            -Recurse:$recurse | Out-Null
        $fetched += $target
    }
}

$ok = ($fetched.Count -gt 0)
$details = @{
    remote_results = $remoteResults
    local_dir = $localDir
    fetched = $fetched
}
if (-not $ok) {
    $details["reason"] = "no_result_files_fetched"
}

$status = New-StatusObject -ScriptName "fetch-results.ps1" -Ok $ok -ExperimentId $ExperimentId -Details $details

$outPath = Get-StatusFilePath -ProjectRoot $projectRoot -ExperimentId $ExperimentId -Name "fetch-results"
Write-StatusJson -Data $status -Path $outPath -Json:$Json

if (-not $ok) {
    exit 1
}
