# -*- coding: utf-8 -*-
"""The Persian/English display layer: dictionary, wiring and asset delivery."""
import json
import re
import unittest

from _paths import project_file

import taskhub


def dictionary():
    return json.loads(project_file("i18n.json").read_text(encoding="utf-8"))


class DictionaryTests(unittest.TestCase):
    def setUp(self):
        self.data = dictionary()

    def test_every_entry_has_a_real_translation(self):
        for persian, english in self.data["strings"].items():
            self.assertTrue(persian.strip(), "empty source text")
            self.assertTrue(english.strip(), persian)
            self.assertNotEqual(persian, english)
            # A translation that still carries Persian letters is a leftover.
            self.assertIsNone(re.search(r"[؀-ۿ]", english), persian)

    def test_source_text_is_normalised(self):
        for persian in self.data["strings"]:
            self.assertEqual(persian, " ".join(persian.split()), persian)

    def test_patterns_compile_and_use_their_groups(self):
        for entry in self.data["patterns"]:
            pattern = re.compile(entry["from"])
            for index in re.findall(r"\$(\d)", entry["to"]):
                self.assertLessEqual(int(index), pattern.groups, entry["from"])

    def test_the_visible_shell_is_translated(self):
        strings = self.data["strings"]
        for key in ("داشبورد", "کارتابل", "تسک‌ها", "پروژه‌ها", "گزارش‌گیری",
                    "خروج از حساب", "نام کاربری", "رمز عبور", "انصراف"):
            self.assertIn(key, strings)


class WiringTests(unittest.TestCase):
    def test_ui_loads_the_layer_and_offers_the_switch(self):
        html = project_file("ui.html").read_text(encoding="utf-8")
        self.assertIn('<script src="/assets/i18n.js"></script>', html)
        self.assertIn('onclick="toggleLanguage()"', html)

    def test_the_layer_is_cached_and_shipped(self):
        worker = project_file("service-worker.js").read_text(encoding="utf-8")
        self.assertIn("/assets/i18n.js", worker)
        self.assertIn("/assets/i18n.json", worker)
        build = project_file("build.bat").read_text(encoding="utf-8")
        self.assertIn('--add-data "src\\web\\i18n.js;web"', build)
        self.assertIn('--add-data "src\\web\\i18n.json;web"', build)

    def test_english_is_a_stored_choice_that_flips_direction(self):
        script = project_file("i18n.js").read_text(encoding="utf-8")
        self.assertIn("taskhub_lang", script)
        self.assertIn("'ltr'", script)
        self.assertIn("'rtl'", script)


class AssetTests(unittest.TestCase):
    def test_both_files_are_served(self):
        client = taskhub.flask_app.test_client()
        for name in ("i18n.js", "i18n.json"):
            response = client.get("/assets/" + name)
            self.assertEqual(response.status_code, 200, name)
            self.assertTrue(response.data)
            response.close()


if __name__ == "__main__":
    unittest.main()
