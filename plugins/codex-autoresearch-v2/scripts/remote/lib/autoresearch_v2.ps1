Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-DefaultAutoresearchV2Config {
    return @{
        ProgramPath = "autoresearch/program-example.md"
        TargetPath = "autoresearch/targets/example-cpu.yaml"
        LocalRunRoot = "autoresearch-runs"
        LocalRepositoryPath = ""
        LocalGitRemoteName = ""
        LocalGitRemoteUrl = ""
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
    $exitCode = $LASTEXITCODE
    $text = ($output | Out-String).Trim()
    if ($exitCode -ne 0) {
        throw $text
    }
    return ($text | ConvertFrom-Json)
}

function ConvertTo-AutoresearchCommandLineValue {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Value
    )

    if ($Value -match '[\s"]') {
        return '"' + $Value.Replace('"', '""') + '"'
    }
    return $Value
}

function Get-AutoresearchV2GitSshCommand {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $Access
    )

    $ssh = Get-AutoresearchOpenSshExecutable -Name "ssh.exe"
    $config = [string] $Access.SshConfigPath
    return (
        (ConvertTo-AutoresearchCommandLineValue $ssh) +
        " -F " +
        (ConvertTo-AutoresearchCommandLineValue $config) +
        " -o BatchMode=yes"
    )
}

function Invoke-AutoresearchV2Git {
    param(
        [Parameter(Mandatory = $true)]
        [string] $RepositoryPath,
        [Parameter(Mandatory = $true)]
        [string[]] $Arguments,
        [string] $GitSshCommand = "",
        [switch] $AllowFailure
    )

    $previousSsh = ""
    $hadPreviousSsh = $false
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    if (-not [string]::IsNullOrWhiteSpace($GitSshCommand)) {
        $previousSsh = [Environment]::GetEnvironmentVariable("GIT_SSH_COMMAND")
        $hadPreviousSsh = $null -ne $previousSsh
        [Environment]::SetEnvironmentVariable("GIT_SSH_COMMAND", $GitSshCommand)
    }
    try {
        $output = & git -C $RepositoryPath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
        $text = ($output | Out-String).Trim()
        if (($exitCode -ne 0) -and (-not $AllowFailure)) {
            throw "git failed with exit code ${exitCode}: $text"
        }
        return [pscustomobject]@{ exit_code = $exitCode; output = $text }
    } finally {
        $ErrorActionPreference = $previousErrorAction
        if ($hadPreviousSsh) {
            [Environment]::SetEnvironmentVariable("GIT_SSH_COMMAND", $previousSsh)
        } elseif (-not [string]::IsNullOrWhiteSpace($GitSshCommand)) {
            [Environment]::SetEnvironmentVariable("GIT_SSH_COMMAND", $null)
        }
    }
}

function Resolve-AutoresearchV2LocalRepositoryPath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot,
        [Parameter(Mandatory = $true)]
        [hashtable] $Config
    )

    $value = [string] $Config.LocalRepositoryPath
    if ([string]::IsNullOrWhiteSpace($value)) {
        return ""
    }
    if ([System.IO.Path]::IsPathRooted($value)) {
        return $value
    }
    return Join-Path $ProjectRoot $value
}

function Get-AutoresearchV2LocalGitRemoteName {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $Config,
        [Parameter(Mandatory = $true)]
        [hashtable] $Access
    )

    $value = [string] $Config.LocalGitRemoteName
    if ([string]::IsNullOrWhiteSpace($value)) {
        $profile = if ($Access.ContainsKey("SelectedRemoteProfile")) { [string] $Access.SelectedRemoteProfile } else { "" }
        if ([string]::IsNullOrWhiteSpace($profile)) {
            throw "LocalGitRemoteName is required when LocalRepositoryPath is configured."
        }
        $value = "ar2-" + ($profile -replace '[^A-Za-z0-9._-]', '-')
    }
    if ($value -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$') {
        throw "LocalGitRemoteName must be a valid git remote name: $value"
    }
    return $value
}

function Ensure-LocalAutoresearchV2GitRemote {
    param(
        [Parameter(Mandatory = $true)]
        [string] $RepositoryPath,
        [Parameter(Mandatory = $true)]
        [string] $RemoteName,
        [Parameter(Mandatory = $true)]
        [string] $RemoteUrl,
        [string] $GitSshCommand = ""
    )

    $existing = Invoke-AutoresearchV2Git `
        -RepositoryPath $RepositoryPath `
        -Arguments @("remote", "get-url", $RemoteName) `
        -GitSshCommand $GitSshCommand `
        -AllowFailure
    if ($existing.exit_code -ne 0) {
        $null = Invoke-AutoresearchV2Git `
            -RepositoryPath $RepositoryPath `
            -Arguments @("remote", "add", $RemoteName, $RemoteUrl) `
            -GitSshCommand $GitSshCommand
    } elseif ($existing.output -ne $RemoteUrl) {
        $null = Invoke-AutoresearchV2Git `
            -RepositoryPath $RepositoryPath `
            -Arguments @("remote", "set-url", $RemoteName, $RemoteUrl) `
            -GitSshCommand $GitSshCommand
    }
    return $RemoteUrl
}

function Get-AutoresearchV2RunBranchRefPattern {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $Config,
        [Parameter(Mandatory = $true)]
        [string] $RunTag
    )

    $prefix = ([string] $Config.BranchPrefix).TrimEnd("/")
    if ([string]::IsNullOrWhiteSpace($prefix)) {
        $prefix = "autoresearch"
    }
    return $prefix + "/" + $RunTag + "-*"
}

function Invoke-AutoresearchV2LocalFetch {
    param(
        [Parameter(Mandatory = $true)]
        [string] $RepositoryPath,
        [Parameter(Mandatory = $true)]
        [string] $RemoteName,
        [Parameter(Mandatory = $true)]
        [string] $RefPattern,
        [string] $GitSshCommand = ""
    )

    $refspec = "+refs/heads/" + $RefPattern + ":refs/remotes/" + $RemoteName + "/" + $RefPattern
    return Invoke-AutoresearchV2Git `
        -RepositoryPath $RepositoryPath `
        -Arguments @("fetch", $RemoteName, $refspec) `
        -GitSshCommand $GitSshCommand
}

function Invoke-AutoresearchV2LocalFetchBranch {
    param(
        [Parameter(Mandatory = $true)]
        [string] $RepositoryPath,
        [Parameter(Mandatory = $true)]
        [string] $RemoteName,
        [Parameter(Mandatory = $true)]
        [string] $Branch,
        [string] $GitSshCommand = ""
    )

    $refspec = "+refs/heads/" + $Branch + ":refs/remotes/" + $RemoteName + "/" + $Branch
    return Invoke-AutoresearchV2Git `
        -RepositoryPath $RepositoryPath `
        -Arguments @("fetch", $RemoteName, $refspec) `
        -GitSshCommand $GitSshCommand
}

function Sync-AutoresearchV2LocalRepository {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $Access,
        [Parameter(Mandatory = $true)]
        [hashtable] $Config,
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string] $RunTag,
        [string] $TargetPath = "",
        [string] $ContractValidator = "",
        [string] $RemoteUrl = "",
        [string] $FetchBranch = "",
        [string] $CheckoutBranch = "",
        [switch] $Checkout
    )

    $localRepo = Resolve-AutoresearchV2LocalRepositoryPath -ProjectRoot $ProjectRoot -Config $Config
    if ([string]::IsNullOrWhiteSpace($localRepo)) {
        return $null
    }
    if (-not (Test-Path -LiteralPath (Join-Path $localRepo ".git"))) {
        throw "LocalRepositoryPath is not a git repository: $localRepo"
    }

    $remoteName = Get-AutoresearchV2LocalGitRemoteName -Config $Config -Access $Access
    if ([string]::IsNullOrWhiteSpace($RemoteUrl)) {
        $configuredRemoteUrl = [string] $Config.LocalGitRemoteUrl
        if (-not [string]::IsNullOrWhiteSpace($configuredRemoteUrl)) {
            $RemoteUrl = $configuredRemoteUrl
        } else {
            if ([string]::IsNullOrWhiteSpace($ContractValidator)) {
                throw "ContractValidator is required when RemoteUrl is not provided."
            }
            if ([string]::IsNullOrWhiteSpace($TargetPath)) {
                $TargetPath = [string] $Config.TargetPath
            }
            $validated = Invoke-AutoresearchContractValidation `
                -ScriptPath $ContractValidator `
                -Command validate-target `
                -InputPath (Resolve-AutoresearchV2LocalPath -ProjectRoot $ProjectRoot -PathValue $TargetPath)
            $RemoteUrl = ([string] $Access.RemoteHost).TrimEnd("/") + ":" + [string] $validated.target.repo.path
        }
    }

    $gitSshCommand = Get-AutoresearchV2GitSshCommand -Access $Access
    $null = Ensure-LocalAutoresearchV2GitRemote `
        -RepositoryPath $localRepo `
        -RemoteName $remoteName `
        -RemoteUrl $RemoteUrl `
        -GitSshCommand $gitSshCommand

    $refPattern = Get-AutoresearchV2RunBranchRefPattern -Config $Config -RunTag $RunTag
    $null = Invoke-AutoresearchV2LocalFetch `
        -RepositoryPath $localRepo `
        -RemoteName $remoteName `
        -RefPattern $refPattern `
        -GitSshCommand $gitSshCommand

    if ([string]::IsNullOrWhiteSpace($FetchBranch) -and $Checkout -and -not [string]::IsNullOrWhiteSpace($CheckoutBranch)) {
        $FetchBranch = $CheckoutBranch
    }
    if (-not [string]::IsNullOrWhiteSpace($FetchBranch)) {
        $null = Invoke-AutoresearchV2LocalFetchBranch `
            -RepositoryPath $localRepo `
            -RemoteName $remoteName `
            -Branch $FetchBranch `
            -GitSshCommand $gitSshCommand
    }
    $fetchedBranches = @($refPattern)
    if (-not [string]::IsNullOrWhiteSpace($FetchBranch)) {
        $fetchedBranches += $FetchBranch
    }

    $checkedOut = ""
    if ($Checkout) {
        if ([string]::IsNullOrWhiteSpace($CheckoutBranch)) {
            throw "CheckoutBranch is required when Checkout is requested."
        }
        $remoteRef = "refs/remotes/" + $remoteName + "/" + $CheckoutBranch
        $null = Invoke-AutoresearchV2Git `
            -RepositoryPath $localRepo `
            -Arguments @("checkout", "-B", $CheckoutBranch, $remoteRef) `
            -GitSshCommand $gitSshCommand
        $checkedOut = $CheckoutBranch
    }

    return [pscustomobject]@{
        repository = $localRepo
        remote = $remoteName
        remote_url = $RemoteUrl
        ref_pattern = $refPattern
        fetched_branches = $fetchedBranches
        checkout = $checkedOut
    }
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
