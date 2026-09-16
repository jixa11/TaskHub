# -*- coding: utf-8 -*-
from pathlib import Path
import re
import unittest

from _paths import ROOT, SRC, project_file  # noqa: E402


def src(name):
    return project_file(name).read_text(encoding="utf-8")


class R9PermissionGranularityTests(unittest.TestCase):
    def test_contract_archive_is_grantable_without_contract_manage(self):
        from rbac import default_permissions, permission_for_request, user_has_permission

        defaults = default_permissions("finance")
        self.assertIn("menu.contracts", defaults)
        self.assertIn("contracts.view", defaults)
        # R12: the finance specialist owns the financial records outright, so
        # archiving is now on by default for that role.
        self.assertIn("contracts.archive", defaults)
        # The granularity itself still holds: a role that is not meant to
        # archive does not receive it, and the permission remains independent
        # of contracts.manage.
        self.assertNotIn("contracts.archive", default_permissions("reporter"))

        configured = {
            "role": "reporter",
            "permissions": ["menu.contracts", "contracts.view", "contracts.archive"],
        }
        self.assertTrue(user_has_permission(configured, "contracts.archive"))
        self.assertFalse(user_has_permission(configured, "contracts.manage"))
        self.assertEqual(
            permission_for_request("api_v7_contract_archive", {}, configured),
            "contracts.archive",
        )

    def test_archive_and_approval_operations_have_independent_permissions(self):
        rbac = src("rbac.py")
        expected = {
            "api_v7_contract_archive": "contracts.archive",
            "api_v7_extension_decide": "extensions.approve",
            "api_v7_extension_archive": "extensions.archive",
            "api_v7_statement_internal_decide": "statements.internal_approve",
            "api_v7_statement_archive": "statements.archive",
            "api_v7_attachment_update": "attachments.edit",
            "api_v7_attachment_archive": "attachments.archive",
            "api_v8_team_archive": "teams.archive",
            "api_v8_project_team_archive": "teams.archive",
        }
        for endpoint, permission in expected.items():
            self.assertIn(f'"{endpoint}": "{permission}"', rbac)

    def test_contract_archive_ui_is_not_coupled_to_edit_permission(self):
        js = src("v7_ui.js")
        self.assertIn("if(can('contracts.archive'))actions+=", js)
        self.assertIn("async function v7ArchiveContract(id){if(!can('contracts.archive'))", js)
        archive_function = js[js.index("async function v7ArchiveContract"):]
        archive_function = archive_function[:archive_function.index("async function", 20)]
        self.assertNotIn("contracts.manage", archive_function)

    def test_child_finance_actions_use_exact_permissions(self):
        js = src("v7_ui.js")
        for token in (
            "v7CanApproveExtension(){return CU&&can('extensions.approve')",
            "v7CanApproveStatement(){return CU&&can('statements.internal_approve')",
            "if(can('extensions.archive'))actions+=",
            "if(can('statements.archive'))actions+=",
            "can('attachments.edit')",
            "can('attachments.archive')",
        ):
            self.assertIn(token, js)

    def test_backend_archive_has_no_hidden_approval_dependency(self):
        py = src("v7_features.py")
        start = py.index("def _archive_entity")
        end = py.index("@app.route('/api/financial_plan'", start)
        block = py[start:end]
        self.assertNotIn("extensions.approve", block)
        self.assertNotIn("statements.internal_approve", block)
        self.assertIn("UPDATE %s SET is_active=0", block)

    def test_attachment_backend_uses_exact_operation_permission(self):
        py = src("v7_features.py")
        self.assertIn("_can_access_entity(cur,row['entity_type'],row['entity_id'],'attachments.edit')", py)
        self.assertIn("_can_access_entity(cur,row['entity_type'],row['entity_id'],'attachments.archive')", py)
        self.assertIn("_can_access_entity(cur,et,eid,'attachments.upload')", py)
        self.assertIn("_can_access_entity(cur,et,eid,'attachments.view')", py)

    def test_project_team_archive_is_not_coupled_to_team_manage(self):
        py = src("v8_features.py")
        start = py.index("def api_v8_project_team_archive")
        end = py.index("@app.route", start)
        block = py[start:end]
        self.assertNotIn("can_manage_team", block)
        self.assertNotIn("teams.manage", block)

    def test_menu_and_page_detail_are_both_required(self):
        html = src("ui.html")
        self.assertIn("const PAGE_DETAIL_PERMISSION_MAP=", html)
        self.assertIn("function pageAllowed(page)", html)
        self.assertIn("return (!menu||can(menu))&&(!detail||can(detail))", html)
        self.assertIn("if(CU&&!pageAllowed(n))", html)

    def test_explicit_permission_is_not_blocked_by_legacy_role_markup(self):
        html = src("ui.html")
        self.assertIn("var explicit=el.hasAttribute('data-permission')", html)
        self.assertIn("var allowed=explicit?true:roleAllowsElement(el)", html)

    def test_task_comments_are_hidden_and_blocked_without_permission(self):
        html = src("ui.html")
        self.assertIn("if(!can('tasks.comments'))return;", html)
        self.assertIn("if(can('tasks.comments')){", html)
        self.assertIn('"api_task_comments": "tasks.comments"', src("rbac.py"))
        self.assertIn('"api_task_comment_add": "tasks.comments"', src("rbac.py"))

    def test_every_report_subsection_has_its_own_permission(self):
        # R12 split the umbrella keys so an administrator can grant one report
        # without granting its neighbours. Each tab now carries its own key and
        # the server checks the same key behind it.
        ui = src("v8_ui.js")
        backend = src("v8_features.py")
        rbac_src = src("rbac.py")
        for key in ("reports.team_dashboard", "reports.contribution",
                    "reports.capacity", "reports.shared_projects",
                    "reports.data_quality", "reports.financial_attribution"):
            self.assertIn('data-permission="%s"' % key, ui, key)
            # Enforced either inside the report branch or through the
            # endpoint->permission map; both are server-side.
            enforced = ('if not user_has_permission(g.user, "%s")' % key in backend
                        or '": "%s",' % key in rbac_src)
            self.assertTrue(enforced, key)
        # No report tab may be left without a switch.
        tabs = re.findall(r'<button[^>]*data-v8-report="[^"]*"[^>]*>', ui)
        self.assertTrue(tabs)
        for tab in tabs:
            self.assertIn("data-permission=", tab, tab)

    def test_access_screen_explains_three_independent_layers(self):
        ui = src("v8_ui.js")
        self.assertIn("هر عملیات به سه لایه مستقل نیاز دارد", ui)
        self.assertIn("بایگانی قرارداد", ui)
        self.assertIn("نیازی به مجوز ثبت و ویرایش قرارداد ندارد", ui)

    def test_every_referenced_permission_exists_in_catalog(self):
        from rbac import ALL_PERMISSION_KEYS, ENDPOINT_PERMISSIONS

        refs = set(ENDPOINT_PERMISSIONS.values())
        patterns = (
            r"can\(['\"]([^'\"]+)['\"]\)",
            r"user_has_permission\([^,]+,\s*['\"]([^'\"]+)['\"]\)",
            r"data-permission=['\"]([^'\"]+)['\"]",
            r"data-detail-permission=['\"]([^'\"]+)['\"]",
        )
        for filename in (
            "ui.html", "v7_ui.js", "v8_ui.js", "taskhub.py",
            "v7_features.py", "v8_features.py", "v802_features.py",
        ):
            text = src(filename)
            for pattern in patterns:
                refs.update(re.findall(pattern, text))
        self.assertEqual(sorted(refs - set(ALL_PERMISSION_KEYS)), [])

    def test_financial_progress_legacy_approval_predicate_remains_protected(self):
        for filename in ("v7_features.py", "v8_features.py", "v802_features.py"):
            text = src(filename)
            self.assertIn("employer_decision_at IS NOT NULL", text)
            self.assertIn("COALESCE(", text)
            self.assertIn("'employer_rejected','revised','void'", text)
        js = src("v7_ui.js")
        self.assertIn("approvedPct=target?Math.round(approved/target*100):0", js)

    def test_version_remains_r9(self):
        self.assertIn("v 1.0.0", src("v8_ui.js"))
        self.assertIn("APP_VERSION = '1.0.0'", src("config.py"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
