# Builds a release: runs the tests, the PyInstaller exe and (if Inno Setup 6
# is installed) the installer, all stamped with the version from
# src\smartdoc\__init__.py.
#
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -SkipTests
param([switch]$SkipTests)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$version = (Select-String -Path "$root\src\smartdoc\__init__.py" -Pattern '^__version__ = "([^"]+)"').Matches[0].Groups[1].Value
if ($version -notmatch '^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$') { throw "Version '$version' is not SemVer (MAJOR.MINOR.PATCH)" }
Write-Host "== MewBook $version ==" -ForegroundColor Cyan

if (-not $SkipTests) {
    $env:QT_QPA_PLATFORM = 'offscreen'
    uv run --no-sync pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed -- release aborted.' }
    Remove-Item Env:QT_QPA_PLATFORM
}

# The installer's license page shows the same EULA the app shows on first run.
uv run --no-sync python -c "from smartdoc.presentation.eula_dialog import EULA_TEXT; open(r'$PSScriptRoot\EULA.txt','w',encoding='utf-8-sig').write(EULA_TEXT)"

uv run --no-sync pyinstaller --noconfirm --distpath "$root\dist" --workpath "$root\build_pyinstaller" "$PSScriptRoot\MewBook.spec"
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }

$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc "/DMyAppVersion=$version" "$PSScriptRoot\MewBook.iss"
    if ($LASTEXITCODE -ne 0) { throw 'Inno Setup failed.' }
    Write-Host "Installer: dist\installer\MewBook-Setup-$version.exe" -ForegroundColor Green
} else {
    Write-Warning 'Inno Setup 6 not found (https://jrsoftware.org/isdl.php) -- built the exe only: dist\MewBook\MewBook.exe'
}
