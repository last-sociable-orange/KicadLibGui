# Build the Windows one-file executable.
#
# Usage (from anywhere):
#   .\build\build_windows.ps1
#   .\build\build_windows.ps1 -SkipTests
#
# Requires Python 3.13 x64 with Tkinter, plus the packages in
# requirements-build.txt.  PyInstaller cannot cross-compile.

[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$OneDir
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Get-Python {
    $candidates = @(
        (Join-Path $Root ".venv\Scripts\python.exe"),
        (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
    ) | Where-Object { $_ -and (Test-Path $_) }
    if (-not $candidates) { throw "Python 3.13 was not found. Create .venv or install Python 3.13." }
    return $candidates[0]
}

$Python = Get-Python
Write-Host "Using $Python"
& $Python -c "import sys, tkinter; assert sys.version_info >= (3, 13); print('Python', sys.version.split()[0], 'Tk', tkinter.TkVersion)"

if (-not $SkipTests) {
    & $Python -c "import pytest" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Running tests..."
        & $Python -m pytest -q
        if ($LASTEXITCODE -ne 0) { throw "Tests failed." }
    }
    else {
        Write-Warning "pytest is not installed in this environment; skipping tests."
    }
}

Write-Host "Generating assets..."
& $Python build\make_assets.py

$Version = (& $Python -c "import version; print(version.__version__)").Trim()

if ($OneDir) {
    Write-Host "Running PyInstaller (one-dir fallback)..."
    & $Python -m PyInstaller --clean --noconfirm --onedir --windowed `
        --name KiCadLibGenDir --icon assets\app.ico --add-data "assets;assets" `
        --version-file build\version_info.txt --exclude-module prompt_toolkit gui_main.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
    $Zip = Join-Path $Root "dist\KiCadLibGen-$Version-win64-onedir.zip"
    Compress-Archive -Path (Join-Path $Root "dist\KiCadLibGenDir") -DestinationPath $Zip -Force
    $SelfTest = Start-Process -FilePath (Join-Path $Root "dist\KiCadLibGenDir\KiCadLibGenDir.exe") `
        -ArgumentList "--self-test" -Wait -PassThru
    if ($SelfTest.ExitCode -ne 0) { throw "Self-test failed with exit code $($SelfTest.ExitCode)." }
    $Hash = (Get-FileHash -Algorithm SHA256 $Zip).Hash.ToLower()
    "$Hash  $(Split-Path -Leaf $Zip)" | Set-Content -Encoding ascii "$Zip.sha256"
    Write-Host "Fallback: $Zip ($([math]::Round((Get-Item $Zip).Length / 1MB, 1)) MB)"
    Write-Host "SHA256: $Hash"
    return
}

Write-Host "Running PyInstaller..."
& $Python -m PyInstaller --clean --noconfirm build\kicad_lib_gen_gui.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

$Built = Join-Path $Root "dist\KiCadLibGen.exe"
if (-not (Test-Path $Built)) { throw "Expected build output not found: $Built" }

$Artifact = Join-Path $Root "dist\KiCadLibGen-$Version-win64.exe"
Move-Item -Force $Built $Artifact
$SizeMb = [math]::Round((Get-Item $Artifact).Length / 1MB, 1)
Write-Host "Artifact: $Artifact ($SizeMb MB)"

Write-Host "Self-test..."
$SelfTest = Start-Process -FilePath $Artifact -ArgumentList "--self-test" -Wait -PassThru
if ($SelfTest.ExitCode -ne 0) { throw "Self-test failed with exit code $($SelfTest.ExitCode)." }

Write-Host "Measuring cold start (includes a 0.25 s deliberate lifetime)..."
$Start = Get-Date
$Startup = Start-Process -FilePath $Artifact -ArgumentList "--startup-test" -Wait -PassThru
$Elapsed = (Get-Date) - $Start
if ($Startup.ExitCode -ne 0) { throw "Startup test failed with exit code $($Startup.ExitCode)." }
$Seconds = [math]::Round($Elapsed.TotalSeconds, 2)
Write-Host ("Cold start (window shown and closed): {0} s" -f $Seconds)

$Hash = (Get-FileHash -Algorithm SHA256 $Artifact).Hash.ToLower()
"$Hash  $(Split-Path -Leaf $Artifact)" | Set-Content -Encoding ascii "$Artifact.sha256"
Write-Host "SHA256: $Hash"
Write-Host "Done."
