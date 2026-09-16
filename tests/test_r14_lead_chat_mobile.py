# -*- coding: utf-8 -*-
"""R14: the group lead role, the client chat rule and the mobile chat list."""
import pathlib
import unittest

from _paths import ROOT, SRC, project_file  # noqa: E402


def src(name):
    return project_file(name).read_text(encoding="utf-8")


class LeadRoleTests(unittest.TestCase):
    def test_lead_is_support_plus_group_task_creation(self):
        from rbac import ROLES, default_permissions
        self.assertIn(("lead", "سرگروه"), ROLES)
        from rbac import LEAD_GROUP_KEYS, LEAD_REPORT_KEYS
        # R16 adds the groups page and the group report to the lead.
        self.assertEqual(default_permissions("lead"),
                         default_permissions("support") | set(LEAD_GROUP_KEYS) | set(LEAD_REPORT_KEYS))
        # Managers and planners work team-wide, so the sub-group keys stay off.
        for role in ("support", "supervisor", "employer", "finance", "reporter", "manager", "planner"):
            for key in LEAD_GROUP_KEYS:
                self.assertNotIn(key, default_permissions(role), (role, key))

    def test_task_save_resolves_to_the_group_permission_for_a_lead(self):
        from rbac import default_permissions, permission_for_request
        lead = {"id": 5, "role": "lead", "permissions": sorted(default_permissions("lead"))}
        support = {"id": 6, "role": "support", "permissions": sorted(default_permissions("support"))}
        self.assertEqual(permission_for_request("api_v7_task_save", {}, lead), "tasks.create_for_group")
        self.assertEqual(permission_for_request("api_v7_task_save", {}, support), "tasks.create")
        # R15: editing an existing task resolves to the lead's group permission.
        self.assertEqual(permission_for_request("api_v7_task_save", {"id": 9}, lead), "tasks.edit_group")
        self.assertEqual(permission_for_request("api_v7_task_save", {"id": 9}, support), "tasks.work")

    def test_lead_needs_a_team_and_earns_like_support(self):
        import gamification_domain as gd
        from team_scope import requires_team
        self.assertTrue(requires_team("lead"))
        self.assertIn("lead", gd.WALLET_ROLES)
        self.assertIn("lead", gd.TASK_EARNING_ROLES)

    def test_server_limits_a_lead_to_themselves_and_their_sub_group(self):
        py = src("v7_features.py")
        block = py[py.index("user_has_permission(u, 'tasks.create_for_group')"):]
        block = block[:block.index("if not full_task_access and user_has_permission(u, 'tasks.self_manage')")]
        self.assertIn("lead_group_ids(cur, u['id'])", block)
        self.assertIn("staff_id not in allowed_staff", block)
        self.assertIn("d['status'] = 'assigned'", block)
        self.assertIn("d['progress_weight'] = 1", block)
        self.assertIn("d['contract_id'] = None", block)

    def test_sub_groups_moved_to_named_groups(self):
        py = src("taskhub.py")
        # R16: the table stays so the one-time migration can read an old database.
        self.assertIn("CREATE TABLE LeadMembers(", py)
        save = py[py.index("def api_user_save"):py.index("def _can_manage_target_user")]
        self.assertIn("'lead'", save[:save.index("if role not in allowed_roles")])
        self.assertNotIn("group_member_ids", save)
        # A role change releases only what the new role cannot hold.
        self.assertIn("UPDATE WorkGroups SET lead_id=NULL,updated_at=GETDATE() WHERE lead_id=?", save)
        self.assertIn("DELETE FROM WorkGroupMembers WHERE user_id=?", save)
        delete = py[py.index("def api_user_delete"):]
        delete = delete[:delete.index("DELETE FROM Users WHERE id=?")]
        self.assertIn("DELETE FROM WorkGroupMembers WHERE user_id=?", delete)
        self.assertIn("user['group_member_ids']", py)

    def test_ui_offers_the_role_and_the_task_button(self):
        html = src("ui.html")
        self.assertIn('<option value="lead">🧭 سرگروه</option>', html)
        # R16: the group is set on the groups page, not on the user form.
        self.assertIn('id="vulead-hint"', html)
        self.assertNotIn("function userGroupOptions", html)
        self.assertNotIn("group_member_ids: role==='lead'", html)
        self.assertIn("mt:'tasks.create,tasks.create_for_group'", html)
        self.assertIn("function leadTaskStaffIds", html)
        form = html[html.index("function applyTaskFormRole"):]
        form = form[:form.index("\n}\n")]
        self.assertIn("leadRestrictStaff()", form)
        self.assertIn("leadRestrictStaff", src("v8_ui.js"))
        for name in ("ui.html", "v7_ui.js", "v8_ui.js", "game_ui.js"):
            self.assertIn("lead:'سرگروه'", src(name), name)

    def test_help_explains_the_lead_role(self):
        html = src("ui.html")
        card = html[html.index("function _helpRoleScopeCard"):html.index("function _helpTaskEntryCard")]
        self.assertIn("lead:'<p>شما سرگروه هستید", card)


class ClientChatRuleTests(unittest.TestCase):
    def setUp(self):
        from team_scope import chat_pair_allowed
        self.allowed = chat_pair_allowed
        # Employer 10 and supervisor 11 share a project planned by 20;
        # employer 12 belongs to another client, planned by 21.
        self.contacts = {10: {11, 20}, 11: {10, 20}, 12: {21}}
        self.of = lambda uid: self.contacts.get(uid, set())

    def test_staff_talk_freely(self):
        self.assertTrue(self.allowed(1, "support", 2, "manager", self.of))
        self.assertTrue(self.allowed(1, "admin", 20, "planner", self.of))

    def test_client_reaches_own_company_and_its_planner_only(self):
        self.assertTrue(self.allowed(10, "employer", 11, "supervisor", self.of))
        self.assertTrue(self.allowed(10, "employer", 20, "planner", self.of))
        self.assertFalse(self.allowed(10, "employer", 30, "support", self.of))
        self.assertFalse(self.allowed(10, "employer", 12, "employer", self.of))
        self.assertFalse(self.allowed(1, "admin", 10, "employer", self.of))

    def test_rule_holds_from_both_ends(self):
        self.assertFalse(self.allowed(30, "support", 10, "employer", self.of))
        self.assertTrue(self.allowed(20, "planner", 11, "supervisor", self.of))

    def test_every_chat_entry_point_enforces_the_rule(self):
        py = src("v8_features.py")
        for endpoint in ("def api_v8_chat_conversation_create",
                         "def api_v8_chat_conversation_members_save",
                         "def api_v8_chat_message_send"):
            body = py[py.index(endpoint):]
            body = body[:body.index("@app.route")]
            self.assertIn("chat_members_error(cur", body, endpoint)
        users = py[py.index("def api_v8_chat_users"):]
        users = users[:users.index("@app.route")]
        self.assertIn('client_contact_ids(cur, g.user["id"])', users)
        self.assertIn("u.role NOT IN (N'employer',N'supervisor') OR EXISTS(", users)

    def test_clients_leave_staff_team_channels_and_announcements(self):
        py = src("v8_features.py")
        self.assertIn("AND u.role NOT IN (N'employer',N'supervisor')", py)
        self.assertIn("WHERE m.is_active=1 AND c.kind IN ('team','announcement')", py)
        self.assertIn("continue  # R14: clients stay out of the staff team channel", py)

    def test_contacts_are_the_project_clients_and_its_planners(self):
        py = src("v8_features.py")
        fn = py[py.index("def client_contact_ids"):py.index("def chat_members_error")]
        self.assertIn("u.role IN (N'employer',N'supervisor')", fn)
        self.assertIn("tm.team_role='planner' OR u.role='planner'", fn)


class MobileChatListTests(unittest.TestCase):
    def test_conversation_list_can_shrink_and_scroll(self):
        css = src("v8_ui.css")
        self.assertIn(".v8-conversations{overflow-y:auto;overflow-x:hidden;flex:1 1 auto;min-height:0;", css)
        mobile = css[css.index("/* Mobile: one pane at a time"):]
        mobile = mobile[:mobile.index("@media(max-width:520px)")]
        self.assertIn(".v8-chat-shell{display:flex;flex-direction:column", mobile)
        self.assertIn(".v8-chat-side{display:flex;flex:1 1 auto;min-height:0", mobile)
        self.assertNotIn(".v8-chat-side{display:flex;height:100%", mobile)


class LeadManagesGroupTasksTests(unittest.TestCase):
    """R15: the lead edits, deletes and approves the tasks of their sub-group."""

    def test_delete_and_approve_resolve_to_group_permissions(self):
        from rbac import default_permissions, permission_for_request
        lead = {"id": 5, "role": "lead", "permissions": sorted(default_permissions("lead"))}
        self.assertEqual(permission_for_request("api_v7_task_delete", {"id": 9}, lead), "tasks.delete_group")
        for action in ("approve", "send_back"):
            self.assertEqual(permission_for_request("api_task_transition", {"action": action}, lead),
                             "tasks.approve_group")
        manager = {"id": 2, "role": "manager", "permissions": sorted(default_permissions("manager"))}
        self.assertEqual(permission_for_request("api_task_transition", {"action": "approve"}, manager),
                         "tasks.approve")

    def test_group_is_the_lead_and_their_active_members(self):
        from team_scope import lead_group_ids

        class Cursor:
            def execute(self, sql, *params):
                self.sql, self.params = sql, params

            def fetchall(self):
                return [(3,), (4,)]
        cur = Cursor()
        self.assertEqual(lead_group_ids(cur, 1), {1, 3, 4})
        self.assertIn("u.is_active=1", cur.sql)
        self.assertEqual(cur.params, (1,))

    def test_server_scopes_every_operation_to_the_group(self):
        v7 = src("v7_features.py")
        save = v7[v7.index("def api_v7_task_save"):v7.index("def api_v7_task_delete")]
        self.assertIn("user_has_permission(u, 'tasks.edit_group')", save)
        self.assertIn("d['status'] = old.get('status')", save)
        self.assertIn("d['progress_weight'] = str(old.get('progress_weight') or 1)", save)
        delete = v7[v7.index("def api_v7_task_delete"):v7.index("def _effective_end_expr")]
        self.assertIn("user_has_permission(u, 'tasks.delete_group')", delete)
        self.assertIn("old.get('status') != 'done'", delete)
        where = v7[v7.index("def _task_where"):v7.index("def _team_scope_condition")]
        self.assertIn("FROM WorkGroupMembers gm JOIN WorkGroups wg", where)
        taskhub = src("taskhub.py")
        start = taskhub.index("def api_task_transition")
        trans = taskhub[start:taskhub.index("def api_export():", start)]
        self.assertIn("user_has_permission(flask_g.user, 'tasks.approve_group')", trans)
        self.assertIn("lead_group_ids(cur, flask_g.user['id'])", trans)
        self.assertIn("SELECT wg.lead_id FROM WorkGroupMembers gm", trans)

    def test_ui_offers_edit_delete_and_approve_on_group_tasks_only(self):
        html = src("ui.html")
        self.assertIn("function leadOwnsTask(t)", html)
        edit = html[html.index("function canEditTask"):html.index("function canDeleteTask")]
        self.assertIn("can('tasks.edit_group')&&leadOwnsTask(t)", edit)
        delete = html[html.index("function canDeleteTask"):html.index("function eTask")]
        self.assertIn("can('tasks.delete_group')&&leadOwnsTask(t)&&t.status!=='done'", delete)
        self.assertIn("if(can('tasks.approve')||(can('tasks.approve_group')&&leadOwnsTask(t))){", html)
        form = html[html.index("function applyTaskFormRole"):]
        form = form[:form.index("\n}\n")]
        self.assertIn("leadRestrictStaff(leadGroupIds())", form)


if __name__ == "__main__":
    unittest.main()
