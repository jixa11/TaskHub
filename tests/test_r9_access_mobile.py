# -*- coding: utf-8 -*-
from pathlib import Path
import unittest
import ast
import re
import subprocess
import tempfile

from _paths import ROOT, SRC, project_file  # noqa: E402

def src(name):
    return project_file(name).read_text(encoding="utf-8")

class R9DashboardRegressionTests(unittest.TestCase):
    def test_legacy_employer_decision_counts_in_financial_progress(self):
        py = src("v7_features.py")
        tree = ast.parse(py)
        fn_node = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_statement_is_employer_approved"
        )
        import decimal
        namespace = {"_decimal": decimal}
        exec(compile(ast.Module(body=[fn_node], type_ignores=[]), "<approval-helper>", "exec"), namespace)
        approved = namespace["_statement_is_employer_approved"]
        self.assertTrue(approved({
            "business_status": "sent", "employer_decision_at": "2026-07-01",
            "confirmed_without_vat": 5171250000,
        }))
        self.assertTrue(approved({
            "business_status": "employer_approved", "employer_decision_at": None
        }))
        self.assertFalse(approved({
            "business_status": "sent", "employer_decision_at": None,
            "confirmed_price": 5171250000
        }))
        self.assertFalse(approved({
            "business_status": "employer_rejected",
            "employer_decision_at": "2026-07-01",
            "confirmed_price": 5171250000,
        }))
        self.assertGreaterEqual(py.count("_statement_is_employer_approved("), 3)

    def test_dashboard_has_granular_permissions(self):
        rbac = src("rbac.py")
        ui = src("ui.html")
        for key in (
            "dashboard.personal_tasks", "dashboard.personal_calendar",
            "dashboard.personal_schedule", "dashboard.personal_rank",
            "dashboard.team_presence", "dashboard.team_schedule",
            "dashboard.team_ranking", "dashboard.organization_summary",
            "dashboard.organization_analytics", "dashboard.financial",
        ):
            self.assertIn(key, rbac)
            self.assertIn(key, ui if key != "dashboard.financial" else ui + src("v7_ui.js"))
        support_block = rbac[rbac.index('"support": {'):rbac.index('"supervisor": {')]
        self.assertIn('"dashboard.personal_tasks"', support_block)
        # Granularity still holds: support gets its own cards, not the
        # organisation-wide analytics.
        self.assertNotIn('"dashboard.organization_analytics"', support_block)
        self.assertNotIn('"dashboard.organization_summary"', support_block)
        # The company goal card is deliberately company-wide from R12 on; it is
        # one read-only tile and is separate from reports.financial.
        self.assertIn('"dashboard.financial"', support_block)

    def test_personal_ranking_does_not_return_team_rows(self):
        py = src("taskhub.py")
        self.assertIn("self_only = d.get('scope') == 'self'", py)
        self.assertIn("ranking = [row]", py)
        self.assertIn("ranking_total", py)
        self.assertIn("scope:'self'", src("ui.html"))


    def test_explicit_permission_is_authoritative_over_legacy_role_markup(self):
        html = src("ui.html")
        self.assertIn("function roleAllowsElement", html)
        self.assertIn("function permissionAllowsElement", html)
        self.assertIn('data-detail-permission="dashboard.organization_analytics"', html)
        self.assertIn("var allowed=explicit?true:roleAllowsElement(el)", html)
        self.assertIn("function pageAllowed(page)", html)

    def test_inline_ui_javascript_parses(self):
        html = src("ui.html")
        inline_scripts = re.findall(
            r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        self.assertTrue(inline_scripts)
        try:
            for script in inline_scripts:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".js", encoding="utf-8", delete=False
                ) as tmp:
                    tmp.write(script)
                    tmp_path = tmp.name
                result = subprocess.run(
                    ["node", "--check", tmp_path],
                    capture_output=True, text=True,
                )
                Path(tmp_path).unlink(missing_ok=True)
                self.assertEqual(result.returncode, 0, result.stderr)
        except FileNotFoundError:
            self.skipTest("node is unavailable")

    def test_project_notes_require_permission_and_project_team_scope(self):
        py = src("taskhub.py")
        self.assertIn("def _team_project_access", py)
        self.assertIn("permission = 'project_notes.manage' if manage else 'project_notes.view'", py)
        self.assertIn("return _team_project_access(cur, actor, project_id, manage=manage)", py)
        self.assertNotIn("PROJECT_NOTES_ACTIVE_TASK_STATUSES", py)
        self.assertNotIn("def _assigned_project_task_access", py)

    def test_project_notes_ui_respects_view_and_manage_permissions(self):
        html = src("ui.html")
        self.assertIn("if(t.project_id && can('project_notes.view'))", html)
        self.assertIn("can('project_notes.manage') ? '<button", html)

    def test_mobile_rules_cover_dashboard_and_access_matrix(self):
        html = src("ui.html")
        css = src("v8_ui.css")
        self.assertIn(".dashboard-personal-grid", html)
        self.assertIn(".chart-bar-row{display:grid", html)
        self.assertIn(".v8-access-group-grid", css)

if __name__ == '__main__':
    unittest.main(verbosity=2)
