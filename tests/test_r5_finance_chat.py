# -*- coding: utf-8 -*-
import ast
import datetime as dt
from pathlib import Path
import unittest

from _paths import ROOT, SRC, project_file  # noqa: E402


def src(name):
    return project_file(name).read_text(encoding="utf-8")


def load_jalali_helpers():
    tree = ast.parse(src("v7_features.py"))
    names = {"_jalali_to_gregorian", "_gregorian_to_jalali", "_jalali_month_window"}
    module = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[])
    ns = {"_dt": dt}
    exec(compile(module, "v7_features_helpers", "exec"), ns)
    return ns


class R5JalaliFinancialDashboardTests(unittest.TestCase):
    def test_jalali_conversion_and_previous_month_boundary(self):
        ns = load_jalali_helpers()
        self.assertEqual(ns["_jalali_to_gregorian"](1405, 1, 1), (2026, 3, 21))
        self.assertEqual(ns["_jalali_to_gregorian"](1405, 5, 1), (2026, 7, 23))
        self.assertEqual(ns["_gregorian_to_jalali"](2026, 7, 23), (1405, 5, 1))
        start, end, previous_start, previous_year, previous_month = ns["_jalali_month_window"](1405, 1)
        self.assertEqual(start, dt.date(2026, 3, 21))
        self.assertEqual((previous_year, previous_month), (1404, 12))
        self.assertLess(previous_start, start)
        self.assertGreater(end, start)

    def test_jalali_round_trip_and_month_windows_for_supported_recent_years(self):
        ns = load_jalali_helpers()
        checked_dates = 0
        checked_windows = 0
        for year in range(1390, 1411):
            for month in range(1, 13):
                for day in (1, 28):
                    gy, gm, gd = ns["_jalali_to_gregorian"](year, month, day)
                    self.assertEqual(ns["_gregorian_to_jalali"](gy, gm, gd),
                                     (year, month, day))
                    checked_dates += 1
                start, end, previous_start, previous_year, previous_month = \
                    ns["_jalali_month_window"](year, month)
                self.assertLess(previous_start, start)
                self.assertLess(start, end)
                if month == 1:
                    self.assertEqual((previous_year, previous_month), (year - 1, 12))
                else:
                    self.assertEqual((previous_year, previous_month), (year, month - 1))
                checked_windows += 1
        self.assertEqual(checked_dates, 504)
        self.assertEqual(checked_windows, 252)

    def test_financial_dashboard_uses_monthly_jalali_target_and_period(self):
        py = src("v7_features.py")
        js = src("v7_ui.js")
        for marker in (
            "selected_month = _int(d.get('jalali_month'))",
            "FinancialPlanPeriods WHERE plan_id=? AND month_no=?",
            "s.period_year=?",
            "s.period_month=?",
            "target_label=target_label",
        ):
            self.assertIn(marker, py)
        for marker in (
            "v7FinancialMonthChanged",
            "v7MonthOptions(selected,true)",
            "جزئیات و نمودارها",
            "r.target_amount",
            "V7_MONTHS",
        ):
            self.assertIn(marker, js)

    def test_financial_plan_contains_monthly_and_cumulative_charts(self):
        js = src("v7_ui.js")
        css = src("v7_ui.css")
        self.assertIn('id="v7-plan-charts"', js)
        self.assertIn("function v7PlanChartsHtml", js)
        self.assertIn("نمودار ماهانه هدف و عملکرد", js)
        self.assertIn("روند تجمعی تحقق هدف", js)
        self.assertIn("v7-plan-line-chart", css)
        self.assertIn("v7-plan-bar-chart", css)

    def test_task_comparison_is_jalali_selectable_and_compares_previous_month(self):
        py = src("v7_features.py")
        js = src("v7_ui.js")
        for marker in (
            "comparison_jalali_year",
            "comparison_jalali_month",
            "_jalali_month_window(comparison_year, comparison_month)",
            "previous_jalali_year=previous_year",
        ):
            self.assertIn(marker, py)
        for marker in (
            "v71ComparisonChanged",
            'id="v71-compare-year"',
            'id="v71-compare-month"',
            "مقایسه پیشرفت تسک‌ها (شمسی)",
            "تسک ",
        ):
            self.assertIn(marker, js)


class R5ConversationManagementTests(unittest.TestCase):
    def test_group_rename_and_soft_delete_are_server_authorized(self):
        py = src("v8_features.py")
        rbac = src("rbac.py")
        for marker in (
            '/api/v8/chat/conversation_update',
            '/api/v8/chat/conversation_delete',
            "فقط مدیر گروه اجازه ویرایش نام را دارد",
            "UPDATE ChatConversations SET is_active=0",
            "UPDATE ChatMembers SET is_active=0",
            "deleted_for_all=deleted_for_all",
        ):
            self.assertIn(marker, py)
        self.assertIn('"api_v8_chat_conversation_update": "chat.manage_groups"', rbac)
        self.assertIn('"api_v8_chat_conversation_delete": "chat.use"', rbac)
        self.assertIn("Promote another active member first", py)
        self.assertIn("member_role='owner'", py)

    def test_chat_ui_exposes_edit_delete_and_leave_by_conversation_kind(self):
        js = src("v8_ui.js")
        for marker in (
            'id="v8-chat-edit"',
            'id="v8-chat-delete"',
            "function v8ChatOpenEdit",
            "function v8ChatSaveEdit",
            "function v8ChatDeleteConversation",
            "حذف گفتگو",
            "حذف گروه",
            "ترک گروه",
        ):
            self.assertIn(marker, js)

    def test_help_documents_new_finance_and_chat_behaviour(self):
        html = src("ui.html")
        self.assertIn("هدف مالی و نمودارهای شمسی", html)
        self.assertIn("فروردین تا اسفند", html)
        self.assertIn("مدیر گروه می‌تواند نام و اعضا را ویرایش", html)
        self.assertIn("ماه شمسی قبل", html)

    def test_r5_version_and_build_output(self):
        self.assertIn("APP_VERSION = '1.0.0'", src("config.py"))
        self.assertIn("TaskHub.exe", src("build.bat"))
        self.assertIn("TaskHub.exe", src("Run_TaskHub.cmd"))
        self.assertIn("1.0.0", src("service-worker.js"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
