# -*- coding: utf-8 -*-
"""Regression guards for the defects found during on-site testing of R12."""
import pathlib
import re
import subprocess
import unittest

from _paths import ROOT, SRC, project_file  # noqa: E402


def src(name):
    return project_file(name).read_text(encoding="utf-8")


class ChatLayoutTests(unittest.TestCase):
    def test_chat_shell_no_longer_guesses_its_height(self):
        css = src("v8_ui.css")
        # calc(100dvh - N) never matched the real header stack, so the compose
        # box sat below the fold and the list could not reach its end.
        self.assertNotIn("height:calc(100dvh - 190px)", css)
        self.assertNotIn("height:calc(100vh - 165px)", css)
        self.assertNotIn("height:calc(100dvh - 205px)", css)
        self.assertNotIn("height:calc(100dvh - 214px)", css)

    def test_chat_page_is_a_flex_column_that_fills_the_page(self):
        css = src("v8_ui.css")
        self.assertIn("#pg24.page.active{display:flex;flex-direction:column;height:100%", css)
        self.assertRegex(css, r"\.v8-chat-shell\{flex:1 1 auto;height:auto")


class PhonebookTests(unittest.TestCase):
    def test_directory_is_not_limited_to_employers(self):
        py = src("taskhub.py")
        book = py[py.index("def api_phonebook"):py.index("def api_update_phone")]
        self.assertNotIn("u.role=N'employer'", book)
        self.assertIn("WHERE u.is_active=1", book)

    def test_ui_does_not_re_filter_the_server_answer(self):
        html = src("ui.html")
        render = html[html.index("function renderPhonebook"):]
        render = render[:render.index("\nfunction ")]
        self.assertNotIn("u.role==='employer'", render)


class SeedTeamTests(unittest.TestCase):
    def test_seed_team_is_created_once_not_on_every_start(self):
        py = src("v8_features.py")
        self.assertIn("AND NOT EXISTS(SELECT 1 FROM V8MigrationState WHERE migration_key='default_team_v1')\n        INSERT INTO Teams", py)

    def test_backfill_is_skipped_when_the_seed_team_is_gone(self):
        py = src("v8_features.py")
        self.assertIn("if default_team_id is not None:", py)


class WorkShareScopeTests(unittest.TestCase):
    def test_timesheets_are_personal_without_tasks_view_all(self):
        py = src("v7_features.py")
        fn = py[py.index("def _work_report_data"):py.index("def _report_rows")] \
            if "def _report_rows" in py else py[py.index("def _work_report_data"):][:4000]
        self.assertIn("if not user_has_permission(user, 'tasks.view_all'):", fn)
        # An injected user_id must not widen the result.
        self.assertIn("elif requested_user_id is not None:", fn)


class ArchiveCascadeTests(unittest.TestCase):
    def test_archiving_a_contract_archives_its_children(self):
        py = src("v7_features.py")
        block = py[py.index("def api_v7_contract_archive"):py.index("def api_v7_extensions")]
        self.assertIn("UPDATE ContractStatements SET is_active=0,archived_with_contract=1", block)
        self.assertIn("UPDATE ContractExtensions SET is_active=0,archived_with_contract=1", block)

    def test_restore_returns_only_what_the_cascade_took(self):
        py = src("v7_features.py")
        block = py[py.index("def _restore_record"):py.index("@app.route('/api/contract_restore'")]
        self.assertIn("archived_with_contract=1", block)
        self.assertIn("if entity == 'contract':", block)

    def test_upgrade_fixes_contracts_archived_before_this_release(self):
        py = src("v8_features.py")
        self.assertIn("r12_archive_cascade_v1", py)
        self.assertIn("archived_with_contract BIT NOT NULL", py)


class EmployerVisibilityTests(unittest.TestCase):
    def test_project_employers_are_visible_to_their_project_team(self):
        py = src("taskhub.py")
        block = py[py.index("def api_users_list"):py.index("def api_phonebook")]
        self.assertIn("FROM ProjectTeams client_pt JOIN TeamMembers mine", block)


class DatePickerTests(unittest.TestCase):
    def test_picker_is_anchored_to_the_viewport(self):
        html = src("ui.html")
        self.assertIn(".dp-pop{position:fixed;z-index:9999;", html)
        self.assertNotIn(".dp-pop{position:absolute", html)
        self.assertIn("document.body.appendChild(pop);", html)
        self.assertIn("function positionDP", html)
        self.assertIn("function closeDP", html)

    def test_closing_removes_the_viewport_listeners(self):
        html = src("ui.html")
        close = html[html.index("function closeDP"):]
        close = close[:close.index("\nfunction ")]
        # Guards against the recursion this refactor briefly introduced.
        self.assertNotIn("closeDP();", close)
        self.assertIn("removeEventListener('resize',dpReposition,true)", close)
        self.assertIn("removeEventListener('scroll',dpReposition,true)", close)

    def test_every_date_field_still_opens_the_picker(self):
        hint = re.compile(r'id="[^"]*(date|-fa)[^"]*"|placeholder="[^"]*تاریخ', re.I)
        missing = []
        for name in ("ui.html", "v7_ui.js", "v8_ui.js"):
            for m in re.finditer(r"<input\b[^>]*>", src(name)):
                tag = m.group(0)
                if not hint.search(tag) or "openDP(" in tag:
                    continue
                if 'type="number"' in tag or "vat-factor" in tag:
                    continue
                missing.append((name, tag[:70]))
        self.assertEqual(missing, [])


class DashboardTabTests(unittest.TestCase):
    def test_dashboard_sections_are_grouped(self):
        html = src("ui.html")
        for tab in ("overview", "me", "team", "finance", "org"):
            self.assertIn('data-dash-tab="%s"' % tab, html + src("v7_ui.js"), tab)
        self.assertIn("function renderDashTabs", html)
        self.assertIn(".dash-hidden{display:none!important;}", html)

    def test_tabs_are_rebuilt_after_permissions_are_applied(self):
        html = src("ui.html")
        apply_role = html[html.index("function applyRole()"):]
        apply_role = apply_role[:apply_role.index("\nfunction ")]
        self.assertLess(apply_role.index("applyPermissionUI()"),
                        apply_role.index("renderDashTabs()"))

    def test_tab_behaviour_matches_the_dom_test(self):
        script = ROOT / "tests" / "dashboard_tabs_check.js"
        try:
            result = subprocess.run(["node", str(script)], capture_output=True,
                                    text=True, cwd=str(SRC),
                                    encoding="utf-8", errors="replace")
        except FileNotFoundError:
            self.skipTest("node is unavailable")
        if result.returncode and "Cannot find module 'jsdom'" in result.stderr:
            self.skipTest("jsdom is not installed")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class ScheduleOverviewTests(unittest.TestCase):
    def test_weekly_page_shows_everyone_before_a_person_is_picked(self):
        html = src("ui.html")
        self.assertIn("function renderSchedOverview", html)
        self.assertIn("await renderSchedOverview(); return;", html)
        self.assertIn("if(n==13&&typeof loadSchedEditor==='function')loadSchedEditor();", html)


class FinanceHelpTests(unittest.TestCase):
    def test_finance_gets_a_column_by_column_report_reference(self):
        html = src("ui.html")
        self.assertIn("function _helpFinanceReportsCard", html)
        self.assertIn("_helpFinanceReportsCard()", html)
        card = html[html.index("function _helpFinanceReportsCard"):]
        card = card[:card.index("\n// Every role has a different boundary")]
        # Every financial surface must be covered.
        for topic in ("درآمد پروژه‌ها", "اهداف مالی", "پایش هدف مالی",
                      "بایگانی", "تحقق برنامه", "سهم از کل درآمد",
                      "مانده قرارداد", "کدام گزارش را برای کدام سؤال"):
            self.assertIn(topic, card, topic)
        # It must state the rules that make two reports disagree.
        self.assertIn("چرا عددها با هم نمی‌خوانند", card)

    def test_reference_is_shown_only_to_roles_that_read_money(self):
        html = src("ui.html")
        self.assertIn("if(can('reports.financial'))cards.push(_helpFinanceReportsCard());", html)


class LoginPageTests(unittest.TestCase):
    def test_cache_clear_button_is_gone_from_the_login_screen(self):
        html = src("ui.html")
        login = html[html.index('id="lg-pass"'):html.index('>Jixa<')]
        self.assertNotIn("taskhubClearCacheAndReload", login)


if __name__ == "__main__":
    unittest.main()
