param(
    [string] $OutputPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $projectRoot "plugins\codex-autoresearch-v2"
} elseif (-not [System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath = Join-Path $projectRoot $OutputPath
}
$outputRoot = [System.IO.Path]::GetFullPath($OutputPath)
if ((Split-Path -Leaf $outputRoot) -ne "codex-autoresearch-v2") {
    throw "OutputPath must end with codex-autoresearch-v2."
}

$skillFiles = @(
    "SKILL.md",
    "agents\openai.yaml",
    "references\input-contract.md",
    "references\remote-access-contract.md",
    "references\result-provenance-contract.md",
    "references\runtime-contract.md",
    "scripts\autoresearch_v2_contracts.py"
)
$runtimeFiles = @(
    "autoresearch-v2.ps1",
    "guard-autoresearch-mode.ps1",
    "select-profile.ps1",
    "smoke-autoresearch-v2.ps1",
    "access\select-remote-profile.ps1",
    "lib\autoresearch_v2.ps1",
    "lib\common.ps1",
    "lib\config.ps1",
    "lib\remote_access.ps1",
    "remote-bin\autoresearch_v2_common.py",
    "remote-bin\autoresearch_v2_driver.py",
    "remote-bin\autoresearch_v2_gpu_lease.py",
    "remote-bin\autoresearch_v2_mode_guard.py",
    "remote-bin\run_autoresearch_v2_bridge.sh"
)

function Copy-PackageFile {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Source,
        [Parameter(Mandatory = $true)]
        [string] $Destination
    )

    $destinationPath = Join-Path $outputRoot $Destination
    $destinationDirectory = Split-Path -Parent $destinationPath
    [void] (New-Item -ItemType Directory -Path $destinationDirectory -Force)
    Copy-Item -LiteralPath $Source -Destination $destinationPath
}

function Write-Utf8Json {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Value,
        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    $directory = Split-Path -Parent $Path
    [void] (New-Item -ItemType Directory -Path $directory -Force)
    $json = $Value | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText($Path, $json + "`n", (New-Object System.Text.UTF8Encoding($false)))
}

if (Test-Path -LiteralPath $outputRoot) {
    Remove-Item -LiteralPath $outputRoot -Recurse -Force
}
[void] (New-Item -ItemType Directory -Path $outputRoot)

$skillRoot = Join-Path $projectRoot ".agents\skills\codex-autoresearch-v2"
foreach ($relative in $skillFiles) {
    Copy-PackageFile `
        -Source (Join-Path $skillRoot $relative) `
        -Destination (Join-Path "skills\codex-autoresearch-v2" $relative)
}

$runtimeRoot = Join-Path $projectRoot "scripts\remote"
foreach ($relative in $runtimeFiles) {
    Copy-PackageFile `
        -Source (Join-Path $runtimeRoot $relative) `
        -Destination (Join-Path "scripts\remote" $relative)
}

Copy-PackageFile `
    -Source (Join-Path $projectRoot "config\autoresearch-v2.example.psd1") `
    -Destination "assets\autoresearch-v2.example.psd1"

$policy = Get-Content -LiteralPath (Join-Path $projectRoot ".codex\research-policy.json") -Raw | ConvertFrom-Json
$metadata = Get-Content -LiteralPath (Join-Path $projectRoot ".codex\autoresearch-v2-plugin.json") -Raw | ConvertFrom-Json
$version = [string] $policy.autoresearch.packaged_plugin.version

$manifest = [ordered]@{
    name = $metadata.name
    version = $version
    description = $metadata.description
    author = $metadata.author
    skills = $metadata.skills
    interface = $metadata.interface
}
Write-Utf8Json -Value $manifest -Path (Join-Path $outputRoot ".codex-plugin\plugin.json")

$readonlyContract = [ordered]@{
    schema_version = "autoresearch-v2-package-contract"
    name = $metadata.name
    version = $version
    mode = "invoke"
    runtime_entrypoint = "scripts/remote/autoresearch-v2.ps1"
    guard_entrypoint = "scripts/remote/guard-autoresearch-mode.ps1"
    sealed_paths = @("skills/codex-autoresearch-v2/**", "scripts/remote/**")
    development_skill = "codex-autoresearch-v2-dev"
}
Write-Utf8Json -Value $readonlyContract -Path (Join-Path $outputRoot "assets\readonly-contract.json")

[pscustomobject]@{
    plugin = $metadata.name
    version = $version
    output = $outputRoot
    files = @(Get-ChildItem -LiteralPath $outputRoot -Recurse -File).Count
} | ConvertTo-Json -Compress
