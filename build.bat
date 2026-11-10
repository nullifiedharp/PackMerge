@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title PackMerge build

echo.
echo ==============================================
echo   PackMerge - build exe + installer
echo ==============================================
echo.

:: ---- Python -------------------------------------------------------------
where python >nul 2>nul
if errorlevel 1 (
    echo [!] Python was not found on PATH. Install Python 3.13 from python.org
    echo     and tick "Add python.exe to PATH", then run this again.
    goto :fail
)

:: version comes from packmerge.py so there is one place to bump it
set "VERSION="
for /f "tokens=2" %%v in ('python packmerge.py --version') do set "VERSION=%%v"
if not defined VERSION (
    echo [!] Couldn't read the version from packmerge.py
    goto :fail
)
echo Building PackMerge %VERSION%
echo.

:: ---- PyInstaller --------------------------------------------------------
echo [1/3] Installing / updating PyInstaller...
python -m pip install --upgrade --quiet pyinstaller
if errorlevel 1 goto :fail

echo [2/3] Building PackMerge.exe...
if exist build rmdir /s /q build
if exist dist\PackMerge rmdir /s /q dist\PackMerge
python -m PyInstaller --noconfirm --clean --windowed --onedir ^
    --name PackMerge ^
    --icon assets\icon.ico ^
    --add-data "assets;assets" ^
    packmerge.py
if errorlevel 1 goto :fail
if not exist dist\PackMerge\PackMerge.exe (
    echo [!] PyInstaller finished but dist\PackMerge\PackMerge.exe is missing.
    goto :fail
)

:: ---- Inno Setup ---------------------------------------------------------
echo [3/3] Building the installer...
call :find_iscc
if not defined ISCC (
    echo     Inno Setup not found - installing it with winget...
    winget install --id JRSoftware.InnoSetup -e --accept-source-agreements --accept-package-agreements
    call :find_iscc
)
if not defined ISCC (
    echo [!] Still can't find ISCC.exe. Install Inno Setup 6 from https://jrsoftware.org/isdl.php
    echo     then run this again. The plain exe is already in dist\PackMerge\
    goto :fail
)

"%ISCC%" /Qp /DMyAppVersion=%VERSION% installer.iss
if errorlevel 1 goto :fail

echo.
echo ==============================================
echo   Done!
echo   Installer: dist\PackMerge-Setup-%VERSION%.exe
echo   Portable:  dist\PackMerge\PackMerge.exe
echo ==============================================
echo.
pause
exit /b 0

:find_iscc
set "ISCC="
for /f "delims=" %%i in ('where iscc 2^>nul') do if not defined ISCC set "ISCC=%%i"
if defined ISCC exit /b 0
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if defined ISCC exit /b 0
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if defined ISCC exit /b 0
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if defined ISCC exit /b 0
if exist "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
if defined ISCC exit /b 0
if exist "%ProgramFiles%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 7\ISCC.exe"
exit /b 0

:fail
echo.
echo Build FAILED - see the messages above.
echo.
pause
exit /b 1
