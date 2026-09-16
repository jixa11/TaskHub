# -*- coding: utf-8 -*-
"""Database-backed role permissions for TaskHub.

The permission catalog is versioned with the application while each role's
allow/deny choices are stored in SQL Server.  The browser only uses the same
permission list to hide menus and buttons; every mapped API is checked again
on the server.

The one intentional exception is ``access_control.manage``: it is reserved for
the built-in ``admin`` role and cannot be delegated through the UI or API.
"""
from __future__ import annotations

from collections import OrderedDict

ROLES = (
    ("manager", "مدیر"),
    ("planner", "پلنر"),
    ("finance", "کارشناس مالی"),
    ("reporter", "کارشناس اجرایی"),
    ("support", "پشتیبان"),
    ("lead", "سرگروه"),
    ("supervisor", "راهبر"),
    ("employer", "کارفرما"),
)

# group_key, group_label, [(permission_key, label)]
_LEGACY_PERMISSION_GROUPS = (
    ("menus", "نمایش منوها", (
        ("menu.dashboard", "داشبورد"), ("menu.cities", "شهرها"),
        ("menu.projects", "پروژه‌ها"), ("menu.task_categories", "دسته‌بندی تسک"),
        ("menu.tasks", "تسک‌ها"), ("menu.kanban", "کارتابل"),
        ("menu.schedule", "برنامه هفتگی"), ("menu.leave", "ماموریت و مرخصی"),
        ("menu.users", "مدیریت کاربران"), ("menu.contracts", "قراردادها"),
        ("menu.extensions", "الحاقیه‌ها"), ("menu.statements", "صورت‌وضعیت‌ها"),
        ("menu.financial_plan", "برنامه مالی"), ("menu.project_income", "درآمد پروژه‌ها"),
        ("menu.work_share", "سهم کارکرد"), ("menu.reports", "گزارش‌گیری"),
        ("menu.search", "جستجو"), ("menu.phonebook", "دفتر تلفن"),
        ("menu.settings", "تنظیمات"), ("menu.teams", "تیم‌ها"),
        ("menu.team_reports", "گزارش تیم‌ها"), ("menu.chat", "پیامرسان"),
        ("menu.team_plan", "برنامه مالی تیم"), ("menu.help", "راهنمای سامانه"),
        ("menu.club", "امتیاز و فروشگاه"), ("menu.club_admin", "مدیریت فروشگاه"),
    )),
    ("dashboard", "جزئیات داشبورد", (
        ("dashboard.personal_tasks", "تسک‌های فعال و معوق خود کاربر"),
        ("dashboard.personal_calendar", "تقویم، مرخصی و حضور خود کاربر"),
        ("dashboard.personal_schedule", "برنامه هفتگی خود کاربر"),
        ("dashboard.personal_rank", "رتبه شخصی کاربر در تیم"),
        ("dashboard.team_presence", "حاضرین و وضعیت فعالیت اعضای تیم"),
        ("dashboard.team_schedule", "برنامه امروز اعضای تیم"),
        ("dashboard.team_ranking", "رتبه‌بندی و بار کاری اعضای تیم"),
        ("dashboard.organization_summary", "آمار کلی شهر، پروژه و کارفرما"),
        ("dashboard.organization_analytics", "نمودارها و تحلیل‌های کل سازمان"),
        ("dashboard.financial", "هدف، پیشرفت و کارت‌های مالی داشبورد"),
    )),
    ("base", "اطلاعات پایه و پروژه", (
        ("cities.view", "مشاهده شهرهای مجاز"),
        ("cities.create", "دکمه ثبت شهر"),
        ("cities.edit", "دکمه ویرایش شهر"),
        ("cities.delete", "دکمه حذف شهر"),
        ("cities.manage", "مدیریت کامل شهرها (سازگاری)"),
        ("projects.view", "مشاهده پروژه‌های مجاز"),
        ("projects.view_all", "مجوز قدیمی مشاهده همه پروژه‌ها؛ محدوده تیم را دور نمی‌زند"),
        ("projects.create", "دکمه ثبت پروژه"),
        ("projects.edit", "دکمه ویرایش پروژه"),
        ("projects.delete", "دکمه حذف پروژه"),
        ("projects.manage", "مدیریت کامل پروژه‌ها (سازگاری)"),
        ("task_categories.view", "مشاهده دسته‌بندی تسک"),
        ("task_categories.create", "دکمه ثبت دسته‌بندی تسک"),
        ("task_categories.edit", "دکمه ویرایش دسته‌بندی تسک"),
        ("task_categories.delete", "دکمه حذف دسته‌بندی تسک"),
        ("task_categories.manage", "مدیریت کامل دسته‌بندی تسک (سازگاری)"),
        ("project_notes.view", "مشاهده اطلاعات حساس پروژه‌های تیم"),
        ("project_notes.manage", "ویرایش اطلاعات حساس پروژه‌های تیم"),
    )),
    ("tasks", "تسک و گردش کار", (
        ("tasks.view", "مشاهده تسک‌های مجاز"),
        ("tasks.view_all", "مشاهده همه تسک‌ها"),
        ("tasks.create", "ثبت تسک"), ("tasks.edit", "ویرایش کامل تسک"),
        ("tasks.create_for_group", "ثبت تسک برای خود و اعضای زیرگروه (سرگروه)"),
        ("tasks.edit_group", "ویرایش تسک‌های خود و اعضای زیرگروه (سرگروه)"),
        ("tasks.delete_group", "حذف تسک‌های تمام‌نشده خود و اعضای زیرگروه (سرگروه)"),
        ("tasks.approve_group", "تأیید پایان و برگشت تسک‌های خود و اعضای زیرگروه (سرگروه)"),
        ("tasks.work", "ثبت نحوه انجام و زمان روی تسک واگذارشده"),
        ("tasks.self_manage", "ثبت و ویرایش تسک درخواست‌کننده/کارفرما"),
        ("tasks.delete", "حذف تسک"), ("tasks.import", "ورود تسک از Excel"),
        ("tasks.export", "خروجی تسک"), ("tasks.templates", "مدیریت قالب تسک"),
        ("tasks.assign", "ارجاع و مدیریت همکاران تسک"),
        ("tasks.triage", "بررسی اولیه و تایید/رد درخواست جدید"),
        ("tasks.approve", "تأیید پایان و برگشت تسک"),
        ("tasks.evaluate", "ثبت امتیاز و ارزیابی تسک"),
        ("tasks.comments", "مشاهده و ثبت نظر روی تسک"),
        ("tasks.link_contract", "انتخاب قرارداد مرتبط در فرم تسک"),
    )),
    ("account_phonebook", "حساب شخصی و دفتر تلفن", (
        ("account.view", "بازکردن پنجره حساب من"),
        ("account.edit_identity", "ویرایش نام کاربری و نام نمایشی خود"),
        ("account.change_password", "تغییر رمز عبور خود"),
        ("phonebook.view", "مشاهده دفتر تلفن"),
        ("phonebook.view_all", "مشاهده دفتر تلفن کل شرکت"),
        ("phonebook.edit", "ویرایش شماره‌های دفتر تلفن"),
    )),
    ("users", "کاربران", (
        ("users.view", "مشاهده کاربران مجاز"), ("users.view_all", "مشاهده همه کاربران"),
        ("users.create", "ساخت کاربر"), ("users.edit", "ویرایش کاربر"),
        ("users.delete", "حذف کاربر"), ("users.reset_password", "بازنشانی رمز عبور"),
        ("users.toggle", "فعال/غیرفعال‌کردن کاربر"),
        ("users.manage_privileged", "مدیریت نقش‌های مدیر و پلنر (حساب مدیر سیستم مستثناست)"),
    )),
    ("work", "برنامه کاری و حضور", (
        ("schedule.view", "مشاهده برنامه هفتگی و تعطیلات"),
        ("schedule.manage", "ثبت و ویرایش برنامه هفتگی و تعطیلات"),
        ("leave.view", "مشاهده ماموریت و مرخصی مجاز"),
        ("leave.request", "ثبت، ویرایش و حذف درخواست مرخصی خود"),
        ("leave.manage", "مدیریت ماموریت و مرخصی همه کاربران"),
        ("attendance.view", "مشاهده حضور و کارکرد مجاز"),
        ("attendance.manage", "ثبت و اصلاح حضور و زمان کار همه کاربران"),
    )),
    ("finance", "قرارداد و امور مالی", (
        ("contracts.view", "مشاهده قراردادها"), ("contracts.manage", "ثبت و ویرایش قرارداد"),
        ("contracts.relink_project", "تغییر پروژه قرارداد دارای سابقه و انتقال وابستگی‌ها"),
        ("contracts.approve", "امتیاز و تأیید مدیریتی قرارداد"),
        ("contracts.archive", "بایگانی قرارداد"),
        ("extensions.view", "مشاهده الحاقیه‌ها"), ("extensions.manage", "ثبت و ویرایش الحاقیه"),
        ("extensions.edit_any_status", "ویرایش الحاقیه در همه وضعیت‌ها و بازگرداندن به پیش‌نویس"),
        ("extensions.approve", "تأیید یا رد الحاقیه"), ("extensions.archive", "بایگانی الحاقیه"),
        ("statements.view", "مشاهده صورت‌وضعیت‌ها"), ("statements.manage", "ثبت و ویرایش صورت‌وضعیت"),
        ("statements.edit_before_employer_decision", "ویرایش صورت‌وضعیت تا قبل از ثبت تأییدیه کارفرما"),
        ("statements.edit_any_status", "مجوز قدیمی ویرایش وضعیت‌های در گردش"),
        ("statements.internal_approve", "تأیید داخلی صورت‌وضعیت"),
        ("statements.employer_status", "ثبت ارسال و نتیجه کارفرما"),
        ("statements.archive", "بایگانی صورت‌وضعیت"),
        ("archives.view", "مشاهده رکوردهای بایگانی‌شده قرارداد، الحاقیه و صورت‌وضعیت"),
        ("archives.restore", "بازگرداندن رکورد بایگانی‌شده به فهرست فعال"),
        ("financial_plan.view", "مشاهده برنامه مالی"),
        ("financial_plan.manage", "ثبت و ویرایش برنامه مالی"),
        ("financial_plan.lock", "قفل و بازکردن دوره مالی"),
        ("contract_weights.manage", "تنظیم وزن نوع تسک قرارداد"),
    )),
    ("teams", "تیم و برنامه‌ریزی", (
        ("teams.view", "مشاهده تیم‌های مجاز"),
        ("teams.view_all", "مجوز قدیمی مشاهده همه تیم‌ها؛ محدوده تیم را دور نمی‌زند"),
        ("teams.create", "دکمه ساخت تیم"),
        ("teams.edit", "دکمه ویرایش مشخصات تیم"),
        ("teams.members_manage", "دکمه مدیریت اعضای تیم"),
        ("teams.project_types_manage", "دکمه مدیریت نوع پروژه‌های تیم"),
        ("teams.project_assign", "دکمه اتصال پروژه به تیم"),
        ("teams.manage", "مدیریت کامل تیم (سازگاری)"),
        ("teams.archive", "بایگانی تیم و جریان کاری"),
        ("team_financial.manage", "تنظیم هدف مالی تیم"),
    )),
    ("files_reports", "فایل و گزارش", (
        ("attachments.view", "مشاهده و دریافت فایل‌ها"),
        ("attachments.upload", "بارگذاری فایل"), ("attachments.edit", "ویرایش مشخصات فایل"),
        ("attachments.archive", "بایگانی فایل"),
        ("reports.view", "مشاهده گزارش‌ها و داشبورد تحلیلی"),
        ("reports.financial", "مشاهده مبالغ و گزارش‌های مالی"),
        ("reports.capacity", "مشاهده گزارش ظرفیت و کیفیت داده"),
        ("reports.export", "خروجی Excel و PDF"),
        # One key per report, so a role can be given exactly the reports it
        # needs instead of a whole family at once.
        ("reports.team_dashboard", "گزارش داشبورد تیم‌ها"),
        ("reports.contribution", "گزارش سهم زمان و خروجی افراد"),
        ("reports.shared_projects", "گزارش پروژه‌های مشترک"),
        ("reports.data_quality", "گزارش کیفیت داده"),
        ("reports.financial_attribution", "گزارش سهم مالی قراردادها"),
        ("reports.project_income", "گزارش درآمد پروژه‌ها"),
        ("reports.work_share", "گزارش سهم کارکرد"),
        # Dashboard analytics cards, individually switchable.
        ("dashboard.chart_status", "نمودار وضعیت تسک‌ها در داشبورد"),
        ("dashboard.chart_city", "نمودار شهر و پروژه در داشبورد"),
        ("dashboard.chart_staff", "نمودار عملکرد افراد در داشبورد"),
        ("dashboard.chart_trend", "نمودار روند زمانی در داشبورد"),
    )),
    ("chat", "پیامرسان", (
        ("chat.use", "استفاده از پیامرسان"),
        ("chat.file_upload", "دکمه ارسال عکس و فایل"),
        ("chat.file_download", "دکمه دریافت و بازکردن عکس و فایل"),
        ("chat.manage_groups", "ساخت گروه، اطلاعیه و مدیریت اعضا"),
        ("chat.delete", "حذف پیام مجاز"),
    )),
    # R13 points, coins and item shop. Earning follows the role (support from
    # tasks; planner, finance and reporter from the monthly stars); these keys
    # decide who may see, buy and run each part of it.
    ("gamification", "امتیاز، سکه و فروشگاه", (
        ("gamification.view_own", "دیدن امتیاز، سطح، سکه و تاریخچه خود"),
        ("gamification.team_board", "رتبه‌بندی تیم: سه نفر اول و جایگاه خود"),
        ("gamification.full_ranking", "جدول کامل رتبه‌ها"),
        ("gamification.kudos", "قدردانی «ممنونم» از همکار روی تسک"),
        ("shop.view", "دیدن فروشگاه، تاریخچه عمومی خرید و دفتر هدیه‌ها"),
        ("shop.buy", "خرید از فروشگاه با سکه"),
        ("shop.manage_items", "ثبت، ویرایش، حذف و فعال‌سازی آیتم‌ها"),
        ("shop.manage_festivals", "ساخت و مدیریت جشنواره تخفیف"),
        ("shop.gift", "هدیه دادن آیتم با دلیل مستند"),
        ("shop.deliver", "لیست تحویل آیتم‌ها"),
        ("shop.pay_rewards", "لیست پرداخت پاداش‌های مالی"),
        ("ratings.monthly", "ستاره ماهانه پلنر، کارشناس مالی و کارشناس اجرایی"),
        ("wallet.adjust", "اصلاح دستی موجودی سکه با دلیل"),
        ("economy.view", "داشبورد اقتصاد سکه"),
        ("game.settings", "تنظیمات امتیاز و سکه، و باز و بسته کردن فروشگاه"),
    )),
    ("system", "تنظیمات و مدیریت سیستم", (
        ("settings.view", "مشاهده تنظیمات سامانه"),
        ("system.autostart", "تغییر اجرای خودکار سرور"),
        ("system.backup", "پشتیبان‌گیری و دانلود نسخه پشتیبان"),
        ("system.audit", "مشاهده گزارش ممیزی"),
        ("system.sessions", "مدیریت نشست‌های فعال"),
        ("system.health", "مشاهده سلامت سیستم"),
        ("system.data_export", "خروجی کامل داده‌ها"),
        ("system.sql", "اجرای ابزار SQL داخلی"),
        ("access_control.manage", "مدیریت دسترسی نقش‌ها"),
    )),
)

# R16: the access screen is organised by area of the app. Each section holds
# the menu of that area together with its view and action permissions, so an
# administrator finds everything about one screen in one place. Keys and their
# stored grants are unchanged; only the grouping and some labels are new.
_R16_LABELS = {
    "menu.groups": "گروه‌ها",
    "groups.view": "مشاهده گروه‌های تیم‌های مجاز",
    "groups.create": "ساخت گروه",
    "groups.edit": "ویرایش نام، توضیح و سرگروه گروه",
    "groups.members_manage": "تعیین اعضای گروه",
    "groups.projects_manage": "تعیین پروژه‌های مسئول گروه",
    "groups.archive": "بایگانی گروه",
    "reports.groups": "گزارش گروه‌ها",
    "holidays.manage": "ثبت و حذف تعطیلات رسمی",
    "missions.manage": "ثبت و حذف ماموریت همکاران",
    "leave.approve": "تأیید یا رد درخواست مرخصی",
}
_RELABEL = {
    "schedule.manage": "ثبت و ویرایش برنامه هفتگی همکاران",
    "leave.manage": "ثبت، ویرایش و حذف مرخصی همکاران",
    "tasks.create_for_group": "ثبت تسک برای خود و اعضای گروه (سرگروه)",
    "tasks.edit_group": "ویرایش تسک‌های خود و اعضای گروه (سرگروه)",
    "tasks.delete_group": "حذف تسک‌های تمام‌نشده خود و اعضای گروه (سرگروه)",
    "tasks.approve_group": "تأیید پایان و برگشت تسک‌های خود و اعضای گروه (سرگروه)",
}
_SECTIONS = (
    ("dashboard", "داشبورد", (
        "menu.dashboard",
        "dashboard.personal_tasks", "dashboard.personal_calendar", "dashboard.personal_schedule",
        "dashboard.personal_rank", "dashboard.team_presence", "dashboard.team_schedule",
        "dashboard.team_ranking", "dashboard.organization_summary",
        "dashboard.organization_analytics", "dashboard.chart_status", "dashboard.chart_city",
        "dashboard.chart_staff", "dashboard.chart_trend", "dashboard.financial")),
    ("tasks", "تسک، کارتابل و جستجو", (
        "menu.tasks", "menu.kanban", "menu.search",
        "tasks.view", "tasks.view_all", "tasks.create", "tasks.edit", "tasks.delete",
        "tasks.self_manage", "tasks.comments", "tasks.link_contract",
        "tasks.templates", "tasks.import", "tasks.export")),
    ("workflow", "گردش کار تسک", (
        "tasks.work", "tasks.assign", "tasks.triage", "tasks.approve", "tasks.evaluate")),
    ("groups", "گروه‌ها و سرگروه", (
        "menu.groups", "groups.view", "groups.create", "groups.edit",
        "groups.members_manage", "groups.projects_manage", "groups.archive",
        "tasks.create_for_group", "tasks.edit_group", "tasks.delete_group",
        "tasks.approve_group")),
    ("base", "شهر، پروژه و دسته‌بندی", (
        "menu.cities", "cities.view", "cities.create", "cities.edit", "cities.delete",
        "cities.manage",
        "menu.projects", "projects.view", "projects.view_all", "projects.create",
        "projects.edit", "projects.delete", "projects.manage",
        "project_notes.view", "project_notes.manage",
        "menu.task_categories", "task_categories.view", "task_categories.create",
        "task_categories.edit", "task_categories.delete", "task_categories.manage")),
    ("teams", "تیم‌ها", (
        "menu.teams", "teams.view", "teams.view_all", "teams.create", "teams.edit",
        "teams.members_manage", "teams.project_types_manage", "teams.project_assign",
        "teams.manage", "teams.archive")),
    ("users", "کاربران", (
        "menu.users", "users.view", "users.view_all", "users.create", "users.edit",
        "users.delete", "users.reset_password", "users.toggle", "users.manage_privileged")),
    ("work", "برنامه کاری، مرخصی و حضور", (
        "menu.schedule", "schedule.view", "schedule.manage", "holidays.manage",
        "menu.leave", "leave.view", "leave.request", "leave.manage", "leave.approve",
        "missions.manage", "attendance.view", "attendance.manage")),
    ("reports", "گزارش‌ها", (
        "menu.reports", "reports.view", "reports.export",
        "menu.team_reports", "reports.team_dashboard", "reports.contribution",
        "reports.groups", "reports.capacity", "reports.data_quality",
        "reports.shared_projects", "menu.work_share", "reports.work_share")),
    ("finance", "قرارداد و امور مالی", (
        "menu.contracts", "contracts.view", "contracts.manage", "contracts.relink_project",
        "contracts.approve", "contracts.archive",
        "menu.extensions", "extensions.view", "extensions.manage",
        "extensions.edit_any_status", "extensions.approve", "extensions.archive",
        "menu.statements", "statements.view", "statements.manage",
        "statements.edit_before_employer_decision", "statements.edit_any_status",
        "statements.internal_approve", "statements.employer_status", "statements.archive",
        "archives.view", "archives.restore",
        "menu.financial_plan", "financial_plan.view", "financial_plan.manage",
        "financial_plan.lock", "menu.team_plan", "team_financial.manage",
        "contract_weights.manage", "menu.project_income", "reports.financial",
        "reports.project_income", "reports.financial_attribution")),
    ("files", "فایل‌ها و پیوست‌ها", (
        "attachments.view", "attachments.upload", "attachments.edit", "attachments.archive")),
    ("chat", "پیامرسان", (
        "menu.chat", "chat.use", "chat.file_upload", "chat.file_download",
        "chat.manage_groups", "chat.delete")),
    ("account", "حساب شخصی، دفتر تلفن و راهنما", (
        "account.view", "account.edit_identity", "account.change_password",
        "menu.phonebook", "phonebook.view", "phonebook.view_all", "phonebook.edit",
        "menu.help")),
    ("gamification", "امتیاز، سکه و فروشگاه", (
        "menu.club", "gamification.view_own", "gamification.team_board",
        "gamification.full_ranking", "gamification.kudos", "shop.view", "shop.buy",
        "menu.club_admin", "shop.manage_items", "shop.manage_festivals", "shop.gift",
        "shop.deliver", "shop.pay_rewards", "ratings.monthly", "wallet.adjust",
        "economy.view", "game.settings")),
    ("system", "تنظیمات و مدیریت سیستم", (
        "menu.settings", "settings.view", "system.audit", "system.health",
        "system.autostart", "system.backup", "system.sessions", "system.data_export",
        "system.sql", "access_control.manage")),
)
# One line under each section of the access screen.
GROUP_HINTS = {
    "dashboard": "کدام کارت‌ها و نمودارها روی داشبورد دیده شوند.",
    "tasks": "دیدن، ثبت، ویرایش و خروجی تسک‌ها. داده همیشه به تیم‌های خود کاربر محدود است.",
    "workflow": "انجام کار روی تسک، ارجاع، بررسی اولیه، تأیید پایان و ارزیابی ستاره‌ای.",
    "groups": "تعریف گروه‌ها و کارهایی که سرگروه روی تسک‌های خودش و اعضای گروهش انجام می‌دهد.",
    "base": "شهرها، پروژه‌ها، دسته‌بندی تسک و اطلاعات حساس پروژه.",
    "teams": "تیم‌ها، اعضا و اتصال پروژه به تیم.",
    "users": "ساخت و ویرایش حساب‌ها. نقش‌های سراسری را فقط مدیر سیستم می‌سازد.",
    "work": "برنامه هفتگی، تعطیلات، مرخصی، ماموریت و حضور.",
    "reports": "هر گزارش مجوز جدا دارد؛ گرفتن خروجی Excel و PDF هم مجوز جداست.",
    "finance": ("⚠ ثبت، ویرایش، تأیید و بایگانی اسناد مالی به تیم محدود نیست و در کل شرکت "
                "اعمال می‌شود؛ فقط به نقش‌های مورد اعتماد بدهید."),
    "files": "پیوست‌های تسک، قرارداد و اسناد مالی.",
    "chat": "پیامرسان و فایل‌های آن.",
    "account": "حساب کاربری خود، دفتر تلفن و راهنما.",
    "gamification": "امتیاز، سکه، فروشگاه و مدیریت آن.",
    "system": ("ابزارهای قفل‌شده (SQL، پشتیبان، خروجی کامل، نشست‌ها، اجرای خودکار و "
               "مدیریت دسترسی) فقط در اختیار مدیر سیستم‌اند."),
}


def _build_permission_groups():
    labels = {}
    for _, _, entries in _LEGACY_PERMISSION_GROUPS:
        labels.update(entries)
    labels.update(_R16_LABELS)
    labels.update(_RELABEL)
    placed = [key for _, _, keys in _SECTIONS for key in keys]
    missing = sorted(set(labels) - set(placed))
    doubled = sorted({key for key in placed if placed.count(key) > 1})
    unknown = sorted(set(placed) - set(labels))
    if missing or doubled or unknown:
        raise ValueError("permission sections are inconsistent: missing=%s doubled=%s unknown=%s"
                         % (missing, doubled, unknown))
    groups = []
    for key, label, keys in _SECTIONS:
        entries = []
        for perm in keys:
            text = labels[perm]
            if perm.startswith("menu."):
                text = "نمایش منوی «%s»" % text
            entries.append((perm, text))
        groups.append((key, label, tuple(entries)))
    return tuple(groups)


PERMISSION_GROUPS = _build_permission_groups()

CATALOG = OrderedDict()
for group_key, group_label, entries in PERMISSION_GROUPS:
    for key, label in entries:
        CATALOG[key] = {
            "key": key, "label": label, "group": group_key,
            "group_label": group_label,
        }
ALL_PERMISSION_KEYS = frozenset(CATALOG)
# Admin-only tools. They used to be hard-wired to the admin role in the route
# decorators while the access screen showed them as grantable; from R16 the
# screen shows them locked and the server refuses them to everyone else.
NON_DELEGABLE = frozenset(("access_control.manage", "system.sql", "system.data_export",
                           "system.backup", "system.sessions", "system.autostart"))

# The manager runs a team, not the company ledger. Financial records stay
# readable - scoped to the team the finance specialist linked them to by
# ContractProjectTeams / ContractStatementTeams - but creating, approving and
# archiving them belongs to finance. Everything operational (tasks, people,
# planning, reports for their own team) stays complete, including working on
# tasks personally and approving what their team submits.
_MANAGER_EXCLUDED = frozenset((
    "contracts.manage", "contracts.relink_project", "contracts.approve",
    "contracts.archive",
    "extensions.manage", "extensions.edit_any_status", "extensions.approve",
    "extensions.archive",
    "statements.manage", "statements.edit_before_employer_decision",
    "statements.edit_any_status", "statements.internal_approve",
    "statements.employer_status", "statements.archive",
    "archives.restore",
    "financial_plan.manage", "financial_plan.lock", "contract_weights.manage",
    # R13: the manager runs the shop and gives stars on tasks but holds no
    # wallet of their own; the company-wide levers stay with the administrator.
    "gamification.view_own", "shop.buy", "shop.manage_festivals", "shop.deliver",
    "shop.pay_rewards", "ratings.monthly", "wallet.adjust", "economy.view",
    "game.settings",
    # R15: the group-lead keys act on a sub-group; the manager already holds
    # the team-wide tasks.create/edit/delete/approve.
    "tasks.create_for_group", "tasks.edit_group", "tasks.delete_group", "tasks.approve_group",
))

#
# The planner mirrors the manager with two deliberate carve-outs:
#   * money - contracts, extensions, statements, financial goals, income
#     reports and the financial dashboard cards belong to the manager and the
#     finance specialist. Linking a contract to a task survives, because that
#     is a planning act and exposes no amounts.
#   * approving other people's leave and missions, which stays a manager
#     decision. The planner still sees the calendar, since planning work
#     without knowing who is away is impossible, and still files their own.
_PLANNER_EXCLUDED = frozenset((
    "menu.contracts", "menu.extensions", "menu.statements",
    "menu.financial_plan", "menu.project_income", "menu.team_plan",
    "contracts.view", "contracts.manage", "contracts.relink_project",
    "contracts.approve", "contracts.archive",
    "extensions.view", "extensions.manage", "extensions.edit_any_status",
    "extensions.approve", "extensions.archive",
    "statements.view", "statements.manage",
    "statements.edit_before_employer_decision", "statements.edit_any_status",
    "statements.internal_approve", "statements.employer_status",
    "statements.archive",
    "archives.view", "archives.restore",
    "financial_plan.view", "financial_plan.manage", "financial_plan.lock",
    "team_financial.manage", "contract_weights.manage",
    "reports.financial",
    "leave.manage",
    # R13: the planner earns monthly stars and buys from the shop like finance
    # and the reporter; running the shop, gifts and the economy is not theirs.
    "menu.club_admin", "gamification.full_ranking", "shop.manage_items",
    "shop.manage_festivals", "shop.gift", "shop.deliver", "shop.pay_rewards",
    "ratings.monthly", "wallet.adjust", "economy.view", "game.settings",
    # R15: like the manager, the planner works team-wide, not through a sub-group.
    "tasks.create_for_group", "tasks.edit_group", "tasks.delete_group", "tasks.approve_group",
    # R16: approving leave and sending people on missions stays with the manager.
    "leave.approve", "missions.manage",
))
# The dashboard goal card is deliberately not in that list: everybody sees how
# the company is tracking against its target. It is a single read-only card and
# is separate from reports.financial, which still opens the detailed money
# screens the planner does not get.

_DEFAULTS = {
    "manager": set(ALL_PERMISSION_KEYS) - set(NON_DELEGABLE) - set(_MANAGER_EXCLUDED),
    "planner": set(ALL_PERMISSION_KEYS) - set(NON_DELEGABLE) - set(_PLANNER_EXCLUDED),
    # The finance specialist owns every financial record end to end: create,
    # edit in any status, approve, archive and restore contracts, extensions
    # and statements, plus every financial report and dashboard card.
    "finance": {
        "menu.dashboard", "menu.projects", "menu.contracts", "menu.extensions",
        "menu.statements", "menu.financial_plan", "menu.project_income",
        "menu.reports", "menu.team_reports", "menu.team_plan", "menu.help",
        "cities.view", "projects.view",
        "projects.view_all", "tasks.view", "users.view", "contracts.view",
        "contracts.manage", "contracts.relink_project", "contracts.approve",
        "contracts.archive", "extensions.view",
        "extensions.manage", "extensions.edit_any_status", "extensions.approve",
        "extensions.archive", "statements.view", "statements.manage",
        "statements.edit_before_employer_decision", "statements.edit_any_status",
        "statements.internal_approve", "statements.employer_status",
        "statements.archive", "archives.view", "archives.restore",
        "financial_plan.view",
        "financial_plan.manage", "financial_plan.lock", "team_financial.manage",
        "contract_weights.manage", "teams.view",
        "reports.view", "reports.financial", "reports.capacity",
        "reports.export", "reports.team_dashboard", "reports.contribution",
        "reports.shared_projects", "reports.data_quality",
        "reports.financial_attribution", "reports.project_income",
        "reports.work_share",
        "dashboard.chart_status", "dashboard.chart_city",
        "dashboard.chart_staff", "dashboard.chart_trend",
        "attachments.view", "attachments.upload",
        "attachments.edit", "attachments.archive",
        "dashboard.organization_summary",
        "dashboard.organization_analytics", "dashboard.financial",
        "menu.phonebook", "phonebook.view", "phonebook.view_all",
        "account.view", "account.edit_identity", "account.change_password",
        # R13: monthly stars earn coins; the payment list is where cash rewards
        # bought in the shop are marked as paid with the next salary.
        "menu.club", "menu.club_admin", "gamification.view_own", "gamification.kudos",
        "shop.view", "shop.buy", "shop.pay_rewards",
    },
    # The reporter's job is company-wide reporting, so nothing is hidden and
    # nothing is team-scoped (see team_scope.GLOBAL_COMPANY_ROLES). What it
    # must not have is the ability to change operational records: no create,
    # edit, approve, archive or delete anywhere. The only writes are its own
    # account, the phonebook numbers granted in R11, and the messenger.
    "reporter": {
        "menu.dashboard", "menu.cities", "menu.projects", "menu.tasks",
        "menu.kanban", "menu.reports", "menu.search", "menu.phonebook",
        "menu.contracts", "menu.extensions", "menu.statements",
        "menu.project_income", "menu.work_share", "menu.chat", "menu.help",
        "menu.teams", "menu.team_reports", "menu.financial_plan",
        "menu.schedule", "menu.leave", "menu.task_categories",
        "cities.view", "projects.view", "projects.view_all", "tasks.view",
        "tasks.view_all", "tasks.export", "task_categories.view",
        "users.view", "users.view_all", "contracts.view",
        "extensions.view", "statements.view", "financial_plan.view",
        "archives.view", "teams.view",
        "schedule.view", "leave.view", "leave.request", "attendance.view",
        "reports.view", "reports.financial", "reports.capacity",
        "reports.export", "reports.team_dashboard", "reports.contribution",
        "reports.shared_projects", "reports.data_quality",
        "reports.financial_attribution", "reports.project_income",
        "reports.work_share",
        "dashboard.chart_status", "dashboard.chart_city",
        "dashboard.chart_staff", "dashboard.chart_trend",
        "attachments.view", "chat.use", "chat.file_upload",
        "chat.file_download", "chat.manage_groups",
        "tasks.comments", "dashboard.organization_summary",
        "dashboard.organization_analytics", "dashboard.financial",
        "dashboard.team_presence", "dashboard.team_schedule",
        "dashboard.team_ranking", "dashboard.personal_schedule",
        "dashboard.personal_rank", "dashboard.personal_tasks",
        "dashboard.personal_calendar",
        "phonebook.view", "phonebook.view_all", "phonebook.edit",
        "account.view", "account.edit_identity", "account.change_password",
        # R13: earns coins from the monthly stars and spends them in the shop.
        "menu.club", "gamification.view_own", "gamification.kudos",
        "shop.view", "shop.buy",
        # R16: reads the groups and their report like every other report.
        "menu.groups", "groups.view", "reports.groups",
    },
    "support": {
        "menu.dashboard", "menu.kanban", "menu.tasks", "menu.reports",
        "menu.phonebook", "menu.work_share", "menu.chat", "menu.help",
        "menu.schedule", "menu.leave", "projects.view", "tasks.view",
        "tasks.work", "tasks.export", "tasks.comments", "users.view",
        "schedule.view", "leave.view", "leave.request", "attendance.view",
        "attachments.view", "attachments.upload", "reports.view",
        "reports.work_share", "dashboard.chart_status", "chat.use",
        "chat.file_upload", "chat.file_download", "chat.manage_groups",
        "project_notes.view", "project_notes.manage", "dashboard.personal_tasks",
        "dashboard.personal_calendar", "dashboard.personal_schedule",
        "dashboard.personal_rank", "dashboard.financial",
        "phonebook.view", "phonebook.view_all", "phonebook.edit",
        "account.view", "account.edit_identity", "account.change_password",
        # R13: earns points and coins from approved tasks.
        "menu.club", "gamification.view_own", "gamification.team_board",
        "gamification.kudos", "shop.view", "shop.buy",
    },
    # The supervisor and the employer may use the messenger, but not start
    # groups or announcements. From R14 they reach only the other client
    # accounts of their own project and the planners of the teams running it
    # (team_scope.chat_pair_allowed, enforced by every v8 chat endpoint).
    "supervisor": {
        "menu.dashboard", "menu.kanban", "menu.reports", "menu.help",
        "menu.chat", "menu.phonebook",
        "projects.view", "tasks.view", "tasks.triage", "tasks.export",
        "reports.view", "tasks.comments", "dashboard.organization_summary",
        "dashboard.organization_analytics", "dashboard.financial",
        "reports.team_dashboard", "dashboard.chart_status",
        "dashboard.chart_city", "dashboard.chart_trend",
        "chat.use", "chat.file_upload", "chat.file_download",
        "phonebook.view",
        "account.view", "account.edit_identity", "account.change_password",
    },
    "employer": {
        "menu.dashboard", "menu.kanban", "menu.tasks", "menu.help",
        "menu.chat", "menu.phonebook",
        "projects.view", "tasks.view", "tasks.self_manage", "tasks.comments",
        # The company goal card belongs to the staff, not the client, so the
        # employer does not get dashboard.financial. It stays delegable from
        # the access screen if that ever changes.
        "dashboard.personal_tasks",
        "attachments.view", "attachments.upload",
        "chat.use", "chat.file_upload", "chat.file_download",
        "phonebook.view",
        "account.view", "account.edit_identity", "account.change_password",
    },
}
# R14/R15: the group lead (سرگروه) is a support worker who also raises, edits,
# deletes (while unfinished) and approves the tasks of themselves and of the
# people an administrator lists as their sub-group. A sub-group is not a team;
# team scope still bounds everything.
LEAD_GROUP_KEYS = ("tasks.create_for_group", "tasks.edit_group",
                   "tasks.delete_group", "tasks.approve_group")
# R16: a lead also sees the groups page and the report of their own group.
LEAD_REPORT_KEYS = ("menu.groups", "groups.view", "menu.team_reports", "reports.groups")
_DEFAULTS["lead"] = set(_DEFAULTS["support"]) | set(LEAD_GROUP_KEYS) | set(LEAD_REPORT_KEYS)

MENU_PERMISSION_BY_PAGE = {
    0: "menu.dashboard", 1: "menu.cities", 2: "menu.projects",
    5: "menu.task_categories", 6: "menu.tasks", 7: "menu.reports",
    8: "menu.search", 9: "menu.kanban", 10: "menu.users",
    11: "menu.help", 12: "menu.phonebook", 13: "menu.schedule",
    14: "menu.leave", 15: "menu.settings", 16: "menu.contracts",
    17: "menu.extensions", 18: "menu.statements", 19: "menu.financial_plan",
    20: "menu.project_income", 21: "menu.work_share", 22: "menu.teams",
    23: "menu.team_reports", 24: "menu.chat", 25: "menu.team_plan",
    26: "access_control.manage", 27: "menu.club", 28: "menu.club_admin",
    29: "menu.groups",
}

# Flask endpoint name -> permission. Endpoints whose operation depends on the
# request body are resolved in ``permission_for_request`` below.
ENDPOINT_PERMISSIONS = {
    # Users and settings
    "api_users_list": "users.view",
    "api_phonebook": "phonebook.view",
    "api_update_phone": "phonebook.edit",
    "api_account_update": "account.view",
    "api_user_reset_pw": "users.reset_password",
    "api_user_toggle": "users.toggle",
    "api_user_delete": "users.delete",
    "api_schedule": "schedule.view",
    "api_holidays": "schedule.view",
    "api_schedule_save": "schedule.manage",
    "api_holiday_save": "holidays.manage",
    "api_holiday_delete": "holidays.manage",
    "api_missions": "leave.view",
    "api_mission_save": "missions.manage",
    "api_mission_delete": "missions.manage",
    "api_attendance_close_stale": "attendance.manage",
    "api_attendance": "attendance.view",
    "api_attendance_save": "attendance.manage",
    "api_project_notes_get": "project_notes.view",
    "api_project_notes_save": "project_notes.manage",
    "api_time_report": "reports.view",
    "api_export_time_report": "reports.export",
    "api_leaves": "leave.view",
    "api_leave_review": "leave.approve",
    "api_ranking": "dashboard.team_ranking",
    "api_task_comments": "tasks.comments",
    "api_task_comment_add": "tasks.comments",
    "api_templates": "tasks.templates",
    "api_template_save": "tasks.templates",
    "api_template_delete": "tasks.templates",
    "api_audit_log": "system.audit",
    "api_active_sessions": "system.sessions",
    "api_session_revoke": "system.sessions",
    "api_system_health": "system.health",
    "api_data_export": "system.data_export",
    "api_role_permissions": "access_control.manage",
    "api_role_permissions_save": "access_control.manage",
    "api_query": "system.sql",
    "api_run": "system.sql",
    "api_analytics": "dashboard.organization_analytics",
    "api_dashboard_stats": "dashboard.organization_analytics",
    "api_overdue_tasks": "tasks.view",
    "api_presence": "dashboard.team_presence",
    "api_task_evaluation_get": "tasks.evaluate",
    "api_task_evaluation_save": "tasks.evaluate",
    "api_task_time_daily": "reports.view",
    "api_export": "tasks.export",
    "api_template": "tasks.import",
    "api_import": "tasks.import",

    # Contracts and finance
    "api_v7_contracts": "contracts.view",
    "api_v7_task_contract_options": "tasks.link_contract",
    "api_v7_contract_lookups": "contracts.view",
    "api_v7_contract_save": "contracts.manage",
    "api_v7_contract_rating": "contracts.approve",
    "api_v7_contract_archive": "contracts.archive",
    "api_v7_extensions": "extensions.view",
    "api_v7_extension_save": "extensions.manage",
    "api_v7_extension_submit": "extensions.manage",
    "api_v7_extension_decide": "extensions.approve",
    "api_v7_extension_archive": "extensions.archive",
    "api_v7_statements": "statements.view",
    "api_v7_statement_save": "statements.manage",
    "api_v8_statement_teams_save": "statements.manage",
    "api_v7_statement_submit": "statements.manage",
    "api_v7_statement_internal_decide": "statements.internal_approve",
    "api_v7_statement_mark_sent": "statements.employer_status",
    "api_v7_statement_employer_decide": "statements.employer_status",
    "api_v7_statement_revision": "statements.manage",
    "api_v7_statement_archive": "statements.archive",
    "api_v71_project_financial_report": "reports.financial",
    "api_v71_project_work_report": "reports.view",
    "api_v71_dashboard_reports": "dashboard.organization_analytics",
    "api_v7_financial_plan": "financial_plan.view",
    "api_v7_financial_dashboard": "dashboard.financial",
    "api_v7_financial_plan_save": "financial_plan.manage",
    "api_v7_financial_periods_save": "financial_plan.manage",
    "api_v7_financial_period_lock": "financial_plan.lock",
    "api_v7_planned_statement_save": "financial_plan.manage",
    "api_v7_planned_statement_archive": "financial_plan.manage",
    "api_v7_planned_link_tasks": "financial_plan.manage",
    "api_v7_recommendations": "financial_plan.view",
    "api_contract_task_weights": "contracts.view",
    "api_financial_attribution": "reports.financial_attribution",
    "api_financial_attribution_export": "reports.export",

    # Files, reports and backups
    "api_v7_attachments": "attachments.view",
    "api_v7_attachment_upload": "attachments.upload",
    "api_v7_attachment_download": "attachments.view",
    "api_v7_attachment_archive": "attachments.archive",
    "api_v7_attachment_update": "attachments.edit",
    "api_v7_storage_stats": "system.backup",
    "api_v7_backups": "system.backup",
    "api_v7_backup_run": "system.backup",
    "api_v7_backup_verify": "system.backup",
    "api_v7_backup_download": "system.backup",
    "api_v7_export": "reports.export",

    # Teams
    "api_v8_teams": "teams.view",
    "api_v8_team_archive": "teams.archive",
    "api_v8_team_members_save": "teams.members_manage",
    "api_v8_team_types_save": "teams.project_types_manage",
    "api_v8_project_team_save": "teams.project_assign",
    "api_v8_project_team_archive": "teams.archive",
    "api_v8_contract_teams": "contracts.view",
    "api_v8_contract_teams_save": "contracts.manage",
    "api_v8_reports": "reports.view",
    "api_v8_report_export": "reports.export",
    # R16 groups (گروه). Saving name/lead resolves to create or edit.
    "api_v8_groups": "groups.view",
    "api_v8_group_members_save": "groups.members_manage",
    "api_v8_group_projects_save": "groups.projects_manage",
    "api_v8_group_archive": "groups.archive",

    # Chat
    "api_v8_chat_config": "chat.use",
    "api_v8_chat_device": "chat.use",
    "api_v8_chat_device_revoke": "chat.use",
    "api_v8_chat_devices": "chat.use",
    "api_v8_chat_device_approval_challenge": "chat.use",
    "api_v8_chat_device_approve": "chat.use",
    "api_v8_chat_users": "chat.use",
    "api_v8_chat_conversations": "chat.use",
    "api_v8_chat_key_rotation_begin": "chat.use",
    "api_v8_chat_key_rotation_claim": "chat.use",
    "api_v8_chat_member_devices": "chat.use",
    "api_v8_chat_keys_save": "chat.use",
    "api_v8_chat_conversation_members_save": "chat.manage_groups",
    "api_v8_chat_conversation_update": "chat.manage_groups",
    "api_v8_chat_conversation_delete": "chat.use",
    "api_v7_contract_restore": "archives.restore",
    "api_v7_extension_restore": "archives.restore",
    "api_v7_statement_restore": "archives.restore",
    "api_v8_team_financial_detail": "financial_plan.view",
    "api_v8_chat_messages": "chat.use",
    "api_v8_chat_unread_summary": "chat.use",
    "api_v8_chat_message_send": "chat.use",
    "api_v8_chat_read": "chat.use",
    "api_v8_chat_file_upload": "chat.file_upload",
    "api_v8_chat_file_download": "chat.file_download",
    "api_v8_chat_message_delete": "chat.delete",

    # R13 points, coins and shop. api_game_summary, api_game_hall,
    # api_game_cosmetics and api_game_admin_wallet_users check inside the
    # handler, because each serves several roles with different permissions.
    "api_game_history": "gamification.view_own",
    "api_game_board": "gamification.team_board",
    "api_game_kudos_give": "gamification.kudos",
    "api_game_shop_items": "shop.view",
    "api_game_shop_item_image": "shop.view",
    "api_game_shop_feed": "shop.view",
    "api_game_shop_wishlist_toggle": "shop.view",
    "api_game_shop_equip": "shop.view",
    "api_game_shop_buy": "shop.buy",
    "api_game_shop_my_orders": "shop.buy",
    "api_game_shop_order_reschedule": "shop.buy",
    "api_game_shop_order_cancel": "shop.buy",
    "api_game_admin_items": "shop.manage_items",
    "api_game_admin_item_save": "shop.manage_items",
    "api_game_admin_item_delete": "shop.manage_items",
    "api_game_admin_item_toggle": "shop.manage_items",
    "api_game_admin_festivals": "shop.manage_festivals",
    "api_game_admin_festival_save": "shop.manage_festivals",
    "api_game_admin_festival_delete": "shop.manage_festivals",
    "api_game_admin_gift": "shop.gift",
    "api_game_admin_deliveries": "shop.deliver",
    "api_game_admin_deliver_mark": "shop.deliver",
    "api_game_admin_payments": "shop.pay_rewards",
    "api_game_admin_payment_mark": "shop.pay_rewards",
    "api_game_admin_monthly": "ratings.monthly",
    "api_game_admin_monthly_save": "ratings.monthly",
    "api_game_admin_economy": "economy.view",
    "api_game_admin_wallet_adjust": "wallet.adjust",
    "api_game_admin_settings": "game.settings",
    "api_game_admin_settings_save": "game.settings",
}


def default_permissions(role: str):
    if role == "admin":
        return set(ALL_PERMISSION_KEYS)
    return set(_DEFAULTS.get(role, ()))


def user_has_permission(user, permission_key: str) -> bool:
    if not user or permission_key not in ALL_PERMISSION_KEYS:
        return False
    if user.get("role") == "admin":
        return True
    if permission_key in NON_DELEGABLE:
        return False
    perms = user.get("permissions")
    if perms is None:
        perms = default_permissions(user.get("role"))
    return permission_key in set(perms)


def init_rbac_tables(conn):
    """Create/extend the role matrix without overwriting administrator choices."""
    cur = conn.cursor()
    cur.execute("""IF OBJECT_ID('RolePermissions','U') IS NULL CREATE TABLE RolePermissions(
        role NVARCHAR(20) NOT NULL, permission_key NVARCHAR(100) NOT NULL,
        is_allowed BIT NOT NULL, updated_by INT NULL,
        updated_at DATETIME NOT NULL DEFAULT GETDATE(),
        CONSTRAINT PK_RolePermissions PRIMARY KEY(role,permission_key))""")
    cur.execute("""IF OBJECT_ID('RbacMigrations','U') IS NULL CREATE TABLE RbacMigrations(
        migration_key NVARCHAR(120) NOT NULL PRIMARY KEY,
        applied_at DATETIME NOT NULL DEFAULT GETDATE())""")
    for role, _ in ROLES:
        defaults = default_permissions(role)
        for key in ALL_PERMISSION_KEYS:
            allowed = 1 if key in defaults else 0
            cur.execute("""IF NOT EXISTS(SELECT 1 FROM RolePermissions WHERE role=? AND permission_key=?)
                INSERT INTO RolePermissions(role,permission_key,is_allowed) VALUES(?,?,?)""",
                        role, key, role, key, allowed)

    # R4 intentionally starts manager and planner with complete operational
    # parity with admin. This migration runs only once so later administrator
    # choices in the access-control screen are never overwritten on restart.
    parity_migration = 'r4_manager_planner_admin_parity_v1'
    cur.execute("SELECT 1 FROM RbacMigrations WHERE migration_key=?", parity_migration)
    if not cur.fetchone():
        for role in ('manager', 'planner'):
            for key in ALL_PERMISSION_KEYS:
                allowed = 0 if key in NON_DELEGABLE else 1
                cur.execute("""UPDATE RolePermissions SET is_allowed=?,updated_by=NULL,
                    updated_at=GETDATE() WHERE role=? AND permission_key=?""",
                            allowed, role, key)
        cur.execute("INSERT INTO RbacMigrations(migration_key) VALUES(?)", parity_migration)

    # R10 splits broad management permissions into button-level permissions.
    # Copy existing grants once so upgrades preserve the administrator's intent.
    granular_migration = 'r10_granular_permissions_v1'
    cur.execute("SELECT 1 FROM RbacMigrations WHERE migration_key=?", granular_migration)
    if not cur.fetchone():
        copies = {
            'cities.manage': ('cities.create','cities.edit','cities.delete'),
            'projects.manage': ('projects.create','projects.edit','projects.delete'),
            'task_categories.manage': ('task_categories.create','task_categories.edit','task_categories.delete'),
            'teams.manage': ('teams.create','teams.edit','teams.members_manage',
                             'teams.project_types_manage','teams.project_assign'),
            'chat.use': ('chat.file_upload','chat.file_download'),
        }
        for role, _ in ROLES:
            for source, targets in copies.items():
                cur.execute("SELECT is_allowed FROM RolePermissions WHERE role=? AND permission_key=?", role, source)
                row = cur.fetchone()
                if row and bool(row[0]):
                    for target in targets:
                        cur.execute("""UPDATE RolePermissions SET is_allowed=1,updated_by=NULL,
                            updated_at=GETDATE() WHERE role=? AND permission_key=?""",
                                    role, target)
        # Requested R10 default: support can view and edit sensitive data for
        # projects linked to the support user's active team.
        for key in ('project_notes.view','project_notes.manage'):
            cur.execute("""UPDATE RolePermissions SET is_allowed=1,updated_by=NULL,
                updated_at=GETDATE() WHERE role=N'support' AND permission_key=?""", key)
        cur.execute("INSERT INTO RbacMigrations(migration_key) VALUES(?)", granular_migration)

    # R11 restores the self-service account popup, separates the phonebook
    # from the team-scoped user-management list, and adds the task-contract
    # selector as an independently delegable operation. This runs once so
    # later administrator choices are never reset during application startup.
    r11_migration = 'r11_account_phonebook_contract_permissions_v1'
    cur.execute("SELECT 1 FROM RbacMigrations WHERE migration_key=?", r11_migration)
    if not cur.fetchone():
        for role, _ in ROLES:
            for key in ('account.view','account.edit_identity','account.change_password'):
                cur.execute("""UPDATE RolePermissions SET is_allowed=1,updated_by=NULL,
                    updated_at=GETDATE() WHERE role=? AND permission_key=?""", role, key)
        for role in ('finance','reporter','support'):
            for key in ('phonebook.view','phonebook.view_all'):
                cur.execute("""UPDATE RolePermissions SET is_allowed=1,updated_by=NULL,
                    updated_at=GETDATE() WHERE role=? AND permission_key=?""", role, key)
        for role in ('reporter','support'):
            cur.execute("""UPDATE RolePermissions SET is_allowed=1,updated_by=NULL,
                updated_at=GETDATE() WHERE role=? AND permission_key=N'phonebook.edit'""", role)
        cur.execute("INSERT INTO RbacMigrations(migration_key) VALUES(?)", r11_migration)

    # R12 gives the finance specialist complete ownership of the financial
    # records instead of a read-heavy subset: approval, archiving, restoring
    # and every financial report. Runs once, so an administrator who later
    # removes one of these keeps their decision across restarts.
    r12_finance = 'r12_finance_full_financial_access_v1'
    cur.execute("SELECT 1 FROM RbacMigrations WHERE migration_key=?", r12_finance)
    if not cur.fetchone():
        for key in sorted(_DEFAULTS['finance']):
            cur.execute("""UPDATE RolePermissions SET is_allowed=1,updated_by=NULL,
                updated_at=GETDATE() WHERE role=N'finance' AND permission_key=?""", key)
        # Archive browsing is read-only, so every role that may already read a
        # record type is allowed to look at its archive too. Restoring stays
        # with the roles that were trusted to archive in the first place.
        for role in ('manager', 'planner', 'reporter'):
            cur.execute("""UPDATE RolePermissions SET is_allowed=1,updated_by=NULL,
                updated_at=GETDATE() WHERE role=? AND permission_key=N'archives.view'""", role)
        for role in ('manager', 'planner'):
            cur.execute("""UPDATE RolePermissions SET is_allowed=1,updated_by=NULL,
                updated_at=GETDATE() WHERE role=? AND permission_key=N'archives.restore'""", role)
        cur.execute("INSERT INTO RbacMigrations(migration_key) VALUES(?)", r12_finance)

    # R12 also narrows the planner, which until now shared the manager's full
    # parity. Money and leave approval move out; everything else the planner
    # needs is granted explicitly so the role is complete rather than partial.
    r12_planner = 'r12_planner_scope_v1'
    cur.execute("SELECT 1 FROM RbacMigrations WHERE migration_key=?", r12_planner)
    if not cur.fetchone():
        for key in sorted(_DEFAULTS['planner']):
            cur.execute("""UPDATE RolePermissions SET is_allowed=1,updated_by=NULL,
                updated_at=GETDATE() WHERE role=N'planner' AND permission_key=?""", key)
        for key in sorted(_PLANNER_EXCLUDED):
            cur.execute("""UPDATE RolePermissions SET is_allowed=0,updated_by=NULL,
                updated_at=GETDATE() WHERE role=N'planner' AND permission_key=?""", key)
        cur.execute("INSERT INTO RbacMigrations(migration_key) VALUES(?)", r12_planner)

    # R12 gives the manager a team, not the ledger: financial records stay
    # readable within their own team but are written by finance. The reporter
    # gains the remaining read-only surfaces it needs to report on the whole
    # company. Both run once so later administrator choices are preserved.
    r12_roles = 'r12_manager_team_finance_reporter_readonly_v1'
    cur.execute("SELECT 1 FROM RbacMigrations WHERE migration_key=?", r12_roles)
    if not cur.fetchone():
        for key in sorted(_MANAGER_EXCLUDED):
            cur.execute("""UPDATE RolePermissions SET is_allowed=0,updated_by=NULL,
                updated_at=GETDATE() WHERE role=N'manager' AND permission_key=?""", key)
        for key in sorted(_DEFAULTS['manager']):
            cur.execute("""UPDATE RolePermissions SET is_allowed=1,updated_by=NULL,
                updated_at=GETDATE() WHERE role=N'manager' AND permission_key=?""", key)
        for key in sorted(_DEFAULTS['reporter']):
            cur.execute("""UPDATE RolePermissions SET is_allowed=1,updated_by=NULL,
                updated_at=GETDATE() WHERE role=N'reporter' AND permission_key=?""", key)
        cur.execute("INSERT INTO RbacMigrations(migration_key) VALUES(?)", r12_roles)

    # The company goal card is one read-only tile and everybody is meant to see
    # how the company is tracking. It is separate from reports.financial, which
    # still gates the detailed money screens.
    r12_goal_card = 'r12_dashboard_goal_card_for_everyone_v1'
    cur.execute("SELECT 1 FROM RbacMigrations WHERE migration_key=?", r12_goal_card)
    if not cur.fetchone():
        # Everyone on staff; the employer is a client and does not see how the
        # company is tracking against its own target.
        for role, _ in ROLES:
            allowed = 0 if role == 'employer' else 1
            cur.execute("""UPDATE RolePermissions SET is_allowed=?,updated_by=NULL,
                updated_at=GETDATE() WHERE role=? AND permission_key=N'dashboard.financial'""",
                        allowed, role)
        cur.execute("INSERT INTO RbacMigrations(migration_key) VALUES(?)", r12_goal_card)

    # The supervisor and the employer join the messenger and the phonebook.
    # Group and announcement creation stays out of their set on purpose, and
    # the contact list limits them to real working relationships.
    r12_contact_roles = 'r12_supervisor_employer_messenger_v1'
    cur.execute("SELECT 1 FROM RbacMigrations WHERE migration_key=?", r12_contact_roles)
    if not cur.fetchone():
        for role in ('supervisor', 'employer'):
            for key in ('menu.chat', 'chat.use', 'chat.file_upload',
                        'chat.file_download', 'menu.phonebook', 'phonebook.view'):
                cur.execute("""UPDATE RolePermissions SET is_allowed=1,updated_by=NULL,
                    updated_at=GETDATE() WHERE role=? AND permission_key=?""", role, key)
            cur.execute("""UPDATE RolePermissions SET is_allowed=0,updated_by=NULL,
                updated_at=GETDATE() WHERE role=? AND permission_key=N'chat.manage_groups'""", role)
        cur.execute("INSERT INTO RbacMigrations(migration_key) VALUES(?)", r12_contact_roles)

    # R12 split the coarse report keys so each report and each dashboard chart
    # can be switched on its own. Roles that held the old umbrella key inherit
    # the finer ones, otherwise the upgrade would silently take reports away.
    r12_fine_reports = 'r12_per_report_permissions_v1'
    cur.execute("SELECT 1 FROM RbacMigrations WHERE migration_key=?", r12_fine_reports)
    if not cur.fetchone():
        inherit = {
            'reports.team_dashboard': 'reports.view',
            'reports.contribution': 'reports.view',
            'reports.shared_projects': 'reports.financial',
            'reports.data_quality': 'reports.capacity',
            'reports.financial_attribution': 'reports.financial',
            'reports.project_income': 'reports.financial',
            'reports.work_share': 'reports.view',
            'dashboard.chart_status': 'dashboard.organization_analytics',
            'dashboard.chart_city': 'dashboard.organization_analytics',
            'dashboard.chart_staff': 'dashboard.organization_analytics',
            'dashboard.chart_trend': 'dashboard.organization_analytics',
        }
        for new_key, source_key in inherit.items():
            cur.execute("""UPDATE target SET is_allowed=1,updated_by=NULL,updated_at=GETDATE()
                FROM RolePermissions target
                JOIN RolePermissions source ON source.role=target.role
                  AND source.permission_key=? AND source.is_allowed=1
                WHERE target.permission_key=?""", source_key, new_key)
        cur.execute("INSERT INTO RbacMigrations(migration_key) VALUES(?)", r12_fine_reports)

    # R16 splits holidays out of the weekly schedule, and missions and leave
    # approval out of leave management. Each role starts the new key exactly
    # where it had the old one, so the upgrade neither adds nor takes away.
    r16_split = 'r16_holiday_mission_leave_split_v1'
    cur.execute("SELECT 1 FROM RbacMigrations WHERE migration_key=?", r16_split)
    if not cur.fetchone():
        for new_key, source_key in (("holidays.manage", "schedule.manage"),
                                    ("missions.manage", "leave.manage"),
                                    ("leave.approve", "leave.manage")):
            cur.execute("""UPDATE target SET is_allowed=source.is_allowed,updated_by=NULL,
                updated_at=GETDATE() FROM RolePermissions target
                JOIN RolePermissions source ON source.role=target.role AND source.permission_key=?
                WHERE target.permission_key=?""", source_key, new_key)
        cur.execute("INSERT INTO RbacMigrations(migration_key) VALUES(?)", r16_split)

    # Keep obsolete catalog rows for audit history, but they are ignored by
    # ``permissions_for_role``. The admin-only tools stay non-delegable, so
    # no stored row can show them as granted to another role.
    for key in sorted(NON_DELEGABLE):
        cur.execute("""UPDATE RolePermissions SET is_allowed=0,updated_at=GETDATE()
            WHERE role<>N'admin' AND permission_key=?""", key)
    conn.commit()


def permissions_for_role(cur, role: str):
    if role == "admin":
        return sorted(ALL_PERMISSION_KEYS)
    cur.execute("SELECT permission_key,is_allowed FROM RolePermissions WHERE role=?", role)
    rows = cur.fetchall()
    if not rows:
        return sorted(default_permissions(role))
    allowed = {
        str(row[0]) for row in rows
        if bool(row[1]) and str(row[0]) in ALL_PERMISSION_KEYS
        and str(row[0]) not in NON_DELEGABLE
    }
    return sorted(allowed)


def _first_allowed(user, *permission_keys):
    for key in permission_keys:
        if user_has_permission(user, key):
            return key
    return permission_keys[0] if permission_keys else None


def permission_for_request(endpoint: str, data=None, user=None):
    """Resolve the single permission that guards the current API request."""
    data = data or {}
    if endpoint == "api_user_save":
        return "users.edit" if data.get("id") else "users.create"
    if endpoint == "api_v7_master_save":
        suffix = "edit" if data.get("id") else "create"
        return {
            "city": "cities." + suffix,
            "project": "projects." + suffix,
            "category": "task_categories." + suffix,
        }.get(data.get("kind"))
    if endpoint == "api_v7_master_delete":
        return {
            "city": "cities.delete", "project": "projects.delete",
            "category": "task_categories.delete",
        }.get(data.get("kind"))
    if endpoint == "api_v8_team_save":
        return "teams.edit" if data.get("id") else "teams.create"
    if endpoint == "api_v8_group_save":
        return "groups.edit" if data.get("id") else "groups.create"
    if endpoint == "api_v7_task_save":
        if data.get("id"):
            return _first_allowed(user, "tasks.edit", "tasks.edit_group", "tasks.self_manage", "tasks.work")
        return _first_allowed(user, "tasks.create", "tasks.self_manage", "tasks.create_for_group")
    if endpoint == "api_v7_task_delete":
        return _first_allowed(user, "tasks.delete", "tasks.self_manage", "tasks.delete_group")
    if endpoint == "api_task_transition":
        action = data.get("action")
        if action in ("start", "forward", "back_admin", "pause"):
            return "tasks.work"
        if action == "assign":
            return "tasks.assign"
        if action in ("add_helper", "remove_helper", "set_work_time"):
            return _first_allowed(user, "tasks.assign", "tasks.work")
        if action in ("triage_approve", "triage_reject"):
            return "tasks.triage"
        if action in ("approve", "send_back"):
            return _first_allowed(user, "tasks.approve", "tasks.approve_group")
        return "tasks.edit"
    if endpoint == "api_autostart":
        return "system.autostart" if "set" in data and data.get("set") is not None else "settings.view"
    if endpoint in ("api_leave_save", "api_leave_update", "api_leave_delete"):
        return _first_allowed(user, "leave.manage", "leave.request")
    if endpoint == "api_v8_team_financial_plan":
        return "team_financial.manage" if data.get("action") == "save" else "financial_plan.view"
    if endpoint == "api_contract_task_weights":
        return "contract_weights.manage" if data.get("action") == "save" else "contracts.view"
    if endpoint == "api_ranking":
        return "dashboard.personal_rank" if data.get("scope") == "self" else "dashboard.team_ranking"
    if endpoint == "api_v8_chat_conversation_create":
        return "chat.manage_groups" if data.get("kind") in ("group", "announcement") else "chat.use"
    return ENDPOINT_PERMISSIONS.get(endpoint)


def catalog_payload():
    groups = []
    for group_key, group_label, entries in PERMISSION_GROUPS:
        groups.append({
            "key": group_key,
            "label": group_label,
            "hint": GROUP_HINTS.get(group_key, ""),
            "permissions": [{"key": key, "label": label} for key, label in entries],
        })
    return groups
