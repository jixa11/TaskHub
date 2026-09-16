# -*- coding: utf-8 -*-
"""Pure rules of the R13 points, coins and item-shop economy.

Nothing in this file touches the database, Flask or the wall clock. The route
module reads rows, hands plain values to these functions and writes back what
they return, so every rule a colleague might question - why a task earned 32
points, why a coin expired, what a festival price is - can be unit-tested with
ordinary numbers.
"""
from __future__ import annotations

import datetime as _dt
import statistics
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# ── Who takes part ──────────────────────────────────────────────────────────
# Managers and administrators run the system and hold no wallet. The client
# roles (employer, supervisor) never see any of it.
WALLET_ROLES = ("support", "lead", "planner", "finance", "reporter")
# R14: the group lead does support work and earns from tasks the same way.
TASK_EARNING_ROLES = ("support", "lead")
MONTHLY_STAR_ROLES = ("planner", "finance", "reporter")
CONTROLLER_ROLES = ("admin", "manager")

LEVEL_TITLES = ("تازه‌کار", "کاردان", "ماهر", "خبره", "استاد")
DEFAULT_LEVEL_THRESHOLDS = (0, 300, 1000, 3000, 8000)
SEASON_NAMES = ("بهار", "تابستان", "پاییز", "زمستان")
MONTH_NAMES = ("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
               "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند")

BASE_POINTS = Decimal(10)
STAR_FACTORS = {1: Decimal("0.8"), 2: Decimal("0.9"), 3: Decimal("1"),
                4: Decimal("1.1"), 5: Decimal("1.2")}

ITEM_TYPES = (
    ("leave", "مرخصی تشویقی"),
    ("remote", "دورکاری یا ورود شناور"),
    ("money", "پاداش مالی"),
    ("goods", "کالا، کارت هدیه، کتاب یا دوره"),
    ("cosmetic", "تزئینی"),
    ("team_pot", "صندوق تیم"),
    ("other", "سایر"),
)
ITEM_TYPE_KEYS = tuple(key for key, _ in ITEM_TYPES)
DATED_TYPES = ("leave", "remote")
COSMETIC_SLOTS = {
    "frame": ("قاب آواتار", ("gold", "silver", "emerald", "ruby", "sapphire", "violet")),
    "chat": ("رنگ حباب چت", ("teal", "rose", "amber", "violet", "emerald")),
    "title": ("لقب زیر نام", None),
}

BADGES = (
    {"key": "flawless", "title": "بی‌نقص", "desc": "۱۰ تسک پشت‌سرهم بدون برگشت",
     "roles": ("support", "lead"), "period": "season"},
    {"key": "ontime", "title": "سروقت", "desc": "۲۰ تسک تحویل‌شده تا موعد",
     "roles": ("support", "lead"), "period": "season"},
    {"key": "helper", "title": "همیار", "desc": "کمک در ۵ تسک مشترک",
     "roles": ("support", "lead"), "period": "season"},
    {"key": "complete", "title": "پرونده کامل",
     "desc": "۲۰ تسک با اطلاعات کامل: دسته، تیم و شرح انجام کار",
     "roles": ("support", "lead"), "period": "season"},
    {"key": "untangler", "title": "گره‌گشا",
     "desc": "بستن تسکی که بیش از ۳۰ روز باز مانده بود",
     "roles": ("support", "lead"), "period": "season"},
    {"key": "steady", "title": "منظم",
     "desc": "۴ هفته پیاپی بدون تسک معوق؛ مرخصی، مأموریت و تعطیلی زنجیره را قطع نمی‌کنند",
     "roles": ("support", "lead"), "period": "season"},
    {"key": "no_queue", "title": "بدون صف",
     "desc": "یک ماه بدون تسکی که بیش از یک روز کاری در صف تأیید مانده باشد",
     "roles": ("planner",), "period": "month"},
    {"key": "precise", "title": "برنامه‌ریز دقیق", "desc": "۹۰٪ تسک‌های تیم در ماه سر موعد",
     "roles": ("planner",), "period": "month"},
    {"key": "on_schedule", "title": "سر موعد",
     "desc": "همه صورت‌وضعیت‌های برنامه ماه تا تاریخ برنامه ثبت شده‌اند",
     "roles": ("finance",), "period": "month"},
    {"key": "clean_books", "title": "دفتر تمیز", "desc": "صفر ایراد داده مالی در پایان ماه",
     "roles": ("finance",), "period": "month"},
    {"key": "bright3", "title": "سه ماه درخشان", "desc": "سه ماه پیاپی ۴ ستاره یا بیشتر",
     "roles": ("planner", "finance", "reporter"), "period": "season"},
)
BADGE_BY_KEY = {badge["key"]: badge for badge in BADGES}

QUESTS = (
    ("zero_overdue", "صفر تسک معوق در پایان ماه"),
    ("on_time", "۹۰٪ تحویل سروقت"),
    ("finance_goal", "رسیدن به هدف مالی ماه تیم"),
)
QUEST_TITLES = dict(QUESTS)

_DIGITS_IN = "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩"
_DIGITS_OUT = "01234567890123456789"
_TO_ASCII = str.maketrans(_DIGITS_IN, _DIGITS_OUT)
_TO_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


# ── Small conversions ───────────────────────────────────────────────────────
def to_int(value, default=None):
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(Decimal(str(value).translate(_TO_ASCII).replace(",", "").strip()))
    except (InvalidOperation, ValueError, TypeError):
        return default


def to_dec(value, default=None):
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value).translate(_TO_ASCII).replace(",", "").strip())
    except (InvalidOperation, ValueError, TypeError):
        return default


def fa_digits(value):
    return str(value).translate(_TO_FA)


def round_half_up(value):
    return int(Decimal(value).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def as_date(value):
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    try:
        return _dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


# ── Jalali calendar (same Borkowski algorithm as ui.html) ──────────────────
def g2j(gy, gm, gd):
    g_d_m = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    gy2 = gy + 1 if gm > 2 else gy
    days = (355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100)
            + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1])
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def j2g(jy, jm, jd):
    jy2 = jy + 1595
    days = (-355668 + (365 * jy2) + ((jy2 // 33) * 8) + (((jy2 % 33) + 3) // 4) + jd
            + ((jm - 1) * 31 if jm < 7 else ((jm - 7) * 30) + 186))
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0
    month_days = (0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    gm = 0
    while gm < 13 and gd > month_days[gm]:
        gd -= month_days[gm]
        gm += 1
    return gy, gm, gd


def jalali_of(value):
    day = as_date(value)
    return g2j(day.year, day.month, day.day)


def jalali_text(value):
    jy, jm, jd = jalali_of(value)
    return "%04d/%02d/%02d" % (jy, jm, jd)


def parse_jalali(text):
    """'1405/06/19' (Persian or Latin digits, / or -) -> date, else None."""
    if not text:
        return None
    raw = str(text).translate(_TO_ASCII).strip().replace("-", "/")
    parts = raw.split("/")
    if len(parts) != 3:
        return None
    try:
        jy, jm, jd = (int(x) for x in parts)
    except ValueError:
        return None
    if not (1300 <= jy <= 1700 and 1 <= jm <= 12 and 1 <= jd <= 31):
        return None
    gy, gm, gd = j2g(jy, jm, jd)
    try:
        day = _dt.date(gy, gm, gd)
    except ValueError:
        return None
    # 1405/07/31 does not exist; j2g would silently roll it into Aban.
    return day if g2j(day.year, day.month, day.day) == (jy, jm, jd) else None


def month_key(value):
    jy, jm, _ = jalali_of(value)
    return "%04d-%02d" % (jy, jm)


def season_key(value):
    jy, jm, _ = jalali_of(value)
    return "%04d-%d" % (jy, (jm - 1) // 3 + 1)


def _key_parts(key):
    jy, rest = str(key).split("-")
    return int(jy), int(rest)


def month_bounds(key):
    """First and last Gregorian day of a Jalali month key such as '1405-06'."""
    jy, jm = _key_parts(key)
    start = _dt.date(*j2g(jy, jm, 1))
    ny, nm = (jy + 1, 1) if jm == 12 else (jy, jm + 1)
    return start, _dt.date(*j2g(ny, nm, 1)) - _dt.timedelta(days=1)


def season_bounds(key):
    jy, season = _key_parts(key)
    start = _dt.date(*j2g(jy, (season - 1) * 3 + 1, 1))
    ny, ns = (jy + 1, 1) if season == 4 else (jy, season + 1)
    return start, _dt.date(*j2g(ny, (ns - 1) * 3 + 1, 1)) - _dt.timedelta(days=1)


def previous_month_key(key):
    jy, jm = _key_parts(key)
    return "%04d-%02d" % ((jy - 1, 12) if jm == 1 else (jy, jm - 1))


def next_month_key(key):
    jy, jm = _key_parts(key)
    return "%04d-%02d" % ((jy + 1, 1) if jm == 12 else (jy, jm + 1))


def month_label(key):
    jy, jm = _key_parts(key)
    return "%s %s" % (MONTH_NAMES[jm - 1], fa_digits(jy))


def season_label(key):
    jy, season = _key_parts(key)
    return "%s %s" % (SEASON_NAMES[season - 1], fa_digits(jy))


def season_of_month(key):
    jy, jm = _key_parts(key)
    return "%04d-%d" % (jy, (jm - 1) // 3 + 1)


def add_months(value, months):
    month_index = value.month - 1 + int(months)
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    leap = (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
    last = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[month - 1]
    return value.replace(year=year, month=month, day=min(value.day, last))


# ── Working days ────────────────────────────────────────────────────────────
def is_day_off(day, holidays=()):
    # Friday is the weekend; Python counts Monday as 0, so Friday is 4.
    return day.weekday() == 4 or day in holidays


def next_working_day(day, holidays=()):
    day = day + _dt.timedelta(days=1)
    while is_day_off(day, holidays):
        day += _dt.timedelta(days=1)
    return day


def within_one_working_day(started, decided, holidays=()):
    """A decision on the same day or on the next working day is on time."""
    return as_date(decided) <= next_working_day(as_date(started), holidays)


# ── Task points ─────────────────────────────────────────────────────────────
def quality_factor(returns):
    value = Decimal("1.2") - Decimal("0.1") * max(0, int(returns or 0))
    return max(value, Decimal("0.8"))


def on_time(completed, due):
    """True/False once there is a due date, None when the task had none."""
    if due is None or completed is None:
        return None
    return as_date(completed) <= as_date(due)


def on_time_factor(flag):
    return Decimal("1.2") if flag is True else Decimal("1")


def star_factor(stars):
    return STAR_FACTORS.get(to_int(stars), Decimal("1"))


def task_points(progress_weight, category_weight, returns, on_time_flag,
                stars=None, share=1, halved=False):
    progress = to_dec(progress_weight, Decimal(1))
    category = to_dec(category_weight, Decimal(1))
    if progress <= 0 or category <= 0:
        return 0
    value = (BASE_POINTS * progress * category * quality_factor(returns)
             * on_time_factor(on_time_flag) * star_factor(stars) * to_dec(share, Decimal(1)))
    if halved:
        value = value / 2
    return max(0, round_half_up(value))


def split_shares(primary_id, participant_ids=(), seconds_by_user=None):
    """Share of one task per person.

    Logged time decides the split, so whoever actually worked gets the credit.
    With no logged time the primary assignee gets the whole task rather than
    everyone an invented equal slice."""
    timed = {}
    for uid, seconds in (seconds_by_user or {}).items():
        seconds = to_int(seconds, 0) or 0
        if uid is not None and seconds > 0:
            timed[int(uid)] = timed.get(int(uid), 0) + seconds
    total = sum(timed.values())
    if total > 0:
        return {uid: Decimal(seconds) / Decimal(total) for uid, seconds in timed.items()}
    if primary_id is not None:
        return {int(primary_id): Decimal(1)}
    people = [int(x) for x in participant_ids or () if x is not None]
    if len(set(people)) == 1:
        return {people[0]: Decimal(1)}
    return {}


def coins_for_points(points, points_per_coin):
    per_coin = max(1, to_int(points_per_coin, 10) or 10)
    points = to_int(points, 0) or 0
    if points <= 0:
        return 0
    return round_half_up(Decimal(points) / Decimal(per_coin))


def softcap_applies(index_in_day, cap):
    cap = to_int(cap, 15) or 15
    return int(index_in_day) >= cap


def parse_thresholds(text):
    values = []
    for part in str(text or "").split(","):
        number = to_int(part)
        if number is not None and number >= 0:
            values.append(number)
    values = sorted(set(values))
    if not values or values[0] != 0:
        values = [0] + values
    return tuple(values) if len(values) > 1 else DEFAULT_LEVEL_THRESHOLDS


def level_info(points, thresholds=DEFAULT_LEVEL_THRESHOLDS):
    points = max(0, to_int(points, 0) or 0)
    steps = sorted(set(thresholds)) or list(DEFAULT_LEVEL_THRESHOLDS)
    index = max(i for i, floor in enumerate(steps) if points >= floor)
    index = min(index, len(LEVEL_TITLES) - 1)
    floor = steps[index]
    upcoming = steps[index + 1] if index + 1 < min(len(steps), len(LEVEL_TITLES)) else None
    progress = 100 if upcoming is None else int((points - floor) * 100 // max(1, upcoming - floor))
    return {"index": index, "title": LEVEL_TITLES[index], "points": points,
            "floor": floor, "next": upcoming, "progress": max(0, min(100, progress)),
            "to_next": None if upcoming is None else upcoming - points}


def median(values):
    values = [float(v) for v in values if v is not None]
    return statistics.median(values) if values else None


def percent(part, whole):
    whole = to_int(whole, 0) or 0
    if whole <= 0:
        return None
    return int(round((to_int(part, 0) or 0) * 100.0 / whole))


# ── Badges and quests ───────────────────────────────────────────────────────
def flawless_streak(returns_in_order, length=10):
    """The last `length` approved tasks, oldest first, all without a return."""
    recent = list(returns_in_order)[-length:]
    return len(recent) == length and all((to_int(r, 0) or 0) == 0 for r in recent)


def quest_zero_overdue(overdue_count, had_activity):
    return bool(had_activity) and int(overdue_count or 0) == 0


def quest_on_time(on_time_count, with_due_count, minimum=5, threshold=Decimal("0.9")):
    with_due_count = int(with_due_count or 0)
    if with_due_count < minimum:
        return False
    return Decimal(int(on_time_count or 0)) / Decimal(with_due_count) >= threshold


def quest_finance(target, approved):
    target = to_dec(target, Decimal(0)) or Decimal(0)
    return target > 0 and (to_dec(approved, Decimal(0)) or Decimal(0)) >= target


def bright_streak(stars_by_month, minimum=4, length=3):
    """stars_by_month: the last `length` months, oldest first; None = unrated."""
    recent = list(stars_by_month)[-length:]
    return len(recent) == length and all(s is not None and int(s) >= minimum for s in recent)


# ── Shop ────────────────────────────────────────────────────────────────────
def discounted_price(price, percent_off):
    price = max(0, to_int(price, 0) or 0)
    off = to_int(percent_off, 0) or 0
    if off <= 0:
        return price
    off = min(off, 90)
    return max(1, round_half_up(Decimal(price) * (100 - off) / 100))


def hourly_end(start_text, hours):
    try:
        hh, mm = (int(x) for x in str(start_text).translate(_TO_ASCII).split(":"))
    except ValueError:
        return None
    if not (0 <= hh < 24 and 0 <= mm < 60):
        return None
    total = hh * 60 + mm + int(round(float(hours) * 60))
    if total >= 24 * 60:
        return None
    return "%02d:%02d" % (total // 60, total % 60)


def can_change_booking(booked_day, today):
    """A dated item can be moved or cancelled until the day before."""
    booked_day = as_date(booked_day)
    return booked_day is not None and as_date(today) < booked_day


def validate_item(data):
    """Normalise an item form. Returns (clean, None) or (None, Persian error)."""
    data = data or {}
    name = str(data.get("name") or "").strip()
    if len(name) < 2 or len(name) > 150:
        return None, "نام آیتم باید بین ۲ تا ۱۵۰ حرف باشد"
    item_type = str(data.get("item_type") or "")
    if item_type not in ITEM_TYPE_KEYS:
        return None, "نوع آیتم معتبر نیست"
    price = to_int(data.get("price"))
    if price is None or price < 1 or price > 1000000:
        return None, "قیمت باید عددی بین ۱ تا ۱٬۰۰۰٬۰۰۰ سکه باشد"
    description = str(data.get("description") or "").strip()
    if len(description) > 1000:
        return None, "توضیح آیتم حداکثر ۱۰۰۰ حرف است"
    clean = {"name": name, "item_type": item_type, "price": price,
             "description": description or None,
             "is_active": bool(data.get("is_active", True)),
             "show_in_public": bool(data.get("show_in_public", True)),
             "stock_total": None, "per_user_monthly_limit": None,
             "sale_from": None, "sale_to": None,
             "leave_mode": None, "leave_hours": None, "reward_amount": None,
             "team_goal": None, "cosmetic_slot": None, "cosmetic_value": None}
    for key, label in (("stock_total", "موجودی"), ("per_user_monthly_limit", "سقف خرید ماهانه")):
        raw = data.get(key)
        if raw not in (None, ""):
            number = to_int(raw)
            if number is None or number < 1:
                return None, "%s باید عدد مثبت باشد یا خالی بماند" % label
            clean[key] = number
    for key in ("sale_from", "sale_to"):
        raw = data.get(key)
        if raw not in (None, ""):
            day = as_date(raw) if isinstance(raw, (_dt.date, _dt.datetime)) else parse_jalali(raw)
            if day is None:
                return None, "تاریخ بازه فروش معتبر نیست"
            clean[key] = day
    if clean["sale_from"] and clean["sale_to"] and clean["sale_to"] < clean["sale_from"]:
        return None, "پایان بازه فروش نمی‌تواند قبل از شروع آن باشد"
    if item_type == "leave":
        mode = str(data.get("leave_mode") or "day")
        if mode not in ("day", "hours"):
            return None, "نوع مرخصی باید «یک روز» یا «چند ساعت» باشد"
        clean["leave_mode"] = mode
        if mode == "hours":
            hours = to_dec(data.get("leave_hours"))
            if hours is None or hours < Decimal("0.5") or hours > 8:
                return None, "مدت مرخصی ساعتی باید بین نیم تا ۸ ساعت باشد"
            clean["leave_hours"] = hours
    elif item_type == "money":
        amount = to_int(data.get("reward_amount"))
        if amount is None or amount < 1000:
            return None, "مبلغ پاداش مالی را به ریال وارد کنید"
        clean["reward_amount"] = amount
    elif item_type == "team_pot":
        goal = to_int(data.get("team_goal"))
        if goal is None or goal < 1:
            return None, "هدف صندوق تیم باید تعداد سکه مثبت باشد"
        clean["team_goal"] = goal
        clean["stock_total"] = None
    elif item_type == "cosmetic":
        slot = str(data.get("cosmetic_slot") or "")
        if slot not in COSMETIC_SLOTS:
            return None, "نوع آیتم تزئینی را انتخاب کنید"
        value = str(data.get("cosmetic_value") or "").strip()
        allowed = COSMETIC_SLOTS[slot][1]
        if allowed is None:
            if not 1 <= len(value) <= 30:
                return None, "لقب باید بین ۱ تا ۳۰ حرف باشد"
        elif value not in allowed:
            return None, "رنگ یا قاب انتخاب‌شده معتبر نیست"
        clean["cosmetic_slot"] = slot
        clean["cosmetic_value"] = value
    return clean, None


def purchase_error(item, today, balance, price, month_count=0, stock_used=0, booked_day=None):
    """Return the Persian reason a purchase is refused, or None."""
    today = as_date(today)
    if not item or item.get("is_archived"):
        return "این آیتم در فروشگاه نیست"
    if not item.get("is_active"):
        return "این آیتم فعلاً فعال نیست"
    sale_from, sale_to = as_date(item.get("sale_from")), as_date(item.get("sale_to"))
    if sale_from and today < sale_from:
        return "فروش این آیتم هنوز شروع نشده است"
    if sale_to and today > sale_to:
        return "زمان فروش این آیتم تمام شده است"
    if item.get("item_type") != "team_pot":
        stock_total = to_int(item.get("stock_total"))
        if stock_total and int(stock_used or 0) >= stock_total:
            return "موجودی این آیتم تمام شده است"
        limit = to_int(item.get("per_user_monthly_limit"))
        if limit and int(month_count or 0) >= limit:
            return "سقف خرید ماهانه این آیتم برای شما پر شده است"
    if item.get("item_type") in DATED_TYPES:
        booked_day = as_date(booked_day)
        if booked_day is None:
            return "روز استفاده را انتخاب کنید"
        if booked_day <= today:
            return "روز انتخابی باید از فردا به بعد باشد"
    if int(balance or 0) < int(price or 0):
        return "سکه کافی ندارید"
    return None


# ── Wallet with first-in-first-out expiry ───────────────────────────────────
def wallet_state(entries, now, soon_days=30):
    """Balance of one person's coin ledger.

    Every positive entry is a lot with its own expiry date. Spending uses the
    oldest lot that was still valid at the moment of spending. A refund
    cancels the spend it reverses, as if the purchase had never happened. A
    reversal larger than what is left becomes a debt, repaid by the next coins
    earned. Lots whose expiry has passed simply stop counting; nothing has to
    be written for that to be true.
    """
    rows = [dict(row) for row in entries]
    cancelled = set()
    for row in rows:
        if row.get("kind") == "refund" and row.get("reverses_id"):
            cancelled.add(int(row["reverses_id"]))
            cancelled.add(int(row["id"]))
    rows = [row for row in rows if int(row["id"]) not in cancelled]
    rows.sort(key=lambda row: (row["created_at"], int(row["id"])))
    lots, debt = [], 0
    for row in rows:
        amount = int(row["amount"])
        moment = row["created_at"]
        if amount > 0:
            lot = {"id": int(row["id"]), "amount": amount, "remaining": amount,
                   "expires_at": row.get("expires_at"), "created_at": moment}
            if debt:
                used = min(debt, amount)
                debt -= used
                lot["remaining"] -= used
            lots.append(lot)
        elif amount < 0:
            need = -amount
            for lot in lots:
                if need <= 0:
                    break
                expires = lot["expires_at"]
                if lot["remaining"] <= 0 or (expires is not None and expires <= moment):
                    continue
                used = min(need, lot["remaining"])
                lot["remaining"] -= used
                need -= used
            debt += need
    horizon = now + _dt.timedelta(days=soon_days)
    balance, soon, next_expiry, expired, expired_lots = -debt, 0, None, 0, []
    for lot in lots:
        if lot["remaining"] <= 0:
            continue
        expires = lot["expires_at"]
        if expires is not None and expires <= now:
            expired += lot["remaining"]
            expired_lots.append({"id": lot["id"], "amount": lot["remaining"], "expired_at": expires})
            continue
        balance += lot["remaining"]
        if expires is not None:
            if expires <= horizon:
                soon += lot["remaining"]
            if next_expiry is None or expires < next_expiry:
                next_expiry = expires
    return {"balance": balance, "debt": debt, "expiring_soon": soon,
            "next_expiry": next_expiry, "expired": expired, "expired_lots": expired_lots}
