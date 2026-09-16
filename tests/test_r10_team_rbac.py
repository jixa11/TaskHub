# -*- coding: utf-8 -*-
"""Release regression checks for TaskHub 1.0.0."""
from pathlib import Path
import unittest

from _paths import ROOT, SRC, project_file  # noqa: E402

def src(name):
    return project_file(name).read_text(encoding="utf-8")


class R10TeamScopeTests(unittest.TestCase):
    def test_company_scope_is_limited_to_three_roles(self):
        py = src("team_scope.py")
        self.assertIn('GLOBAL_COMPANY_ROLES = frozenset(("admin", "finance", "reporter"))', py)
        self.assertIn('TEAM_REQUIRED_ROLES = frozenset(("manager", "planner", "support", "lead", "supervisor", "employer"))', py)

    def test_new_team_roles_require_a_primary_team(self):
        py = src("taskhub.py")
        html = src("ui.html")
        self.assertIn("if requires_team(role) and not team_id", py)
        self.assertIn("برای این نقش انتخاب تیم الزامی است", py)
        self.assertIn("id=\"vuteam\"", html)
        self.assertIn("team_id:needsTeam?(team||null):null", html)

    def test_company_roles_cannot_be_delegated_by_team_managers(self):
        py = src("taskhub.py")
        html = src("ui.html")
        self.assertIn("company_roles = ('admin','finance','reporter')", py)
        self.assertIn("ساخت یا تغییر نقش‌های سراسری فقط برای مدیر سیستم مجاز است", py)
        self.assertIn("['admin','finance','reporter'].indexOf(role)>=0", html)

    def test_legacy_users_receive_a_safe_primary_team(self):
        py = src("r10_features.py")
        self.assertIn("legacy-default", py)
        self.assertIn("UX_TeamMembers_ActivePrimaryUser", py)
        self.assertIn("NOT EXISTS(SELECT 1 FROM TeamMembers tm", py)

    def test_task_project_users_and_programs_are_team_bounded(self):
        taskhub = src("taskhub.py")
        v7 = src("v7_features.py")
        for marker in ("def _team_user_access", "def _team_project_access", "def _task_team_scope"):
            self.assertIn(marker, taskhub)
        self.assertIn("Visibility is permission-driven; data scope is team-driven.", v7)
        self.assertIn("active teams, even when the administrator grants tasks.view_all", v7)
        self.assertIn("این همکار خارج از محدوده تیم شماست", taskhub)

    def test_phonebook_and_user_directory_have_independent_scope(self):
        py = src("taskhub.py")
        self.assertIn("Team-scoped user directory used by the user-management page", py)
        self.assertIn("def api_phonebook", py)
        self.assertIn("phonebook.view_all", py)
        self.assertIn("target_tm JOIN TeamMembers mine_tm", py)

    def test_project_creation_requires_and_links_a_team(self):
        py = src("v7_features.py")
        js = src("v7_ui.js")
        self.assertIn("انتخاب تیم مسئول پروژه الزامی است", py)
        self.assertIn("INSERT INTO ProjectTeams", py)
        self.assertIn("team_id:teamId||null", js)
        self.assertIn("نام، شهر، نوع پروژه و تیم مسئول الزامی است", js)

    def test_custom_project_types_are_loaded_dynamically(self):
        py = src("v7_features.py")
        self.assertIn("SELECT id,name FROM ProjectTypes WHERE id>0 AND is_active=1 ORDER BY id", py)
        self.assertIn("«بینا» and «سپنتا»", py)
        self.assertNotIn("DELETE FROM ProjectTypes", src("r10_features.py"))

    def test_financial_and_people_reports_use_team_scope_not_view_all(self):
        v7 = src("v7_features.py")
        v8 = src("v8_features.py")
        v802 = src("v802_features.py")
        self.assertIn("R10: team-scoped reports may include every teammate", v7)
        self.assertIn("scoped_team_ids is the authoritative R10 boundary", v8)
        self.assertIn('GLOBAL_FINANCIAL_ROLES = ("admin", "finance", "reporter")', v802)


class R10GranularPermissionTests(unittest.TestCase):
    def test_small_buttons_have_independent_permissions(self):
        rbac = src("rbac.py")
        for key in (
            "cities.create", "cities.edit", "cities.delete",
            "projects.create", "projects.edit", "projects.delete",
            "task_categories.create", "task_categories.edit", "task_categories.delete",
            "teams.create", "teams.edit", "teams.members_manage",
            "teams.project_types_manage", "teams.project_assign",
            "chat.file_upload", "chat.file_download",
        ):
            self.assertIn('"%s"' % key, rbac)
        self.assertIn("r10_granular_permissions_v1", rbac)

    def test_sensitive_project_access_has_lower_granular_options(self):
        ui = src("v8_ui.js")
        rbac = src("rbac.py")
        self.assertNotIn("فعال‌سازی اطلاعات حساس پروژه", ui)
        self.assertIn("دسترسی اطلاعات حساس پروژه", ui)
        self.assertIn("v8-sensitive-view", ui)
        self.assertIn("v8-sensitive-manage", ui)
        self.assertNotIn("['menu.projects','projects.view','project_notes.view','project_notes.manage']", ui)
        self.assertIn("Requested R10 default: support can view and edit sensitive data", rbac)

    def test_sensitive_notes_require_permission_and_project_team(self):
        py = src("taskhub.py")
        self.assertIn("Permission + team boundary for VPN/remote/login information", py)
        self.assertIn("return _team_project_access(cur, actor, project_id, manage=manage)", py)
        self.assertNotIn("PROJECT_NOTES_ACTIVE_TASK_STATUSES", py)

    def test_chat_file_error_is_fixed_and_permissions_are_separate(self):
        js = src("v8_ui.js")
        rbac = src("rbac.py")
        self.assertIn("var res=await fetch('/api/v8/chat/file_download/'", js)
        self.assertNotIn("if(TOKEN)headers['X-Token']=TOKEN,res=await fetch", js)
        self.assertIn("can('chat.file_download')", js)
        self.assertIn('"api_v8_chat_file_download": "chat.file_download"', rbac)

    def test_attachments_are_team_scoped_even_with_broad_permissions(self):
        py = src("v7_features.py")
        block = py[py.index("def _can_access_entity"):py.index("@app.route('/api/attachments'")]
        self.assertIn("if has_company_scope(g.user)", block)
        self.assertIn("JOIN TeamMembers tm", block)
        self.assertNotIn("projects.view_all", block)
        self.assertNotIn("tasks.view_all", block)


class R10ReleaseTests(unittest.TestCase):
    def test_release_identity_and_lan_build(self):
        self.assertIn("APP_VERSION = '1.0.0'", src("config.py"))
        self.assertIn("TaskHub.exe", src("build.bat"))
        self.assertIn("--hidden-import r10_features", src("build.bat"))
        self.assertIn("--hidden-import team_scope", src("build.bat"))
        self.assertIn("taskhub-v1-0-0-static", src("service-worker.js"))
        self.assertIn("v 1.0.0", src("v8_ui.js"))


if __name__ == "__main__":
    unittest.main()
