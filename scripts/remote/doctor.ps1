param(
    [string] $ExperimentId = "",
    [string] $RemoteHost = "",
    [string] $SshConfigPath = "",
    [switch] $Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$remoteScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $remoteScriptRoot "lib\common.ps1")
. (Join-Path $remoteScriptRoot "lib\ssh.ps1")
. (Join-Path $remoteScriptRoot "lib\result.ps1")

$projectRoot = Get-ProjectRoot -RemoteScriptRoot $remoteScriptRoot
$config = Get-RemoteConfig -ProjectRoot $projectRoot
if (-not [string]::IsNullOrWhiteSpace($RemoteHost)) { $config.RemoteHost = $RemoteHost }
if (-not [string]::IsNullOrWhiteSpace($SshConfigPath)) { $config.SshConfigPath = $SshConfigPath }
if (-not [string]::IsNullOrWhiteSpace($ExperimentId)) { Assert-ExperimentId -ExperimentId $ExperimentId }

$checks = [ordered] @{}
$checks.ssh_config_exists = Test-Path -LiteralPath ([string] $config.SshConfigPath)

$tunnelScript = Find-LocalTunnelScript -Config $config
$checks.local_tunnel_script = $tunnelScript
$checks.local_tunnel_script_exists = -not [string]::IsNullOrWhiteSpace($tunnelScript)

$taskName = [string] $config.ProxyTaskName
$taskOutput = & schtasks.exe /Query /TN $taskName 2>&1
$checks.proxy_task_exists = ($LASTEXITCODE -eq 0)
$checks.proxy_task_name = $taskName

$tunnelAlias = [string] $config.TunnelAlias
$tunnelProc = Get-CimInstance Win32_Process -Filter "name='ssh.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains($tunnelAlias) } |
    Select-Object -First 1
$checks.tunnel_process_running = ($null -ne $tunnelProc)

$sshCheck = Invoke-RemoteSsh `
    -RemoteHost ([string] $config.RemoteHost) `
    -SshConfigPath ([string] $config.SshConfigPath) `
    -ConnectTimeoutSec ([int] $config.ConnectTimeoutSec) `
    -RemoteCommand "exit" `
    -AllowFailure
$checks.ssh_exit_code = $sshCheck.exit_code
$checks.ssh_output = $sshCheck.output

$proxyPort = [int] $config.ProxyPort
$remoteProxyCommand = "bash -lc " + (Quote-PosixSingle "timeout 2 bash -c ':</dev/tcp/127.0.0.1/$proxyPort' >/dev/null 2>&1")
$proxyCheck = Invoke-RemoteSsh `
    -RemoteHost ([string] $config.RemoteHost) `
    -SshConfigPath ([string] $config.SshConfigPath) `
    -ConnectTimeoutSec ([int] $config.ConnectTimeoutSec) `
    -RemoteCommand $remoteProxyCommand `
    -AllowFailure
$checks.remote_proxy_port_open = ($proxyCheck.exit_code -eq 0)

$remoteProxyRoot = [string] $config.RemoteProxyRoot
Assert-RemotePath -Path $remoteProxyRoot -Name "RemoteProxyRoot"
$remotePrereqCommand = "bash -lc " + (Quote-PosixSingle "test -f '$remoteProxyRoot/proxy-env.sh' && test -f '$remoteProxyRoot/ensure-vscode-proxy-active.sh'")
$remotePrereq = Invoke-RemoteSsh `
    -RemoteHost ([string] $config.RemoteHost) `
    -SshConfigPath ([string] $config.SshConfigPath) `
    -ConnectTimeoutSec ([int] $config.ConnectTimeoutSec) `
    -RemoteCommand $remotePrereqCommand `
    -AllowFailure
$checks.remote_proxy_scripts_exist = ($remotePrereq.exit_code -eq 0)

$remoteEntries = @(
    [string] $config.RemoteSmokeEntry,
    [string] $config.RemoteTrainEntry,
    [string] $config.RemoteStatusEntry,
    [string] $config.RemoteCancelEntry
)
foreach ($entry in $remoteEntries) {
    Assert-RemotePath -Path $entry -Name "RemoteEntry"
}
$entryChecks = ($remoteEntries | ForEach-Object { "test -x " + (Quote-PosixSingle $_) }) -join " && "
$remoteEntryCommand = "bash -lc " + (Quote-PosixSingle $entryChecks)
$remoteEntryCheck = Invoke-RemoteSsh `
    -RemoteHost ([string] $config.RemoteHost) `
    -SshConfigPath ([string] $config.SshConfigPath) `
    -ConnectTimeoutSec ([int] $config.ConnectTimeoutSec) `
    -RemoteCommand $remoteEntryCommand `
    -AllowFailure
$checks.remote_entrypoints_exist = ($remoteEntryCheck.exit_code -eq 0)
$checks.remote_entrypoints = $remoteEntries

$coreOk = [bool] ($checks.ssh_config_exists -and ($checks.ssh_exit_code -eq 0) -and $checks.remote_entrypoints_exist)
$proxyOk = [bool] ($checks.tunnel_process_running -and $checks.remote_proxy_port_open -and $checks.remote_proxy_scripts_exist)

$status = New-StatusObject -ScriptName "doctor.ps1" -Ok $coreOk -ExperimentId $ExperimentId -Details @{
    core_ok = $coreOk
    codex_proxy_ok = $proxyOk
    checks = $checks
}

$outPath = ""
if (-not [string]::IsNullOrWhiteSpace($ExperimentId)) {
    $outPath = Get-StatusFilePath -ProjectRoot $projectRoot -ExperimentId $ExperimentId -Name "health"
}
Write-StatusJson -Data $status -Path $outPath -Json:$Json

if (-not $coreOk) {
    exit 1
}
