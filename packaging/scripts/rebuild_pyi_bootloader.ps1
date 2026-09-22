# Rebuild PyInstaller Windows bootloader from official sources and replace
# stock runw.exe / run.exe in the active PyInstaller install.
#
# Why: stock bootloaders are shared by thousands of unsigned apps and trip
# AV "dropper" heuristics. A locally-built stub has a different PE fingerprint.
#
# Prerequisites (Windows x64):
#   - Git
#   - Python 3 (Quantis .venv / poetry)
#   - C toolchain: Visual Studio Build Tools 2017+ (preferred, static stub)
#     OR MinGW-w64 on PATH (e.g. C:\msys64\ucrt64\bin) - used automatically
#     when MSVC is missing. Pass -Gcc to force MinGW.
#
# Usage:
#   .\packaging\scripts\rebuild_pyi_bootloader.ps1
#   .\packaging\scripts\rebuild_pyi_bootloader.ps1 -Tag v6.22.2
#   .\packaging\scripts\rebuild_pyi_bootloader.ps1 -Gcc
#   .\packaging\scripts\rebuild_pyi_bootloader.ps1 -Dest "C:\path\to\PyInstaller"
#
# After a successful run, rebuild the app:
#   poetry run python packaging/scripts/build_exe.py qt

param(
    [string]$Tag = "",
    [string]$Dest = "",
    [string]$RepoUrl = "https://github.com/pyinstaller/pyinstaller.git",
    [string]$MingwBin = "C:\msys64\ucrt64\bin",
    [switch]$Gcc,
    [switch]$KeepSrc
)

$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $Root

function Get-VenvPython {
    $candidate = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $candidate) {
        return $candidate
    }
    if (Get-Command poetry -ErrorAction SilentlyContinue) {
        $out = & poetry run python -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) {
            return $out.Trim()
        }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return (Get-Command python).Source
    }
    throw "Python not found (need .venv, poetry, or python on PATH)."
}

function Get-FileSha256([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
}

function Test-MsvcAvailable {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path -LiteralPath $vswhere)) {
        return $false
    }
    $vsPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null
    return [bool]$vsPath
}

$Python = Get-VenvPython
Write-Host "==> Resolving PyInstaller install and version"
Write-Host "    python            : $Python"

$resolvePy = @'
import pathlib
import PyInstaller
root = pathlib.Path(PyInstaller.__file__).resolve().parent
print(PyInstaller.__version__)
print(root)
'@

$resolved = @(& $Python -c $resolvePy | Where-Object { $_.Trim() -ne "" })
if ($resolved.Count -lt 2) {
    throw "Could not import PyInstaller. Install it first (or keep a local PyInstaller/ tree)."
}

$InstalledVersion = $resolved[0].Trim()
$InstalledRoot = $resolved[1].Trim()

if (-not $Tag) {
    $Tag = "v$InstalledVersion"
}
if (-not $Dest) {
    $Dest = $InstalledRoot
}

if ([System.IO.Path]::IsPathRooted($Dest)) {
    $Dest = [System.IO.Path]::GetFullPath($Dest)
}
else {
    $Dest = [System.IO.Path]::GetFullPath((Join-Path $Root $Dest))
}

$BootDest = Join-Path $Dest "bootloader\Windows-64bit-intel"
if (-not (Test-Path -LiteralPath $BootDest)) {
    throw "Bootloader destination not found: $BootDest`nPass -Dest to the PyInstaller package root that contains bootloader/Windows-64bit-intel."
}

$useGcc = [bool]$Gcc
if (-not $useGcc -and -not (Test-MsvcAvailable)) {
    if (Test-Path -LiteralPath (Join-Path $MingwBin "gcc.exe")) {
        Write-Warning "MSVC not found; falling back to MinGW at $MingwBin"
        $useGcc = $true
    }
    else {
        throw "No C toolchain: install VS Build Tools (C++) or MinGW-w64 (e.g. msys2 ucrt64), or pass -MingwBin."
    }
}

Write-Host "    installed version : $InstalledVersion"
Write-Host "    clone tag         : $Tag"
Write-Host "    replace into      : $BootDest"
Write-Host "    toolchain         : $(if ($useGcc) { 'MinGW (--gcc)' } else { 'MSVC' })"

if ($useGcc) {
    $env:PATH = "$MingwBin;" + $env:PATH
    foreach ($tool in @("gcc.exe", "windres.exe", "strip.exe")) {
        if (-not (Test-Path -LiteralPath (Join-Path $MingwBin $tool))) {
            throw "MinGW tool missing: $MingwBin\$tool"
        }
    }
}

$SrcDir = Join-Path $Root "build\pyinstaller-src"
$SrcParent = Split-Path $SrcDir -Parent
New-Item -ItemType Directory -Force -Path $SrcParent | Out-Null

if (Test-Path -LiteralPath $SrcDir) {
    Write-Host "==> Updating existing clone at $SrcDir"
    Push-Location $SrcDir
    try {
        git fetch --tags --force --depth 1 origin "refs/tags/${Tag}:refs/tags/${Tag}"
        git checkout -f "tags/$Tag"
        git clean -fdx -- bootloader
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "==> Cloning $RepoUrl ($Tag) -> $SrcDir"
    git clone --depth 1 --branch $Tag $RepoUrl $SrcDir
}

$BootSrc = Join-Path $SrcDir "bootloader"
if (-not (Test-Path -LiteralPath (Join-Path $BootSrc "src"))) {
    throw "Clone is missing bootloader/src - refuse to use a wheel-extracted tree without sources."
}

$wafExtra = @()
if ($useGcc) {
    $wafExtra += "--gcc"
}

Write-Host "==> Building bootloader (waf configure all $($wafExtra -join ' ') --target-arch=64bit)"
Push-Location $BootSrc
try {
    # Run waf with repo venv python while cwd is the clone (poetry -C would also work,
    # but invoking python.exe avoids Poetry reading the clone's pyproject.toml).
    $waf = Join-Path $BootSrc "waf"
    & $Python $waf distclean 2>$null
    & $Python $waf @(@("configure", "all") + $wafExtra + @("--target-arch=64bit"))
    if ($LASTEXITCODE -ne 0) {
        throw "waf build failed with exit $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

$BuiltDir = Join-Path $SrcDir "PyInstaller\bootloader\Windows-64bit-intel"
if (-not (Test-Path -LiteralPath $BuiltDir)) {
    throw "Build finished but artifacts not found at $BuiltDir"
}

$names = @("runw.exe", "run.exe", "runw_d.exe", "run_d.exe")
$copied = @()
Write-Host "==> Installing built bootloaders into $BootDest"
foreach ($name in $names) {
    $src = Join-Path $BuiltDir $name
    if (-not (Test-Path -LiteralPath $src)) {
        continue
    }
    $dst = Join-Path $BootDest $name
    $before = if (Test-Path -LiteralPath $dst) { Get-FileSha256 $dst } else { $null }
    Copy-Item -LiteralPath $src -Destination $dst -Force
    $after = Get-FileSha256 $dst
    $copied += [pscustomobject]@{
        Name    = $name
        Before  = $before
        After   = $after
        Changed = ($before -ne $after)
    }
    Write-Host ("    {0}: {1}" -f $name, $(if ($before -ne $after) { "updated" } else { "unchanged hash" }))
    Write-Host ("             SHA256 {0}" -f $after)
}

$runw = $copied | Where-Object { $_.Name -eq "runw.exe" } | Select-Object -First 1
if (-not $runw) {
    throw "runw.exe was not produced - windowed Quantis builds need it."
}

Write-Host ""
Write-Host "==> OK: custom bootloader installed"
Write-Host "    runw.exe SHA256: $($runw.After)"
if ($runw.Before -and -not $runw.Changed) {
    Write-Warning "runw.exe hash matches the previous file. Rebuild may have reproduced a stock binary (same toolchain/sources as the release)."
}
Write-Host "    Next: poetry run python packaging/scripts/build_exe.py qt"

if (-not $KeepSrc) {
    Write-Host "    Tip: pass -KeepSrc to retain $SrcDir for inspection."
}
