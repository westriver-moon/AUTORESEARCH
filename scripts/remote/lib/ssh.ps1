Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-OpenSshExecutable {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("ssh.exe", "scp.exe")]
        [string] $Name
    )

    $systemPath = Join-Path $env:WINDIR ("System32\OpenSSH\" + $Name)
    if (Test-Path -LiteralPath $systemPath) {
        return $systemPath
    }

    $cmd = Get-Command $Name -ErrorAction Stop
    return $cmd.Source
}

function Invoke-RemoteSsh {
    param(
        [Parameter(Mandatory = $true)]
        [string] $RemoteHost,
        [Parameter(Mandatory = $true)]
        [string] $SshConfigPath,
        [Parameter(Mandatory = $true)]
        [string] $RemoteCommand,
        [int] $ConnectTimeoutSec = 15,
        [switch] $AllowFailure
    )

    $ssh = Get-OpenSshExecutable -Name "ssh.exe"
    $argsList = @(
        "-F", $SshConfigPath,
        "-o", "BatchMode=yes",
        "-o", ("ConnectTimeout=" + $ConnectTimeoutSec),
        $RemoteHost,
        $RemoteCommand
    )

    $output = & $ssh @argsList 2>&1
    $exitCode = $LASTEXITCODE
    $text = ($output | Out-String).Trim()

    if (($exitCode -ne 0) -and (-not $AllowFailure)) {
        throw "ssh command failed with exit code ${exitCode}: $text"
    }

    return [pscustomobject] @{
        exit_code = $exitCode
        output = $text
    }
}

function Invoke-RemoteScpTo {
    param(
        [Parameter(Mandatory = $true)]
        [string] $RemoteHost,
        [Parameter(Mandatory = $true)]
        [string] $SshConfigPath,
        [Parameter(Mandatory = $true)]
        [string] $LocalPath,
        [Parameter(Mandatory = $true)]
        [string] $RemotePath,
        [switch] $Recurse
    )

    $scp = Get-OpenSshExecutable -Name "scp.exe"
    $argsList = @("-F", $SshConfigPath)
    if ($Recurse) {
        $argsList += "-r"
    }
    $argsList += @($LocalPath, ("${RemoteHost}:$RemotePath"))

    $output = & $scp @argsList 2>&1
    $exitCode = $LASTEXITCODE
    $text = ($output | Out-String).Trim()

    if ($exitCode -ne 0) {
        throw "scp upload failed with exit code ${exitCode}: $text"
    }

    return [pscustomobject] @{
        exit_code = $exitCode
        output = $text
    }
}

function Invoke-RemoteScpFrom {
    param(
        [Parameter(Mandatory = $true)]
        [string] $RemoteHost,
        [Parameter(Mandatory = $true)]
        [string] $SshConfigPath,
        [Parameter(Mandatory = $true)]
        [string] $RemotePath,
        [Parameter(Mandatory = $true)]
        [string] $LocalPath,
        [switch] $Recurse
    )

    $scp = Get-OpenSshExecutable -Name "scp.exe"
    $argsList = @("-F", $SshConfigPath)
    if ($Recurse) {
        $argsList += "-r"
    }
    $argsList += @(("${RemoteHost}:$RemotePath"), $LocalPath)

    $output = & $scp @argsList 2>&1
    $exitCode = $LASTEXITCODE
    $text = ($output | Out-String).Trim()

    if ($exitCode -ne 0) {
        throw "scp download failed with exit code ${exitCode}: $text"
    }

    return [pscustomobject] @{
        exit_code = $exitCode
        output = $text
    }
}
