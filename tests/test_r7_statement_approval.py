# -*- coding: utf-8 -*-
"""Regression checks for TaskHub 8.0.3 LAN R7."""
from pathlib import Path
import unittest

from _paths import ROOT, SRC, project_file  # noqa: E402


def src(name):
    return project_file(name).read_text(encoding="utf-8")


class R7LegacyApprovalTests(unittest.TestCase):
    def test_taxpayer_status_is_not_used_as_employer_approval(self):
        py = src("v7_features.py")
        migration = src("migrate_legacy_v7.py")
        self.assertIn("TaxPayerStatusId belongs to the tax workflow", py)
        self.assertIn("r7_legacy_statement_status_repair_v1", py)
        self.assertIn("ISNULL(raw.confirmed_base,0) > 0", py)
        self.assertIn("is_legacy_approved = confirmed_base is not None", migration)
        self.assertIn("'employer_approved' if is_legacy_approved", migration)

    def test_only_approved_statements_reduce_balance(self):
        py = src("v7_features.py")
        self.assertIn("s.business_status='employer_approved'", py)
        self.assertIn("row['financial_progress_percent']", py)
        self.assertIn("_pct(approved, effective)", py)


class R7EmployerDecisionTests(unittest.TestCase):
    def test_approval_copies_full_requested_amount(self):
        py = src("v7_features.py")
        self.assertIn("confirmed_without_vat = requested_base", py)
        self.assertIn("confirmed_vat = requested_vat", py)
        self.assertIn("confirmed_price = (_dec(requested_total)", py)
        self.assertIn("confirmed_without_vat = None", py)

    def test_pre_decision_edit_and_post_decision_lock(self):
        py = src("v7_features.py")
        js = src("v7_ui.js")
        rbac = src("rbac.py")
        self.assertIn("statements.edit_before_employer_decision", rbac)
        self.assertIn("('employer_approved','employer_rejected','revised')", py)
        self.assertIn("preserve_status", py)
        self.assertIn("پس از ثبت تأییدیه کارفرما", js)

    def test_compact_decision_ui_has_no_amount_inputs(self):
        js = src("v7_ui.js")
        self.assertIn("تأییدیه کارفرما", js)
        self.assertIn("تأیید کامل", js)
        self.assertIn("v7-employer-summary", js)
        self.assertNotIn("v7-decision-confirmed", js)
        self.assertNotIn("v7-decision-vat", js)


class R7PresentationTests(unittest.TestCase):
    def test_contract_grid_contains_financial_progress(self):
        js = src("v7_ui.js")
        css = src("v7_ui.css")
        self.assertIn("پیشرفت ریالی", js)
        self.assertIn("financial_progress_percent", js)
        self.assertIn("v7-financial-progress", css)

    def test_release_version(self):
        self.assertIn("APP_VERSION = '1.0.0'", src("config.py"))
        self.assertIn("TaskHub.exe", src("build.bat"))
        self.assertIn("1.0.0", src("service-worker.js"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
