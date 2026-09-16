# -*- coding: utf-8 -*-
"""Regression checks for TaskHub 1.0.0."""
from pathlib import Path
import unittest

from _paths import ROOT, SRC, project_file  # noqa: E402


def src(name):
    return project_file(name).read_text(encoding="utf-8")


class R11PermissionAndProfileTests(unittest.TestCase):
    def test_new_permissions_are_catalogued_and_migrated(self):
        rbac = src("rbac.py")
        for key in (
            "account.view", "account.edit_identity", "account.change_password",
            "phonebook.view", "phonebook.view_all", "phonebook.edit",
            "tasks.link_contract",
        ):
            self.assertIn('("%s",' % key, rbac)
        self.assertIn("r11_account_phonebook_contract_permissions_v1", rbac)

    def test_profile_chip_always_opens_self_service_popup(self):
        html = src("ui.html")
        py = src("taskhub.py")
        block = html[html.index("function openMyAccount"):
                     html.index("function applyRole")]
        self.assertNotIn("showPage(10)", block)
        self.assertIn("account.view", block)
        self.assertIn("account.edit_identity", block)
        self.assertIn("account.change_password", block)
        self.assertIn("مجوز ویرایش نام کاربری یا نام نمایشی", py)
        self.assertIn("مجوز تغییر رمز عبور", py)

    def test_sensitive_access_is_a_lower_two_option_card(self):
        js = src("v8_ui.js")
        header = js[js.index("function v8AccessControlPageHtml"):
                    js.index("async function v8AccessLoad")]
        self.assertNotIn("v8AccessApplyPreset", js)
        self.assertNotIn("فعال‌سازی اطلاعات حساس پروژه", header)
        self.assertIn("v8-sensitive-access-card", header)
        self.assertIn("project_notes.view", header)
        self.assertIn("project_notes.manage", header)


class R11PhonebookTests(unittest.TestCase):
    def test_phonebook_is_independent_from_user_management(self):
        py = src("taskhub.py")
        html = src("ui.html")
        rbac = src("rbac.py")
        self.assertIn("def api_phonebook", py)
        self.assertIn("phonebook.view_all", py)
        self.assertIn("D.phonebook=r.rows||[]", html)
        self.assertIn("12:'phonebook.view'", html)
        self.assertIn("can('phonebook.edit')", html)
        self.assertIn('"api_phonebook": "phonebook.view"', rbac)
        self.assertIn('"api_update_phone": "phonebook.edit"', rbac)

    def test_support_receives_company_phonebook_by_default(self):
        rbac = src("rbac.py")
        support = rbac[rbac.index('"support": {'):rbac.index('"supervisor": {')]
        for key in ("phonebook.view", "phonebook.view_all", "phonebook.edit"):
            self.assertIn('"%s"' % key, support)


class R11CityAndTaskContractTests(unittest.TestCase):
    def test_cities_are_global_and_duplicate_insert_is_friendly(self):
        py = src("v7_features.py")
        core = py[py.index("def api_v7_core_data"):py.index("def api_v7_master_save")]
        self.assertIn("Cities are shared master data across the company", core)
        self.assertIn('SELECT id,name,created_at FROM Cities ORDER BY name', core)
        self.assertNotIn("city_ids = sorted", core)
        self.assertIn("این شهر از قبل وجود دارد و همان رکورد مشترک استفاده شد", py)
        self.assertIn("این شهر دارای پروژه است و قابل حذف نیست", py)

    def test_task_contract_options_are_minimal_team_scoped_and_permissioned(self):
        py = src("v7_features.py")
        js = src("v7_ui.js")
        rbac = src("rbac.py")
        block = py[py.index("def api_v7_task_contract_options"):
                   py.index("def api_v7_task_save")]
        self.assertIn("excludes prices and financial details", block)
        self.assertIn("JOIN TeamMembers scope_tm", block)
        self.assertNotIn("base_price", block)
        self.assertIn('"api_v7_task_contract_options": "tasks.link_contract"', rbac)
        self.assertIn("v7TaskContractMatchesType", js)
        self.assertIn("text.indexOf('توسعه')", js)
        self.assertIn("!x.is_closed", js)
        self.assertIn("else if(rows.length===1)", js)

    def test_task_contract_is_preserved_without_edit_permission(self):
        py = src("v7_features.py")
        self.assertIn("if not user_has_permission(u, 'tasks.link_contract')", py)
        self.assertIn("contract_id = _int(old.get('contract_id'))", py)
        self.assertIn("مجوز اتصال قرارداد به تسک", py)


class R11ReleaseTests(unittest.TestCase):
    def test_release_identity_and_lan_build(self):
        self.assertIn("APP_VERSION = '1.0.0'", src("config.py"))
        self.assertIn("TaskHub.exe", src("build.bat"))
        self.assertIn("TaskHub.exe", src("Run_TaskHub.cmd"))
        self.assertIn("1.0.0", src("service-worker.js"))
        self.assertIn("v 1.0.0", src("v8_ui.js"))


if __name__ == "__main__":
    unittest.main()
