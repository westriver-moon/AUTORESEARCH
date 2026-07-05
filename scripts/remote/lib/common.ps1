Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-ProjectRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string] $RemoteScriptRoot
    )

    $scriptsDir = Split-Path -Parent $RemoteScriptRoot
    return (Resolve-Path (Join-Path $scriptsDir "..")).Path
}

function Get-DefaultRemoteConfig {
    $sshConfig = Join-Path $env:USERPROFILE ".ssh\config"

    return @{
        RemoteHost = "lab-server"
        TunnelAlias = "lab-server-codex-tunnel"
        SshConfigPath = $sshConfig
        LocalTunnelScript = ""
        ProxyTaskName = "CodexProxyTunnelLabServer-Every5Min"
        RemoteProxyRoot = "/home/cgv841/ybj/non_research/codex_proxy"
        RemoteWorkspaceRoot = "/home/cgv841/ybj"
        RemoteAutoresearchTrialEntry = "/home/cgv841/ybj/bin/run_autoresearch_trial.sh"
        RemoteSmokeEntry = "/home/cgv841/ybj/bin/run_smoke_test.sh"
        RemoteTrainEntry = "/home/cgv841/ybj/bin/run_train.sh"
        RemoteStatusEntry = "/home/cgv841/ybj/bin/check_job.sh"
        RemoteCancelEntry = "/home/cgv841/ybj/bin/cancel_job.sh"
        ConnectTimeoutSec = 15
        ProxyPort = 7897
    }
}

function Get-RemoteConfig {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot
    )

    $config = Get-DefaultRemoteConfig
    $localConfig = Join-Path $ProjectRoot "config\remote.local.psd1"

    if (Test-Path -LiteralPath $localConfig) {
        $loaded = Import-PowerShellDataFile -LiteralPath $localConfig
        foreach ($key in $loaded.Keys) {
            $config[$key] = $loaded[$key]
        }
    }

    if ([string]::IsNullOrWhiteSpace([string] $config.SshConfigPath)) {
        $config.SshConfigPath = Join-Path $env:USERPROFILE ".ssh\config"
    }

    return $config
}

function Assert-ExperimentId {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ExperimentId
    )

    if ($ExperimentId -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$') {
        throw "Invalid ExperimentId '$ExperimentId'."
    }
}

function Assert-RemotePath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path,
        [Parameter(Mandatory = $true)]
        [string] $Name
    )

    if ($Path -notmatch '^[A-Za-z0-9_./:=@+-]+$') {
        throw "$Name contains unsupported characters: $Path"
    }
    if ($Path.Contains("..")) {
        throw "$Name must not contain '..': $Path"
    }
}

function Quote-PosixSingle {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Value
    )

    return "'" + $Value.Replace("'", "'\''") + "'"
}

function Find-LocalTunnelScript {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $Config
    )

    if (-not [string]::IsNullOrWhiteSpace([string] $Config.LocalTunnelScript)) {
        if (Test-Path -LiteralPath ([string] $Config.LocalTunnelScript)) {
            return (Resolve-Path -LiteralPath ([string] $Config.LocalTunnelScript)).Path
        }
        throw "Configured LocalTunnelScript was not found: $($Config.LocalTunnelScript)"
    }

    $desktop = Join-Path $env:USERPROFILE "Desktop"
    if (Test-Path -LiteralPath $desktop) {
        $match = Get-ChildItem -LiteralPath $desktop -Recurse -Filter "ensure-codex-proxy-tunnel.ps1" -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($null -ne $match) {
            return $match.FullName
        }
    }

    return ""
}

function New-ExperimentRemoteDir {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string] $ExperimentId
    )

    Assert-ExperimentId -ExperimentId $ExperimentId
    $dir = Join-Path $ProjectRoot (Join-Path "experiments" (Join-Path $ExperimentId "remote"))
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Write-StatusJson {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Data,
        [Parameter(Mandatory = $false)]
        [string] $Path,
        [switch] $Json
    )

    $jsonText = $Data | ConvertTo-Json -Depth 8
    if (-not [string]::IsNullOrWhiteSpace($Path)) {
        Set-Content -LiteralPath $Path -Value $jsonText -Encoding UTF8
    }
    if ($Json) {
        Write-Output $jsonText
    } else {
        Write-Output $Data
    }
}

function New-StatusObject {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ScriptName,
        [Parameter(Mandatory = $true)]
        [bool] $Ok,
        [Parameter(Mandatory = $false)]
        [string] $ExperimentId = "",
        [Parameter(Mandatory = $false)]
        [hashtable] $Details = @{}
    )

    return [pscustomobject] @{
        script = $ScriptName
        ok = $Ok
        experiment_id = $ExperimentId
        timestamp = (Get-Date).ToString("o")
        details = $Details
    }
}
