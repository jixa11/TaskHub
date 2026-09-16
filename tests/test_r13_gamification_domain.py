# -*- coding: utf-8 -*-
"""R13: the pure rules behind points, coins and the item shop."""
import datetime as dt
import pathlib
import sys
import unittest
from decimal import Decimal

from _paths import ROOT, SRC, project_file  # noqa: E402

import gamification_domain as gd  # noqa: E402


def day(y, m, d):
    return dt.date(y, m, d)


def at(y, m, d, hh=10):
    return dt.datetime(y, m, d, hh, 0, 0)


class JalaliTests(unittest.TestCase):
    def test_known_dates(self):
        self.assertEqual(gd.g2j(2026, 3, 21), (1405, 1, 1))
        self.assertEqual(gd.g2j(2026, 9, 10), (1405, 6, 19))
        self.assertEqual(gd.j2g(1405, 6, 19), (2026, 9, 10))
        self.assertEqual(gd.j2g(1405, 1, 1), (2026, 3, 21))

    def test_round_trip_over_several_years(self):
        cursor = day(2023, 1, 1)
        while cursor < day(2031, 1, 1):
            self.assertEqual(dt.date(*gd.j2g(*gd.jalali_of(cursor))), cursor, cursor)
            cursor += dt.timedelta(days=3)

    def test_parse_accepts_persian_digits_and_rejects_impossible_days(self):
        self.assertEqual(gd.parse_jalali("۱۴۰۵/۰۶/۱۹"), day(2026, 9, 10))
        self.assertEqual(gd.parse_jalali("1405-06-19"), day(2026, 9, 10))
        self.assertIsNone(gd.parse_jalali("1405/07/31"))   # Mehr has 30 days
        self.assertIsNone(gd.parse_jalali("not a date"))
        self.assertIsNone(gd.parse_jalali(""))

    def test_month_and_season_keys(self):
        self.assertEqual(gd.month_key(day(2026, 9, 10)), "1405-06")
        self.assertEqual(gd.season_key(day(2026, 9, 10)), "1405-2")
        self.assertEqual(gd.season_key(day(2026, 3, 21)), "1405-1")
        self.assertEqual(gd.previous_month_key("1405-01"), "1404-12")
        self.assertEqual(gd.next_month_key("1405-12"), "1406-01")

    def test_bounds_cover_the_whole_period(self):
        start, end = gd.month_bounds("1405-06")
        self.assertEqual(gd.jalali_text(start), "1405/06/01")
        self.assertEqual(gd.jalali_text(end), "1405/06/31")
        start, end = gd.month_bounds("1405-07")
        self.assertEqual(gd.jalali_text(end), "1405/07/30")
        start, end = gd.season_bounds("1405-2")
        self.assertEqual(gd.jalali_text(start), "1405/04/01")
        self.assertEqual(gd.jalali_text(end), "1405/06/31")

    def test_labels_are_persian(self):
        self.assertEqual(gd.month_label("1405-06"), "شهریور ۱۴۰۵")
        self.assertEqual(gd.season_label("1405-2"), "تابستان ۱۴۰۵")


class TaskPointTests(unittest.TestCase):
    def test_plan_example_is_32_points_and_3_coins(self):
        points = gd.task_points(1, 2, returns=0, on_time_flag=True, stars=4)
        self.assertEqual(points, 32)   # 10 x 2 x 1.2 x 1.2 x 1.1 = 31.68
        self.assertEqual(gd.coins_for_points(points, 10), 3)

    def test_quality_drops_per_return_but_never_below_the_floor(self):
        self.assertEqual(gd.quality_factor(0), Decimal("1.2"))
        self.assertEqual(gd.quality_factor(1), Decimal("1.1"))
        self.assertEqual(gd.quality_factor(4), Decimal("0.8"))
        self.assertEqual(gd.quality_factor(9), Decimal("0.8"))

    def test_lateness_is_not_a_penalty(self):
        self.assertEqual(gd.on_time_factor(False), 1)
        self.assertEqual(gd.on_time_factor(None), 1)
        self.assertEqual(gd.on_time_factor(True), Decimal("1.2"))
        self.assertTrue(gd.on_time(at(2026, 9, 10), day(2026, 9, 10)))
        self.assertFalse(gd.on_time(at(2026, 9, 11), day(2026, 9, 10)))
        self.assertIsNone(gd.on_time(at(2026, 9, 11), None))

    def test_star_factor_is_bounded_and_legacy_scores_are_neutral(self):
        self.assertEqual(gd.star_factor(1), Decimal("0.8"))
        self.assertEqual(gd.star_factor(5), Decimal("1.2"))
        self.assertEqual(gd.star_factor(None), 1)
        self.assertEqual(gd.star_factor(37), 1)   # old open-ended scores

    def test_share_and_daily_halving(self):
        self.assertEqual(gd.task_points(1, 1, 0, True, share=Decimal("0.5")), 7)
        self.assertEqual(gd.task_points(1, 1, 0, True, halved=True), 7)
        self.assertEqual(gd.task_points(0, 1, 0, True), 0)
        self.assertTrue(gd.softcap_applies(15, 15))
        self.assertFalse(gd.softcap_applies(14, 15))

    def test_split_follows_logged_time(self):
        shares = gd.split_shares(1, [1, 2], {1: 3600, 2: 1200})
        self.assertEqual(shares[1], Decimal("0.75"))
        self.assertEqual(shares[2], Decimal("0.25"))

    def test_without_time_the_primary_takes_the_task(self):
        self.assertEqual(gd.split_shares(7, [7, 8], {}), {7: Decimal(1)})
        self.assertEqual(gd.split_shares(None, [5], None), {5: Decimal(1)})
        self.assertEqual(gd.split_shares(None, [5, 6], None), {})


class LevelTests(unittest.TestCase):
    def test_levels_and_progress(self):
        info = gd.level_info(0)
        self.assertEqual(info["title"], "تازه‌کار")
        self.assertEqual(info["next"], 300)
        info = gd.level_info(650)
        self.assertEqual(info["title"], "کاردان")
        self.assertEqual(info["progress"], 50)
        top = gd.level_info(99999)
        self.assertEqual(top["title"], "استاد")
        self.assertIsNone(top["next"])
        self.assertEqual(top["progress"], 100)

    def test_thresholds_from_settings(self):
        self.assertEqual(gd.parse_thresholds("0,100,200"), (0, 100, 200))
        self.assertEqual(gd.parse_thresholds("100,50"), (0, 50, 100))
        self.assertEqual(gd.parse_thresholds("garbage"), gd.DEFAULT_LEVEL_THRESHOLDS)


class WalletTests(unittest.TestCase):
    def entry(self, ident, amount, when, kind="task", expires=None, reverses=None):
        return {"id": ident, "amount": amount, "kind": kind, "created_at": when,
                "expires_at": expires, "reverses_id": reverses}

    def test_spending_uses_the_oldest_lot_first(self):
        rows = [self.entry(1, 10, at(2026, 1, 1), expires=at(2027, 1, 1)),
                self.entry(2, 10, at(2026, 6, 1), expires=at(2027, 6, 1)),
                self.entry(3, -12, at(2026, 7, 1), kind="spend")]
        state = gd.wallet_state(rows, at(2026, 12, 15))
        self.assertEqual(state["balance"], 8)
        # Lot 1 is fully spent, so nothing is about to expire in January.
        self.assertEqual(state["expiring_soon"], 0)
        later = gd.wallet_state(rows, at(2027, 5, 20))
        self.assertEqual(later["expiring_soon"], 8)

    def test_expired_coins_stop_counting_without_any_write(self):
        rows = [self.entry(1, 10, at(2025, 1, 1), expires=at(2026, 1, 1)),
                self.entry(2, 5, at(2026, 2, 1), expires=at(2027, 2, 1))]
        state = gd.wallet_state(rows, at(2026, 3, 1))
        self.assertEqual(state["balance"], 5)
        self.assertEqual(state["expired"], 10)

    def test_a_spend_cannot_use_a_lot_that_had_already_expired(self):
        rows = [self.entry(1, 10, at(2025, 1, 1), expires=at(2026, 1, 1)),
                self.entry(2, 20, at(2025, 6, 1), expires=at(2026, 6, 1)),
                self.entry(3, -15, at(2026, 2, 1), kind="spend")]
        state = gd.wallet_state(rows, at(2026, 3, 1))
        self.assertEqual(state["balance"], 5)

    def test_refund_cancels_its_purchase(self):
        rows = [self.entry(1, 30, at(2026, 1, 1), expires=at(2027, 1, 1)),
                self.entry(2, -20, at(2026, 2, 1), kind="spend"),
                self.entry(3, 20, at(2026, 2, 5), kind="refund", reverses=2)]
        self.assertEqual(gd.wallet_state(rows, at(2026, 3, 1))["balance"], 30)

    def test_reversal_after_spending_becomes_a_debt_repaid_later(self):
        rows = [self.entry(1, 10, at(2026, 1, 1), expires=at(2027, 1, 1)),
                self.entry(2, -10, at(2026, 1, 2), kind="spend"),
                self.entry(3, -4, at(2026, 1, 3), kind="task"),
                self.entry(4, 10, at(2026, 1, 4), expires=at(2027, 1, 4))]
        state = gd.wallet_state(rows, at(2026, 2, 1))
        self.assertEqual(state["balance"], 6)
        self.assertEqual(state["debt"], 0)
        owing = gd.wallet_state(rows[:3], at(2026, 2, 1))
        self.assertEqual(owing["balance"], -4)

    def test_expiry_is_twelve_months_with_short_months_clamped(self):
        self.assertEqual(gd.add_months(at(2026, 1, 31), 1).date(), day(2026, 2, 28))
        self.assertEqual(gd.add_months(at(2026, 9, 10), 12).date(), day(2027, 9, 10))


class ShopTests(unittest.TestCase):
    ITEM = {"is_active": True, "is_archived": False, "item_type": "goods",
            "stock_total": 5, "per_user_monthly_limit": 1}

    def test_festival_percentages(self):
        self.assertEqual(gd.discounted_price(100, 20), 80)
        self.assertEqual(gd.discounted_price(99, 15), 84)     # 84.15
        self.assertEqual(gd.discounted_price(5, 90), 1)       # never free
        self.assertEqual(gd.discounted_price(50, 0), 50)
        self.assertEqual(gd.discounted_price(50, 150), 5)     # capped at 90%

    def test_purchase_rules(self):
        today = day(2026, 9, 10)
        self.assertIsNone(gd.purchase_error(self.ITEM, today, 50, 40))
        self.assertIn("کافی", gd.purchase_error(self.ITEM, today, 30, 40))
        self.assertIn("موجودی", gd.purchase_error(self.ITEM, today, 50, 40, stock_used=5))
        self.assertIn("سقف", gd.purchase_error(self.ITEM, today, 50, 40, month_count=1))
        inactive = dict(self.ITEM, is_active=False)
        self.assertIn("فعال", gd.purchase_error(inactive, today, 50, 40))
        window = dict(self.ITEM, sale_from=day(2026, 9, 20))
        self.assertIn("شروع", gd.purchase_error(window, today, 50, 40))

    def test_dated_items_start_tomorrow_at_the_earliest(self):
        leave = dict(self.ITEM, item_type="leave")
        today = day(2026, 9, 10)
        self.assertIn("روز", gd.purchase_error(leave, today, 50, 40))
        self.assertIn("فردا", gd.purchase_error(leave, today, 50, 40, booked_day=today))
        self.assertIsNone(gd.purchase_error(leave, today, 50, 40, booked_day=day(2026, 9, 11)))

    def test_bookings_change_until_the_day_before(self):
        self.assertTrue(gd.can_change_booking(day(2026, 9, 12), day(2026, 9, 11)))
        self.assertFalse(gd.can_change_booking(day(2026, 9, 12), day(2026, 9, 12)))

    def test_hourly_leave_end_time(self):
        self.assertEqual(gd.hourly_end("09:30", 2), "11:30")
        self.assertEqual(gd.hourly_end("۰۸:۰۰", "1.5"), "09:30")
        self.assertIsNone(gd.hourly_end("23:30", 1))
        self.assertIsNone(gd.hourly_end("bad", 1))

    def test_item_validation(self):
        clean, error = gd.validate_item({"name": "مرخصی نیم‌روز", "item_type": "leave",
                                         "price": "۱۲۰", "leave_mode": "hours", "leave_hours": "4"})
        self.assertIsNone(error)
        self.assertEqual(clean["price"], 120)
        self.assertEqual(clean["leave_hours"], Decimal("4"))
        _, error = gd.validate_item({"name": "x", "item_type": "goods", "price": 10})
        self.assertIn("نام", error)
        _, error = gd.validate_item({"name": "قاب", "item_type": "cosmetic", "price": 10,
                                     "cosmetic_slot": "frame", "cosmetic_value": "pink"})
        self.assertIn("معتبر", error)
        _, error = gd.validate_item({"name": "پاداش", "item_type": "money", "price": 10})
        self.assertIn("ریال", error)
        clean, error = gd.validate_item({"name": "بازه", "item_type": "goods", "price": 10,
                                         "sale_from": "1405/06/20", "sale_to": "1405/06/10"})
        self.assertIn("پایان", error)


class BadgeAndQuestTests(unittest.TestCase):
    def test_flawless_needs_ten_clean_tasks_in_a_row(self):
        self.assertTrue(gd.flawless_streak([1] + [0] * 10))
        self.assertFalse(gd.flawless_streak([0] * 9))
        self.assertFalse(gd.flawless_streak([0] * 9 + [1]))

    def test_quests(self):
        self.assertTrue(gd.quest_zero_overdue(0, True))
        self.assertFalse(gd.quest_zero_overdue(0, False))
        self.assertTrue(gd.quest_on_time(9, 10))
        self.assertFalse(gd.quest_on_time(4, 4))           # fewer than five tasks
        self.assertTrue(gd.quest_finance(1000, 1000))
        self.assertFalse(gd.quest_finance(0, 50))

    def test_bright_streak(self):
        self.assertTrue(gd.bright_streak([5, 4, 4]))
        self.assertFalse(gd.bright_streak([5, None, 5]))
        self.assertFalse(gd.bright_streak([4, 4]))

    def test_working_day_rule_skips_friday_and_holidays(self):
        thursday = day(2026, 9, 10)
        self.assertEqual(thursday.weekday(), 3)
        self.assertEqual(gd.next_working_day(thursday), day(2026, 9, 12))
        self.assertTrue(gd.within_one_working_day(at(2026, 9, 10), at(2026, 9, 12)))
        self.assertFalse(gd.within_one_working_day(at(2026, 9, 10), at(2026, 9, 13)))
        holiday = {day(2026, 9, 12)}
        self.assertEqual(gd.next_working_day(thursday, holiday), day(2026, 9, 13))

    def test_every_badge_is_described(self):
        for badge in gd.BADGES:
            self.assertTrue(badge["title"] and badge["desc"], badge["key"])
            self.assertIn(badge["period"], ("season", "month"))
            self.assertTrue(set(badge["roles"]) <= set(gd.WALLET_ROLES), badge["key"])


if __name__ == "__main__":
    unittest.main()
