# -*- coding: utf-8 -*-
"""Release regression checks for TaskHub 8.0.3 LAN R6."""
from pathlib import Path
import unittest

from _paths import ROOT, SRC, project_file  # noqa: E402


def src(name):
    return project_file(name).read_text(encoding="utf-8")


class R6AccessControlTests(unittest.TestCase):
    def test_new_permissions_are_catalogued_and_delegable(self):
        rbac = src("rbac.py")
        for key in (
            "contracts.relink_project",
            "extensions.edit_any_status",
            "statements.edit_any_status",
        ):
            self.assertIn(key, rbac)
        self.assertIn('NON_DELEGABLE = frozenset(("access_control.manage", "system.data_export",', rbac)
        self.assertIn('"manager": set(ALL_PERMISSION_KEYS) - set(NON_DELEGABLE)', rbac)
        self.assertIn('"planner": set(ALL_PERMISSION_KEYS) - set(NON_DELEGABLE)', rbac)
        self.assertIn('"contracts.manage", "contracts.relink_project"', rbac)
        self.assertIn('"extensions.manage", "extensions.edit_any_status"', rbac)
        self.assertIn('"statements.edit_any_status"', rbac)

    def test_permission_ui_is_catalog_driven_and_admin_only(self):
        ui = src("v8_ui.js")
        html = src("ui.html")
        self.assertIn("v8AccessControlPageHtml", ui)
        self.assertIn("access_control.manage", ui)
        self.assertIn('data-permission="access_control.manage"', ui)
        self.assertIn("تغییر پروژه قرارداد دارای سابقه", html)
        self.assertIn("ویرایش الحاقیه یا صورت‌وضعیت در همه وضعیت‌ها", html)


class R6ContractRelinkTests(unittest.TestCase):
    def test_historical_contract_relink_requires_permission_and_confirmation(self):
        py = src("v7_features.py")
        for marker in (
            "contracts.relink_project",
            "confirm_project_relink",
            "relink_with_history",
            "دقیقاً یک تیم مقصد انتخاب کنید",
            "project_relink",
        ):
            self.assertIn(marker, py)

    def test_relink_moves_operational_and_financial_dependencies_atomically(self):
        py = src("v7_features.py")
        for marker in (
            "UPDATE Tasks SET project_id=?,project_team_id=?",
            "UPDATE PlannedStatements SET project_team_id=?",
            "UPDATE ContractStatements SET project_team_id=?",
            "ContractStatementTeams",
            "ContractExtensionTeams",
            "ContractProjectTeams",
        ):
            self.assertIn(marker, py)

    def test_client_confirms_project_change(self):
        js = src("v7_ui.js")
        self.assertIn("confirm_project_relink", js)
        self.assertIn("پروژه قرارداد تغییر کند؟", js)


class R6FinancialEditAndMigrationTests(unittest.TestCase):
    def test_extension_and_statement_all_status_edit_is_server_enforced(self):
        py = src("v7_features.py")
        js = src("v7_ui.js")
        self.assertIn("extensions.edit_any_status", py)
        self.assertIn("statements.edit_any_status", py)
        self.assertIn("internal_status='draft'", py)
        self.assertIn("preserve_status", py)
        self.assertIn("statements.edit_before_employer_decision", py)
        self.assertIn("function v7CanEditExtension", js)
        self.assertIn("function v7CanEditStatement", js)

    def test_legacy_statement_amount_mapping_uses_actual_base_and_vat(self):
        migration = src("migrate_legacy_v7.py")
        self.assertIn("requested_base = as_decimal(row.get('ContractStatementPrice'))", migration)
        self.assertIn("requested_vat = as_decimal(row.get('ContractStatementVat'))", migration)
        self.assertIn("requested_total = None if requested_base is None else requested_base +", migration)
        self.assertIn("confirmed_base = as_decimal(row.get('ContractStatementConfirmedPrice'))", migration)
        self.assertIn("confirmed_total = (confirmed_base +", migration)
        self.assertIn("is_legacy_approved", migration)
        # Invalid legacy *WithoutVat columns must not drive the converted amount.
        statement_block = migration[migration.index("def statements(self, path):"):]
        self.assertNotIn("ContractStatementPriceWithoutVat", statement_block)
        self.assertNotIn("ContractStatementConfirmedPriceWithoutVat", statement_block)

    def test_existing_database_has_one_time_repair(self):
        py = src("v7_features.py")
        for marker in (
            "r6_legacy_finance_repair_v1",
            "$.ContractStatementPrice",
            "$.ContractStatementVat",
            "$.ContractStatementConfirmedPrice",
            "$.ContractStatementConfirmedVat",
            "requested_price = CASE WHEN raw.requested_base IS NULL",
            "confirmed_price = CASE WHEN raw.confirmed_base IS NULL",
        ):
            self.assertIn(marker, py)

    def test_validated_extension_snapshot_ids_are_not_double_added(self):
        migration = src("migrate_legacy_v7.py")
        py = src("v7_features.py")
        self.assertIn("FINAL_SNAPSHOT_EXTENSION_IDS = {3029, 3030}", migration)
        self.assertIn("IN (3029,3030)", py)
        self.assertIn("'final_snapshot'", migration)
        self.assertIn("internal_status = 'approved'", py)


class R6GridAndFilterTests(unittest.TestCase):
    def test_contract_child_navigation_uses_one_shot_filter(self):
        js = src("v7_ui.js")
        self.assertIn("pendingContractFilter", js)
        self.assertIn("function v7OpenContractChildren", js)
        self.assertIn("V7.pendingContractFilter=null", js)
        self.assertIn("g('v7-extension-contract').value=contractId?String(contractId):''", js)
        self.assertIn("g('v7-statement-contract').value=contractId?String(contractId):''", js)

    def test_contract_grid_uses_latest_effective_extension_end_date(self):
        py = src("v7_features.py")
        self.assertIn("effective_end_date", py)
        self.assertIn("ContractExtensions", py)
        self.assertIn("internal_status='approved' OR", py)
        self.assertIn("legacy_extension_id IS NOT NULL", py)

    def test_all_tables_are_sortable_and_money_inputs_are_formatted(self):
        js = src("v7_ui.js")
        css = src("v7_ui.css")
        v8 = src("v8_ui.js")
        for marker in (
            "function v7InstallTableSorting",
            "table thead th",
            "localeCompare",
            "v7-sort-asc",
            "function v7FormatMoneyInput",
            "data-money-input",
        ):
            self.assertIn(marker, js)
        self.assertIn('table thead th:not([data-no-sort="1"])', css)
        self.assertIn("[data-money-input]", css)
        self.assertIn("data-money-input", v8)


class R6HelpAndReleaseTests(unittest.TestCase):
    def test_help_and_training_cover_new_workflows(self):
        html = src("ui.html")
        js = src("v7_ui.js")
        for marker in (
            "راهنما و آموزش نرم‌افزار",
            "مرتب‌سازی گرید",
            "جداکننده سه‌رقمی",
            "تغییر پروژه قرارداد",
            "ویرایش اسناد مالی",
            "فیلتر قرارداد",
        ):
            self.assertTrue(marker in html or marker in js, marker)

    def test_r6_version_and_output(self):
        self.assertIn("APP_VERSION = '1.0.0'", src("config.py"))
        self.assertIn("TaskHub.exe", src("build.bat"))
        self.assertIn("TaskHub.exe", src("Run_TaskHub.cmd"))
        self.assertIn("1.0.0", src("service-worker.js"))
        self.assertIn("taskhub-v1-0-0-static", src("service-worker.js"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
