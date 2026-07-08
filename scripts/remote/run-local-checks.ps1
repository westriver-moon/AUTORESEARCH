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

function Read-TextIfPresent {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    if (Test-Path -LiteralPath $Path) {
        return Get-Content -LiteralPath $Path -Raw
    }
    return ""
}

$criticalScripts = @(
    "doctor.ps1",
    "ensure-connectivity.ps1",
    "guard-autoresearch-mode.ps1",
    "autoresearch-v2.ps1",
    "smoke-autoresearch-v2.ps1",
    "submit-smoke-test.ps1",
    "submit-job.ps1",
    "check-job.ps1",
    "fetch-results.ps1",
    "cancel-own-job.ps1",
    "sync-code.ps1",
    "lib\common.ps1",
    "lib\ssh.ps1",
    "lib\paths.ps1",
    "lib\result.ps1",
    "lib\training.ps1",
    "lib\autoresearch_v2.ps1",
    "remote-bin\autoresearch_v2_common.py",
    "remote-bin\autoresearch_v2_driver.py",
    "remote-bin\autoresearch_v2_gpu_lease.py",
    "remote-bin\autoresearch_v2_metric_tvilfm.py",
    "remote-bin\autoresearch_v2_mode_guard.py",
    "remote-bin\run_autoresearch_v2_bridge.sh",
    "remote-bin\run_smoke_test.sh",
    "remote-bin\run_train.sh",
    "remote-bin\check_job.sh",
    "remote-bin\cancel_job.sh"
)
foreach ($relative in $criticalScripts) {
    $path = Join-Path $remoteScriptRoot $relative
    Add-Check -Name ("file_exists:" + $relative.Replace("\", "/")) -Ok (Test-Path -LiteralPath $path) -Detail $path
}

$projectFiles = @(
    "config\remote.example.psd1",
    "config\autoresearch-v2.example.psd1",
    "autoresearch\program.md",
    "autoresearch\targets\tvilfm-stage-a.yaml",
    ".agents\skills\codex-autoresearch-v2\SKILL.md",
    ".agents\skills\codex-autoresearch-v2-dev\SKILL.md",
    ".githooks\pre-commit",
    "plugins\codex-autoresearch-v2\.codex-plugin\plugin.json"
)
foreach ($relative in $projectFiles) {
    $path = Join-Path $projectRoot $relative
    Add-Check -Name ("project_file_exists:" + $relative.Replace("\", "/")) -Ok (Test-Path -LiteralPath $path) -Detail $path
}

$expectedExperimentIdRegex = '^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$'
$commonText = Read-TextIfPresent -Path (Join-Path $remoteScriptRoot "lib\common.ps1")
$readmeText = Read-TextIfPresent -Path (Join-Path $remoteScriptRoot "README.md")
Add-Check `
    -Name "experiment_id_regex_consistent" `
    -Ok ($commonText.Contains($expectedExperimentIdRegex)) `
    -Detail ("expected regex: " + $expectedExperimentIdRegex)

$v2ScriptText = Read-TextIfPresent -Path (Join-Path $remoteScriptRoot "autoresearch-v2.ps1")
$v2LibText = Read-TextIfPresent -Path (Join-Path $remoteScriptRoot "lib\autoresearch_v2.ps1")
$smokeText = Read-TextIfPresent -Path (Join-Path $remoteScriptRoot "smoke-autoresearch-v2.ps1")
$targetText = Read-TextIfPresent -Path (Join-Path $projectRoot "autoresearch\targets\tvilfm-stage-a.yaml")
$programText = Read-TextIfPresent -Path (Join-Path $projectRoot "autoresearch\program.md")
$policyText = Read-TextIfPresent -Path (Join-Path $projectRoot ".codex\research-policy.json")
$invokeSkillText = Read-TextIfPresent -Path (Join-Path $projectRoot ".agents\skills\codex-autoresearch-v2\SKILL.md")
$devSkillText = Read-TextIfPresent -Path (Join-Path $projectRoot ".agents\skills\codex-autoresearch-v2-dev\SKILL.md")
$pluginText = Read-TextIfPresent -Path (Join-Path $projectRoot "plugins\codex-autoresearch-v2\.codex-plugin\plugin.json")

Add-Check `
    -Name "v2_modes_declared" `
    -Ok ($v2ScriptText.Contains('"deploy", "doctor", "bootstrap", "inspect", "apply", "baseline", "run", "resume", "status", "collect", "stop", "sync-best"')) `
    -Detail "autoresearch-v2.ps1 should expose the unified control surface."
Add-Check `
    -Name "v2_remote_roots_declared" `
    -Ok ($v2LibText.Contains("RemoteControllerRoot") -and $v2LibText.Contains("RemoteRunRoot") -and $v2LibText.Contains("RemoteWorktreeRoot") -and $v2LibText.Contains("RemoteLeaseRoot")) `
    -Detail "autoresearch_v2.ps1 helper should carry remote controller roots."
Add-Check `
    -Name "smoke_script_is_non_gpu_compile_check" `
    -Ok ($smokeText.Contains("py_compile") -and $smokeText.Contains('policy: none') -and $smokeText.Contains('primary_metric": 1.0')) `
    -Detail "smoke-autoresearch-v2.ps1 should validate the real server layout without consuming a GPU."
Add-Check `
    -Name "default_target_uses_server_git_root" `
    -Ok ($targetText.Contains("remote_root: /home/cgv841/ybj") -and $targetText.Contains("cwd: TVI-LFM") -and $targetText.Contains("TVI-LFM/main.py")) `
    -Detail "default target must match the actual remote git topology."
Add-Check `
    -Name "default_program_scopes_tvilfm_subtree" `
    -Ok ($programText.Contains("TVI-LFM/main.py") -and $programText.Contains("/home/cgv841/ybj")) `
    -Detail "default program should scope mutable paths to the active TVI-LFM subtree."
Add-Check `
    -Name "manual_remote_entrypoints_declared" `
    -Ok ($commonText.Contains("RemoteSmokeEntry") -and $commonText.Contains("RemoteTrainEntry") -and $commonText.Contains("RemoteStatusEntry") -and $commonText.Contains("RemoteCancelEntry") -and $readmeText.Contains("submit-smoke-test.ps1") -and $readmeText.Contains("submit-job.ps1") -and $readmeText.Contains("check-job.ps1") -and $readmeText.Contains("fetch-results.ps1") -and $readmeText.Contains("cancel-own-job.ps1")) `
    -Detail "Manual remote training and status entrypoints should stay declared in config and README."
Add-Check `
    -Name "autoresearch_modes_declared" `
    -Ok ($policyText.Contains('"default_mode": "invoke"') -and $policyText.Contains('"invoke"') -and $policyText.Contains('"develop"') -and $policyText.Contains("guard-autoresearch-mode.ps1") -and $policyText.Contains(".githooks/pre-commit")) `
    -Detail "Autoresearch policy should declare invoke/develop mode boundaries plus guard and hook entrypoints."
Add-Check `
    -Name "invoke_skill_is_sealed" `
    -Ok ($invokeSkillText.Contains("invocation mode") -and $invokeSkillText.Contains("Do not edit sealed autoresearch implementation paths") -and $invokeSkillText.Contains('$codex-autoresearch-v2-dev')) `
    -Detail "Invocation skill should route implementation changes to the development skill."
Add-Check `
    -Name "dev_skill_declares_development_mode" `
    -Ok ($devSkillText.Contains("development mode") -and $devSkillText.Contains("may edit these paths") -and $devSkillText.Contains("guard-autoresearch-mode.ps1")) `
    -Detail "Development skill should be the only agent-facing mode that edits sealed paths."
Add-Check `
    -Name "v2_plugin_packaged" `
    -Ok ($pluginText.Contains('"name": "codex-autoresearch-v2"') -and $pluginText.Contains('"version": "0.1.0"') -and $policyText.Contains('"path": "plugins/codex-autoresearch-v2"')) `
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
