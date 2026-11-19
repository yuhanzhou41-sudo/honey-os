[CmdletBinding()]
param([Parameter(Mandatory)][string]$Package, [Parameter(Mandatory)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$hash = (Get-FileHash -LiteralPath $Package -Algorithm SHA256).Hash
if ($hash -ne '90778DEB1B77E36292828B4B5833C9255C27533F40E0DDD55891AE718944EDC4') { throw 'Unexpected WebView2 SDK package (expected 1.0.4314.35).' }
$output = New-Item -ItemType Directory -Path $OutputDirectory -Force
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $Package).Path)
try {
    foreach ($entry in @('lib/net462/Microsoft.Web.WebView2.Core.dll','lib/net462/Microsoft.Web.WebView2.WinForms.dll','runtimes/win-x64/native/WebView2Loader.dll')) {
        $file = $archive.GetEntry($entry)
        [IO.Compression.ZipFileExtensions]::ExtractToFile($file, (Join-Path $output.FullName $file.Name), $true)
    }
} finally { $archive.Dispose() }
Push-Location -LiteralPath $output.FullName
try {
    & "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /platform:x64 /target:winexe /codepage:65001 /out:CampusHost.exe /reference:Microsoft.Web.WebView2.Core.dll /reference:Microsoft.Web.WebView2.WinForms.dll "$PSScriptRoot\CampusHost.cs"
    if ($LASTEXITCODE -ne 0) { throw 'CampusHost compilation failed.' }
} finally { Pop-Location }
