param(
    [switch] $Json,
    [switch] $FailOnError
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-ProjectRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ScriptRoot
    )

    return (Resolve-Path -LiteralPath (Join-Path $ScriptRoot "..\..")).Path
}

function Get-DefaultAutoresearchConfig {
    return @{
        SkillPath = ".agents\skills\codex-autoresearch"
        VendorPath = ".agents\vendor\codex-autoresearch-windows-skill"
        LockFile = "THIRD_PARTY_SKILLS.lock.yml"
        Invocation = "explicit_only"
        SessionMode = "foreground"
        ResultsDirectory = "autoresearch-results"
        PythonCommand = "python"
        RequireGitRepo = $true
        AllowControlledRemoteTrialBridge = $true
        AllowFullTrainingFromAutoresearch = $false
        AllowImplicitInvocation = $false
        AllowBackground = $false
        AllowExec = $false
        AllowHooks = $false
        AllowFullAccessBypass = $false
        AllowDangerouslyBypassApprovalsAndSandbox = $false
        AllowSshDuringSkillLaunch = $false
        AllowGpuDuringSkillLaunch = $false
        ForbiddenRuntimeArtifacts = @("launch.json", "runtime.json", "runtime.log")
    }
}

function Get-AutoresearchConfig {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot
    )

    $config = Get-DefaultAutoresearchConfig
    $localConfig = Join-Path $ProjectRoot "config\autoresearch.local.psd1"
    if (Test-Path -LiteralPath $localConfig) {
        $loaded = Import-PowerShellDataFile -LiteralPath $localConfig
        foreach ($key in $loaded.Keys) {
            $config[$key] = $loaded[$key]
        }
    }
    return $config
}

function Resolve-ProjectPath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return $Path
    }
    return (Join-Path $ProjectRoot $Path)
}

function Test-CommandAvailable {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name
    )

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    return $null -ne $command
}

function Test-TextContains {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path,
        [Parameter(Mandatory = $true)]
        [string] $Pattern
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }
    $text = Get-Content -Raw -LiteralPath $Path
    return $text.Contains($Pattern)
}

function Get-GitRepoRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot
    )

    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($null -eq $git) {
        return ""
    }

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = "git"
    $startInfo.Arguments = "-C `"$ProjectRoot`" rev-parse --show-toplevel"
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true

    try {
        $process = [System.Diagnostics.Process]::Start($startInfo)
        $stdout = $process.StandardOutput.ReadToEnd()
        $null = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
    } catch {
        return ""
    }

    if ($process.ExitCode -ne 0) {
        return ""
    }
    return ([string] $stdout).Trim()
}

function New-Check {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [Parameter(Mandatory = $true)]
        [bool] $Ok,
        [Parameter(Mandatory = $false)]
        [string] $Detail = ""
    )

    return [pscustomobject] @{
        name = $Name
        ok = $Ok
        detail = $Detail
    }
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Get-ProjectRoot -ScriptRoot $scriptRoot
$config = Get-AutoresearchConfig -ProjectRoot $projectRoot

$skillPath = Resolve-ProjectPath -ProjectRoot $projectRoot -Path ([string] $config.SkillPath)
$vendorPath = Resolve-ProjectPath -ProjectRoot $projectRoot -Path ([string] $config.VendorPath)
$lockPath = Resolve-ProjectPath -ProjectRoot $projectRoot -Path ([string] $config.LockFile)
$resultsPath = Resolve-ProjectPath -ProjectRoot $projectRoot -Path ([string] $config.ResultsDirectory)
$trialConfigPath = Resolve-ProjectPath -ProjectRoot $projectRoot -Path "config\autoresearch-train.example.psd1"
$trialSubmitPath = Resolve-ProjectPath -ProjectRoot $projectRoot -Path "scripts\remote\submit-autoresearch-trial.ps1"
$trialRemoteEntryPath = Resolve-ProjectPath -ProjectRoot $projectRoot -Path "scripts\remote\remote-bin\run_autoresearch_trial.sh"
$skillMd = Join-Path $skillPath "SKILL.md"
$manifest = Join-Path $skillPath "agents\openai.yaml"
$gitRoot = Get-GitRepoRoot -ProjectRoot $projectRoot

$checks = @()
$checks += New-Check -Name "skill_exists" -Ok (Test-Path -LiteralPath $skillMd) -Detail $skillMd
$checks += New-Check -Name "vendor_exists" -Ok (Test-Path -LiteralPath $vendorPath) -Detail $vendorPath
$checks += New-Check -Name "lock_exists" -Ok (Test-Path -LiteralPath $lockPath) -Detail $lockPath
$checks += New-Check -Name "python_available" -Ok (Test-CommandAvailable -Name ([string] $config.PythonCommand)) -Detail ([string] $config.PythonCommand)
$checks += New-Check -Name "git_available" -Ok (Test-CommandAvailable -Name "git") -Detail "git"
$checks += New-Check -Name "project_is_git_repo" -Ok (-not [string]::IsNullOrWhiteSpace($gitRoot)) -Detail $gitRoot
$checks += New-Check -Name "trial_config_exists" -Ok (Test-Path -LiteralPath $trialConfigPath) -Detail $trialConfigPath
$checks += New-Check -Name "trial_submit_script_exists" -Ok (Test-Path -LiteralPath $trialSubmitPath) -Detail $trialSubmitPath
$checks += New-Check -Name "trial_remote_entry_exists" -Ok (Test-Path -LiteralPath $trialRemoteEntryPath) -Detail $trialRemoteEntryPath
$checks += New-Check -Name "explicit_invocation_policy" -Ok (Test-TextContains -Path $manifest -Pattern "allow_implicit_invocation: false") -Detail $manifest
$checks += New-Check -Name "foreground_only_policy" -Ok (Test-TextContains -Path $skillMd -Pattern "Use foreground mode only") -Detail $skillMd
$checks += New-Check -Name "exec_disabled_policy" -Ok (Test-TextContains -Path $skillMd -Pattern "Do not use ``exec`` mode or ``codex exec``.") -Detail $skillMd
$checks += New-Check -Name "hooks_disabled_policy" -Ok (Test-TextContains -Path $skillMd -Pattern "Never run") -Detail $skillMd
$checks += New-Check -Name "python_command_policy" -Ok (Test-TextContains -Path $skillMd -Pattern "call helper scripts with ``python``, not ``python3``") -Detail $skillMd
$checks += New-Check -Name "ssh_gpu_disabled_policy" -Ok (Test-TextContains -Path $skillMd -Pattern "Do not connect SSH or start GPU training") -Detail $skillMd

foreach ($artifact in @($config.ForbiddenRuntimeArtifacts)) {
    $artifactPath = Join-Path $resultsPath ([string] $artifact)
    $checks += New-Check -Name ("forbidden_artifact_absent:" + $artifact) -Ok (-not (Test-Path -LiteralPath $artifactPath)) -Detail $artifactPath
}

$booleanPolicyOk = (
    ([string] $config.Invocation -eq "explicit_only") -and
    ([string] $config.SessionMode -eq "foreground") -and
    ([bool] $config.AllowControlledRemoteTrialBridge) -and
    (-not [bool] $config.AllowFullTrainingFromAutoresearch) -and
    (-not [bool] $config.AllowImplicitInvocation) -and
    (-not [bool] $config.AllowBackground) -and
    (-not [bool] $config.AllowExec) -and
    (-not [bool] $config.AllowHooks) -and
    (-not [bool] $config.AllowFullAccessBypass) -and
    (-not [bool] $config.AllowDangerouslyBypassApprovalsAndSandbox) -and
    (-not [bool] $config.AllowSshDuringSkillLaunch) -and
    (-not [bool] $config.AllowGpuDuringSkillLaunch)
)
$checks += New-Check -Name "local_policy_is_restricted" -Ok $booleanPolicyOk -Detail "config/autoresearch*.psd1"

$requiredChecks = $checks
if (-not [bool] $config.RequireGitRepo) {
    $requiredChecks = @($checks | Where-Object { $_.name -ne "project_is_git_repo" })
}

$ok = -not [bool] (@($requiredChecks | Where-Object { -not $_.ok }).Count)
$data = [pscustomobject] @{
    script = "autoresearch-doctor"
    ok = $ok
    project_root = $projectRoot
    git_root = $gitRoot
    skill_path = $skillPath
    vendor_path = $vendorPath
    results_path = $resultsPath
    checks = $checks
}

if ($Json) {
    $data | ConvertTo-Json -Depth 8
} else {
    $data
}

if ($FailOnError -and -not $ok) {
    exit 1
}
