Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-DefaultTrainingConfig {
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

function Get-TrainingConfig {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot,
        [Parameter(Mandatory = $false)]
        [string] $Path = ""
    )

    $trainingConfig = Get-DefaultTrainingConfig
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
            $trainingConfig[$key] = $loaded[$key]
        }
    }

    return $trainingConfig
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

function Add-RemoteRootExport {
    param(
        [Parameter(Mandatory = $true)]
        [string] $CommandText,
        [Parameter(Mandatory = $true)]
        [string] $RemoteWorkspaceRoot
    )

    Assert-RemotePath -Path $RemoteWorkspaceRoot -Name "RemoteWorkspaceRoot"
    return "REMOTE_ROOT=" + (Quote-PosixSingle $RemoteWorkspaceRoot) + "; export REMOTE_ROOT; " + $CommandText
}

function Assert-TrainingRemotePaths {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $Training
    )

    foreach ($name in @("RemoteProjectRoot", "PythonBin", "DataRoot", "PmtConfig", "Pretrained")) {
        $value = [string] $Training[$name]
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            Assert-RemotePath -Path $value -Name $name
        }
    }
}

function Assert-TrainingGpu {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $Training
    )

    $effectiveGpu = [string] $Training["Gpu"]
    if ((-not [string]::IsNullOrWhiteSpace($effectiveGpu)) -and ($effectiveGpu -notmatch '^[0-9,]+$') -and ($effectiveGpu.ToLowerInvariant() -ne "auto")) {
        throw "Gpu must be 'auto' or contain only digits and commas: $effectiveGpu"
    }
}

function Add-TrainingRemoteArgs {
    param(
        [Parameter(Mandatory = $true)]
        [string] $CommandText,
        [Parameter(Mandatory = $true)]
        [hashtable] $Training
    )

    $CommandText = Add-RemoteArg -CommandText $CommandText -Name "project-root" -Value ([string] $Training["RemoteProjectRoot"])
    $CommandText = Add-RemoteArg -CommandText $CommandText -Name "python" -Value ([string] $Training["PythonBin"])
    $CommandText = Add-RemoteArg -CommandText $CommandText -Name "data-root" -Value ([string] $Training["DataRoot"])
    $CommandText = Add-RemoteArg -CommandText $CommandText -Name "config" -Value ([string] $Training["PmtConfig"])
    $CommandText = Add-RemoteArg -CommandText $CommandText -Name "pretrained" -Value ([string] $Training["Pretrained"])
    $CommandText = Add-RemoteArg -CommandText $CommandText -Name "gpu" -Value ([string] $Training["Gpu"])
    return $CommandText
}
