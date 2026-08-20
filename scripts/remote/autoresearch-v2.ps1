param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("access-doctor", "access-ensure", "deploy", "doctor", "bootstrap", "inspect", "apply", "baseline", "run", "resume", "status", "collect", "stop", "sync-best", "sync")]
    [string] $Mode,
    [string] $RunTag = "",
    [string] $ProgramPath = "",
    [string] $TargetPath = "",
    [string] $Worker = "w1",
    [switch] $AllWorkers,
    [string] $SourcePath = "",
    [string] $Note = "",
    [string] $CheckoutBranch = "",
    [switch] $Checkout,
    [int] $WorkerCount = 0,
    [int] $BudgetMinutes = 0,
    [string] $KeepThreshold = "",
    [string] $SimulateMetric = "",
    [switch] $Foreground,
    [string] $RemoteProfile = "",
    [string] $RemoteHost = "",
    [string] $SshConfigPath = "",
    [switch] $Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$remoteScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $remoteScriptRoot "lib\common.ps1")
. (Join-Path $remoteScriptRoot "lib\config.ps1")
. (Join-Path $remoteScriptRoot "lib\profile_session_state.ps1")
. (Join-Path $remoteScriptRoot "lib\remote_access.ps1")
. (Join-Path $remoteScriptRoot "lib\autoresearch_v2.ps1")

$projectRoot = Get-ProjectRoot -RemoteScriptRoot $remoteScriptRoot
if ([string]::IsNullOrWhiteSpace($RemoteProfile)) {
    $RemoteProfile = (Resolve-AutoresearchSessionProfile -ProjectRoot $projectRoot).profile
}
$remoteAccess = Get-AutoresearchRemoteAccess `
    -ProjectRoot $projectRoot `
    -RemoteProfile $RemoteProfile `
    -RemoteHost $RemoteHost `
    -SshConfigPath $SshConfigPath
$selectedRemoteProfile = if ($remoteAccess.ContainsKey("SelectedRemoteProfile")) {
    [string] $remoteAccess.SelectedRemoteProfile
} else {
    ""
}
$v2Config = Get-AutoresearchV2Config `
    -ProjectRoot $projectRoot `
    -RemoteProfile $selectedRemoteProfile
$contractValidator = Join-Path $projectRoot ".agents\skills\codex-autoresearch-v2\scripts\autoresearch_v2_contracts.py"

if ([string]::IsNullOrWhiteSpace($RunTag)) {
    if ($Mode -in @("access-doctor", "access-ensure", "deploy", "doctor")) {
        $RunTag = "doctor"
    } else {
        throw "RunTag is required for mode $Mode."
    }
}
Assert-AutoresearchRunTag -RunTag $RunTag

$localRunDir = Ensure-AutoresearchV2LocalRunDir -ProjectRoot $projectRoot -Config $v2Config -RunTag $RunTag
$localRemoteDir = Join-Path $localRunDir "remote"
New-Item -ItemType Directory -Force -Path $localRemoteDir | Out-Null

function Write-V2Status {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [Parameter(Mandatory = $true)]
        [bool] $Ok,
        [Parameter(Mandatory = $true)]
        [hashtable] $Details
    )

    $status = New-StatusObject -ScriptName "autoresearch-v2.ps1" -Ok $Ok -ExperimentId $RunTag -Details $Details
    $outPath = Join-Path $localRemoteDir ($Name + ".json")
    Write-StatusJson -Data $status -Path $outPath -Json:$Json
}

function Complete-V2BridgeResult {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [Parameter(Mandatory = $true)]
        [object] $Result,
        [Parameter(Mandatory = $false)]
        [hashtable] $Details = @{},
        [Parameter(Mandatory = $false)]
        [scriptblock] $OnSuccess
    )

    $payload = $null
    $parseError = ""
    try {
        $payload = Convert-BridgeOutput -Text ([string] $Result.output)
    } catch {
        $parseError = $_.Exception.Message
    }

    $Details.remote = $payload
    $Details.raw = [string] $Result.output
    if (-not [string]::IsNullOrWhiteSpace($parseError)) {
        $Details.error = $parseError
    }

    $ok = ([int] $Result.exit_code -eq 0) -and [string]::IsNullOrWhiteSpace($parseError)
    if ($ok -and $null -ne $OnSuccess) {
        $null = & $OnSuccess $payload
    }
    Write-V2Status -Name $Name -Ok $ok -Details $Details
    if (-not $ok) {
        exit 1
    }
}

function Sync-AutoresearchV2LocalAfterBridge {
    param(
        [Parameter(Mandatory = $true)]
        [string] $RunTag
    )

    $null = Sync-AutoresearchV2LocalRepository `
        -Access $remoteAccess `
        -Config $v2Config `
        -ProjectRoot $projectRoot `
        -RunTag $RunTag `
        -TargetPath ([string] $v2Config.TargetPath) `
        -ContractValidator $contractValidator
}

try {
    switch ($Mode) {
        "access-doctor" {
            $accessResult = Test-AutoresearchRemoteAccess -Access $remoteAccess
            Write-V2Status -Name "access-doctor" -Ok ([bool] $accessResult.ok) -Details @{
                remote_access = $accessResult.details
            }
            if (-not $accessResult.ok) { exit 1 }
            break
        }
        "access-ensure" {
            $accessResult = Ensure-AutoresearchRemoteAccess -Access $remoteAccess
            Write-V2Status -Name "access-ensure" -Ok ([bool] $accessResult.ok) -Details @{
                remote_access = $accessResult.details
            }
            if (-not $accessResult.ok) { exit 1 }
            break
        }
        "deploy" {
            $remoteBinDir = Get-PosixParentPath -PathValue ([string] $v2Config.RemoteBridgeEntry)
            Ensure-RemoteDirectory -RemoteAccess $remoteAccess -RemotePath $remoteBinDir
            $files = @(
                "run_autoresearch_v2_bridge.sh",
                "autoresearch_v2_driver.py",
                "autoresearch_v2_common.py",
                "autoresearch_v2_gpu_lease.py"
            )
            $uploaded = @()
            foreach ($name in $files) {
                $localPath = Join-Path (Join-Path $remoteScriptRoot "remote-bin") $name
                $remotePath = $remoteBinDir.TrimEnd("/") + "/" + $name
                Copy-AutoresearchToRemote `
                    -Access $remoteAccess `
                    -LocalPath $localPath `
                    -RemotePath $remotePath | Out-Null
                $uploaded += $remotePath
            }
            $chmodCommand = "bash -lc " + (Quote-PosixSingle ("chmod 700 " + (Quote-PosixSingle ([string] $v2Config.RemoteBridgeEntry))))
            Invoke-AutoresearchRemoteCommand -Access $remoteAccess -RemoteCommand $chmodCommand | Out-Null
            Write-V2Status -Name "deploy" -Ok $true -Details @{
                remote_bridge = [string] $v2Config.RemoteBridgeEntry
                uploaded = $uploaded
            }
            break
        }
        "doctor" {
            $targetCandidate = if ([string]::IsNullOrWhiteSpace($TargetPath)) { [string] $v2Config.TargetPath } else { $TargetPath }
            if ([string]::IsNullOrWhiteSpace($targetCandidate)) {
                throw "TargetPath is required for doctor."
            }
            $targetFull = Resolve-AutoresearchV2LocalPath -ProjectRoot $projectRoot -PathValue $targetCandidate
            $null = Invoke-AutoresearchContractValidation -ScriptPath $contractValidator -Command validate-target -InputPath $targetFull
            $remoteDoctorRoot = ([string] $v2Config.RemoteControllerRoot).TrimEnd("/") + "/uploads/" + $RunTag + "/doctor"
            $remoteDoctorTarget = $remoteDoctorRoot + "/target.yaml"
            Ensure-RemoteDirectory -RemoteAccess $remoteAccess -RemotePath $remoteDoctorRoot
            Copy-AutoresearchToRemote `
                -Access $remoteAccess `
                -LocalPath $targetFull `
                -RemotePath $remoteDoctorTarget | Out-Null
            $result = Invoke-AutoresearchV2Bridge `
                -RemoteAccess $remoteAccess `
                -V2Config $v2Config `
                -Arguments @(
                    "--run-root-base", [string] $v2Config.RemoteRunRoot,
                    "--worktree-root-base", [string] $v2Config.RemoteWorktreeRoot,
                    "--lease-root", [string] $v2Config.RemoteLeaseRoot,
                    "--run-tag", $RunTag,
                    "doctor",
                    "--target", $remoteDoctorTarget
                ) `
                -AllowFailure
            Complete-V2BridgeResult -Name "doctor" -Result $result -Details @{
                target = $targetFull
                remote_target = $remoteDoctorTarget
            }
            break
        }
        "sync" {
            $result = Sync-AutoresearchV2LocalRepository `
                -Access $remoteAccess `
                -Config $v2Config `
                -ProjectRoot $projectRoot `
                -RunTag $RunTag `
                -TargetPath $TargetPath `
                -ContractValidator $contractValidator `
                -FetchBranch $CheckoutBranch `
                -CheckoutBranch $CheckoutBranch `
                -Checkout:$Checkout
            Write-V2Status -Name "sync" -Ok $true -Details @{
                local_sync = $result
            }
            break
        }
        default {
            $remoteRunRoot = Get-AutoresearchV2RemoteRunRoot -Config $v2Config -RunTag $RunTag
            $remoteSpecRoot = $remoteRunRoot + "/spec"
            $remoteProgram = $remoteSpecRoot + "/program.md"
            $remoteTarget = $remoteSpecRoot + "/target.yaml"

            if ($Mode -eq "bootstrap") {
                $programCandidate = if ([string]::IsNullOrWhiteSpace($ProgramPath)) { [string] $v2Config.ProgramPath } else { $ProgramPath }
                $targetCandidate = if ([string]::IsNullOrWhiteSpace($TargetPath)) { [string] $v2Config.TargetPath } else { $TargetPath }
                $programFull = Resolve-AutoresearchV2LocalPath -ProjectRoot $projectRoot -PathValue $programCandidate
                $targetFull = Resolve-AutoresearchV2LocalPath -ProjectRoot $projectRoot -PathValue $targetCandidate
                $null = Invoke-AutoresearchContractValidation -ScriptPath $contractValidator -Command validate-program -InputPath $programFull
                $null = Invoke-AutoresearchContractValidation -ScriptPath $contractValidator -Command validate-target -InputPath $targetFull
                $remoteUploadSpecRoot = ([string] $v2Config.RemoteControllerRoot).TrimEnd("/") + "/uploads/" + $RunTag + "/spec"
                Ensure-RemoteDirectory -RemoteAccess $remoteAccess -RemotePath $remoteUploadSpecRoot
                $remoteUploadProgram = $remoteUploadSpecRoot + "/program.md"
                $remoteUploadTarget = $remoteUploadSpecRoot + "/target.yaml"
                Copy-AutoresearchToRemote `
                    -Access $remoteAccess `
                    -LocalPath $programFull `
                    -RemotePath $remoteUploadProgram | Out-Null
                Copy-AutoresearchToRemote `
                    -Access $remoteAccess `
                    -LocalPath $targetFull `
                    -RemotePath $remoteUploadTarget | Out-Null
                $effectiveWorkers = if ($WorkerCount -gt 0) { $WorkerCount } else { [int] $v2Config.DefaultWorkerCount }
                $effectiveThreshold = if ([string]::IsNullOrWhiteSpace($KeepThreshold)) { [string] $v2Config.DefaultKeepThreshold } else { $KeepThreshold }
                $argsList = @(
                    "--run-root-base", [string] $v2Config.RemoteRunRoot,
                    "--worktree-root-base", [string] $v2Config.RemoteWorktreeRoot,
                    "--lease-root", [string] $v2Config.RemoteLeaseRoot,
                    "--run-tag", $RunTag,
                    "bootstrap",
                    "--program", $remoteUploadProgram,
                    "--target", $remoteUploadTarget,
                    "--branch-prefix", [string] $v2Config.BranchPrefix,
                    "--worker-count", [string] $effectiveWorkers,
                    "--keep-threshold", [string] $effectiveThreshold
                )
                $result = Invoke-AutoresearchV2Bridge -RemoteAccess $remoteAccess -V2Config $v2Config -Arguments $argsList -AllowFailure
                Complete-V2BridgeResult -Name "bootstrap" -Result $result -Details @{
                    program = $programFull
                    target = $targetFull
                    remote_upload_root = $remoteUploadSpecRoot
                }
                $null = Sync-AutoresearchV2LocalAfterBridge -RunTag $RunTag
                break
            }

            Ensure-RemoteDirectory -RemoteAccess $remoteAccess -RemotePath $remoteSpecRoot

            switch ($Mode) {
                "inspect" {
                    $result = Invoke-AutoresearchV2Bridge -RemoteAccess $remoteAccess -V2Config $v2Config -Arguments @(
                        "--run-root-base", [string] $v2Config.RemoteRunRoot,
                        "--worktree-root-base", [string] $v2Config.RemoteWorktreeRoot,
                        "--lease-root", [string] $v2Config.RemoteLeaseRoot,
                        "--run-tag", $RunTag,
                        "inspect",
                        "--worker", $Worker
                    ) -AllowFailure
                    $downloadInspect = {
                        param($payload)
                        if ($null -eq $payload) { return }
                        $localInspect = Join-Path (Join-Path $localRunDir "inspect") $Worker
                        if (Test-Path -LiteralPath $localInspect) {
                            Remove-Item -Recurse -Force -LiteralPath $localInspect
                        }
                        $localInspectParent = Split-Path -Parent $localInspect
                        if (-not [string]::IsNullOrWhiteSpace($localInspectParent)) {
                            New-Item -ItemType Directory -Force -Path $localInspectParent | Out-Null
                        }
                        Copy-AutoresearchFromRemote `
                            -Access $remoteAccess `
                            -RemotePath ([string] $payload.export_root) `
                            -LocalPath $localInspect `
                            -Recurse | Out-Null
                    }
                    Complete-V2BridgeResult -Name "inspect" -Result $result -OnSuccess $downloadInspect
                    break
                }
                "apply" {
                    if ([string]::IsNullOrWhiteSpace($SourcePath)) {
                        throw "SourcePath is required for apply."
                    }
                    $sourceFull = Resolve-Path -LiteralPath $SourcePath
                    $remoteUploadParent = $remoteRunRoot + "/uploads/" + $Worker
                    Ensure-RemoteDirectory -RemoteAccess $remoteAccess -RemotePath $remoteUploadParent
                    $remoteOverlay = $remoteUploadParent + "/" + [System.IO.Path]::GetFileName($sourceFull.Path)
                    Copy-AutoresearchToRemote `
                        -Access $remoteAccess `
                        -LocalPath $sourceFull.Path `
                        -RemotePath ($remoteUploadParent + "/") `
                        -Recurse:((Get-Item -LiteralPath $sourceFull.Path).PSIsContainer) | Out-Null
                    $argsList = @(
                        "--run-root-base", [string] $v2Config.RemoteRunRoot,
                        "--worktree-root-base", [string] $v2Config.RemoteWorktreeRoot,
                        "--lease-root", [string] $v2Config.RemoteLeaseRoot,
                        "--run-tag", $RunTag,
                        "apply",
                        "--worker", $Worker,
                        "--overlay", $remoteOverlay
                    )
                    if (-not [string]::IsNullOrWhiteSpace($Note)) {
                        $argsList += @("--note", $Note)
                    }
                    $result = Invoke-AutoresearchV2Bridge -RemoteAccess $remoteAccess -V2Config $v2Config -Arguments $argsList -AllowFailure
                    Complete-V2BridgeResult `
                        -Name "apply" `
                        -Result $result `
                        -Details @{ source = $sourceFull.Path } `
                        -OnSuccess {
                            param($payload)
                            $null = Sync-AutoresearchV2LocalAfterBridge -RunTag $RunTag
                        }
                    break
                }
                "baseline" { $bridgeCommand = "baseline" }
                "run" { $bridgeCommand = "run" }
                "resume" { $bridgeCommand = "resume" }
                "status" { $bridgeCommand = "status" }
                "collect" { $bridgeCommand = "collect" }
                "stop" { $bridgeCommand = "stop" }
                "sync-best" { $bridgeCommand = "sync-best" }
                default { throw "Unsupported mode: $Mode" }
            }

            if ($Mode -notin @("inspect", "apply", "bootstrap")) {
                $argsList = @(
                    "--run-root-base", [string] $v2Config.RemoteRunRoot,
                    "--worktree-root-base", [string] $v2Config.RemoteWorktreeRoot,
                    "--lease-root", [string] $v2Config.RemoteLeaseRoot,
                    "--run-tag", $RunTag,
                    $bridgeCommand
                )
                if ($Mode -in @("baseline", "run", "resume")) {
                    if ($AllWorkers) {
                        $argsList += "--all-workers"
                    } else {
                        $argsList += @("--worker", $Worker)
                    }
                    if ($BudgetMinutes -gt 0) {
                        $argsList += @("--budget-minutes", [string] $BudgetMinutes)
                    }
                    if (-not [string]::IsNullOrWhiteSpace($SimulateMetric)) {
                        $argsList += @("--simulate-metric", $SimulateMetric)
                    }
                    if ($Foreground) {
                        $argsList += "--foreground"
                    }
                } elseif ($Mode -in @("stop", "sync-best")) {
                    if ($AllWorkers) {
                        $argsList += "--all-workers"
                    } else {
                        $argsList += @("--worker", $Worker)
                    }
                }
                $result = Invoke-AutoresearchV2Bridge -RemoteAccess $remoteAccess -V2Config $v2Config -Arguments $argsList -AllowFailure
                $onSuccess = $null
                if ($Mode -eq "collect") {
                    $onSuccess = {
                        param($payload)
                        if ($null -eq $payload) { return }
                        $localCollectRoot = Join-Path $localRunDir "collected"
                        if (Test-Path -LiteralPath $localCollectRoot) {
                            Remove-Item -Recurse -Force -LiteralPath $localCollectRoot
                        }
                        Copy-AutoresearchFromRemote `
                            -Access $remoteAccess `
                            -RemotePath ([string] $payload.run_root) `
                            -LocalPath $localCollectRoot `
                            -Recurse | Out-Null
                        $null = Sync-AutoresearchV2LocalAfterBridge -RunTag $RunTag
                    }
                } elseif ($Mode -in @("baseline", "run", "resume", "sync-best")) {
                    $onSuccess = {
                        param($payload)
                        $null = Sync-AutoresearchV2LocalAfterBridge -RunTag $RunTag
                    }
                }
                Complete-V2BridgeResult -Name $Mode -Result $result -OnSuccess $onSuccess
            }
        }
    }
} catch {
    Write-V2Status -Name $Mode -Ok $false -Details @{
        error = $_.Exception.Message
    }
    exit 1
}
