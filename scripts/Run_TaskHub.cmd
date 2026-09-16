@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "taskhub_config.json" (
  if exist "taskhub_config.LAN.example.json" copy /y "taskhub_config.LAN.example.json" "taskhub_config.json" >nul
  echo.
  echo فایل taskhub_config.json ساخته شد.
  echo ابتدا نام کاربری و رمز SQL را در آن تنظیم کنید، سپس همین فایل را دوباره اجرا کنید.
  echo.
  start "" notepad.exe "taskhub_config.json"
  pause
  exit /b 1
)

if not exist "TaskHub.exe" (
  echo [ERROR] TaskHub.exe در این پوشه نیست.
  pause
  exit /b 1
)

start "" "TaskHub.exe"
