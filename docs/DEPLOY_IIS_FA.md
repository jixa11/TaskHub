# استقرار امن TaskHub 8.0.2 روی اینترنت

معماری انتخاب‌شده برای ویندوز سرور:

`Internet → HTTPS/443 روی IIS → ARR Reverse Proxy → Waitress روی 127.0.0.1:19234 → SQL Server داخلی`

پورت 19234 نباید روی مودم یا فایروال اینترنت منتشر شود. فقط 443 باز می‌شود.

## فایل اجرایی سرور

بعد از `build.bat` از فایل زیر استفاده کنید:

`dist\TaskHubServer_v8_0_2.exe`

این فایل بدون پنجره دسکتاپ و با Waitress اجرا می‌شود.

## کانفیگ

فایل `taskhub_config.iis.example.json` را با نام `taskhub_config.json` کنار EXE کپی و مقادیر دامنه و دیتابیس را اصلاح کنید. در حالت IIS نباید `TASKHUB_SSL_CERT_FILE` یا `TASKHUB_SSL_KEY_FILE` داخل کانفیگ باشد؛ TLS در IIS خاتمه پیدا می‌کند.

## IIS

1. IIS، URL Rewrite و Application Request Routing را نصب کنید.
2. در ARR گزینه `Enable Proxy` را فعال کنید و `Preserve host header` را روشن نگه دارید. تنظیم Proxy در سطح سرور IIS انجام می‌شود و عمداً داخل `web.config` قرار نگرفته تا با قفل‌بودن Section خطای 500.19 ایجاد نشود.
3. یک Site با دامنه واقعی بسازید و Certificate معتبر را روی Binding پورت 443 قرار دهید.
4. فایل `deploy\iis\web.config` را در ریشه Site قرار دهید.
5. Application Pool را روی `No Managed Code` بگذارید.
6. دامنه باید به IP عمومی سرور اشاره کند و NAT فقط پورت 443 را به IIS هدایت کند.

## اجرای خودکار

PowerShell را با Run as administrator اجرا کنید:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\deploy\register_server_task.ps1 -InstallDir "C:\TaskHub"
```

Task با حساب SYSTEM در Startup اجرا می‌شود و در صورت توقف هر یک دقیقه مجدداً راه‌اندازی می‌شود.

## کنترل نهایی

روی خود سرور:

```powershell
curl.exe http://127.0.0.1:19234/api/ping
```

از اینترنت:

```text
https://taskhub.example.com/api/ping
```

هر دو باید `{"ok":true}` برگردانند. سپس بررسی کنید هیچ Rule ورودی برای TCP/19234 در Windows Firewall وجود نداشته باشد.
