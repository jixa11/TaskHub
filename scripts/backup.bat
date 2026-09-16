@echo off
REM ─────────────────────────────────────────────────────────────
REM  پشتیبان‌گیری روزانه‌ی دیتابیس تسک هاب
REM  این فایل را در Windows Task Scheduler به‌صورت روزانه تنظیم کنید
REM  (مثلاً هر شب ساعت ۲ بامداد). خودش تشخیص می‌دهد که بکاپ کامل
REM  بگیرد یا دیفرنشیال.
REM ─────────────────────────────────────────────────────────────
cd /d "%~dp0"
if exist "TaskHubBackup_v8.exe" (
  "TaskHubBackup_v8.exe" %*
) else if exist "dist\TaskHubBackup_v8.exe" (
  "dist\TaskHubBackup_v8.exe" %*
) else (
  python backup.py %*
)
if %errorlevel% neq 0 (
  echo خطا در پشتیبان‌گیری - به backups\backup.log مراجعه کنید
  exit /b 1
)
echo پشتیبان‌گیری با موفقیت انجام شد
exit /b 0
