# -*- coding: utf-8 -*-
"""R12: the planner scope, and the rebuilt access-management screen."""
import pathlib
import subprocess
import unittest

from _paths import ROOT, SRC, project_file  # noqa: E402


def src(name):
    return project_file(name).read_text(encoding="utf-8")


class PlannerScopeTests(unittest.TestCase):
    def setUp(self):
        from rbac import default_permissions
        self.planner = default_permissions("planner")
        self.manager = default_permissions("manager")

    def test_planner_matches_the_manager_outside_the_carve_outs(self):
        from rbac import _PLANNER_EXCLUDED
        # R13: the planner holds a wallet (monthly stars, shop) and the manager,
        # who runs the shop, does not; those two keys are the only other gap.
        wallet = {"gamification.view_own", "shop.buy"}
        self.assertEqual(self.planner, (self.manager - set(_PLANNER_EXCLUDED)) | wallet)

    def test_planner_has_no_financial_access_at_all(self):
        for key in ("menu.contracts", "menu.extensions", "menu.statements",
                    "menu.financial_plan", "menu.project_income", "menu.team_plan",
                    "contracts.view", "extensions.view", "statements.view",
                    "financial_plan.view", "financial_plan.manage",
                    "team_financial.manage", "contract_weights.manage",
                    "archives.view", "archives.restore",
                    "reports.financial"):
            self.assertNotIn(key, self.planner, key)
        # The single dashboard goal card is the documented exception: everyone
        # sees how the company is tracking, nobody but finance opens the
        # detailed money screens behind reports.financial.
        self.assertIn("dashboard.financial", self.planner)

    def test_planner_keeps_contract_linking_because_it_exposes_no_amounts(self):
        self.assertIn("tasks.link_contract", self.planner)
        # The endpoint behind the task-contract selector is guarded by that
        # permission alone, so the planner does not need contracts.view.
        self.assertIn('"api_v7_task_contract_options": "tasks.link_contract"', src("rbac.py"))

    def test_planner_sees_leave_but_does_not_approve_it(self):
        self.assertIn("menu.leave", self.planner)
        self.assertIn("leave.view", self.planner)
        self.assertIn("leave.request", self.planner)
        self.assertNotIn("leave.manage", self.planner)

    def test_planner_keeps_everything_else_a_manager_can_do(self):
        for key in ("menu.tasks", "menu.kanban", "menu.projects", "menu.teams",
                    "menu.users", "menu.reports", "menu.schedule",
                    "tasks.create", "tasks.edit", "tasks.assign", "tasks.approve",
                    "projects.create", "teams.create", "users.create",
                    "schedule.manage", "attendance.manage", "reports.view",
                    "reports.capacity", "reports.export", "chat.use"):
            self.assertIn(key, self.planner, key)

    def test_planner_change_is_applied_once_on_upgrade(self):
        rbac = src("rbac.py")
        self.assertIn("r12_planner_scope_v1", rbac)
        block = rbac[rbac.index("r12_planner = "):rbac.index("# Keep obsolete catalog rows")]
        self.assertIn("SELECT 1 FROM RbacMigrations WHERE migration_key=?", block)
        self.assertIn("is_allowed=0", block)
        self.assertIn("is_allowed=1", block)


class AccessScreenTests(unittest.TestCase):
    def test_screen_offers_search_filters_and_bulk_tools(self):
        js = src("v8_ui.js")
        self.assertIn("v8-access-search", js)
        for mode in ("all", "on", "off", "changed", "custom"):
            self.assertIn('data-access-filter="%s"' % mode, js)
        self.assertIn("function v8AccessCopyFrom", js)
        self.assertIn("function v8AccessResetDefault", js)

    def test_unsaved_edits_are_tracked_and_cannot_be_lost_silently(self):
        js = src("v8_ui.js")
        self.assertIn("function v8AccessChangedKeys", js)
        self.assertIn("function v8AccessRevert", js)
        # Switching role and leaving the page both confirm first.
        select = js[js.index("function v8AccessSelectRole"):js.index("function v8AccessSetFilter")]
        self.assertIn("confirm(", select)
        page = js[js.index("showPage=function(n){"):]
        page = page[:page.index("var basePrep=prepM;")]
        self.assertIn("#pg26.page.active", page)
        self.assertIn("v8AccessChangedKeys()", page)

    def test_state_is_a_draft_not_scraped_from_the_dom(self):
        js = src("v8_ui.js")
        save = js[js.index("async function v8AccessSave"):]
        save = save[:save.index("\nfunction v8InstallOverrides")] if "\nfunction v8InstallOverrides" in save else save[:2000]
        # The old screen read the answer back out of checked checkboxes, which
        # is what made search and filtering impossible to add safely.
        self.assertNotIn("querySelectorAll('#v8-access-groups .v8-access-check:checked')", save)
        self.assertIn("Array.from(V8Access.draft)", save)

    def test_destructive_bulk_actions_require_confirmation(self):
        js = src("v8_ui.js")
        for fn in ("v8AccessSelectAll", "v8AccessResetDefault", "v8AccessCopyFrom"):
            body = js[js.index("function %s(" % fn):]
            body = body[:body.index("\nfunction ")]
            self.assertIn("confirm(", body, fn)

    def test_non_delegable_permission_is_shown_locked_not_hidden(self):
        js = src("v8_ui.js")
        self.assertIn("v8AccessLocked", js)
        self.assertIn("فقط مدیر سیستم", js)
        self.assertIn("function v8AccessToggle(", js)
        toggle = js[js.index("function v8AccessToggle("):]
        toggle = toggle[:toggle.index("\nfunction ")]
        self.assertIn("v8AccessLocked(key)", toggle)

    def test_server_supplies_defaults_for_the_reset_action(self):
        taskhub = src("taskhub.py")
        self.assertIn("default_permissions", taskhub)
        self.assertIn("'defaults': defaults", taskhub)

    def test_r11_sensitive_shortcut_and_layer_guidance_survive(self):
        js = src("v8_ui.js")
        self.assertIn("v8-sensitive-access-card", js)
        self.assertIn("v8-sensitive-view", js)
        self.assertIn("v8-sensitive-manage", js)
        self.assertIn("هر عملیات به سه لایه مستقل نیاز دارد", js)
        self.assertIn('data-permission="access_control.manage"', js)

    def test_layout_is_responsive(self):
        css = src("v8_ui.css")
        self.assertIn(".v8-access-shell", css)
        self.assertIn(".v8-access-group-grid", css)
        self.assertIn("@media(max-width:900px)", css)


class AccessMatrixBehaviourTests(unittest.TestCase):
    """Executes the extracted draft/dirty/bulk functions under node."""

    def test_matrix_state_functions_behave(self):
        script = ROOT / "tests" / "access_matrix_check.js"
        try:
            result = subprocess.run(["node", str(script)], capture_output=True,
                                    text=True, cwd=str(SRC),
                                    encoding="utf-8", errors="replace")
        except FileNotFoundError:
            self.skipTest("node is unavailable")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
