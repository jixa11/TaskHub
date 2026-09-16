@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
title Build TaskHub 1.0.0

echo.
echo =====================================================
echo  TaskHub 1.0.0 - One EXE Build
echo =====================================================
echo.

set "PY_BOOT="
where py >nul 2>&1
if not errorlevel 1 (
  py -3.12 --version >nul 2>&1 && set "PY_BOOT=py -3.12"
  if not defined PY_BOOT py -3.11 --version >nul 2>&1 && set "PY_BOOT=py -3.11"
  if not defined PY_BOOT py -3 --version >nul 2>&1 && set "PY_BOOT=py -3"
)
if not defined PY_BOOT (
  where python >nul 2>&1 && set "PY_BOOT=python"
)
if not defined PY_BOOT (
  echo [ERROR] No Python interpreter was found.
  echo Install 64-bit Python and enable Add Python to PATH.
  pause
  exit /b 1
)
REM 3.11 and 3.12 are preferred because they have been used for every release
REM so far, but any newer 3.x that can install requirements.txt is fine. This
REM build has been verified on 3.14 as well.

echo [1/4] Creating isolated build environment...
if not exist ".venv-lan\Scripts\python.exe" %PY_BOOT% -m venv .venv-lan
REM Some Python installs ship a damaged bundled pip. venv then prints an
REM ensurepip error and returns a non-zero code even though the environment is
REM perfectly usable, which used to stop the build here for no reason. What
REM matters is whether we ended up with a working interpreter and pip, so that
REM is what gets checked.
set "PY=.venv-lan\Scripts\python.exe"
if not exist "%PY%" (
  echo [ERROR] Could not create .venv-lan.
  echo Delete the .venv-lan folder and run this script again.
  pause
  exit /b 1
)
"%PY%" --version

echo [2/4] Installing dependencies...
"%PY%" -m pip --version >nul 2>&1
if errorlevel 1 (
  echo [INFO] The environment has no working pip; repairing it from the system Python...
  %PY_BOOT% -m pip --python "%PY%" install --upgrade pip
  if errorlevel 1 (
    echo [ERROR] pip could not be installed into .venv-lan.
    echo Repair the system pip first:  python -m pip install --force-reinstall pip
    pause
    exit /b 1
  )
)
"%PY%" -m pip install --upgrade pip >nul
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [FONT] Checking Vazirmatn faces...
if not exist "src\web\Vazirmatn-Regular.ttf" (
  echo [ERROR] src\web\Vazirmatn-Regular.ttf is missing.
  echo Restore it from the source package; the build must not produce an EXE without it.
  pause
  exit /b 1
)
if not exist "src\web\Vazirmatn-Bold.ttf" (
  echo [ERROR] src\web\Vazirmatn-Bold.ttf is missing.
  echo Without the bold face every heading and button renders at regular weight.
  pause
  exit /b 1
)
echo [OK] Vazirmatn regular and bold are ready.
echo.

echo [3/4] Running automated tests and LAN release checks...
"%PY%" run_tests.py
if errorlevel 1 goto :error
"%PY%" scripts\run_lan_checks.py
if errorlevel 1 goto :error

echo [4/4] Building one elevated Windows executable...
if exist "build\TaskHub" rmdir /s /q "build\TaskHub"
if exist "dist\TaskHub.exe" del /q "dist\TaskHub.exe"

"%PY%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --uac-admin ^
  --name "TaskHub" ^
  --paths "src" ^
  --icon "src\web\icon.ico" ^
  --add-data "src\web\ui.html;web" ^
  --add-data "src\web\v7_ui.js;web" ^
  --add-data "src\web\v7_ui.css;web" ^
  --add-data "src\web\v8_ui.js;web" ^
  --add-data "src\web\v8_ui.css;web" ^
  --add-data "src\web\game_ui.js;web" ^
  --add-data "src\web\game_ui.css;web" ^
  --add-data "src\web\manifest.webmanifest;web" ^
  --add-data "src\web\service-worker.js;web" ^
  --add-data "src\web\taskhub-icon-192.png;web" ^
  --add-data "src\web\taskhub-icon-512.png;web" ^
  --add-data "src\web\Vazirmatn-Regular.ttf;web" ^
  --add-data "src\web\Vazirmatn-Bold.ttf;web" ^
  --add-data "src\web\icon.ico;web" ^
  --hidden-import pyodbc ^
  --hidden-import flask ^
  --hidden-import openpyxl ^
  --hidden-import reportlab ^
  --hidden-import arabic_reshaper ^
  --hidden-import bidi ^
  --hidden-import jinja2 ^
  --hidden-import werkzeug ^
  --hidden-import waitress ^
  --hidden-import cryptography.fernet ^
  --hidden-import v802_features ^
  --hidden-import v802_domain ^
  --hidden-import r10_features ^
  --hidden-import team_scope ^
  --hidden-import rbac ^
  --hidden-import fa_font ^
  --hidden-import gamification ^
  --hidden-import gamification_domain ^
  --hidden-import webview ^
  --hidden-import webview.platforms.edgechromium ^
  --hidden-import pystray ^
  --hidden-import pystray._win32 ^
  --hidden-import PIL.Image ^
  --hidden-import PIL.ImageOps ^
  --collect-all cryptography ^
  src\taskhub.py
if errorlevel 1 goto :error

copy /y "config\taskhub_config.LAN.example.json" "dist\taskhub_config.LAN.example.json" >nul
copy /y "scripts\Run_TaskHub.cmd" "dist\Run_TaskHub.cmd" >nul
copy /y "docs\INSTALL_LAN_FA.md" "dist\INSTALL_LAN_FA.md" >nul

echo.
echo SUCCESS
echo Output folder: %CD%\dist
echo Main file:    TaskHub.exe
echo Client URL:   http://SERVER-IP:19234
echo.
pause
exit /b 0

:error
echo.
echo [ERROR] Build stopped. Read the error above.
pause
exit /b 1
