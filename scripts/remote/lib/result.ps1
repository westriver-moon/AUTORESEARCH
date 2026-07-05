Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-StatusFilePath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot,
        [Parameter(Mandatory = $true)]
        [string] $ExperimentId,
        [Parameter(Mandatory = $true)]
        [string] $Name
    )

    $dir = New-ExperimentRemoteDir -ProjectRoot $ProjectRoot -ExperimentId $ExperimentId
    return Join-Path $dir ($Name + ".json")
}

