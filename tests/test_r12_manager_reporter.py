# -*- coding: utf-8 -*-
"""R12: the manager runs one team's work and only reads its money; the
reporter reads the whole company and writes nothing.
"""
import pathlib
import re
import unittest

from _paths import ROOT, SRC, project_file  # noqa: E402


def src(name):
    return project_file(name).read_text(encoding="utf-8")


class ManagerScopeTests(unittest.TestCase):
    def setUp(self):
        from rbac import default_permissions
        self.manager = default_permissions("manager")

    def test_manager_data_stays_team_scoped_by_role_not_by_permission(self):
        from team_scope import has_company_scope, requires_team
        # A delegated button must never widen the data scope.
        self.assertFalse(has_company_scope("manager"))
        self.assertTrue(requires_team("manager"))

    def test_manager_reads_financial_records_but_writes_none(self):
        for key in ("contracts.view", "extensions.view", "statements.view",
                    "financial_plan.view", "reports.financial",
                    "dashboard.financial", "archives.view"):
            self.assertIn(key, self.manager, key)
        for key in ("contracts.manage", "contracts.approve", "contracts.archive",
                    "contracts.relink_project",
                    "extensions.manage", "extensions.approve", "extensions.archive",
                    "statements.manage", "statements.internal_approve",
                    "statements.employer_status", "statements.archive",
                    "statements.edit_any_status",
                    "financial_plan.manage", "financial_plan.lock",
                    "archives.restore", "contract_weights.manage"):
            self.assertNotIn(key, self.manager, key)

    def test_manager_runs_the_team_work_end_to_end(self):
        for key in ("tasks.create", "tasks.edit", "tasks.assign", "tasks.work",
                    "tasks.triage", "tasks.approve", "tasks.evaluate",
                    "tasks.comments", "team_financial.manage"):
            self.assertIn(key, self.manager, key)


class TeamScopedFinancialListTests(unittest.TestCase):
    """Contracts and extensions must respect the same rule statements did."""

    def test_contract_list_is_team_scoped(self):
        py = src("v7_features.py")
        route = py[py.index("def api_v7_contracts"):py.index("def api_v7_contract_save")]
        self.assertIn("_team_scope_condition(", route)
        self.assertIn("'contract', 'co'", route)
        # The old code only narrowed when a team was explicitly requested,
        # which left every contract visible to every manager.
        self.assertNotIn("Manager/planner have company-wide contract visibility", route)

    def test_extension_list_is_team_scoped_through_its_contract(self):
        py = src("v7_features.py")
        route = py[py.index("def api_v7_extensions"):py.index("def api_v7_extension_save")]
        self.assertIn("_team_scope_condition(", route)
        self.assertIn("'extension', 'e'", route)
        self.assertNotIn("Manager/planner are not implicitly limited", route)

    def test_extension_scope_reuses_the_contract_team_link(self):
        py = src("v7_features.py")
        helper = py[py.index("def _team_scope_condition"):py.index("def _statement_scope_share")]
        self.assertIn("elif entity_kind == 'extension':", helper)
        self.assertIn("scope_cpt.contract_id=%s.contract_id", helper)

    def test_company_roles_still_see_everything(self):
        py = src("v7_features.py")
        helper = py[py.index("def _team_scope_condition"):py.index("def _statement_scope_share")]
        # The narrowing join is only added for non company-scope readers.
        self.assertIn("if not has_company_scope(user):", helper)


class ReporterReadOnlyTests(unittest.TestCase):
    def setUp(self):
        from rbac import default_permissions
        self.reporter = default_permissions("reporter")

    def test_reporter_has_no_team_restriction(self):
        from team_scope import has_company_scope, requires_team
        self.assertTrue(has_company_scope("reporter"))
        self.assertFalse(requires_team("reporter"))

    def test_reporter_can_see_every_reporting_surface(self):
        for key in ("menu.dashboard", "menu.tasks", "menu.kanban", "menu.projects",
                    "menu.teams", "menu.team_reports", "menu.contracts",
                    "menu.extensions", "menu.statements", "menu.financial_plan",
                    "menu.project_income", "menu.work_share", "menu.reports",
                    "menu.schedule", "menu.leave",
                    "teams.view", "tasks.view", "tasks.view_all", "projects.view",
                    "contracts.view", "extensions.view", "statements.view",
                    "financial_plan.view", "archives.view",
                    "schedule.view", "leave.view", "attendance.view",
                    "reports.view", "reports.financial", "reports.capacity",
                    "reports.export", "tasks.export",
                    "dashboard.financial", "dashboard.organization_summary",
                    "dashboard.organization_analytics"):
            self.assertIn(key, self.reporter, key)

    def test_reporter_changes_no_operational_record(self):
        # The only writes a reporter keeps are its own account, its own leave
        # request, the phonebook numbers granted in R11, and the messenger.
        allowed_writes = {
            "account.edit_identity", "account.change_password",
            "phonebook.edit", "leave.request",
            "chat.use", "chat.file_upload", "chat.file_download",
            "chat.manage_groups",
        }
        forbidden = re.compile(
            r"\.(create|edit|delete|manage|approve|archive|restore|assign|triage"
            r"|work|import|evaluate|lock|toggle|reset_password|self_manage"
            r"|relink_project|employer_status|internal_approve|templates)$"
        )
        offenders = sorted(k for k in self.reporter
                           if forbidden.search(k) and k not in allowed_writes)
        self.assertEqual(offenders, [])

    def test_reporter_never_sees_project_credentials(self):
        # Reporting does not require VPN or login details.
        self.assertNotIn("project_notes.view", self.reporter)
        self.assertNotIn("project_notes.manage", self.reporter)

    def test_role_changes_are_applied_once(self):
        rbac = src("rbac.py")
        self.assertIn("r12_manager_team_finance_reporter_readonly_v1", rbac)
        block = rbac[rbac.index("r12_roles = "):rbac.index("# Keep obsolete catalog rows")]
        self.assertIn("SELECT 1 FROM RbacMigrations WHERE migration_key=?", block)
        self.assertIn("role=N'manager'", block)
        self.assertIn("role=N'reporter'", block)


class HelpPerRoleTests(unittest.TestCase):
    def test_help_has_a_card_for_every_role(self):
        html = src("ui.html")
        self.assertIn("function _helpRoleScopeCard", html)
        card = html[html.index("function _helpRoleScopeCard"):]
        card = card[:card.index("function _helpTaskEntryCard")]
        from rbac import ROLES
        for role, _ in ROLES:
            self.assertIn(role + ":", card, role)

    def test_help_states_each_boundary_that_users_cannot_see_in_the_ui(self):
        html = src("ui.html")
        card = html[html.index("function _helpRoleScopeCard"):]
        card = card[:card.index("function _helpTaskEntryCard")]
        # Manager: reads team money, does not write it.
        self.assertIn("فقط می‌بینید", card)
        self.assertIn("کارشناس مالی است", card)
        # Planner: no money, no leave approval.
        self.assertIn("امور مالی برای شما بسته است", card)
        # Reporter: everything, read only.
        self.assertIn("هیچ محدودیت تیمی ندارید", card)
        self.assertIn("فقط خواندنی است", card)

    def test_help_covers_the_new_features_it_should_explain(self):
        html = src("ui.html")
        self.assertIn("بایگانی‌ها", html)
        self.assertIn("اهداف مالی شرکت و تیم‌ها", html)
        self.assertIn("ویرایش صورت‌وضعیت تأییدشده", html)
        self.assertIn("شمارنده کنار منوی پیامرسان", html)

    def test_help_is_still_permission_driven(self):
        html = src("ui.html")
        render = html[html.index("function renderHelp()"):]
        render = render[:render.index("function _helpRoleScopeCard")]
        for key in ("financial_plan.view", "archives.view", "statements.edit_any_status"):
            self.assertIn("can('%s')" % key, render, key)


if __name__ == "__main__":
    unittest.main()
