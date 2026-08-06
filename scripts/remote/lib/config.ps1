Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Merge-AutoresearchConfiguration {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $Base,
        [Parameter(Mandatory = $true)]
        [hashtable] $Override
    )

    $merged = @{}
    foreach ($key in $Base.Keys) {
        $merged[$key] = $Base[$key]
    }
    foreach ($key in $Override.Keys) {
        $merged[$key] = $Override[$key]
    }
    return $merged
}

function Get-AutoresearchConfiguration {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot
    )

    $examplePath = Join-Path $ProjectRoot "config\autoresearch-v2.example.psd1"
    $configuration = Import-PowerShellDataFile -LiteralPath $examplePath

    $localPath = Join-Path $ProjectRoot "config\autoresearch-v2.local.psd1"
    if (Test-Path -LiteralPath $localPath) {
        $local = Import-PowerShellDataFile -LiteralPath $localPath
        $configuration = Merge-AutoresearchConfiguration -Base $configuration -Override $local
    }

    return $configuration
}
