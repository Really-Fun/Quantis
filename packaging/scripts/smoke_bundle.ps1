<#
.SYNOPSIS
    Проверка собранного Quantis изнутри exe (Windows): звук mp3/m4a/webm,
    SVG-иконки, темы, импорты, yt-dlp, сертификаты — см. packaging/smoke/plugin.py.

.DESCRIPTION
    Данные — во временной папке (QUANTIS_DATA_DIR). Настройки Quantis на
    Windows живут в реестре: чтобы включить плагин-проверку, скрипт на время
    пишет HKCU\Software\ReallyFun\Quantis\plugins\enabled и потом возвращает
    прежнее значение.

    -Installer: поставить установщик тихо во временный каталог, проверить
    установленный exe и удалить.

.EXAMPLE
    .\packaging\scripts\smoke_bundle.ps1
    .\packaging\scripts\smoke_bundle.ps1 -Installer .\dist\installer\Quantis-0.3.2-setup.exe
    .\packaging\scripts\smoke_bundle.ps1 -Media D:\Music
#>
param(
    [string]$App = "",
    [string]$Installer = "",
    [string]$Media = ""
)
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
if (-not $Media) { $Media = Join-Path $Root "music" }

$Box = Join-Path $env:TEMP ("quantis-smoke-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
$PluginDir = Join-Path $Box "data\plugins_dir\bundle_smoke"
$MediaDir = Join-Path $Box "media"
New-Item -ItemType Directory -Force -Path $PluginDir, $MediaDir | Out-Null
Copy-Item (Join-Path $Root "packaging\smoke\plugin.py") (Join-Path $PluginDir "plugin.py")
'{"id": "bundle_smoke", "name": "smoke"}' | Set-Content -Encoding utf8 (Join-Path $PluginDir "manifest.json")
foreach ($ext in "mp3", "m4a", "webm") {
    $f = Get-ChildItem -Path $Media -Filter "*.$ext" -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($f) { Copy-Item -LiteralPath $f.FullName (Join-Path $MediaDir "sample.$ext") }
}

$InstallDir = $null
if ($Installer) {
    # Тот же AppId, что у настоящей установки: тестовая перепишет её
    # регистрацию, а тестовое удаление снимет. На такой машине — только без -Installer.
    $AppKey = "Software\Microsoft\Windows\CurrentVersion\Uninstall\{8E2F2C41-4B7D-4B1E-9E4A-3C6D5A9B7F10}_is1"
    foreach ($hive in "HKCU:", "HKLM:", "HKLM:\Software\WOW6432Node") {
        $path = if ($hive -like "*WOW6432Node") { "$hive\" + ($AppKey -replace "^Software\\", "") } else { "$hive\$AppKey" }
        if (Test-Path $path) {
            throw "Quantis уже установлен ($path). Проверку установщика запускайте на машине без Quantis; собранную папку можно проверить без -Installer."
        }
    }
    $InstallDir = Join-Path $Box "install"
    Write-Host "==> Тихая установка в $InstallDir"
    $p = Start-Process -FilePath $Installer -Wait -PassThru -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER",
        "/NOICONS", "/TASKS=", "/DIR=`"$InstallDir`""
    )
    if ($p.ExitCode -ne 0) { throw "Установщик вернул $($p.ExitCode)" }
    $App = Get-ChildItem -Path $InstallDir -Filter "Quantis*.exe" -File |
        Where-Object { $_.Name -notlike "unins*" } | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $App) { $App = Join-Path $Root "dist\Quantis\Quantis.exe" }
if (-not (Test-Path $App)) { throw "Нет exe: $App" }
Write-Host "==> Проверяю $App"

$Key = "HKCU:\Software\ReallyFun\Quantis\plugins"
$HadKey = Test-Path $Key
$Old = $null
$OldKind = $null
if ($HadKey) {
    $Old = (Get-ItemProperty -Path $Key -Name enabled -ErrorAction SilentlyContinue).enabled
    # несколько плагинов Qt хранит как REG_MULTI_SZ — вернём тем же типом
    if ($null -ne $Old) { $OldKind = (Get-Item -Path $Key).GetValueKind("enabled") }
}
$Result = Join-Path $Box "result.json"
$code = 1
try {
    New-Item -Path $Key -Force | Out-Null
    Set-ItemProperty -Path $Key -Name enabled -Value "bundle_smoke"
    $env:QUANTIS_DATA_DIR = Join-Path $Box "data"
    $env:QUANTIS_ENABLE_ADAPTER = "0"
    $env:QT_QPA_PLATFORM = "offscreen"
    $env:SMOKE_MEDIA = $MediaDir
    $env:SMOKE_OUT = $Result
    $proc = Start-Process -FilePath $App -PassThru
    if (-not $proc.WaitForExit(60000)) { $proc.Kill(); Write-Host "Таймаут 60 с" }
} finally {
    # вернуть настройки пользователя как были
    if ($null -ne $Old) { New-ItemProperty -Path $Key -Name enabled -Value $Old -PropertyType $OldKind -Force | Out-Null }
    elseif ($HadKey) { Remove-ItemProperty -Path $Key -Name enabled -ErrorAction SilentlyContinue }
    else { Remove-Item -Path $Key -Recurse -ErrorAction SilentlyContinue }
    foreach ($v in "QUANTIS_DATA_DIR", "QUANTIS_ENABLE_ADAPTER", "QT_QPA_PLATFORM", "SMOKE_MEDIA", "SMOKE_OUT") {
        Remove-Item "Env:$v" -ErrorAction SilentlyContinue
    }
}

if (Test-Path $Result) {
    Get-Content $Result -Encoding utf8
    poetry run python (Join-Path $Root "packaging\smoke\verdict.py") $Result
    $code = $LASTEXITCODE
} else {
    Write-Host "FAIL: проверка не отработала — result.json нет. Данные: $Box"
}

if ($InstallDir) {
    $unins = Get-ChildItem -Path $InstallDir -Filter "unins*.exe" -File | Select-Object -First 1
    if ($unins) {
        Write-Host "==> Удаляю тестовую установку"
        Start-Process -FilePath $unins.FullName -Wait -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"
    }
}
Write-Host "Песочница: $Box"
exit $code
