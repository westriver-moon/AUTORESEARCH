param(
    [switch] $Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$remoteScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $remoteScriptRoot "..\..")).Path
$checks = New-Object System.Collections.Generic.List[object]

function Add-Check {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [Parameter(Mandatory = $true)]
        [bool] $Ok,
        [string] $Detail = ""
    )

    $script:checks.Add([pscustomobject] @{
        name = $Name
        ok = $Ok
        detail = $Detail
    }) | Out-Null
}

function Read-JsonFile {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
}

$criticalScripts = @(
    "guard-autoresearch-mode.ps1",
    "autoresearch-v2.ps1",
    "smoke-autoresearch-v2.ps1",
    "select-profile.ps1",
    "access\select-remote-profile.ps1",
    "lib\common.ps1",
    "lib\config.ps1",
    "lib\remote_access.ps1",
    "lib\autoresearch_v2.ps1",
    "remote-bin\autoresearch_v2_common.py",
    "remote-bin\autoresearch_v2_driver.py",
    "remote-bin\autoresearch_v2_gpu_lease.py",
    "remote-bin\autoresearch_v2_mode_guard.py",
    "remote-bin\run_autoresearch_v2_bridge.sh"
)
foreach ($relative in $criticalScripts) {
    $path = Join-Path $remoteScriptRoot $relative
    Add-Check -Name ("file_exists:" + $relative.Replace("\", "/")) -Ok (Test-Path -LiteralPath $path) -Detail $path
}

$projectFiles = @(
    "config\autoresearch-v2.example.psd1",
    "autoresearch\program-example.md",
    "autoresearch\targets\example-cpu.yaml",
    ".agents\skills\codex-autoresearch-v2\SKILL.md",
    ".agents\skills\codex-autoresearch-v2-dev\SKILL.md",
    ".codex\autoresearch-v2-plugin.json",
    ".codex\research-policy.json",
    ".githooks\pre-commit",
    "scripts\package-autoresearch-v2-plugin.ps1",
    "plugins\codex-autoresearch-v2\.codex-plugin\plugin.json"
)
foreach ($relative in $projectFiles) {
    $path = Join-Path $projectRoot $relative
    Add-Check -Name ("project_file_exists:" + $relative.Replace("\", "/")) -Ok (Test-Path -LiteralPath $path) -Detail $path
}

$expectedExperimentIdRegex = '^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$'
$commonText = Get-Content -LiteralPath (Join-Path $remoteScriptRoot "lib\common.ps1") -Raw
$configText = Get-Content -LiteralPath (Join-Path $remoteScriptRoot "lib\config.ps1") -Raw
$accessText = Get-Content -LiteralPath (Join-Path $remoteScriptRoot "lib\remote_access.ps1") -Raw
$readmeText = Get-Content -LiteralPath (Join-Path $remoteScriptRoot "README.md") -Raw
Add-Check `
    -Name "experiment_id_regex_consistent" `
    -Ok ($commonText.Contains($expectedExperimentIdRegex)) `
    -Detail ("expected regex: " + $expectedExperimentIdRegex)
Add-Check `
    -Name "remote_access_layer_owned" `
    -Ok ($configText.Contains("function Get-AutoresearchConfiguration") -and $accessText.Contains("function Get-AutoresearchRemoteAccess") -and $accessText.Contains("function Invoke-AutoresearchRemoteCommand") -and $accessText.Contains("function Copy-AutoresearchToRemote") -and $accessText.Contains("function Test-AutoresearchRemoteHttpProxy")) `
    -Detail "The integrated access layer must own configuration, Profiles, SSH/SCP, and proxy diagnostics."

$v2ScriptText = Get-Content -LiteralPath (Join-Path $remoteScriptRoot "autoresearch-v2.ps1") -Raw
$v2LibText = Get-Content -LiteralPath (Join-Path $remoteScriptRoot "lib\autoresearch_v2.ps1") -Raw
$smokeText = Get-Content -LiteralPath (Join-Path $remoteScriptRoot "smoke-autoresearch-v2.ps1") -Raw
$targetText = Get-Content -LiteralPath (Join-Path $projectRoot "autoresearch\targets\example-cpu.yaml") -Raw
$programText = Get-Content -LiteralPath (Join-Path $projectRoot "autoresearch\program-example.md") -Raw
$policy = Read-JsonFile -Path (Join-Path $projectRoot ".codex\research-policy.json")
$invokeSkillText = Get-Content -LiteralPath (Join-Path $projectRoot ".agents\skills\codex-autoresearch-v2\SKILL.md") -Raw
$devSkillText = Get-Content -LiteralPath (Join-Path $projectRoot ".agents\skills\codex-autoresearch-v2-dev\SKILL.md") -Raw
$plugin = Read-JsonFile -Path (Join-Path $projectRoot "plugins\codex-autoresearch-v2\.codex-plugin\plugin.json")

Add-Check `
    -Name "v2_modes_declared" `
    -Ok ($v2ScriptText.Contains('"access-doctor", "access-ensure", "deploy", "doctor", "bootstrap", "inspect", "apply", "baseline", "run", "resume", "status", "collect", "stop", "sync-best"')) `
    -Detail "autoresearch-v2.ps1 should expose the unified control surface."
Add-Check `
    -Name "v2_remote_roots_declared" `
    -Ok ($v2LibText.Contains("RemoteControllerRoot") -and $v2LibText.Contains("RemoteRunRoot") -and $v2LibText.Contains("RemoteWorktreeRoot") -and $v2LibText.Contains("RemoteLeaseRoot")) `
    -Detail "autoresearch_v2.ps1 helper should carry remote controller roots."
Add-Check `
    -Name "smoke_script_requires_explicit_generic_inputs" `
    -Ok ($smokeText.Contains('[string] $TargetPath') -and $smokeText.Contains('[string] $ProgramPath') -and $smokeText.Contains('-Mode doctor')) `
    -Detail "smoke-autoresearch-v2.ps1 should operate on an explicit schema v2 target."
Add-Check `
    -Name "default_target_is_schema_v2_cpu" `
    -Ok ($targetText.Contains("schema_version: 2") -and $targetText.Contains("argv:") -and $targetText.Contains("mode: none") -and $targetText.Contains("primary_metric")) `
    -Detail "The example target should demonstrate the generic CPU-first schema."
Add-Check `
    -Name "default_program_is_generic" `
    -Ok ($programText.Contains("primary_metric") -and $programText.Contains("src/**") -and -not $programText.Contains("TVI-LFM")) `
    -Detail "The example program should not embed a project or experiment stage."
Add-Check `
    -Name "generic_remote_support_declared" `
    -Ok ($readmeText.Contains("access-doctor") -and $readmeText.Contains("access-ensure") -and $readmeText.Contains("select-profile.ps1") -and $readmeText.Contains("lib/remote_access.ps1")) `
    -Detail "Remote access must be documented as part of the unified Autoresearch controller."
Add-Check `
    -Name "autoresearch_modes_declared" `
    -Ok ($policy.autoresearch.default_mode -eq "invoke" -and $null -ne $policy.autoresearch.modes.invoke -and $null -ne $policy.autoresearch.modes.develop -and $policy.autoresearch.mode_guard_entrypoint -eq "scripts/remote/guard-autoresearch-mode.ps1" -and $policy.autoresearch.git_hook_entrypoint -eq ".githooks/pre-commit") `
    -Detail "Autoresearch policy should declare invoke/develop mode boundaries plus guard and hook entrypoints."
Add-Check `
    -Name "invoke_skill_is_sealed" `
    -Ok ($invokeSkillText.Contains("invocation mode") -and $invokeSkillText.Contains("Do not edit sealed implementation paths") -and $invokeSkillText.Contains('$codex-autoresearch-v2-dev')) `
    -Detail "Invocation skill should route implementation changes to the development skill."
Add-Check `
    -Name "dev_skill_declares_development_mode" `
    -Ok ($devSkillText.Contains("development mode") -and $devSkillText.Contains(".codex/research-policy.json") -and $devSkillText.Contains("sole authority") -and $devSkillText.Contains("guard-autoresearch-mode.ps1")) `
    -Detail "Development skill should be the only agent-facing mode that edits sealed paths."
Add-Check `
    -Name "v2_plugin_packaged" `
    -Ok ($plugin.name -eq "codex-autoresearch-v2" -and $plugin.version -eq $policy.autoresearch.packaged_plugin.version -and $policy.autoresearch.packaged_plugin.path -eq "plugins/codex-autoresearch-v2") `
    -Detail "Autoresearch v2 should have a versioned repo-local plugin package."

$failed = @($checks | Where-Object { -not $_.ok })
$ok = ($failed.Count -eq 0)
$report = [pscustomobject] @{
    script = "run-local-checks.ps1"
    ok = $ok
    project_root = $projectRoot
    checks = @($checks.ToArray())
}

if ($Json) {
    Write-Output ($report | ConvertTo-Json -Depth 6)
} else {
    Write-Output $report
}

if (-not $ok) {
    exit 1
}
