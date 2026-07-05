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
    [int] $SmokeBatches = 0,
    [int] $MaxSeconds = 0,
    [string] $RemoteHost = "",
    [string] $SshConfigPath = "",
    [switch] $DryRun,
    [switch] $Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$remoteScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $remoteScriptRoot "lib\common.ps1")
. (Join-Path $remoteScriptRoot "lib\ssh.ps1")
. (Join-Path $remoteScriptRoot "lib\paths.ps1")
. (Join-Path $remoteScriptRoot "lib\result.ps1")

function Get-DefaultTrialConfig {
    return @{
        RemoteProjectRoot = ""
        PythonBin = ""
        DataRoot = ""
        PmtConfig = ""
        Pretrained = ""
        Gpu = ""
        SmokeBatches = 1
        MaxSeconds = 300
    }
}

function Get-TrialConfig {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot,
        [Parameter(Mandatory = $false)]
        [string] $Path = ""
    )

    $trialConfig = Get-DefaultTrialConfig
    $candidate = $Path
    if ([string]::IsNullOrWhiteSpace($candidate)) {
        $local = Join-Path $ProjectRoot "config\autoresearch-train.local.psd1"
        $example = Join-Path $ProjectRoot "config\autoresearch-train.example.psd1"
        if (Test-Path -LiteralPath $local) {
            $candidate = $local
        } elseif (Test-Path -LiteralPath $example) {
            $candidate = $example
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($candidate)) {
        $resolved = (Resolve-Path -LiteralPath $candidate).Path
        $loaded = Import-PowerShellDataFile -LiteralPath $resolved
        foreach ($key in $loaded.Keys) {
            $trialConfig[$key] = $loaded[$key]
        }
    }

    return $trialConfig
}

function Add-RemoteArg {
    param(
        [Parameter(Mandatory = $true)]
        [string] $CommandText,
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [Parameter(Mandatory = $true)]
        [string] $Value
    )

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $CommandText
    }
    return $CommandText + " --" + $Name + " " + (Quote-PosixSingle $Value)
}

Assert-ExperimentId -ExperimentId $ExperimentId
$projectRoot = Get-ProjectRoot -RemoteScriptRoot $remoteScriptRoot
$config = Get-RemoteConfig -ProjectRoot $projectRoot
if (-not [string]::IsNullOrWhiteSpace($RemoteHost)) { $config.RemoteHost = $RemoteHost }
if (-not [string]::IsNullOrWhiteSpace($SshConfigPath)) { $config.SshConfigPath = $SshConfigPath }

$trial = Get-TrialConfig -ProjectRoot $projectRoot -Path $TrialConfigPath
if (-not [string]::IsNullOrWhiteSpace($ProjectRootPath)) { $trial["RemoteProjectRoot"] = $ProjectRootPath }
if (-not [string]::IsNullOrWhiteSpace($PythonBin)) { $trial["PythonBin"] = $PythonBin }
if (-not [string]::IsNullOrWhiteSpace($DataRoot)) { $trial["DataRoot"] = $DataRoot }
if (-not [string]::IsNullOrWhiteSpace($RemoteConfigPath)) { $trial["PmtConfig"] = $RemoteConfigPath }
if (-not [string]::IsNullOrWhiteSpace($Pretrained)) { $trial["Pretrained"] = $Pretrained }
if (-not [string]::IsNullOrWhiteSpace($Gpu)) { $trial["Gpu"] = $Gpu }
if ($SmokeBatches -gt 0) { $trial["SmokeBatches"] = $SmokeBatches }
if ($MaxSeconds -gt 0) { $trial["MaxSeconds"] = $MaxSeconds }

$entry = [string] $config.RemoteAutoresearchTrialEntry
Assert-RemotePath -Path $entry -Name "RemoteAutoresearchTrialEntry"

foreach ($name in @("RemoteProjectRoot", "PythonBin", "DataRoot", "PmtConfig", "Pretrained")) {
    $value = [string] $trial[$name]
    if (-not [string]::IsNullOrWhiteSpace($value)) {
        Assert-RemotePath -Path $value -Name $name
    }
}

$effectiveGpu = [string] $trial["Gpu"]
if ((-not [string]::IsNullOrWhiteSpace($effectiveGpu)) -and ($effectiveGpu -notmatch '^[0-9,]+$')) {
    throw "Gpu must contain only digits and commas: $effectiveGpu"
}
$effectiveSmokeBatches = [int] $trial["SmokeBatches"]
$effectiveMaxSeconds = [int] $trial["MaxSeconds"]
if (($effectiveSmokeBatches -lt 1) -or ($effectiveSmokeBatches -gt 10)) {
    throw "SmokeBatches must be between 1 and 10 inclusive. Received: $effectiveSmokeBatches."
}
if (($effectiveMaxSeconds -lt 1) -or ($effectiveMaxSeconds -gt 3600)) {
    throw "MaxSeconds must be between 1 and 3600 inclusive. Received: $effectiveMaxSeconds."
}

$cmdText = "test -x " + (Quote-PosixSingle $entry) + " && " + (Quote-PosixSingle $entry) + " --experiment-id " + (Quote-PosixSingle $ExperimentId)
$cmdText = Add-RemoteArg -CommandText $cmdText -Name "project-root" -Value ([string] $trial["RemoteProjectRoot"])
$cmdText = Add-RemoteArg -CommandText $cmdText -Name "python" -Value ([string] $trial["PythonBin"])
$cmdText = Add-RemoteArg -CommandText $cmdText -Name "data-root" -Value ([string] $trial["DataRoot"])
$cmdText = Add-RemoteArg -CommandText $cmdText -Name "config" -Value ([string] $trial["PmtConfig"])
$cmdText = Add-RemoteArg -CommandText $cmdText -Name "pretrained" -Value ([string] $trial["Pretrained"])
$cmdText = Add-RemoteArg -CommandText $cmdText -Name "gpu" -Value ([string] $trial["Gpu"])
$cmdText += " --smoke-batches " + $effectiveSmokeBatches
$cmdText += " --max-seconds " + $effectiveMaxSeconds
if ($DryRun) { $cmdText += " --dry-run" }

$remoteCommand = "bash -lc " + (Quote-PosixSingle $cmdText)
$result = Invoke-RemoteSsh `
    -RemoteHost ([string] $config.RemoteHost) `
    -SshConfigPath ([string] $config.SshConfigPath) `
    -ConnectTimeoutSec ([int] $config.ConnectTimeoutSec) `
    -RemoteCommand $remoteCommand `
    -AllowFailure

$ok = ($result.exit_code -eq 0)
$status = New-StatusObject -ScriptName "submit-autoresearch-trial.ps1" -Ok $ok -ExperimentId $ExperimentId -Details @{
    remote_entry = $entry
    exit_code = $result.exit_code
    output = $result.output
    project_root = [string] $trial["RemoteProjectRoot"]
    python_bin = [string] $trial["PythonBin"]
    data_root = [string] $trial["DataRoot"]
    pmt_config = [string] $trial["PmtConfig"]
    pretrained = [string] $trial["Pretrained"]
    gpu = [string] $trial["Gpu"]
    smoke_batches = $effectiveSmokeBatches
    max_seconds = $effectiveMaxSeconds
    dry_run = [bool] $DryRun
}

$outPath = Get-StatusFilePath -ProjectRoot $projectRoot -ExperimentId $ExperimentId -Name "autoresearch-trial"
Write-StatusJson -Data $status -Path $outPath -Json:$Json

if (-not $ok) {
    exit 1
}
