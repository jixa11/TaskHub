# -*- coding: utf-8 -*-
"""Checks on the demo data scripts that a T-SQL syntax parser cannot make.

SQL Server rejects a subquery wherever only a scalar expression is allowed -
inside PRINT or inside VALUES, for example. That failure happens while the
batch is being parsed, so the whole script refuses to run and nothing is
inserted; it cost two rounds of trial and error before it was pinned down.
"""
import pathlib
import re
import unittest

from _paths import ROOT

SCRIPTS = ("sql/demo_data.sql", "sql/demo_data_en.sql")

SCALAR_ONLY_CONTEXTS = (
    ("PRINT", re.compile(r"^\s*PRINT\b[^;]*\(\s*SELECT\b", re.I | re.M)),
    ("VALUES", re.compile(r"\bVALUES\s*\([^;]*\(\s*SELECT\b", re.I)),
    ("DEFAULT", re.compile(r"\bDEFAULT\s*\(\s*SELECT\b", re.I)),
)


def script(name):
    return (ROOT / name).read_text(encoding="utf-8-sig")


class DemoScriptTests(unittest.TestCase):
    def test_no_subquery_where_only_a_scalar_is_allowed(self):
        for name in SCRIPTS:
            text = script(name)
            for context, pattern in SCALAR_ONLY_CONTEXTS:
                match = pattern.search(text)
                if match:
                    line = text.count("\n", 0, match.start()) + 1
                    self.fail("%s line %d: subquery inside %s" % (name, line, context))

    def test_identity_insert_is_always_switched_off_again(self):
        for name in SCRIPTS:
            text = script(name)
            for table in set(re.findall(r"SET IDENTITY_INSERT (\w+) ON", text)):
                self.assertEqual(
                    len(re.findall(r"SET IDENTITY_INSERT %s ON" % table, text)),
                    len(re.findall(r"SET IDENTITY_INSERT %s OFF" % table, text)),
                    "%s: %s" % (name, table))

    def test_everything_runs_inside_one_transaction(self):
        for name in SCRIPTS:
            text = script(name)
            self.assertEqual(text.count("BEGIN TRANSACTION"), 1, name)
            self.assertEqual(text.count("COMMIT TRANSACTION"), 1, name)
            self.assertIn("SET XACT_ABORT ON", text, name)

    def test_variables_are_declared_before_use(self):
        for name in SCRIPTS:
            text = script(name)
            declared = set(re.findall(r"DECLARE\s+(@\w+)", text))
            # An @ inside quoted text (a password, say) is not a variable.
            code = re.sub(r"N'(?:[^']|'')*'", "''", text)
            used = set(re.findall(r"(?<![\w@])(@\w+)", code))
            self.assertEqual(used - declared, set(), name)

    def test_the_script_refuses_to_run_twice(self):
        for name in SCRIPTS:
            text = script(name)
            self.assertIn("THROW 51000", text, name)
            self.assertIn("THROW 51001", text, name)

    def test_both_languages_carry_the_same_rows(self):
        counts = [len(re.findall(r"INSERT INTO", script(name))) for name in SCRIPTS]
        self.assertEqual(counts[0], counts[1])
        self.assertGreater(counts[0], 300)

    def test_the_english_script_has_no_persian_left(self):
        self.assertIsNone(re.search(r"[؀-ۿ]", script("sql/demo_data_en.sql")))


if __name__ == "__main__":
    unittest.main()
