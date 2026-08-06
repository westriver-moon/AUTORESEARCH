param(
    [Parameter(Mandatory = $true)]
    [string] $TargetPath,
    [Parameter(Mandatory = $true)]
    [string] $ProgramPath,
    [string] $RunTag = ("generic-smoke-" + (Get-Date -Format "yyyyMMdd-HHmmss")),
    [string] $RemoteHost = "",
    [string] $SshConfigPath = "",
    [switch] $Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$entry = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "autoresearch-v2.ps1"
$common = @("-RunTag", $RunTag, "-TargetPath", $TargetPath)
if (-not [string]::IsNullOrWhiteSpace($RemoteHost)) {
    $common += @("-RemoteHost", $RemoteHost)
}
if (-not [string]::IsNullOrWhiteSpace($SshConfigPath)) {
    $common += @("-SshConfigPath", $SshConfigPath)
}
if ($Json) {
    $common += "-Json"
}

& $entry -Mode doctor @common
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $entry -Mode bootstrap @common -ProgramPath $ProgramPath -WorkerCount 1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $entry -Mode baseline @common -Worker w1 -Foreground
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $entry -Mode collect @common
exit $LASTEXITCODE
