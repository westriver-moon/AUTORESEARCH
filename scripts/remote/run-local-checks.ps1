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
        [Parameter(Mandatory = $false)]
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
    "submit-autoresearch-trial.ps1",
    "submit-smoke-test.ps1",
    "submit-job.ps1",
    "check-job.ps1",
    "sync-code.ps1",
    "fetch-results.ps1",
    "cancel-own-job.ps1",
    "lib\common.ps1",
    "lib\ssh.ps1",
    "lib\paths.ps1",
    "lib\result.ps1",
    "lib\training.ps1",
    "remote-bin\run_autoresearch_trial.sh",
    "remote-bin\run_smoke_test.sh",
    "remote-bin\run_train.sh",
    "remote-bin\check_job.sh"
)
foreach ($relative in $criticalScripts) {
    $path = Join-Path $remoteScriptRoot $relative
    Add-Check `
        -Name ("file_exists:" + $relative.Replace("\", "/")) `
        -Ok (Test-Path -LiteralPath $path) `
        -Detail $path
}

$configTemplates = @(
    "config\autoresearch.example.psd1",
    "config\autoresearch-train.example.psd1",
    "config\remote.example.psd1"
)
foreach ($relative in $configTemplates) {
    $path = Join-Path $projectRoot $relative
    Add-Check `
        -Name ("config_template_exists:" + $relative.Replace("\", "/")) `
        -Ok (Test-Path -LiteralPath $path) `
        -Detail $path
}

$expectedExperimentIdRegex = '^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$'
$commonText = Read-TextIfPresent -Path (Join-Path $remoteScriptRoot "lib\common.ps1")
$readmeText = Read-TextIfPresent -Path (Join-Path $remoteScriptRoot "README.md")
$commonHasRegex = $commonText.Contains($expectedExperimentIdRegex)
$readmeHasRegex = $readmeText.Contains($expectedExperimentIdRegex)
Add-Check `
    -Name "experiment_id_regex_consistent" `
    -Ok ($commonHasRegex -and $readmeHasRegex) `
    -Detail ("expected regex: " + $expectedExperimentIdRegex)

$submitText = Read-TextIfPresent -Path (Join-Path $remoteScriptRoot "submit-autoresearch-trial.ps1")
Add-Check `
    -Name "trial_smoke_batches_upper_bound" `
    -Ok (($submitText -match '\$effectiveSmokeBatches\s+-gt\s+10') -and $submitText.Contains("SmokeBatches must be between 1 and 10")) `
    -Detail "SmokeBatches must be clamped to 1..10."
Add-Check `
    -Name "trial_max_seconds_upper_bound" `
    -Ok (($submitText -match '\$effectiveMaxSeconds\s+-gt\s+3600') -and $submitText.Contains("MaxSeconds must be between 1 and 3600")) `
    -Detail "MaxSeconds must be clamped to 1..3600."

$trainingText = Read-TextIfPresent -Path (Join-Path $remoteScriptRoot "lib\training.ps1")
Add-Check `
    -Name "remote_root_export_helper_exists" `
    -Ok ($trainingText.Contains("Add-RemoteRootExport") -and $trainingText.Contains("REMOTE_ROOT=") -and $trainingText.Contains("export REMOTE_ROOT")) `
    -Detail "Remote entrypoint commands must receive RemoteWorkspaceRoot as REMOTE_ROOT."

$trialTemplateText = Read-TextIfPresent -Path (Join-Path $projectRoot "config\autoresearch-train.example.psd1")
$remoteCommonText = Read-TextIfPresent -Path (Join-Path $remoteScriptRoot "remote-bin\researchops_common.sh")
Add-Check `
    -Name "autoresearch_trial_defaults_to_tvilfm_pmt_vit" `
    -Ok ($trialTemplateText.Contains("TVI-LFM") -and $trialTemplateText.Contains("pmt_vit_stage_a_pmt_recipe_288x144_768.yaml") -and $remoteCommonText.Contains("TVI-LFM") -and $remoteCommonText.Contains("pmt_vit_stage_a_pmt_recipe_288x144_768.yaml")) `
    -Detail "Autoresearch trial template and remote shell fallback should target TVI-LFM Stage A PMT_VIT."
Add-Check `
    -Name "autoresearch_trial_supports_auto_gpu" `
    -Ok ($trialTemplateText.Contains("Gpu = 'auto'") -and $remoteCommonText.Contains("resolve_gpu") -and $remoteCommonText.Contains("nvidia-smi") -and $remoteCommonText.Contains("memory.used <= 1024 MiB")) `
    -Detail "Gpu='auto' should select an idle remote GPU through the fixed entrypoint."
Add-Check `
    -Name "autoresearch_trial_writes_reid_metrics_json" `
    -Ok ($remoteCommonText.Contains("reid-metrics-v1") -and $remoteCommonText.Contains("primary_metric") -and $remoteCommonText.Contains('"metric_name": "mAP"') -and $remoteCommonText.Contains("rank1") -and $remoteCommonText.Contains("mINP")) `
    -Detail "TVI-LFM logs should be normalized into metrics.json for autoresearch decisions."

$remoteTrialText = Read-TextIfPresent -Path (Join-Path $remoteScriptRoot "remote-bin\run_autoresearch_trial.sh")
$remoteSmokeText = Read-TextIfPresent -Path (Join-Path $remoteScriptRoot "remote-bin\run_smoke_test.sh")
$remoteTrainText = Read-TextIfPresent -Path (Join-Path $remoteScriptRoot "remote-bin\run_train.sh")
Add-Check `
    -Name "remote_entrypoints_use_tvilfm_main" `
    -Ok ($remoteTrialText.Contains("main.py") -and $remoteTrialText.Contains("--config_select") -and $remoteSmokeText.Contains("main.py") -and $remoteSmokeText.Contains("--config_select") -and $remoteTrainText.Contains("main.py") -and $remoteTrainText.Contains("--config_select") -and (-not ($remoteTrialText + $remoteSmokeText + $remoteTrainText).Contains("pmt_sysu.train"))) `
    -Detail "Remote trial, smoke, and full-train entrypoints should execute TVI-LFM main.py."

$submitSmokeText = Read-TextIfPresent -Path (Join-Path $remoteScriptRoot "submit-smoke-test.ps1")
$submitJobText = Read-TextIfPresent -Path (Join-Path $remoteScriptRoot "submit-job.ps1")
Add-Check `
    -Name "smoke_reuses_autoresearch_training_config" `
    -Ok ($submitSmokeText.Contains("Get-TrainingConfig") -and $submitSmokeText.Contains("Add-TrainingRemoteArgs") -and $submitSmokeText.Contains("--smoke-batches")) `
    -Detail "submit-smoke-test.ps1 must pass the shared autoresearch training config."
Add-Check `
    -Name "full_train_reuses_autoresearch_training_config" `
    -Ok ($submitJobText.Contains("Get-TrainingConfig") -and $submitJobText.Contains("Add-TrainingRemoteArgs") -and $submitJobText.Contains("--confirm-full-training")) `
    -Detail "submit-job.ps1 must pass the shared autoresearch training config."

$checkJobText = Read-TextIfPresent -Path (Join-Path $remoteScriptRoot "check-job.ps1")
$remoteCheckJobText = Read-TextIfPresent -Path (Join-Path $remoteScriptRoot "remote-bin\check_job.sh")
Add-Check `
    -Name "check_job_not_found_is_failure" `
    -Ok ($checkJobText.Contains('remote_state') -and $checkJobText.Contains('"not_found"') -and $remoteCheckJobText.Contains('sys.exit(1 if data.get("state") == "not_found" else 0)')) `
    -Detail "not_found status must not become a successful check on later polling."

$syncText = Read-TextIfPresent -Path (Join-Path $remoteScriptRoot "sync-code.ps1")
Add-Check `
    -Name "sync_code_uses_path_boundary_check" `
    -Ok ($syncText.Contains("Test-IsPathAtOrUnder") -and $syncText.Contains('$rootWithSeparator') -and (-not $syncText.Contains('.StartsWith($resolvedProject'))) `
    -Detail "SourcePath must be equal to the project root or under a project-root path separator."

$fetchText = Read-TextIfPresent -Path (Join-Path $remoteScriptRoot "fetch-results.ps1")
$fetchTargetsPresent = (
    $fetchText.Contains('"metrics.json"') -and
    $fetchText.Contains('"summary.json"') -and
    $fetchText.Contains('"config_used.yaml"') -and
    $fetchText.Contains('"logs"') -and
    $fetchText.Contains('"error_samples"')
)
Add-Check `
    -Name "fetch_results_whitelist_extended" `
    -Ok ($fetchTargetsPresent -and $fetchText.Contains("test -e") -and $fetchText.Contains("Invoke-RemoteScpFrom")) `
    -Detail "Allowed result targets must stay explicit and optional."
Add-Check `
    -Name "fetch_results_empty_is_failure" `
    -Ok ($fetchText.Contains('$ok = ($fetched.Count -gt 0)') -and $fetchText.Contains("no_result_files_fetched") -and $fetchText.Contains("exit 1")) `
    -Detail "Fetching no result files should fail clearly."

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
