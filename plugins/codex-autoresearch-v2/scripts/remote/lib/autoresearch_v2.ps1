Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-DefaultAutoresearchV2Config {
    return @{
        ProgramPath = "autoresearch/program-example.md"
        TargetPath = "autoresearch/targets/example-cpu.yaml"
        LocalRunRoot = "autoresearch-runs"
        BranchPrefix = "autoresearch/"
        DefaultWorkerCount = 1
        DefaultBudgetMinutes = 30
        DefaultKeepThreshold = "0.0"
        DefaultLeaseWaitSeconds = 300
        RemoteControllerRoot = "/home/research/autoresearch-v2"
        RemoteRunRoot = "/home/research/autoresearch-v2/runs"
        RemoteWorktreeRoot = "/home/research/autoresearch-v2/worktrees"
        RemoteLeaseRoot = "/home/research/autoresearch-v2/leases"
        RemoteBridgeEntry = "/home/research/bin/run_autoresearch_v2_bridge.sh"
    }
}

function Get-AutoresearchV2Config {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot,
        [string] $RemoteProfile = ""
    )

    $config = Get-DefaultAutoresearchV2Config
    $configuration = Get-AutoresearchConfiguration -ProjectRoot $ProjectRoot
    foreach ($key in @($config.Keys)) {
        if ($configuration.ContainsKey($key)) {
            $config[$key] = $configuration[$key]
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($RemoteProfile)) {
        if (-not $configuration.ContainsKey("RemoteProfiles")) {
            throw "Remote profile '$RemoteProfile' cannot supply runtime settings because RemoteProfiles is not configured."
        }
        $profiles = $configuration.RemoteProfiles
        if (-not ($profiles -is [hashtable]) -or (-not $profiles.ContainsKey($RemoteProfile))) {
            throw "Remote profile '$RemoteProfile' was not found in RemoteProfiles."
        }
        $profile = $profiles[$RemoteProfile]
        if (-not ($profile -is [hashtable])) {
            throw "RemoteProfiles['$RemoteProfile'] must be a hashtable."
        }
        foreach ($key in @($config.Keys)) {
            if ($profile.ContainsKey($key)) {
                $config[$key] = $profile[$key]
            }
        }
    }
    return $config
}

function Resolve-AutoresearchV2LocalPath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string] $PathValue
    )

    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        return ""
    }
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return (Resolve-Path -LiteralPath $PathValue).Path
    }
    return (Resolve-Path -LiteralPath (Join-Path $ProjectRoot $PathValue)).Path
}

function Get-PosixParentPath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $PathValue
    )

    $normalized = $PathValue.Replace("\", "/")
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        throw "PathValue must not be empty."
    }
    if ($normalized -eq "/") {
        return "/"
    }
    $trimmed = $normalized.TrimEnd("/")
    $lastSlash = $trimmed.LastIndexOf("/")
    if ($lastSlash -lt 0) {
        return "."
    }
    if ($lastSlash -eq 0) {
        return "/"
    }
    return $trimmed.Substring(0, $lastSlash)
}

function Get-AutoresearchV2LocalRunDir {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot,
        [Parameter(Mandatory = $true)]
        [hashtable] $Config,
        [Parameter(Mandatory = $true)]
        [string] $RunTag
    )

    return Join-Path $ProjectRoot (Join-Path ([string] $Config.LocalRunRoot) $RunTag)
}

function Ensure-AutoresearchV2LocalRunDir {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot,
        [Parameter(Mandatory = $true)]
        [hashtable] $Config,
        [Parameter(Mandatory = $true)]
        [string] $RunTag
    )

    $dir = Get-AutoresearchV2LocalRunDir -ProjectRoot $ProjectRoot -Config $Config -RunTag $RunTag
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Ensure-RemoteDirectory {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $RemoteAccess,
        [Parameter(Mandatory = $true)]
        [string] $RemotePath
    )

    Assert-RemotePath -Path $RemotePath -Name "RemotePath"
    $command = "bash -lc " + (Quote-PosixSingle ("mkdir -p " + (Quote-PosixSingle $RemotePath)))
    Invoke-AutoresearchRemoteCommand -Access $RemoteAccess -RemoteCommand $command | Out-Null
}

function Convert-BridgeOutput {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Text
    )

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return $null
    }
    return $Text | ConvertFrom-Json
}

function Invoke-AutoresearchV2Bridge {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $RemoteAccess,
        [Parameter(Mandatory = $true)]
        [hashtable] $V2Config,
        [Parameter(Mandatory = $true)]
        [string[]] $Arguments,
        [switch] $AllowFailure
    )

    $bridge = [string] $V2Config.RemoteBridgeEntry
    Assert-RemotePath -Path $bridge -Name "RemoteBridgeEntry"
    $cmdText = "test -x " + (Quote-PosixSingle $bridge) + " && " + (Quote-PosixSingle $bridge)
    foreach ($argument in $Arguments) {
        $cmdText += " " + (Quote-PosixSingle $argument)
    }
    $remoteCommand = "bash -lc " + (Quote-PosixSingle $cmdText)
    return Invoke-AutoresearchRemoteCommand `
        -Access $RemoteAccess `
        -RemoteCommand $remoteCommand `
        -AllowFailure:$AllowFailure
}

function Invoke-AutoresearchContractValidation {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ScriptPath,
        [Parameter(Mandatory = $true)]
        [ValidateSet("validate-program", "validate-target")]
        [string] $Command,
        [Parameter(Mandatory = $true)]
        [string] $InputPath
    )

    $output = & python $ScriptPath $Command --path $InputPath 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($output | Out-String)
    }
    return ($output | Out-String).Trim()
}

function Get-AutoresearchV2RemoteRunRoot {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $Config,
        [Parameter(Mandatory = $true)]
        [string] $RunTag
    )

    return ([string] $Config.RemoteRunRoot).TrimEnd("/") + "/" + $RunTag
}
