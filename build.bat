@echo off
REM Сборка CleanPlayer.exe на Windows.
REM Требуется: активированный venv с установленными зависимостями + PyInstaller.
REM Локали ytmusicapi (RU и др.) подключаются через spec.

echo Checking PyInstaller...
python -c "import PyInstaller" 2>nul || (
    echo PyInstaller not found. Install with: pip install pyinstaller
    exit /b 1
)

echo Building CleanPlayer...
pyinstaller --noconfirm --clean CleanPlayer.spec

if %ERRORLEVEL% neq 0 (
    echo Build failed.
    exit /b 1
)

echo.
echo Done. Run: dist\CleanPlayer\CleanPlayer.exe
echo VLC must be installed on the target machine.
pause
