# -*- coding: utf-8 -*-
import ast
import pathlib
import subprocess
import unittest
from decimal import Decimal

from _paths import ROOT, SRC, project_file  # noqa: E402

from v802_domain import (allocate_approved_amount, percent,
                         split_person_task_score, weighted_task_score)


class V802FinancialAttributionRulesTests(unittest.TestCase):
    def test_task_score_links_task_category_weight_and_progress_weight(self):
        self.assertEqual(weighted_task_score(3, "1.5"), Decimal("4.5"))
        self.assertEqual(weighted_task_score(0, 20), Decimal("0"))

    def test_real_time_is_used_before_assignee_fallback(self):
        rows, unresolved = split_person_task_score(
            Decimal("8"), {10: 3, 11: 1}, {10, 11, 12}
        )
        self.assertFalse(unresolved)
        self.assertEqual(rows[10], Decimal("6"))
        self.assertEqual(rows[11], Decimal("2"))
        self.assertNotIn(12, rows)

    def test_one_assignee_without_timer_receives_task_score(self):
        rows, unresolved = split_person_task_score(5, {}, {20})
        self.assertFalse(unresolved)
        self.assertEqual(rows, {20: Decimal("5")})

    def test_multi_assignee_without_timer_is_not_split_equally(self):
        rows, unresolved = split_person_task_score(5, {}, {20, 21})
        self.assertTrue(unresolved)
        self.assertEqual(rows, {})

    def test_approved_amount_allocation_is_proportional_not_compensation(self):
        self.assertEqual(
            allocate_approved_amount(1_000_000, 3, 4),
            Decimal("750000"),
        )
        self.assertEqual(percent(3, 4), Decimal("75.00"))


class V802StructuralTests(unittest.TestCase):
    def source(self, name):
        return project_file(name).read_text(encoding="utf-8")

    def test_existing_revenue_report_is_extended_without_new_top_level_page(self):
        js = self.source("v7_ui.js")
        self.assertEqual(js.count('data-pg="20"'), 2)  # nav item + listener selector
        self.assertIn("گزارش درآمد", js)
        self.assertIn("این نما بخشی از همان گزارش درآمد است", js)
        self.assertIn("v71ChooseFinancialDimension('city'", js)
        self.assertIn("v71ChooseFinancialDimension('contract_type'", js)
        self.assertNotIn('data-pg="26"', js)

    def test_contract_type_migration_is_once_only_and_keeps_undefined_active(self):
        py = self.source("v802_features.py")
        self.assertIn("v802_contract_types_migrated", py)
        self.assertEqual(py.count("UPDATE Contracts SET contract_type_id=0"), 1)
        for label in ("نوع تعیین نشده", "فروش", "توسعه", "پشتیبانی"):
            self.assertIn(label, py)
        self.assertIn("UPDATE ContractTypes SET is_active=0 WHERE id NOT IN (0,1,2,3)", py)

    def test_task_contract_must_match_task_project(self):
        py = self.source("v7_features.py")
        self.assertIn("قرارداد انتخاب‌شده متعلق به پروژه این تسک نیست", py)
        self.assertIn("SELECT id,project_id FROM Contracts WHERE id=? AND is_active=1", py)

    def test_task_contract_dropdown_only_lists_selected_project_contracts(self):
        v7_js = self.source("v7_ui.js")
        v8_js = self.source("v8_ui.js")
        self.assertIn("Number(x.project_id)===pid", v7_js)
        self.assertIn("rows.some(function(x){return String(x.id)===cur;})", v7_js)
        self.assertIn("!x.is_closed", v7_js)
        self.assertIn("if(typeof v7FillTaskLinks==='function')v7FillTaskLinks()", v8_js)

    def test_attribution_has_city_team_person_and_contract_type_dimensions(self):
        py = self.source("v802_features.py")
        js = self.source("v8_ui.js")
        for key in ("cities", "contract_types", "teams", "people", "contracts"):
            self.assertIn('"%s"' % key, py)
        self.assertIn("سهم مالی قراردادها", js)
        self.assertIn("سهم تحلیلی از درآمد", js)
        self.assertIn("multi_assignee_without_time", py)
        self.assertIn("split_person_task_score", py)

    def test_every_financial_report_has_pdf_and_xlsx(self):
        v7_py = self.source("v7_features.py")
        v7_js = self.source("v7_ui.js")
        v8_py = self.source("v8_features.py")
        v802_py = self.source("v802_features.py")
        self.assertIn("v71ExportReport('project_revenue','pdf')", v7_js)
        self.assertIn("v71ExportReport('work_share','pdf')", v7_js)
        self.assertIn("if fmt=='pdf'", v7_py)
        self.assertIn('fmt = (data.get("format") or "xlsx").lower()', v8_py)
        self.assertIn('if fmt == "pdf"', v802_py)
        self.assertIn("TaskHub_financial_attribution.pdf", v802_py)
        self.assertIn("TaskHub_financial_attribution.xlsx", v802_py)

    def test_financial_report_permissions_are_server_enforced(self):
        py = self.source("v802_features.py")
        self.assertIn('FINANCIAL_REPORT_ROLES = ("admin", "manager", "planner", "finance", "reporter")', py)
        self.assertIn('GLOBAL_FINANCIAL_ROLES = ("admin", "finance", "reporter")', py)
        # R16: the route follows the access screen instead of a fixed role list.
        from rbac import ENDPOINT_PERMISSIONS
        self.assertNotIn("@require_roles(*FINANCIAL_REPORT_ROLES)", py)
        self.assertIn("api_financial_attribution", ENDPOINT_PERMISSIONS)
        self.assertIn("api_financial_attribution_export", ENDPOINT_PERMISSIONS)
        self.assertIn("به این تیم دسترسی ندارید", py)
        self.assertIn('user_has_permission(g.user, "contract_weights.manage")', py)
        self.assertIn("دسترسی تغییر وزن‌ها را ندارید", py)

    def test_empty_team_membership_cannot_fall_through_to_global_financial_data(self):
        py = self.source("v802_features.py")
        self.assertIn("if scope_limited and not tids", py)
        self.assertIn('"access_scope": {"limited": True, "team_ids": []}', py)
        self.assertIn("if scope_limited:", py)
        self.assertNotIn("t.project_team_id IS NULL OR EXISTS", py)

    def test_financial_exports_have_contract_section_disclaimer_and_persian_headers(self):
        py = self.source("v802_features.py")
        self.assertIn('("خلاصه قراردادها", data.get("contracts") or []', py)
        self.assertIn('("قراردادها", data.get("contracts") or []', py)
        self.assertIn('("contract_title", "عنوان قرارداد")', py)
        self.assertIn("سهم تحلیلی؛ نه حقوق، پاداش یا بدهی شرکت", py)
        self.assertIn("کیفیت داده —", py)

    def test_cache_upgrade_is_automatic_and_never_clears_chat_keys(self):
        sw = self.source("service-worker.js")
        html = self.source("ui.html")
        self.assertIn("taskhub-v1-0-0-static", sw)
        self.assertIn("self.skipWaiting()", sw)
        self.assertIn("self.clients.claim()", sw)
        self.assertIn("taskhubClearCacheAndReload", html)
        clear_block = html[html.index("async function taskhubClearCacheAndReload"):
                           html.index("async function", html.index("async function taskhubClearCacheAndReload") + 20)]
        self.assertNotIn("localStorage.clear", clear_block)
        self.assertNotIn("indexedDB.deleteDatabase", clear_block)


    def test_dashboard_financial_cards_fill_the_two_column_grid(self):
        js = self.source("v7_ui.js")
        html = self.source("ui.html")
        py = self.source("v7_features.py")
        for card_id in ("chart-project-type", "chart-income-city",
                        "chart-income-contract-type", "chart-financial-attribution"):
            self.assertIn(card_id, js)
        self.assertIn("v802OpenIncomeDimension", js)
        self.assertIn("v802OpenFinancialAttribution", js)
        self.assertIn("v802LoadDashboardFinancialCards", js)
        self.assertIn('id="dash-charts"', html)
        self.assertIn('data-permission="reports.view" id="dash-charts"', html)
        from rbac import ENDPOINT_PERMISSIONS
        self.assertIn("api_v71_dashboard_reports", ENDPOINT_PERMISSIONS)

    def test_lan_build_ships_both_vazirmatn_faces(self):
        html = self.source("ui.html")
        taskhub = self.source("taskhub.py")
        build = self.source("build.bat")
        self.assertIn("@font-face", html)
        self.assertIn("/assets/Vazirmatn-Regular.ttf?v=1.0.0", html)
        self.assertIn("/assets/Vazirmatn-Bold.ttf?v=1.0.0", html)
        self.assertIn("Tahoma", html)
        # A single static face must never claim the whole 100-900 range; that
        # is what stopped the browser from bolding headings and buttons.
        self.assertNotIn("font-weight:100 900", html)
        self.assertIn("'Vazirmatn-Regular.ttf', 'Vazirmatn-Bold.ttf'", taskhub)
        for name in ("Vazirmatn-Regular.ttf", "Vazirmatn-Bold.ttf"):
            self.assertTrue(project_file(name).exists(), name)
            self.assertIn('--add-data "src\\web\\%s;web"' % name, build)

    def test_pdf_exports_use_the_bundled_persian_font(self):
        # Every export used to resolve its own font and looked only at
        # C:\\Windows\\Fonts, so the bundled Vazirmatn was never used in PDFs.
        for name in ("taskhub.py", "v7_features.py", "v8_features.py", "v802_features.py"):
            source = self.source(name)
            self.assertIn("fa_font", source, name)
            self.assertNotIn(r"C:\Windows\Fonts\tahoma.ttf", source, name)
        helper = self.source("fa_font.py")
        self.assertIn("_MEIPASS", helper)
        self.assertIn("registerFontFamily", helper)

    def test_iis_waitress_reverse_proxy_mode_is_packaged(self):
        config = self.source("config.py")
        taskhub = self.source("taskhub.py")
        build = self.source("build.bat")
        self.assertIn("TASKHUB_REVERSE_PROXY", config)
        self.assertIn("SERVER_ENGINE", config)
        self.assertIn("ProxyFix", taskhub)
        self.assertIn("from waitress import serve", taskhub)
        self.assertIn("bind_host = '127.0.0.1' if REVERSE_PROXY else HOST", taskhub)
        self.assertIn("TaskHub", build)
        self.assertTrue((ROOT / "deploy" / "iis" / "web.config").exists())
        self.assertTrue((ROOT / "docs" / "DEPLOY_IIS_FA.md").exists())

    def test_v802_literal_sql_execute_marker_counts(self):
        tree = ast.parse(self.source("v802_features.py"))
        mismatches = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and
                    isinstance(node.func, ast.Attribute) and
                    node.func.attr == "execute" and node.args):
                continue
            sql_node = node.args[0]
            if not (isinstance(sql_node, ast.Constant) and
                    isinstance(sql_node.value, str)):
                continue
            marker_count = sql_node.value.count("?")
            supplied = len(node.args) - 1
            if supplied == 1 and not isinstance(node.args[1], ast.Constant):
                continue
            if marker_count != supplied:
                mismatches.append((node.lineno, marker_count, supplied))
        self.assertEqual(mismatches, [])

    def test_javascript_and_service_worker_parse(self):
        try:
            for name in ("v7_ui.js", "v8_ui.js", "service-worker.js"):
                result = subprocess.run(
                    ["node", "--check", str(project_file(name))],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
        except FileNotFoundError:
            self.skipTest("node is unavailable")


if __name__ == "__main__":
    unittest.main()
