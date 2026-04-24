# Optional Authenticode signing for dist\bacnet-commissioning.exe (Windows only).
# When repository secrets are not set, exits 0 without doing anything.
#
# Required environment variables (typically from GitHub Actions secrets):
#   WINDOWS_CODESIGN_PFX_BASE64 — PFX file as base64
#   WINDOWS_CODESIGN_PFX_PASSWORD — PFX password (may be empty for some tokens)
#
# Optional:
#   WINDOWS_CODESIGN_TIMESTAMP_URL — RFC3161 timestamp server (default DigiCert)

$ErrorActionPreference = "Stop"
$exe = Join-Path $PSScriptRoot "..\..\dist\bacnet-commissioning.exe" | Resolve-Path -ErrorAction SilentlyContinue
if (-not $exe) {
    Write-Host "sign_windows_exe: dist\bacnet-commissioning.exe not found; skip"
    exit 0
}

if (-not $env:WINDOWS_CODESIGN_PFX_BASE64) {
    Write-Host "sign_windows_exe: WINDOWS_CODESIGN_PFX_BASE64 not set; skip signing"
    exit 0
}

$ts = if ($env:WINDOWS_CODESIGN_TIMESTAMP_URL) { $env:WINDOWS_CODESIGN_TIMESTAMP_URL } else { "http://timestamp.digicert.com" }

$pfxPath = Join-Path $env:TEMP "bacnet-codesign.pfx"
[IO.File]::WriteAllBytes($pfxPath, [Convert]::FromBase64String($env:WINDOWS_CODESIGN_PFX_BASE64))

$signtool = $null
foreach ($cand in @(
        "${env:ProgramFiles(x86)}\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe",
        "${env:ProgramFiles(x86)}\Windows Kits\10\bin\x64\signtool.exe"
    )) {
    if (Test-Path $cand) { $signtool = $cand; break }
}
if (-not $signtool) {
    $found = Get-ChildItem -Path "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Filter "signtool.exe" -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
        Select-Object -First 1
    if ($found) { $signtool = $found.FullName }
}
if (-not $signtool) {
    Write-Error "signtool.exe not found; install Windows SDK or add signtool to PATH"
    exit 1
}

$passArg = @()
if ($null -ne $env:WINDOWS_CODESIGN_PFX_PASSWORD) {
    $passArg = @("/p", $env:WINDOWS_CODESIGN_PFX_PASSWORD)
}

& $signtool sign /f $pfxPath @passArg /tr $ts /td SHA256 /fd SHA256 $exe
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "sign_windows_exe: signed $exe"
exit 0
