# -*- coding: utf-8 -*-
"""R16: groups (گروه) with projects, the group report and the access screen."""
import ast
import pathlib
import unittest

from _paths import ROOT, SRC, project_file  # noqa: E402


def src(name):
    return project_file(name).read_text(encoding="utf-8")


def block(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i + len(start))]


class AccessCatalogTests(unittest.TestCase):
    def test_every_permission_sits_in_exactly_one_section(self):
        from rbac import ALL_PERMISSION_KEYS, GROUP_HINTS, PERMISSION_GROUPS
        placed = [key for _, _, entries in PERMISSION_GROUPS for key, _ in entries]
        self.assertEqual(len(placed), len(set(placed)))
        self.assertEqual(set(placed), set(ALL_PERMISSION_KEYS))
        for key, _, entries in PERMISSION_GROUPS:
            self.assertTrue(entries, key)
            self.assertTrue(GROUP_HINTS.get(key), key)
        self.assertIn('"hint": GROUP_HINTS.get(group_key, "")', src("rbac.py"))

    def test_each_area_keeps_its_menu_with_its_actions(self):
        from rbac import PERMISSION_GROUPS
        where = {key: group for group, _, entries in PERMISSION_GROUPS for key, _ in entries}
        self.assertEqual(where["menu.groups"], "groups")
        self.assertEqual(where["tasks.create_for_group"], "groups")
        self.assertEqual(where["menu.tasks"], "tasks")
        self.assertEqual(where["menu.leave"], "work")
        self.assertEqual(where["leave.approve"], "work")
        self.assertEqual(where["menu.contracts"], "finance")
        self.assertEqual(where["system.sql"], "system")
        self.assertNotIn("menus", set(where.values()))

    def test_admin_tools_cannot_be_delegated(self):
        from rbac import NON_DELEGABLE, ROLES, default_permissions
        for key in ("access_control.manage", "system.sql", "system.data_export",
                    "system.backup", "system.sessions", "system.autostart"):
            self.assertIn(key, NON_DELEGABLE)
            for role, _ in ROLES:
                if role != "admin":
                    self.assertNotIn(key, default_permissions(role), (role, key))
        self.assertIn("for key in sorted(NON_DELEGABLE):", src("rbac.py"))

    def test_split_keys_start_where_the_old_key_was(self):
        mig = block(src("rbac.py"), "r16_holiday_mission_leave_split_v1", "# Keep obsolete catalog rows")
        self.assertIn('("holidays.manage", "schedule.manage")', mig)
        self.assertIn('("missions.manage", "leave.manage")', mig)
        self.assertIn('("leave.approve", "leave.manage")', mig)
        self.assertIn("SET is_allowed=source.is_allowed", mig)

    def test_defaults_for_the_new_keys(self):
        from rbac import default_permissions
        lead = default_permissions("lead")
        for key in ("menu.groups", "groups.view", "menu.team_reports", "reports.groups"):
            self.assertIn(key, lead)
        for key in ("groups.create", "groups.edit", "groups.members_manage"):
            self.assertNotIn(key, lead)
        reporter = default_permissions("reporter")
        for key in ("menu.groups", "groups.view", "reports.groups"):
            self.assertIn(key, reporter)
        self.assertNotIn("groups.create", reporter)
        manager = default_permissions("manager")
        for key in ("groups.create", "groups.members_manage", "groups.projects_manage",
                    "holidays.manage", "missions.manage", "leave.approve", "reports.groups"):
            self.assertIn(key, manager)
        planner = default_permissions("planner")
        self.assertIn("groups.create", planner)
        self.assertIn("holidays.manage", planner)
        self.assertNotIn("leave.approve", planner)
        self.assertNotIn("missions.manage", planner)
        self.assertNotIn("groups.view", default_permissions("support"))

    def test_routes_resolve_to_the_new_permissions(self):
        from rbac import ENDPOINT_PERMISSIONS, permission_for_request
        expected = {
            "api_holiday_save": "holidays.manage", "api_holiday_delete": "holidays.manage",
            "api_mission_save": "missions.manage", "api_mission_delete": "missions.manage",
            "api_leave_review": "leave.approve", "api_v8_groups": "groups.view",
            "api_v8_group_members_save": "groups.members_manage",
            "api_v8_group_projects_save": "groups.projects_manage",
            "api_v8_group_archive": "groups.archive",
        }
        for endpoint, key in expected.items():
            self.assertEqual(ENDPOINT_PERMISSIONS[endpoint], key, endpoint)
        user = {"id": 1, "role": "manager", "permissions": []}
        self.assertEqual(permission_for_request("api_v8_group_save", {}, user), "groups.create")
        self.assertEqual(permission_for_request("api_v8_group_save", {"id": 4}, user), "groups.edit")
        taskhub = src("taskhub.py")
        self.assertIn("user_has_permission(flask_g.user, 'holidays.manage')", taskhub)
        self.assertIn("user_has_permission(actor,'missions.manage')", taskhub)
        self.assertIn("user_has_permission(actor,'leave.approve')", taskhub)
        self.assertIn("permission_key=N'leave.approve'", taskhub)


class RoleGateTests(unittest.TestCase):
    ADMIN_ONLY = {
        "api_role_permissions", "api_role_permissions_save", "api_query", "api_run",
        "api_active_sessions", "api_session_revoke", "api_data_export",
        "api_v7_storage_stats", "api_v7_backups", "api_v7_backup_run",
        "api_v7_backup_verify", "api_v7_backup_download",
    }

    def test_only_admin_tools_keep_a_fixed_role_gate(self):
        gated = set()
        for filename in ("taskhub.py", "v7_features.py", "v8_features.py", "v802_features.py"):
            for node in ast.walk(ast.parse(src(filename))):
                if not isinstance(node, ast.FunctionDef):
                    continue
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and getattr(dec.func, "id", "") == "require_roles":
                        self.assertEqual([getattr(a, "value", None) for a in dec.args], ["admin"], node.name)
                        gated.add(node.name)
        self.assertEqual(gated, self.ADMIN_ONLY)

    def test_released_routes_are_checked_by_permission(self):
        from rbac import ENDPOINT_PERMISSIONS
        for name in ("api_user_reset_pw", "api_user_toggle", "api_user_delete", "api_template_save",
                     "api_audit_log", "api_system_health", "api_analytics", "api_dashboard_stats",
                     "api_task_evaluation_save", "api_import", "api_v7_contract_save",
                     "api_v7_statement_internal_decide", "api_v7_financial_period_lock",
                     "api_v8_contract_teams_save", "api_financial_attribution"):
            self.assertIn(name, ENDPOINT_PERMISSIONS, name)

    def test_team_archive_checks_the_team(self):
        body = block(src("v8_features.py"), "def api_v8_team_archive", "@app.route")
        self.assertIn("can_manage_team(cur, g.user, tid)", body)
        self.assertIn("UPDATE WorkGroups SET is_active=0", body)

    def test_import_keeps_to_the_importers_teams_and_group(self):
        body = block(src("taskhub.py"), "def api_import", "def api_winaction")
        self.assertIn("actor_projects = group_project_ids(cur, actor['id'])", body)
        self.assertIn("if actor_projects and pid not in actor_projects:", body)


class GroupBackendTests(unittest.TestCase):
    def test_tables_and_one_time_migration(self):
        py = src("v8_features.py")
        for marker in ("CREATE TABLE WorkGroups(", "CREATE TABLE WorkGroupMembers(",
                       "CREATE TABLE WorkGroupProjects(", "IX_WorkGroupMembers_user"):
            self.assertIn(marker, py)
        mig = block(py, "IF OBJECT_ID('LeadMembers','U') IS NOT NULL", 'END""")')
        self.assertIn("migration_key='r16_lead_members_to_groups_v1'", mig)
        self.assertIn("WHERE u.role=N'lead' AND u.is_active=1", mig)
        # A member listed under two leads joins one group only.
        self.assertIn("ROW_NUMBER() OVER(PARTITION BY lm.member_id ORDER BY wg.id)", mig)
        self.assertIn("INSERT INTO V8MigrationState(migration_key,detail)", mig)

    def test_every_group_change_checks_the_team(self):
        py = src("v8_features.py")
        for endpoint in ("def api_v8_group_save", "def api_v8_group_members_save",
                         "def api_v8_group_projects_save", "def api_v8_group_archive"):
            self.assertIn("can_manage_team(cur, g.user,", block(py, endpoint, "@app.route"), endpoint)

    def test_people_and_projects_are_validated(self):
        py = src("v8_features.py")
        members = block(py, "def api_v8_group_members_save", "@app.route")
        self.assertIn("u.role IN ('support','lead')", members)
        self.assertIn("other_group_of(cur, uid, gid)", members)
        self.assertIn("wanted = [x for x in wanted if x != lead_id]", members)
        save = block(py, "def api_v8_group_save", "@app.route")
        self.assertIn('lead["role"] != "lead"', save)
        self.assertIn("other_group_of(cur, lead_id, gid)", save)
        projects = block(py, "def api_v8_group_projects_save", "@app.route")
        self.assertIn("FROM ProjectTeams", projects)
        self.assertIn("WHERE team_id=? AND is_active=1", projects)

    def test_context_shares_groups_only_with_those_who_may_see_them(self):
        ctx = block(src("v8_features.py"), "def api_v8_context", "@app.route")
        self.assertIn('if user_has_permission(g.user, "groups.view"):', ctx)


class GroupScopeTests(unittest.TestCase):
    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def execute(self, sql, *params):
            self.sql, self.params = sql, params

        def fetchall(self):
            return self.rows

    def test_group_projects_of_a_lead_or_member(self):
        from team_scope import group_project_ids
        cur = self.Cursor([(7,), (9,)])
        self.assertEqual(group_project_ids(cur, 3), {7, 9})
        self.assertEqual(cur.params, (3, 3))
        self.assertIn("wg.is_active=1", cur.sql)
        self.assertIn("wg.lead_id=?", cur.sql)

    def test_lead_group_reads_named_groups(self):
        from team_scope import lead_group_ids
        cur = self.Cursor([(3,)])
        self.assertEqual(lead_group_ids(cur, 1), {1, 3})
        self.assertIn("FROM WorkGroupMembers gm", cur.sql)

    def test_projects_and_new_tasks_follow_the_group(self):
        v7 = src("v7_features.py")
        core = block(v7, "def api_v7_core_data", "@app.route")
        self.assertIn("group_projects = sorted(group_project_ids(cur, g.user['id']))", core)
        save = block(v7, "def api_v7_task_save", "def api_v7_task_delete")
        self.assertIn("این پروژه جزو پروژه‌های گروه شما نیست", save)
        self.assertIn("not (ident and project_id == _int(old.get('project_id')))", save)
        # The lead's own create and edit paths reach the check as well.
        self.assertLess(save.index("full_task_access = True"), save.index("group_project_ids(cur, u['id'])"))
        taskhub = src("taskhub.py")
        self.assertIn("user['group_project_ids'] = sorted(group_project_ids(cur, row[0]))", taskhub)
        self.assertIn("if row[2] in ('support', 'lead'):", taskhub)


class GroupReportTests(unittest.TestCase):
    def test_report_kind_export_and_scope(self):
        py = src("v8_features.py")
        reports = block(py, "def api_v8_reports", "@app.route")
        self.assertIn('elif kind == "groups":', reports)
        self.assertIn('user_has_permission(g.user, "reports.groups")', reports)
        export = block(py, "def api_v8_report_export", "@app.route")
        self.assertIn('groups_report(cur, g.user, tids, start, end)["rows"]', export)
        fn = block(py, "def groups_report", "@app.route")
        # A lead or member without team rights sees their own group only.
        self.assertIn('mine_only = not (has_company_scope(user) or user_has_permission(user, "teams.view"))', fn)
        for key in ("done_count", "active_count", "overdue_count", "returned_count",
                    "on_time_percent", "work_hours", "in_scope_percent"):
            self.assertIn('"%s"' % key, fn)


class GroupUiTests(unittest.TestCase):
    def test_groups_page_menu_and_report_tab(self):
        js = src("v8_ui.js")
        html = src("ui.html")
        self.assertIn('data-pg="29" data-permission="groups.view"', js)
        self.assertIn("29:'menu.groups'", html)
        self.assertIn("29:'groups.view'", html)
        self.assertIn('<div class="page" id="pg29">', js)
        self.assertIn('id="v8-m-group"', js)
        for fn in ("async function v8LoadGroups", "function v8OpenGroup", "async function v8SaveGroup",
                   "async function v8ArchiveGroup", "function v8RenderGroupsReport",
                   "function v8SyncReportTab", "function v8GroupsHelpHtml"):
            self.assertIn(fn, js)
        self.assertIn('data-permission="reports.groups" data-v8-report="groups"', js)
        self.assertIn("if(n===29)v8LoadGroups();", js)
        self.assertIn("if(n===23)v8OpenReports();", js)

    def test_group_filters_on_tasks_and_reports(self):
        html = src("ui.html")
        self.assertIn('id="fgroup" data-permission="groups.view"', html)
        self.assertIn('id="rgroup"', html)
        self.assertIn("if(fgp&&fgp.indexOf(Number(t.staff_id))<0)return false;", html)
        self.assertIn("function groupPeople(id)", html)
        self.assertIn("groupFilterOptions();", block(html, "function upSelects", "\n}\n"))
        self.assertIn("'fgroup'", block(html, "function clrF", "\n}\n"))

    def test_menu_follows_the_access_screen(self):
        html = src("ui.html")
        nav = block(html, "document.querySelectorAll('.nav-item[data-pg]').forEach(function(el){", "});")
        self.assertNotIn("roleAllowsElement", nav)

    def test_access_screen_shows_section_hints(self):
        self.assertIn("v8-access-hint", src("v8_ui.js"))
        self.assertIn(".v8-access-hint", src("v8_ui.css"))

    def test_permission_renames_reach_the_ui(self):
        html = src("ui.html")
        self.assertIn("var canEditHolidays = can('holidays.manage');", html)
        self.assertIn("if(!CU || !can('leave.approve')) return 0;", html)
        self.assertIn('data-permission="missions.manage" onclick="saveMission()"', html)
        self.assertIn("if(can('leave.approve'))", html)
        self.assertNotIn("can('leave.manage')?'<button", html)


if __name__ == "__main__":
    unittest.main()
