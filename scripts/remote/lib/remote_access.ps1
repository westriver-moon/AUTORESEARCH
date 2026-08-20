Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-DefaultAutoresearchRemoteAccess {
    return @{
        RemoteHost = ""
        TunnelAlias = ""
        SshConfigPath = (Join-Path $env:USERPROFILE ".ssh\config")
        LocalTunnelScript = ""
        ProxyTaskName = ""
        ConnectTimeoutSec = 15
        ExpectedHostname = ""
        ExpectedUser = ""
        LocalProxyPort = 7897
        ProxyPort = 7897
        ProxyProbeUrl = "https://github.com"
        ProxyMode = "optional"
    }
}

function Merge-AutoresearchRemoteAccessValues {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $Destination,
        [Parameter(Mandatory = $true)]
        [hashtable] $Source
    )

    $keys = @($Destination.Keys)
    foreach ($key in $keys) {
        if ($Source.ContainsKey($key)) {
            $Destination[$key] = $Source[$key]
        }
    }
}

function Get-AutoresearchRemoteAccess {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ProjectRoot,
        [string] $RemoteProfile = "",
        [string] $RemoteHost = "",
        [string] $SshConfigPath = ""
    )

    $configuration = Get-AutoresearchConfiguration -ProjectRoot $ProjectRoot
    $access = Get-DefaultAutoresearchRemoteAccess
    Merge-AutoresearchRemoteAccessValues -Destination $access -Source $configuration

    $selectedProfile = $RemoteProfile
    $activeProfile = if ($configuration.ContainsKey("ActiveRemoteProfile")) { [string] $configuration.ActiveRemoteProfile } else { "" }
    if ([string]::IsNullOrWhiteSpace($selectedProfile)) {
        $selectedProfile = $activeProfile
    }

    if (-not [string]::IsNullOrWhiteSpace($selectedProfile)) {
        if (-not $configuration.RemoteProfiles.ContainsKey($selectedProfile)) {
            throw "Remote profile '$selectedProfile' was not found in RemoteProfiles."
        }
        Merge-AutoresearchRemoteAccessValues -Destination $access -Source $configuration.RemoteProfiles[$selectedProfile]
        $access.SelectedRemoteProfile = $selectedProfile
    }

    if (-not [string]::IsNullOrWhiteSpace($RemoteHost)) {
        $access.RemoteHost = $RemoteHost
    }
    if (-not [string]::IsNullOrWhiteSpace($SshConfigPath)) {
        $access.SshConfigPath = $SshConfigPath
    }
    if ([string]::IsNullOrWhiteSpace([string] $access.SshConfigPath)) {
        $access.SshConfigPath = Join-Path $env:USERPROFILE ".ssh\config"
    }
    if ([string]::IsNullOrWhiteSpace([string] $access.RemoteHost)) {
        throw "RemoteHost is required. Configure it in config/autoresearch-v2.local.psd1 or pass -RemoteHost."
    }
    if ([string] $access.ProxyMode -notin @("disabled", "optional", "required")) {
        throw "ProxyMode must be disabled, optional, or required."
    }
    return $access
}

function Get-AutoresearchOpenSshExecutable {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("ssh.exe", "scp.exe")]
        [string] $Name
    )

    $overrideEnv = if ($Name -eq "ssh.exe") { "CODEX_TEST_SSH_EXE" } else { "CODEX_TEST_SCP_EXE" }
    $overrideItem = Get-Item -LiteralPath "Env:$overrideEnv" -ErrorAction SilentlyContinue
    $overrideValue = if ($null -eq $overrideItem) { "" } else { [string] $overrideItem.Value }
    if (-not [string]::IsNullOrWhiteSpace($overrideValue)) {
        if (-not (Test-Path -LiteralPath $overrideValue)) {
            throw "Configured override $overrideEnv was not found: $overrideValue"
        }
        return (Resolve-Path -LiteralPath $overrideValue).Path
    }

    $systemPath = Join-Path $env:WINDIR ("System32\OpenSSH\" + $Name)
    if (Test-Path -LiteralPath $systemPath) {
        return $systemPath
    }
    return (Get-Command $Name -ErrorAction Stop).Source
}

function Get-AutoresearchOpenSshArguments {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $Access
    )

    return @(
        "-F", [string] $Access.SshConfigPath,
        "-o", "BatchMode=yes",
        "-o", ("ConnectTimeout=" + [int] $Access.ConnectTimeoutSec)
    )
}

function Invoke-AutoresearchRemoteCommand {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $Access,
        [Parameter(Mandatory = $true)]
        [string] $RemoteCommand,
        [switch] $AllowFailure
    )

    $ssh = Get-AutoresearchOpenSshExecutable -Name "ssh.exe"
    $arguments = @(Get-AutoresearchOpenSshArguments -Access $Access)
    $arguments += @([string] $Access.RemoteHost, $RemoteCommand)
    $output = & $ssh @arguments 2>&1
    $exitCode = $LASTEXITCODE
    $text = ($output | Out-String).Trim()
    if (($exitCode -ne 0) -and (-not $AllowFailure)) {
        throw "ssh command failed with exit code ${exitCode}: $text"
    }
    return [pscustomobject]@{ exit_code = $exitCode; output = $text }
}

function Invoke-AutoresearchScp {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $Access,
        [Parameter(Mandatory = $true)]
        [string] $Source,
        [Parameter(Mandatory = $true)]
        [string] $Destination,
        [Parameter(Mandatory = $true)]
        [ValidateSet("upload", "download")]
        [string] $Operation,
        [switch] $Recurse
    )

    $scp = Get-AutoresearchOpenSshExecutable -Name "scp.exe"
    $arguments = @(Get-AutoresearchOpenSshArguments -Access $Access)
    if ($Recurse) { $arguments += "-r" }
    $arguments += @($Source, $Destination)

    $output = & $scp @arguments 2>&1
    $exitCode = $LASTEXITCODE
    $text = ($output | Out-String).Trim()
    if ($exitCode -ne 0) {
        throw "scp $Operation failed with exit code ${exitCode}: $text"
    }
    return [pscustomobject]@{ exit_code = $exitCode; output = $text }
}

function Copy-AutoresearchToRemote {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $Access,
        [Parameter(Mandatory = $true)]
        [string] $LocalPath,
        [Parameter(Mandatory = $true)]
        [string] $RemotePath,
        [switch] $Recurse
    )

    return Invoke-AutoresearchScp `
        -Access $Access `
        -Source $LocalPath `
        -Destination (([string] $Access.RemoteHost) + ":" + $RemotePath) `
        -Operation upload `
        -Recurse:$Recurse
}

function Copy-AutoresearchFromRemote {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $Access,
        [Parameter(Mandatory = $true)]
        [string] $RemotePath,
        [Parameter(Mandatory = $true)]
        [string] $LocalPath,
        [switch] $Recurse
    )

    return Invoke-AutoresearchScp `
        -Access $Access `
        -Source (([string] $Access.RemoteHost) + ":" + $RemotePath) `
        -Destination $LocalPath `
        -Operation download `
        -Recurse:$Recurse
}

function Test-AutoresearchLocalTcpPort {
    param(
        [string] $HostName = "127.0.0.1",
        [Parameter(Mandatory = $true)]
        [ValidateRange(1, 65535)]
        [int] $Port,
        [int] $TimeoutMilliseconds = 2000
    )

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $pending = $client.ConnectAsync($HostName, $Port)
        return ($pending.Wait($TimeoutMilliseconds) -and $client.Connected)
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Resolve-AutoresearchLocalTunnelScript {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $Access
    )

    $path = [string] $Access.LocalTunnelScript
    if ([string]::IsNullOrWhiteSpace($path)) {
        return ""
    }
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Configured LocalTunnelScript was not found: $path"
    }
    return (Resolve-Path -LiteralPath $path).Path
}

function Test-AutoresearchRemoteHttpProxy {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $Access
    )

    $parsed = $null
    if (-not [System.Uri]::TryCreate([string] $Access.ProxyProbeUrl, [System.UriKind]::Absolute, [ref] $parsed)) {
        throw "ProxyProbeUrl must be an absolute HTTP(S) URL."
    }
    if ($parsed.Scheme -notin @("http", "https")) {
        throw "ProxyProbeUrl must use HTTP or HTTPS."
    }
    $proxyUrl = "http://127.0.0.1:" + [int] $Access.ProxyPort
    $probe = @(
        "curl", "--silent", "--show-error", "--head", "--output", "/dev/null",
        "--connect-timeout", "5", "--max-time", "15", "--proxy",
        (Quote-PosixSingle $proxyUrl), (Quote-PosixSingle $parsed.AbsoluteUri)
    ) -join " "
    return Invoke-AutoresearchRemoteCommand -Access $Access -RemoteCommand ("bash -lc " + (Quote-PosixSingle $probe)) -AllowFailure
}

function Test-AutoresearchRemoteAccess {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $Access
    )

    $details = [ordered]@{
        profile = if ($Access.ContainsKey("SelectedRemoteProfile")) { [string] $Access.SelectedRemoteProfile } else { "" }
        remote_host = [string] $Access.RemoteHost
        ssh_config_exists = Test-Path -LiteralPath ([string] $Access.SshConfigPath)
        proxy_mode = [string] $Access.ProxyMode
    }
    $sshResult = if ($details.ssh_config_exists) {
        Invoke-AutoresearchRemoteCommand -Access $Access -RemoteCommand "hostname; whoami" -AllowFailure
    } else {
        [pscustomobject]@{ exit_code = -1; output = "SSH config was not found." }
    }
    $details.ssh_exit_code = $sshResult.exit_code
    $details.ssh_output = $sshResult.output

    $proxyRequired = ([string] $Access.ProxyMode -eq "required")
    if ([string] $Access.ProxyMode -eq "disabled") {
        $details.local_proxy_port_open = $null
        $details.remote_proxy_http_ok = $null
        $details.remote_proxy_http_diagnostic = "proxy checks disabled"
    } else {
        $details.local_proxy_port_open = Test-AutoresearchLocalTcpPort -Port ([int] $Access.LocalProxyPort)
        $proxyResult = if ($sshResult.exit_code -eq 0) {
            Test-AutoresearchRemoteHttpProxy -Access $Access
        } else {
            [pscustomobject]@{ exit_code = -1; output = "proxy probe skipped because SSH failed" }
        }
        $details.remote_proxy_http_ok = ($proxyResult.exit_code -eq 0)
        $details.remote_proxy_http_diagnostic = $proxyResult.output
    }

    $identityOk = $true
    $identity = @($sshResult.output -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($identity.Count -ge 2) {
        $details.remote_hostname = $identity[0]
        $details.remote_user = $identity[-1]
        $expectedHostname = if ($Access.ContainsKey("ExpectedHostname")) { [string] $Access.ExpectedHostname } else { "" }
        $expectedUser = if ($Access.ContainsKey("ExpectedUser")) { [string] $Access.ExpectedUser } else { "" }
        if (-not [string]::IsNullOrWhiteSpace($expectedHostname)) {
            $details.expected_hostname = $expectedHostname
            $identityOk = $identityOk -and ($details.remote_hostname -eq $expectedHostname)
        }
        if (-not [string]::IsNullOrWhiteSpace($expectedUser)) {
            $details.expected_user = $expectedUser
            $identityOk = $identityOk -and ($details.remote_user -eq $expectedUser)
        }
    }
    $details.identity_ok = $identityOk

    $sshOk = [bool] ($details.ssh_config_exists -and ($sshResult.exit_code -eq 0) -and $identityOk)
    $proxyOk = [bool] ((-not $proxyRequired) -or ($details.local_proxy_port_open -and $details.remote_proxy_http_ok))
    return [pscustomobject]@{ ok = [bool] ($sshOk -and $proxyOk); details = $details }
}

function Ensure-AutoresearchRemoteAccess {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable] $Access
    )

    if ([string] $Access.ProxyMode -ne "disabled") {
        $tunnelScript = Resolve-AutoresearchLocalTunnelScript -Access $Access
        if (-not [string]::IsNullOrWhiteSpace($tunnelScript)) {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $tunnelScript
            if ($LASTEXITCODE -ne 0) {
                throw "Local tunnel script failed with exit code $LASTEXITCODE."
            }
            Start-Sleep -Seconds 1
        }
    }
    return Test-AutoresearchRemoteAccess -Access $Access
}
