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
    "sync-code.ps1",
    "fetch-results.ps1",
    "lib\common.ps1",
    "lib\ssh.ps1",
    "lib\paths.ps1",
    "lib\result.ps1",
    "remote-bin\run_autoresearch_trial.sh"
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
