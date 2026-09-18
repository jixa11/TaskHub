# تسک هاب (TaskHub)

سامانه‌ی تحت شبکه برای مدیریت تیم، پروژه و تسک، با پیام‌رسان داخلی، گزارش‌های مالی و سیستم امتیازدهی. رابط کاربری فارسی و راست‌به‌چپ است و تاریخ‌ها شمسی‌اند.

*A Persian (RTL) team, project and task management system with a built-in messenger, financial reports and gamification. Python/Flask backend on SQL Server, runs as a Windows desktop app or a LAN server.*

## امکانات

- **تسک‌ها:** ثبت، واگذاری، شروع و پایان، تأیید و برگشت، ثبت زمان واقعی کار، قالب تسک، فیلترهای ذخیره‌شده و ورود و خروج Excel
- **تیم‌ها و گروه‌ها:** محدوده‌ی دسترسی تیمی، سرگروه و پروژه‌های هر گروه
- **مدیریت دسترسی:** نقش‌ها با مجوزهای ریز و قابل تنظیم که همه سمت سرور بررسی می‌شوند
- **حضور و غیاب:** برنامه‌ی هفتگی، تعطیلات رسمی، مرخصی و مأموریت
- **قرارداد و مالی:** قرارداد، الحاقیه، صورت‌وضعیت، برنامه‌ی مالی، گزارش درآمد و سهم تیم‌ها با خروجی PDF و Excel
- **پیام‌رسان:** گفتگوی فردی و گروهی با پیام‌های رمزگذاری‌شده و ارسال فایل
- **امتیاز و فروشگاه:** امتیاز و سکه، سطح، نشان، رتبه‌بندی و فروشگاه داخلی
- **مدیریت سیستم:** Audit log، مدیریت نشست‌ها، پشتیبان‌گیری و بازیابی، نسخه‌ی موبایل (PWA)

## نیازمندی‌ها

- Windows
- Python 3.11 یا جدیدتر (64 بیتی)
- SQL Server و ODBC Driver 17 for SQL Server

## اجرا از روی سورس

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy config\taskhub_config.LAN.example.json src\taskhub_config.json
```

مشخصات اتصال SQL Server را در `src\taskhub_config.json` وارد کنید و بعد برنامه را اجرا کنید:

```bat
.venv\Scripts\python src\taskhub.py            :: پنجره‌ی دسکتاپ
.venv\Scripts\python src\taskhub.py --server   :: فقط سرور، بدون پنجره
```

برنامه جدول‌ها را خودش می‌سازد. در اولین اجرا کاربر `admin` ساخته می‌شود و رمز آن در فایل `initial_admin_password.txt` کنار برنامه قرار می‌گیرد. آدرس پیش‌فرض `http://<IP سرور>:19234` است.

## ساخت فایل EXE

فایل `build.bat` را اجرا کنید. این فایل وابستگی‌ها را نصب می‌کند، تست‌ها را اجرا می‌کند و خروجی را در پوشه‌ی `dist` می‌سازد. راهنمای کامل نصب روی سرور در [docs/INSTALL_LAN_FA.md](docs/INSTALL_LAN_FA.md) است.

## تست‌ها

```bat
python run_tests.py
python scripts\run_lan_checks.py
```

## ساختار پوشه‌ها

| پوشه | محتوا |
|---|---|
| `src/` | کد سرور؛ نقطه‌ی شروع برنامه `src/taskhub.py` است |
| `src/web/` | رابط کاربری، آیکون‌ها و فونت Vazirmatn |
| `scripts/` | پشتیبان‌گیری، بازیابی، ریست دیتابیس و بررسی‌های پیش از انتشار |
| `config/` | نمونه‌ی فایل تنظیمات |
| `deploy/` | تنظیمات IIS و ثبت سرور به‌عنوان Scheduled Task |
| `sql/` | اسکریپت‌های فقط‌خواندنی برای بررسی دیتابیس بعد از ارتقا |
| `docs/` | راهنمای نصب، دسترسی‌ها، گزارش‌ها و پیام‌رسان؛ سوابق نسخه‌های قبلی در `docs/history/` |
| `tests/` | تست‌های خودکار |
| `tools/` | به‌روزرسانی آیکون برنامه |
| `branding/` | فایل اصلی آیکون به‌صورت SVG |

## مستندات

- [راهنمای نصب در شبکه‌ی داخلی](docs/INSTALL_LAN_FA.md)
- [استقرار پشت IIS](docs/DEPLOY_IIS_FA.md)
- [ماتریس دسترسی نقش‌ها](docs/ACCESS_MATRIX_FA.md)
- [فرمول‌های گزارش مالی](docs/REPORTS_FA.md)
- [راه‌اندازی پیام‌رسان](docs/MESSENGER_SETUP_FA.md)
- [تاریخچه‌ی تغییرات](CHANGELOG.md)

## سازنده

علی اسد (jixa)

فونت [Vazirmatn](https://github.com/rastikerdar/vazirmatn) تحت مجوز SIL OFL همراه برنامه منتشر می‌شود؛ متن مجوز در `src/web/Vazirmatn-OFL.txt` است.
