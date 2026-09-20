# Builds MewBook: runs the tests, the PyInstaller exe and (if Inno Setup 6 is installed) the installer, all
# stamped with the version from src\smartdoc\__init__.py.
#
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1              tests + exe (+ installer)
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -SkipTests
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -Release     a publishable set, see below
#
# -Release refuses to go on unless the tests run, the working tree is clean (so the source package matches what
# was built) and Inno Setup is installed. It then writes dist\release\ with the installer, the AGPL source
# package (git archive of the tag vX.Y.Z, or of HEAD if the tag does not exist yet) and SHA256SUMS.txt computed
# after signing. Tagging, pushing and publishing stay a manual step: docs\RELEASE_CHECKLIST.md.
#
# Signing is optional. Set these in YOUR session (nothing is stored in the repo or printed):
#   MEWBOOK_SIGN_PFX, MEWBOOK_SIGN_PFX_PASSWORD   a .pfx certificate file and its password, or
#   MEWBOOK_SIGN_THUMBPRINT                       a certificate already in the Windows certificate store
#   MEWBOOK_SIGN_TIMESTAMP_URL                    optional, default http://timestamp.digicert.com
# Without them the exe and installer are left unsigned and the script says so (SmartScreen will warn).
param([switch]$SkipTests, [switch]$Release)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$version = (Select-String -Path "$root\src\smartdoc\__init__.py" -Pattern '^__version__ = "([^"]+)"').Matches[0].Groups[1].Value
if ($version -notmatch '^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$') { throw "Version '$version' is not SemVer (MAJOR.MINOR.PATCH)" }
Write-Host "== MewBook $version ==" -ForegroundColor Cyan

$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1

# -Release preconditions: fail now, not after a ten-minute build.
if ($Release) {
    if ($SkipTests) { throw '-Release cannot be combined with -SkipTests.' }
    if (-not $iscc) { throw 'Inno Setup 6 is required for -Release (https://jrsoftware.org/isdl.php).' }
    if (git status --porcelain) { throw 'The working tree has uncommitted changes: commit first so the source package matches what is built.' }
}

$script:unsigned = @()

function Find-SignTool {
    $found = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($found) { return $found.Source }
    $kits = "${env:ProgramFiles(x86)}\Windows Kits\10\bin"
    if (Test-Path $kits) {
        return Get-ChildItem $kits -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '\\x64\\' } | Sort-Object FullName -Descending |
            Select-Object -First 1 -ExpandProperty FullName
    }
}

function Get-SigningArguments {
    $stamp = if ($env:MEWBOOK_SIGN_TIMESTAMP_URL) { $env:MEWBOOK_SIGN_TIMESTAMP_URL } else { 'http://timestamp.digicert.com' }
    $common = @('sign', '/fd', 'SHA256', '/tr', $stamp, '/td', 'SHA256')
    if ($env:MEWBOOK_SIGN_PFX) {
        $signArgs = $common + @('/f', $env:MEWBOOK_SIGN_PFX)
        if ($env:MEWBOOK_SIGN_PFX_PASSWORD) { $signArgs += @('/p', $env:MEWBOOK_SIGN_PFX_PASSWORD) }
        return $signArgs
    }
    if ($env:MEWBOOK_SIGN_THUMBPRINT) { return $common + @('/sha1', $env:MEWBOOK_SIGN_THUMBPRINT) }
    return $null
}

function Invoke-Sign([string]$file) {
    if (-not (Test-Path $file)) { return }
    $signArgs = Get-SigningArguments
    if (-not $signArgs) { $script:unsigned += $file; return }
    $signtool = Find-SignTool
    if (-not $signtool) {
        Write-Warning 'Signing is configured but signtool.exe was not found (install the Windows SDK) -- not signing.'
        $script:unsigned += $file
        return
    }
    & $signtool @signArgs $file | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Signing failed for $file (certificate or timestamp server problem)." }
    & $signtool verify /pa $file | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "The signature on $file does not verify." }
    Write-Host "Signed: $file" -ForegroundColor Green
}

if (-not $SkipTests) {
    $env:QT_QPA_PLATFORM = 'offscreen'
    uv run --no-sync pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed -- release aborted.' }
    Remove-Item Env:QT_QPA_PLATFORM
}

uv run --no-sync pyinstaller --noconfirm --distpath "$root\dist" --workpath "$root\build_pyinstaller" "$PSScriptRoot\MewBook.spec"
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }

# The build must carry the id of the commit it was made from (MewBook.spec stamps it): error reports name it and it is
# how a reported error is traced to the exact source (docs/handoff/09, ERR-A14). A release must match HEAD exactly.
$stampFile = "$root\dist\MewBook\_internal\smartdoc\data\build_info.json"
if (-not (Test-Path $stampFile)) { throw 'The build carries no smartdoc\data\build_info.json.' }
$buildId = (Get-Content $stampFile -Raw | ConvertFrom-Json).build_id
$head = (git rev-parse --short=12 HEAD)
if ($Release -and $buildId -ne $head) { throw "The build id '$buildId' does not match the commit '$head'." }
if ($buildId -eq 'dev' -or $buildId -like '*-dirty') {
    Write-Warning "Build id '$buildId': a developer build. It works, but it will not send error reports (only a clean commit does)."
} else {
    Write-Host "Build id: $buildId" -ForegroundColor Cyan
}
Invoke-Sign "$root\dist\MewBook\MewBook.exe"  # before the installer, so the installer packs the signed exe

$installer = "$root\dist\installer\MewBook-Setup-$version.exe"
if ($iscc) {
    & $iscc "/DMyAppVersion=$version" "$PSScriptRoot\MewBook.iss"
    if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed.' }
    Invoke-Sign $installer
    Write-Host "Installer: dist\installer\MewBook-Setup-$version.exe" -ForegroundColor Green
} else {
    Write-Warning 'Inno Setup 6 not found (https://jrsoftware.org/isdl.php) -- built the exe only: dist\MewBook\MewBook.exe'
}

if ($Release) {
    $out = "$root\dist\release"
    New-Item -ItemType Directory -Force $out | Out-Null
    Get-ChildItem $out -File | Remove-Item -Force  # only this script's own previous output
    Copy-Item $installer $out

    $tag = "v$version"
    git rev-parse -q --verify "refs/tags/$tag" | Out-Null
    $ref = if ($LASTEXITCODE -eq 0) { $tag } else { 'HEAD' }
    if ($ref -eq 'HEAD') { Write-Warning "Tag $tag does not exist yet: the source package is built from HEAD. After tagging, run -Release again so the package matches the tag." }
    git archive --format=zip --prefix="MewBook-$version/" -o "$out\MewBook-$version-source.zip" $ref
    if ($LASTEXITCODE -ne 0) { throw 'git archive failed.' }

    # Hashes last, after signing: signing changes the file.
    Get-ChildItem $out -File | Where-Object { $_.Name -ne 'SHA256SUMS.txt' } | Sort-Object Name | ForEach-Object {
        '{0}  {1}' -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Name
    } | Set-Content -Encoding ASCII "$out\SHA256SUMS.txt"
    Write-Host "Release files: dist\release\ (installer, MewBook-$version-source.zip, SHA256SUMS.txt)" -ForegroundColor Green
}

if ($script:unsigned.Count -gt 0) {
    Write-Warning ('Not signed (Windows SmartScreen will warn on first run): ' + (($script:unsigned | ForEach-Object { Split-Path $_ -Leaf }) -join ', ') + '. Set MEWBOOK_SIGN_PFX or MEWBOOK_SIGN_THUMBPRINT to sign.')
}
