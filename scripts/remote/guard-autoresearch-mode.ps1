param(
    [ValidateSet("invoke", "develop")]
    [string] $Mode = "invoke",
    [string[]] $ChangedFile = @(),
    [switch] $FromGit,
    [switch] $Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$guard = Join-Path $scriptRoot "remote-bin\autoresearch_v2_mode_guard.py"

$arguments = @($guard, "--mode", $Mode)
foreach ($path in $ChangedFile) {
    $arguments += @("--changed-file", $path)
}
if ($FromGit) {
    $arguments += "--from-git"
}
if ($Json) {
    $arguments += "--json"
}

& python @arguments
exit $LASTEXITCODE
