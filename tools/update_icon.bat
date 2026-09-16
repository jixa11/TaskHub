@echo off
cd /d "%~dp0.."
if "%~1"=="" (echo Drag a PNG onto this bat file & pause & exit /b)
python tools\update_icon.py "%~1"
