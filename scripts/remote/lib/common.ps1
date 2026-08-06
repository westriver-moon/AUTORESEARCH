Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-ProjectRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string] $RemoteScriptRoot
    )

    $scriptsDir = Split-Path -Parent $RemoteScriptRoot
    return (Resolve-Path (Join-Path $scriptsDir "..")).Path
}

function Assert-AutoresearchRunTag {
    param(
        [Parameter(Mandatory = $true)]
        [string] $RunTag
    )

    if ($RunTag -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$') {
        throw "Invalid RunTag '$RunTag'."
    }
}

function Assert-RemotePath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path,
        [Parameter(Mandatory = $true)]
        [string] $Name
    )

    if ($Path -notmatch '^[A-Za-z0-9_./:=@+-]+$') {
        throw "$Name contains unsupported characters: $Path"
    }
    if ($Path.Contains("..")) {
        throw "$Name must not contain '..': $Path"
    }
}

function Quote-PosixSingle {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Value
    )

    return "'" + $Value.Replace("'", "'\''") + "'"
}

function Write-StatusJson {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Data,
        [string] $Path = "",
        [switch] $Json
    )

    $jsonText = $Data | ConvertTo-Json -Depth 8
    if (-not [string]::IsNullOrWhiteSpace($Path)) {
        Set-Content -LiteralPath $Path -Value $jsonText -Encoding UTF8
    }
    if ($Json) {
        Write-Output $jsonText
    } else {
        Write-Output $Data
    }
}

function New-StatusObject {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ScriptName,
        [Parameter(Mandatory = $true)]
        [bool] $Ok,
        [string] $ExperimentId = "",
        [hashtable] $Details = @{}
    )

    return [pscustomobject]@{
        script = $ScriptName
        ok = $Ok
        experiment_id = $ExperimentId
        timestamp = (Get-Date).ToString("o")
        details = $Details
    }
}
