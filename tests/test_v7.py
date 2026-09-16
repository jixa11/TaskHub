# -*- coding: utf-8 -*-
import ast
import datetime
import json
import os
import pathlib
import subprocess
import sys
import types
import unittest


from _paths import ROOT, SRC, project_file  # noqa: E402

from v7_domain import (contract_remaining, effective_contract_price,
                       expiry_level, statement_amount_without_vat,
                       validate_monthly_allocation)


class FinancialRulesTests(unittest.TestCase):
    def test_effective_contract_price_uses_only_passed_approved_deltas(self):
        self.assertEqual(effective_contract_price(1_000, [100, -25]), 1075)

    def test_statement_amount_excludes_vat_and_prefers_confirmed(self):
        row = {'requested_price': 150, 'requested_without_vat': 120,
               'confirmed_price': 130, 'confirmed_without_vat': 110,
               'confirmed_vat': 20}
        self.assertEqual(statement_amount_without_vat(row), 110)

    def test_remaining_only_receives_employer_approved_rows(self):
        approved = [{'confirmed_without_vat': 200}, {'requested_without_vat': 50}]
        self.assertEqual(contract_remaining(1000, approved), 750)

    def test_overrun_is_visible_not_clamped(self):
        self.assertEqual(contract_remaining(100, [{'confirmed_without_vat': 120}]), -20)

    def test_36_billion_can_be_allocated_3_billion_per_month(self):
        ok, error, gap = validate_monthly_allocation(36_000_000_000,
                                                     [3_000_000_000] * 12)
        self.assertTrue(ok); self.assertIsNone(error); self.assertEqual(gap, 0)

    def test_monthly_total_cannot_exceed_annual(self):
        ok, _, gap = validate_monthly_allocation(100, [10] * 12)
        self.assertFalse(ok); self.assertLess(gap, 0)

    def test_expiry_thresholds(self):
        today = datetime.date(2026, 7, 21)
        self.assertEqual(expiry_level(today - datetime.timedelta(days=1), today)[0], 'red')
        self.assertEqual(expiry_level(today + datetime.timedelta(days=15), today)[0], 'red')
        self.assertEqual(expiry_level(today + datetime.timedelta(days=16), today)[0], 'yellow')
        self.assertEqual(expiry_level(today + datetime.timedelta(days=46), today)[0], 'normal')


class StructuralSafetyTests(unittest.TestCase):
    def source(self, name):
        return project_file(name).read_text(encoding='utf-8')

    def function_ast(self, path, function):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        node = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == function)
        return ast.dump(node, include_attributes=False)

    def test_connection_string_function_unchanged_from_621(self):
        old = ROOT.parent / 'review-v621' / 'TaskHub_v6.2.1_fixed' / 'config.py'
        if not old.exists():
            self.skipTest('v6.2.1 comparison source not present in package')
        self.assertEqual(self.function_ast(old, 'connection_string'),
                         self.function_ast(project_file('config.py'), 'connection_string'))

    def test_version_is_803_lan(self):
        self.assertIn("APP_VERSION = '1.0.0'", self.source('config.py'))


    def test_manager_planner_operational_parity_is_permission_driven(self):
        rbac = self.source('rbac.py'); html = self.source('ui.html')
        self.assertIn('"manager": set(ALL_PERMISSION_KEYS) - set(NON_DELEGABLE)', rbac)
        self.assertIn('"planner": set(ALL_PERMISSION_KEYS) - set(NON_DELEGABLE)', rbac)
        self.assertIn('"contracts.archive"', rbac)
        self.assertIn('"extensions.archive"', rbac)
        self.assertIn('"statements.archive"', rbac)
        self.assertIn('legacyAdminEquivalent', html)
        self.assertIn('منوی «مدیریت دسترسی‌ها» فقط برای مدیر سیستم است', html)

    def test_planner_is_always_team_scoped_in_r10(self):
        py = self.source('v7_features.py')
        self.assertIn('Visibility is permission-driven; data scope is team-driven.', py)
        self.assertIn('if not has_company_scope(user):', py)
        self.assertIn('active teams, even when the administrator grants tasks.view_all', py)
        self.assertIn("scope_tm.user_id=? AND scope_tm.is_active=1", py)

    def test_web_core_uses_permission_scoped_endpoint(self):
        js = self.source('v7_ui.js'); py = self.source('v7_features.py')
        self.assertIn("api('/core_data'", js)
        self.assertIn("@require_auth\n    def api_v7_core_data", py)
        self.assertIn("user_has_permission(user, 'tasks.self_manage')", py)
        self.assertIn("user_has_permission(user, 'tasks.work')", py)
        self.assertIn('if not has_company_scope(g.user):', py)

    def test_v7_json_payloads_encode_sql_rowversion_bytes(self):
        py = self.source('v7_features.py')
        self.assertIn('isinstance(obj, (bytes, bytearray, memoryview))', py)
        self.assertGreaterEqual(py.count('jsonify(_jsonable(payload))'), 2)

    def test_closed_contracts_and_financial_dashboard_are_present(self):
        py = self.source('v7_features.py'); js = self.source('v7_ui.js')
        self.assertIn('AS is_closed', py)
        self.assertIn("level = 'closed'", py)
        self.assertIn("@app.route('/api/financial_dashboard'", py)
        self.assertIn('v7-finance-dashboard', js)
        self.assertIn('exp-closed', js)

    def test_finance_menu_and_user_search(self):
        js = self.source('v7_ui.js'); html = self.source('ui.html')
        self.assertIn("section('قرارداد و امور مالی'", js)
        self.assertIn("[16,17,18,19]", js)
        self.assertIn('id="user-search"', html)

    def test_project_type_is_required_and_seeded(self):
        py = self.source('v7_features.py'); js = self.source('v7_ui.js')
        for name in ('CMS', 'CMMS', 'PM', 'نور', 'رها', 'ETL', 'صندوق نصیر'):
            self.assertIn(name, py)
        self.assertIn('FK_Projects_ProjectTypes', py)
        self.assertIn("return _err('انتخاب نوع پروژه الزامی است')", py)
        self.assertIn("project_type_id:ptid", js)

    def test_advanced_sections_always_reopen_closed(self):
        js = self.source('v7_ui.js')
        self.assertIn('id="v71-contract-more"', js)
        self.assertIn('id="v71-task-more"', js)
        self.assertIn('id="v71-statement-more"', js)
        self.assertIn("document.querySelectorAll('.v71-more').forEach(function(x){x.open=false;})", js)
        self.assertNotIn("if(x&&x.open", js)

    def test_drilldown_financial_and_work_reports_exist(self):
        py = self.source('v7_features.py'); js = self.source('v7_ui.js')
        self.assertIn("@app.route('/api/project_financial_report'", py)
        self.assertIn("@app.route('/api/project_work_report'", py)
        self.assertIn('function v71ShowFinancialType', js)
        self.assertIn('function v71ShowFinancialProject', js)
        self.assertIn('function v71ShowFinancialContract', js)
        self.assertIn('project_share_percent', py)

    def test_dashboard_defaults_to_all_time_and_week_label(self):
        js = self.source('v7_ui.js'); html = self.source('ui.html')
        self.assertIn('<option value="all" selected>همه زمان‌ها</option>', js)
        self.assertIn('<option value="week">هفته اخیر</option>', js)
        self.assertNotIn('<option value="week">۷ روز اخیر</option>', html)
        self.assertIn('function v71FilterDashboardTasks', js)
        self.assertIn("if(typeof upDashLists==='function')upDashLists()", js)
        self.assertIn("v71FilterDashboardTasks(D.t)", html)

    def test_sent_and_approved_amounts_are_separate(self):
        py = self.source('v7_features.py')
        self.assertIn("Sent money is always the requested amount without VAT", py)
        self.assertIn("Revenue is\n        always the employer-approved amount without VAT", py)
        self.assertIn("COALESCE(scoped.requested_without_vat,", py)
        self.assertIn("*scoped.scope_percent/100", py)
        self.assertIn("COALESCE(scoped.confirmed_without_vat,", py)

    def test_new_ui_has_no_direct_raw_sql_calls(self):
        self.assertNotIn('dbQ(', self.source('v7_ui.js'))
        self.assertNotIn('dbR(', self.source('v7_ui.js'))

    def test_task_links_have_no_money_column(self):
        schema = self.source('v7_features.py')
        self.assertIn("Tasks','contract_id", schema)
        self.assertIn("Tasks','planned_statement_id", schema)
        self.assertNotIn("Tasks','planned_amount", schema)

    def test_backup_manifest_has_no_connection_configuration(self):
        text = self.source('backup.py')
        start = text.index("manifest = {")
        end = text.index("with zipfile.ZipFile", start)
        block = text[start:end]
        self.assertNotIn('CONN_STR', block)
        self.assertNotIn('DB_PASSWORD', block)

    def test_javascript_parses(self):
        try:
            result = subprocess.run(['node', '--check', str(project_file('v7_ui.js'))],
                                    capture_output=True, text=True)
        except FileNotFoundError:
            self.skipTest('node is not installed')
        self.assertEqual(result.returncode, 0, result.stderr)


class LegacyMigrationTests(unittest.TestCase):
    def test_default_cli_dry_run_is_offline_and_exact(self):
        if not (ROOT / 'migration_data' / 't_Contract Data.xlsx').exists():
            self.skipTest('packaged migration workbooks not present')
        result = subprocess.run([sys.executable, str(project_file('migrate_legacy_v7.py'))],
                                cwd=str(SRC), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['mode'], 'DRY-RUN')
        self.assertEqual(data['contracts_inserted'], 143)
        self.assertEqual(data['extensions_orphan'], 2006)
        self.assertEqual(data['statements_inserted'], 475)
        self.assertEqual(data['quarantine'], 2016)
        self.assertEqual(data.get('extensions_ambiguous', 0), 0)

    def test_supplied_files_reconcile_to_known_counts(self):
        upload = ROOT.parent / 'upload'
        if not upload.exists():
            upload = ROOT / 'migration_data'
        files = [upload / 't_Contract Data.xlsx', upload / 't_ContractExtension Data.xlsx',
                 upload / 't_ContractStatement Data.xlsx']
        if not all(x.exists() for x in files):
            self.skipTest('legacy source workbooks not included')
        sys.modules.setdefault('pyodbc', types.SimpleNamespace())
        original = sys.modules.get('v7_features')
        sys.modules['v7_features'] = types.SimpleNamespace(init_v7_tables=lambda c: None)
        try:
            import importlib
            migration = importlib.import_module('migrate_legacy_v7')
        finally:
            if original is not None:
                sys.modules['v7_features'] = original

        class Cursor:
            def __init__(self): self.last = ''; self.identity = 100
            def execute(self, sql, *params):
                if len(params) == 1 and isinstance(params[0], list): params = tuple(params[0])
                if sql.count('?') != len(params):
                    raise AssertionError('SQL parameter mismatch')
                self.last = sql; return self
            def fetchall(self): return []
            def fetchone(self):
                if 'OUTPUT INSERTED.id' in self.last:
                    self.identity += 1; return (self.identity,)
                return None
        class Connection:
            def __init__(self): self.cur = Cursor()
            def cursor(self): return self.cur
            def commit(self): pass
            def rollback(self): pass

        m = migration.Migrator(Connection(), apply=True); m.load_existing_contracts()
        m.contracts(str(files[0])); m.extensions(str(files[1])); m.statements(str(files[2]))
        stats = m.finish()
        self.assertEqual(stats['contracts_inserted'], 143)
        self.assertEqual(stats['sentinels'], 1)
        self.assertEqual(stats['extensions_inserted'], 40)
        self.assertEqual(stats['extensions_orphan'], 2006)
        self.assertEqual(stats['statements_inserted'], 475)
        self.assertEqual(stats['statements_orphan'], 5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
