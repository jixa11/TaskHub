# اصلاح LAN R1

علت خطای شروع نشدن سرور این بود که فایل `taskhub_config.json` قدیمی کنار EXE هنوز مسیرهای Certificate را داشت. Waitress مستقیماً TLS را اجرا نمی‌کند و برنامه با خطای زیر متوقف می‌شد:

`Waitress does not terminate TLS`

در R1، حالت LAN به صورت پیش‌فرض HTTP-only است و تنظیمات قدیمی زیر را نادیده می‌گیرد:

- `TASKHUB_HOST=127.0.0.1`
- مسیرهای `TASKHUB_SSL_CERT_FILE` و `TASKHUB_SSL_KEY_FILE`
- `TASKHUB_REVERSE_PROXY=true`
- `TASKHUB_EXTERNAL_SCHEME=https`

برنامه همیشه روی `0.0.0.0:19234` با HTTP اجرا می‌شود و از شبکه با آدرس زیر در دسترس است:

`http://192.168.1.100:19234`

برای ساخت، `build.bat` را اجرا کنید. خروجی:

`dist\TaskHub_v8_0_3_LAN_R1.exe`
