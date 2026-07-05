Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Join-RemotePath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Left,
        [Parameter(Mandatory = $true)]
        [string] $Right
    )

    return $Left.TrimEnd("/") + "/" + $Right.TrimStart("/")
}

function Get-RemoteExperimentRoot {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $Config,
        [Parameter(Mandatory = $true)]
        [string] $ExperimentId
    )

    Assert-ExperimentId -ExperimentId $ExperimentId
    return Join-RemotePath -Left ([string] $Config.RemoteWorkspaceRoot) -Right ("experiments/" + $ExperimentId)
}

