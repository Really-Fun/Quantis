# Сборка Quantis (Qt Multimedia) или Quantis-VLC
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("qt", "vlc")]
    [string]$Backend,

    [string]$VlcHome = $env:VLC_HOME
)

$ErrorActionPreference = "Stop"
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $Root

if ($Backend -eq "vlc") {
    poetry install --with dev,build,vlc
    if ($VlcHome) {
        $env:VLC_HOME = $VlcHome
    }
} else {
    poetry install --with dev,build
}

poetry run python packaging/scripts/build_exe.py $Backend
