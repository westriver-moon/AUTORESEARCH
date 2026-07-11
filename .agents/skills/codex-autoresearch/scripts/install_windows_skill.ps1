param(
    [string]$SkillName = "codex-autoresearch",
    [string]$CodexHome = "$env:USERPROFILE\.codex",
    [switch]$NoHooks
)

$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
    $scriptDir = Split-Path -Parent $PSCommandPath
    return (Resolve-Path (Join-Path $scriptDir "..")).Path
}

function Copy-Skill {
    param(
        [string]$Source,
        [string]$Destination
    )

    if (Test-Path $Destination) {
        Remove-Item -Recurse -Force $Destination
    }

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    Copy-Item -Recurse -Force $Source $Destination

    $removePaths = @(
        ".git",
        ".pytest_cache",
        ".venv",
        "autoresearch-results",
        "debug",
        "fix",
        "security",
        "ship"
    )

    foreach ($relative in $removePaths) {
        $path = Join-Path $Destination $relative
        if (Test-Path $path) {
            Remove-Item -Recurse -Force $path
        }
    }

    Get-ChildItem -Path $Destination -Recurse -Force -Directory -Filter "__pycache__" |
        Remove-Item -Recurse -Force
}

$repoRoot = Resolve-RepoRoot
$skillRoot = Join-Path (Join-Path $CodexHome "skills") $SkillName

if (-not (Test-Path (Join-Path $repoRoot "SKILL.md"))) {
    throw "SKILL.md not found at repository root: $repoRoot"
}

Copy-Skill -Source $repoRoot -Destination $skillRoot

if (-not $NoHooks) {
    $hooksCtl = Join-Path $skillRoot "scripts\autoresearch_hooks_ctl.py"
    python $hooksCtl install | Out-Host
}

Write-Host ""
Write-Host "Installed $SkillName to:"
Write-Host "  $skillRoot"
Write-Host ""
Write-Host "Restart Codex, then verify with:"
Write-Host "  codex debug prompt-input '`$codex-autoresearch test'"
