param(
    [string] $RunTag = "",
    [string] $RemoteHost = "",
    [string] $SshConfigPath = "",
    [switch] $SkipDeploy,
    [switch] $Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$remoteScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $remoteScriptRoot "lib\common.ps1")
. (Join-Path $remoteScriptRoot "lib\result.ps1")

$projectRoot = Get-ProjectRoot -RemoteScriptRoot $remoteScriptRoot
$v2Script = Join-Path $remoteScriptRoot "autoresearch-v2.ps1"
if ([string]::IsNullOrWhiteSpace($RunTag)) {
    $RunTag = "v2-smoke-" + (Get-Date -Format "yyyyMMdd-HHmmss")
}

$localRunDir = Join-Path (Join-Path $projectRoot "autoresearch-runs") $RunTag
$inputRoot = Join-Path $localRunDir "smoke-inputs"
New-Item -ItemType Directory -Force -Path $inputRoot | Out-Null

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$programPath = Join-Path $inputRoot "program.md"
$targetPath = Join-Path $inputRoot "target.yaml"

$programText = @"
---
goal: Smoke-test remote-first autoresearch against the actual server git root.
metric: primary_metric
direction: higher
budget_mode: short
worker_count: 1
keep_threshold: 0.0
mutable_paths:
  - TVI-LFM/main.py
  - TVI-LFM/core/build.py
  - TVI-LFM/core/train.py
  - TVI-LFM/data_loader/loader.py
  - TVI-LFM/data_loader/sampler.py
  - TVI-LFM/tools/loss.py
  - TVI-LFM/network/model.py
  - TVI-LFM/network/pmt_vit.py
  - TVI-LFM/network/pmt_vit_adapter.py
  - TVI-LFM/network/gem_pool.py
  - TVI-LFM/config/stage_a/*.yaml
---

# Remote Smoke Program
"@

$targetText = @"
name: tvilfm-stage-a-build-smoke
repo:
  remote_root: /home/cgv841/ybj
  base_ref: main
  mutable_paths:
    - TVI-LFM/main.py
    - TVI-LFM/core/build.py
    - TVI-LFM/core/train.py
    - TVI-LFM/data_loader/loader.py
    - TVI-LFM/data_loader/sampler.py
    - TVI-LFM/tools/loss.py
    - TVI-LFM/network/model.py
    - TVI-LFM/network/pmt_vit.py
    - TVI-LFM/network/pmt_vit_adapter.py
    - TVI-LFM/network/gem_pool.py
    - TVI-LFM/config/stage_a/*.yaml
  readonly_paths:
    - non_research/**
    - scripts/remote/**
run:
  cwd: TVI-LFM
  command:
    - "{python_bin}"
    - "-c"
    - |
        import json
        import py_compile
        from pathlib import Path
        files = [
            "main.py",
            "core/build.py",
            "core/train.py",
            "data_loader/loader.py",
            "data_loader/sampler.py",
            "tools/loss.py",
            "network/model.py",
            "network/pmt_vit.py",
            "network/pmt_vit_adapter.py",
            "network/gem_pool.py",
        ]
        for rel in files:
            py_compile.compile(rel, doraise=True)
        out = Path("{run_results_dir}")
        out.mkdir(parents=True, exist_ok=True)
        (out / "metrics.json").write_text(json.dumps({"available": True, "primary_metric": 1.0}), encoding="utf-8")
  budget_minutes:
    short: 5
    medium: 5
    long: 5
  metric:
    parser: json_file
    path: metrics.json
    primary_key: primary_metric
    direction: higher
artifacts:
  collect:
    - metrics.json
training:
  python_bin: /home/cgv841/anaconda3/envs/clipreid/bin/python
gpu:
  policy: none
  selector: "0"
  max_wait_seconds: 0
"@

[System.IO.File]::WriteAllText($programPath, $programText, $utf8NoBom)
[System.IO.File]::WriteAllText($targetPath, $targetText, $utf8NoBom)

function Invoke-V2 {
    param(
        [Parameter(Mandatory = $true)]
        [string[]] $Arguments
    )

    $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $v2Script) + $Arguments
    if (-not [string]::IsNullOrWhiteSpace($RemoteHost)) {
        $argList += @("-RemoteHost", $RemoteHost)
    }
    if (-not [string]::IsNullOrWhiteSpace($SshConfigPath)) {
        $argList += @("-SshConfigPath", $SshConfigPath)
    }
    $argList += "-Json"
    $output = & powershell.exe @argList 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($output | Out-String)
    }
    return (($output | Out-String).Trim() | ConvertFrom-Json)
}

if (-not $SkipDeploy) {
    $null = Invoke-V2 -Arguments @("-Mode", "deploy", "-RunTag", $RunTag)
}
$doctor = Invoke-V2 -Arguments @("-Mode", "doctor", "-RunTag", $RunTag)
$bootstrap = Invoke-V2 -Arguments @(
    "-Mode", "bootstrap",
    "-RunTag", $RunTag,
    "-ProgramPath", $programPath,
    "-TargetPath", $targetPath,
    "-WorkerCount", "1"
)
$inspect = Invoke-V2 -Arguments @("-Mode", "inspect", "-RunTag", $RunTag, "-Worker", "w1")
$baseline = Invoke-V2 -Arguments @("-Mode", "baseline", "-RunTag", $RunTag, "-Worker", "w1", "-Foreground")
$status = Invoke-V2 -Arguments @("-Mode", "status", "-RunTag", $RunTag)
$collect = Invoke-V2 -Arguments @("-Mode", "collect", "-RunTag", $RunTag)

$summary = New-StatusObject -ScriptName "smoke-autoresearch-v2.ps1" -Ok $true -ExperimentId $RunTag -Details @{
    run_tag = $RunTag
    input_root = $inputRoot
    doctor = $doctor.details.remote
    bootstrap = $bootstrap.details.remote
    inspect = $inspect.details.remote
    baseline = $baseline.details.remote
    status = $status.details.remote
    collect = $collect.details.remote
}

$outPath = Join-Path $localRunDir "remote\smoke.json"
Write-StatusJson -Data $summary -Path $outPath -Json:$Json
