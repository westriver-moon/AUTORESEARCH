param(
    [Parameter(Mandatory = $true)]
    [string] $RequestPath,
    [Parameter(Mandatory = $true)]
    [string] $ResultPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

try {
    $request = Get-Content -LiteralPath $RequestPath -Raw | ConvertFrom-Json
    $profiles = @($request.profiles)
    if ($profiles.Count -eq 0) {
        throw "No remote profiles are available."
    }
    $defaultIndex = [int] $request.default_index
    if (($defaultIndex -lt 1) -or ($defaultIndex -gt $profiles.Count)) {
        $defaultIndex = 1
    }

    Write-Host ""
    Write-Host "Select remote profile:"
    Write-Host "Number  Server  Address  Port  User"
    for ($index = 0; $index -lt $profiles.Count; $index++) {
        $profile = $profiles[$index]
        Write-Host ([string]::Format("[{0}] {1} {2} {3} {4}", $index + 1, $profile.server, $profile.ip, $profile.port, $profile.user))
    }

    while ($true) {
        $selection = Read-Host "Input number (or Enter for default $defaultIndex)"
        if ([string]::IsNullOrWhiteSpace($selection)) {
            $selectedIndex = $defaultIndex - 1
        } else {
            $parsed = 0
            if (-not [int]::TryParse($selection, [ref] $parsed)) {
                Write-Host "Invalid selection: $selection"
                continue
            }
            $selectedIndex = $parsed - 1
        }
        if (($selectedIndex -lt 0) -or ($selectedIndex -ge $profiles.Count)) {
            Write-Host "Selection out of range: $selection"
            continue
        }
        Set-Content -LiteralPath $ResultPath -Value ([string] $profiles[$selectedIndex].profile) -Encoding UTF8
        exit 0
    }
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
