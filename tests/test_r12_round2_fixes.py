# -*- coding: utf-8 -*-
"""Second round of on-site findings for R12."""
import pathlib
import subprocess
import unittest

from _paths import ROOT, SRC, project_file  # noqa: E402


def src(name):
    return project_file(name).read_text(encoding="utf-8")


def node_check(script):
    try:
        # The checks print Persian; without an explicit codec Windows decodes
        # the output as cp1252 and the test dies before reading the result.
        result = subprocess.run(["node", str(ROOT / "tests" / script)],
                                capture_output=True, text=True, cwd=str(SRC),
                                encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return None, "node is unavailable"
    if result.returncode and "Cannot find module 'jsdom'" in result.stderr:
        return None, "jsdom is not installed"
    return result, None


class RepeatedDenialToastTests(unittest.TestCase):
    def test_lookups_are_not_fetched_without_the_permission_they_need(self):
        js = src("v7_ui.js")
        # /contract_lookups needs contracts.view; asking for it on behalf of
        # someone who only sees the dashboard goal card produced a 403 on
        # every poll, which became a toast every few seconds.
        self.assertIn("if(can('contracts.view')||can('financial_plan.view'))await v7LoadLookups();", js)

    def test_background_loaders_stay_silent_on_denial(self):
        js = src("v7_ui.js")
        fn = js[js.index("async function v7LoadLookups"):]
        fn = fn[:fn.index("\nasync function ")]
        self.assertNotIn("toast(", fn)

    def test_api_flags_forbidden_instead_of_treating_it_as_an_incident(self):
        html = src("ui.html")
        self.assertIn("if(r.status === 403){", html)
        self.assertIn("forbidden:true", html)


class DashboardTabContentTests(unittest.TestCase):
    def test_a_tab_is_empty_when_all_its_cards_are_hidden(self):
        html = src("ui.html")
        fn = html[html.index("function dashTabHasContent"):]
        fn = fn[:fn.index("\nfunction ")]
        # Checking only the wrapper is what offered empty tabs to everyone.
        self.assertIn("querySelectorAll('[data-permission]", fn)
        self.assertIn("gated.length", fn)

    def test_few_groups_means_no_tab_bar(self):
        html = src("ui.html")
        self.assertIn("if(available.length<3){", html)

    def test_behaviour_matches_the_dom_test(self):
        result, skip = node_check("dashboard_tabs_check.js")
        if skip:
            self.skipTest(skip)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class FinancialCardTests(unittest.TestCase):
    def test_detail_button_needs_the_permission_of_the_page_it_opens(self):
        js = src("v7_ui.js")
        self.assertIn("var detailBtn=can('financial_plan.view')?", js)
        self.assertIn("showPage(25)", js)

    def test_card_offers_a_team_picker_to_multi_team_readers(self):
        js = src("v7_ui.js")
        for fn in ("v7FinanceTeams", "v7FinanceTeamPicker", "v7FinancialTeamChanged"):
            self.assertIn("function %s" % fn, js)
        self.assertIn("if(V7.financeTeam)payload._team_scope=V7.financeTeam;", js)
        # A stored team the reader lost access to must not blank the card.
        self.assertIn("if(V7.financeTeam&&!v7FinanceTeams().some(", js)

    def test_backend_already_honours_the_team_filter(self):
        py = src("v7_features.py")
        block = py[py.index("def api_v7_financial_dashboard"):]
        self.assertIn("_int(d.get('_team_scope'))", block[:3000])


class UnassignedUserTests(unittest.TestCase):
    def test_a_user_with_no_team_can_be_reached_by_a_team_manager(self):
        py = src("taskhub.py")
        fn = py[py.index("def _team_user_access"):py.index("def _team_project_access")]
        self.assertIn("teams.members_manage", fn)
        self.assertIn("NOT EXISTS(SELECT 1 FROM TeamMembers tm", fn)

    def test_unassigned_users_appear_in_the_list_that_can_assign_them(self):
        py = src("taskhub.py")
        block = py[py.index("def api_users_list"):py.index("def api_phonebook")]
        self.assertIn("NOT EXISTS(SELECT 1 FROM TeamMembers any_tm", block)
        self.assertIn("'teams.members_manage'", block)


class ViewStatePreservationTests(unittest.TestCase):
    def test_background_refresh_restores_scroll_and_focus(self):
        html = src("ui.html")
        self.assertIn("function _captureViewState", html)
        self.assertIn("function _restoreViewState", html)
        poll = html[html.index("async function pollForUpdates"):]
        poll = poll[:poll.index("\nasync function ")]
        # Only the silent refresh restores; a deliberate reload may reset.
        self.assertIn("(opts && opts.silent) ? _captureViewState() : null", poll)
        self.assertIn("_restoreViewState(view)", poll)

    def test_focus_and_caret_are_kept(self):
        html = src("ui.html")
        fn = html[html.index("function _captureViewState"):html.index("function _restoreViewState")]
        self.assertIn("selectionStart", fn)


class SearchableSelectTests(unittest.TestCase):
    def test_native_select_remains_the_source_of_truth(self):
        html = src("ui.html")
        fn = html[html.index("function selSearchOpen"):]
        fn = fn[:fn.index("\nfunction applySelSearch")]
        # Existing readers use el.value and existing handlers use change.
        self.assertIn("sel.value=value;", fn)
        self.assertIn("new Event('change',{bubbles:true})", fn)

    def test_multi_select_keeps_the_popup_open(self):
        html = src("ui.html")
        self.assertIn("draw();                       // stay open so more can be picked", html)

    def test_wrapping_runs_after_render_and_on_modal_open(self):
        html = src("ui.html")
        self.assertIn("if(typeof applySelSearch==='function') applySelSearch();", html)
        open_m = html[html.index("function openM(id){"):html.index("function closeM(id){")]
        self.assertIn("applySelSearch()", open_m)

    def test_behaviour_matches_the_dom_test(self):
        result, skip = node_check("select_search_check.js")
        if skip:
            self.skipTest(skip)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class KanbanFilterTests(unittest.TestCase):
    def test_personal_boards_do_not_show_a_filter_row(self):
        html = src("ui.html")
        bar = html[html.index('<div class="fb" id="kb-filters"'):]
        bar = bar[:bar.index(">") + 1]
        # A data-permission here would make applyPermissionUI ignore the role
        # list, which is how the employer and supervisor kept seeing it.
        self.assertNotIn("data-permission", bar)
        # R16: a lead's board holds their group's tasks, so it gets the filters too.
        self.assertIn('data-role="admin,support,lead,manager,planner"', bar)


class ContactRolesTests(unittest.TestCase):
    def setUp(self):
        from rbac import default_permissions
        self.sup = default_permissions("supervisor")
        self.emp = default_permissions("employer")

    def test_both_roles_can_use_the_messenger(self):
        for perms in (self.sup, self.emp):
            for key in ("menu.chat", "chat.use", "chat.file_upload", "chat.file_download"):
                self.assertIn(key, perms, key)

    def test_neither_role_can_start_groups_or_announcements(self):
        self.assertNotIn("chat.manage_groups", self.sup)
        self.assertNotIn("chat.manage_groups", self.emp)

    def test_contact_list_is_limited_to_real_working_relationships(self):
        py = src("v8_features.py")
        block = py[py.index('route("/api/v8/chat/users"'):]
        block = block[:block.index("@app.route", 10)]
        # Teammates, the team running my project, and the people on my tasks.
        self.assertIn("FROM TeamMembers target JOIN TeamMembers mine", block)
        self.assertIn("JOIN ProjectTeams mine_pt ON mine_pt.project_id=me.project_id", block)
        self.assertIn("FROM Tasks t", block)
        self.assertIn("TaskAssignees", block)

    def test_group_button_is_permission_gated(self):
        js = src("v8_ui.js")
        self.assertIn('data-permission="chat.manage_groups" onclick="v8ChatOpenCreate(\'group\')"', js)

    def test_upgrade_applies_the_change_once(self):
        rbac = src("rbac.py")
        self.assertIn("r12_supervisor_employer_messenger_v1", rbac)


class ContactRoleHelpTests(unittest.TestCase):
    def test_both_roles_get_a_real_guide(self):
        html = src("ui.html")
        card = html[html.index("function _helpRoleScopeCard"):]
        card = card[:card.index("function _helpTaskEntryCard")]
        for topic in ("کارتابل", "پیامرسان", "دفتر تلفن"):
            self.assertIn(topic, card, topic)
        # The employer needs to know the filter row is absent by design.
        self.assertIn("نوار فیلتر نمایش داده نمی‌شود", card)
        self.assertIn("ساخت گروه", card)


if __name__ == "__main__":
    unittest.main()
