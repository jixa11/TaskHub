# -*- coding: utf-8 -*-
"""Third round of on-site findings for R12."""
import pathlib
import re
import unittest

from _paths import ROOT, SRC, project_file  # noqa: E402


def src(name):
    return project_file(name).read_text(encoding="utf-8")


class DropdownReadabilityTests(unittest.TestCase):
    def test_popup_is_never_narrower_than_its_content_needs(self):
        html = src("ui.html")
        rule = re.search(r"\.sel-pop\{[^}]*\}", html).group(0)
        self.assertIn("min-width:260px", rule)
        # Matching the trigger exactly is what cut Persian labels to fragments.
        self.assertIn("var w=Math.min(Math.max(r.width,260)", html)

    def test_long_labels_wrap_instead_of_being_cut(self):
        html = src("ui.html")
        rule = re.search(r"\.sel-opt\{[^}]*\}", html).group(0)
        self.assertIn("white-space:normal", rule)
        self.assertNotIn("text-overflow:ellipsis", rule)
        self.assertIn("font-family", rule)


class AccessPanelTests(unittest.TestCase):
    def test_only_one_role_selector_remains(self):
        js = src("v8_ui.js")
        self.assertNotIn("v8-access-role-mobile", js)
        self.assertNotIn('id="v8-access-role"', js)
        self.assertIn('id="v8-access-roles"', js)

    def test_no_dead_reference_to_the_removed_control(self):
        js = src("v8_ui.js")
        self.assertNotIn("g('v8-access-role')", js)


class TaskFilterScopeTests(unittest.TestCase):
    def test_city_and_project_filters_are_hidden_from_personal_lists(self):
        html = src("ui.html")
        for ident in ("fcity", "fptype", "fproj", "fstaff"):
            tag = re.search(r'<select[^>]*id="%s"[^>]*>' % ident, html).group(0)
            self.assertIn("data-role=", tag, ident)
            self.assertNotIn("supervisor", tag, ident)
            self.assertNotIn("employer", tag, ident)


class GranularReportPermissionTests(unittest.TestCase):
    def test_each_report_has_its_own_key(self):
        from rbac import ALL_PERMISSION_KEYS
        for key in ("reports.team_dashboard", "reports.contribution",
                    "reports.shared_projects", "reports.data_quality",
                    "reports.financial_attribution", "reports.project_income",
                    "reports.work_share"):
            self.assertIn(key, ALL_PERMISSION_KEYS, key)

    def test_each_dashboard_chart_has_its_own_key(self):
        from rbac import ALL_PERMISSION_KEYS
        js = src("v7_ui.js")
        for key in ("dashboard.chart_status", "dashboard.chart_city",
                    "dashboard.chart_staff", "dashboard.chart_trend"):
            self.assertIn(key, ALL_PERMISSION_KEYS, key)
            self.assertIn('data-permission="%s"' % key, js, key)

    def test_no_report_tab_or_export_is_left_unswitchable(self):
        v8 = src("v8_ui.js")
        v7 = src("v7_ui.js")
        for tab in re.findall(r'<button[^>]*data-v8-report="[^"]*"[^>]*>', v8):
            self.assertIn("data-permission=", tab, tab)
        for btn in re.findall(r'<button[^>]*v71ExportReport\([^)]*\)[^>]*>', v7):
            self.assertIn("data-permission=", btn, btn)

    def test_server_enforces_the_new_report_keys(self):
        backend = src("v8_features.py")
        for key in ("reports.team_dashboard", "reports.contribution",
                    "reports.shared_projects", "reports.data_quality"):
            self.assertIn('user_has_permission(g.user, "%s")' % key, backend, key)
        self.assertIn('"api_financial_attribution": "reports.financial_attribution"', src("rbac.py"))

    def test_upgrade_hands_the_fine_keys_to_whoever_had_the_coarse_one(self):
        rbac = src("rbac.py")
        self.assertIn("r12_per_report_permissions_v1", rbac)
        block = rbac[rbac.index("r12_fine_reports = "):rbac.index("# Keep obsolete catalog rows")]
        # Inheriting from the umbrella key is what stops the upgrade from
        # silently removing reports a role already had.
        self.assertIn("JOIN RolePermissions source ON source.role=target.role", block)


class EmployerFinancialTests(unittest.TestCase):
    def test_employer_does_not_see_the_company_goal_card(self):
        from rbac import default_permissions
        employer = default_permissions("employer")
        self.assertNotIn("dashboard.financial", employer)
        for key in ("reports.financial", "reports.project_income",
                    "reports.work_share", "reports.team_dashboard"):
            self.assertNotIn(key, employer, key)

    def test_staff_roles_keep_the_goal_card(self):
        from rbac import default_permissions
        for role in ("manager", "planner", "support", "supervisor",
                     "finance", "reporter"):
            self.assertIn("dashboard.financial", default_permissions(role), role)

    def test_upgrade_excludes_only_the_employer(self):
        rbac = src("rbac.py")
        block = rbac[rbac.index("r12_goal_card = "):rbac.index("r12_contact_roles = ")]
        self.assertIn("0 if role == 'employer' else 1", block)


if __name__ == "__main__":
    unittest.main()
