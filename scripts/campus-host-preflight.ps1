[CmdletBinding()]
param()

$client = 'Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
$machineRoot = if ([Environment]::Is64BitOperatingSystem -and [Environment]::Is64BitProcess) {
    'HKLM:\SOFTWARE\WOW6432Node'
} else {
    'HKLM:\SOFTWARE'
}
$versions = foreach ($root in @('HKCU:\SOFTWARE', $machineRoot)) {
    $value = Get-ItemPropertyValue -LiteralPath (Join-Path $root $client) -Name pv -ErrorAction SilentlyContinue
    $version = $null
    if ([version]::TryParse($value, [ref]$version) -and $version -gt [version]'0.0.0.0') { $version }
}
$runtime = $versions | Sort-Object -Descending | Select-Object -First 1
$dotnet = Get-Command dotnet.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
$sdkAvailable = $false
if ($dotnet) {
    $sdks = & $dotnet.Source --list-sdks 2>$null
    $sdkAvailable = $LASTEXITCODE -eq 0 -and [bool]$sdks
}
[pscustomobject]@{
    webview2RuntimeDetected = [bool]$runtime
    webview2RuntimeVersion = if ($runtime) { $runtime.ToString() } else { $null }
    dotnetSdkOnPath = $sdkAvailable
    hostLaunchVerified = $false
    campusLoginVerified = $false
} | ConvertTo-Json
