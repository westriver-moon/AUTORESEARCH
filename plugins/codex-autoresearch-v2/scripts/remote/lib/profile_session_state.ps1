Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-AutoresearchSessionId {
    $session = [string] $env:CODEX_THREAD_ID
    if ([string]::IsNullOrWhiteSpace($session)) {
        $session = [string] $env:CODEX_SESSION_ID
    }
    return $session.Trim()
}

function Get-AutoresearchSessionStatePath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot
    )

    $stateRoot = [string] $env:CODEX_AUTORESEARCH_STATE_ROOT
    if ([string]::IsNullOrWhiteSpace($stateRoot)) {
        $stateRoot = Join-Path $ProjectRoot ".codex_tmp\autoresearch-v2\session-state"
    }
    $session = Get-AutoresearchSessionId
    if ([string]::IsNullOrWhiteSpace($session)) {
        return ""
    }
    return Join-Path $stateRoot ($session + ".json")
}

function Resolve-AutoresearchSessionProfile {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot,
        [switch] $Force
    )

    $configuration = Get-AutoresearchConfiguration -ProjectRoot $ProjectRoot
    $profiles = @{}
    if ($configuration.ContainsKey("RemoteProfiles")) {
        $profiles = $configuration.RemoteProfiles
    }
    $activeProfile = if ($configuration.ContainsKey("ActiveRemoteProfile")) {
        [string] $configuration.ActiveRemoteProfile
    } else {
        ""
    }

    $statePath = Get-AutoresearchSessionStatePath -ProjectRoot $ProjectRoot
    $profile = ""
    $locked = $false
    if (-not $Force -and -not [string]::IsNullOrWhiteSpace($statePath) -and (Test-Path -LiteralPath $statePath)) {
        $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        if ($profiles.ContainsKey([string] $state.profile)) {
            $profile = [string] $state.profile
            $locked = $true
        }
    }
    if ([string]::IsNullOrWhiteSpace($profile)) {
        $profile = $activeProfile
    }
    if (-not [string]::IsNullOrWhiteSpace($profile) -and -not $profiles.ContainsKey($profile)) {
        throw "Remote profile '$profile' was not found in RemoteProfiles."
    }
    return [pscustomobject]@{ profile = $profile; locked = $locked }
}

function Save-AutoresearchSessionProfile {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string] $Profile
    )

    $statePath = Get-AutoresearchSessionStatePath -ProjectRoot $ProjectRoot
    if ([string]::IsNullOrWhiteSpace($statePath)) {
        return
    }
    $stateDir = Split-Path -Parent $statePath
    New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
    @{
        session = Get-AutoresearchSessionId
        profile = $Profile
    } | ConvertTo-Json -Compress | Set-Content -LiteralPath $statePath -Encoding UTF8
}
