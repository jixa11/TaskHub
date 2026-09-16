# -*- coding: utf-8 -*-
"""R12: the finance specialist owns the financial records, and archives are
browsable instead of being a one-way door.
"""
import pathlib
import unittest

from _paths import ROOT, SRC, project_file  # noqa: E402


def src(name):
    return project_file(name).read_text(encoding="utf-8")


class FinanceOwnsFinancialRecordsTests(unittest.TestCase):
    def setUp(self):
        from rbac import default_permissions
        self.finance = default_permissions("finance")

    def test_finance_can_create_edit_approve_and_archive_every_record_type(self):
        for key in (
            "contracts.view", "contracts.manage", "contracts.approve", "contracts.archive",
            "extensions.view", "extensions.manage", "extensions.approve", "extensions.archive",
            "statements.view", "statements.manage", "statements.internal_approve",
            "statements.employer_status", "statements.archive",
        ):
            self.assertIn(key, self.finance, key)

    def test_finance_can_edit_records_in_any_status(self):
        for key in ("extensions.edit_any_status",
                    "statements.edit_before_employer_decision",
                    "statements.edit_any_status"):
            self.assertIn(key, self.finance, key)

    def test_finance_has_every_financial_report_and_dashboard_card(self):
        for key in ("reports.view", "reports.financial", "reports.export",
                    "dashboard.financial", "dashboard.organization_summary",
                    "dashboard.organization_analytics",
                    "menu.project_income", "menu.reports", "menu.team_reports",
                    "financial_plan.view", "financial_plan.manage",
                    "financial_plan.lock", "team_financial.manage"):
            self.assertIn(key, self.finance, key)

    def test_finance_never_receives_non_financial_administration(self):
        # Broadening finance must not turn it into a second administrator.
        for key in ("access_control.manage", "users.create", "users.delete",
                    "system.backup", "tasks.delete"):
            self.assertNotIn(key, self.finance, key)

    def test_upgrade_grants_the_new_permissions_once(self):
        rbac = src("rbac.py")
        self.assertIn("r12_finance_full_financial_access_v1", rbac)
        block = rbac[rbac.index("r12_finance = "):rbac.index("# Keep obsolete catalog rows")]
        self.assertIn("SELECT 1 FROM RbacMigrations WHERE migration_key=?", block)
        self.assertIn("INSERT INTO RbacMigrations(migration_key) VALUES(?)", block)


class ArchiveBrowsingTests(unittest.TestCase):
    def test_archive_permissions_exist_and_are_separate(self):
        from rbac import ALL_PERMISSION_KEYS, default_permissions
        self.assertIn("archives.view", ALL_PERMISSION_KEYS)
        self.assertIn("archives.restore", ALL_PERMISSION_KEYS)
        finance = default_permissions("finance")
        self.assertIn("archives.view", finance)
        self.assertIn("archives.restore", finance)
        # Read-only roles may look but not bring records back.
        self.assertNotIn("archives.restore", default_permissions("support"))

    def test_every_financial_list_can_show_its_archive(self):
        py = src("v7_features.py")
        self.assertIn("def _archived_view", py)
        self.assertIn('"co.is_active=0" if archived else "co.is_active=1"', py)
        self.assertIn('" WHERE e.is_active=0" if archived else " WHERE e.is_active=1"', py)
        self.assertIn('" WHERE s.is_active=0" if archived else " WHERE s.is_active=1"', py)

    def test_archive_view_is_permission_gated_not_client_gated(self):
        py = src("v7_features.py")
        guard = py[py.index("def _archived_view"):py.index("def _restore_record")]
        # A crafted request without the permission must fall back to the live
        # list rather than exposing archived rows.
        self.assertIn("user_has_permission(g.user, 'archives.view')", guard)
        self.assertIn("return False", guard)

    def test_restore_endpoints_exist_and_are_double_gated(self):
        py = src("v7_features.py")
        self.assertIn("/api/contract_restore", py)
        self.assertIn("/api/extension_restore", py)
        self.assertIn("/api/statement_restore", py)
        restore = py[py.index("def _restore_record"):py.index("@app.route('/api/contract_restore'")]
        # Restoring needs both the archive-restore right and the right to
        # archive that particular record type.
        self.assertIn("'archives.restore'", restore)
        self.assertIn("user_has_permission(g.user, permission)", restore)
        self.assertIn("_entity_audit(cur, entity, ident, 'restore'", restore)
        rbac = src("rbac.py")
        for endpoint in ("api_v7_contract_restore", "api_v7_extension_restore",
                         "api_v7_statement_restore"):
            self.assertIn('"%s": "archives.restore"' % endpoint, rbac)

    def test_ui_offers_an_archive_toggle_on_all_three_pages(self):
        js = src("v7_ui.js")
        self.assertIn("function v7ToggleArchive", js)
        self.assertIn("function v7RestoreRecord", js)
        for kind in ("contract", "extension", "statement"):
            self.assertIn("v7ToggleArchive('%s')" % kind, js)
            self.assertIn("v7-%s-archive-banner" % kind, js)
        # Archived rows are read-only in the UI, matching the server.
        self.assertIn("v7-archived-row", js)
        self.assertIn("archived:v7ArchiveOn('contract')", js)
        self.assertIn("archived:v7ArchiveOn('extension')", js)
        self.assertIn("archived:v7ArchiveOn('statement')", js)


class EditInAnyStatusTests(unittest.TestCase):
    def test_statement_after_employer_decision_is_gated_not_hard_locked(self):
        py = src("v7_features.py")
        save = py[py.index("old_status = (old or {}).get('business_status')"):]
        save = save[:save.index("vals=[cid,typ,num")]
        # The old code returned 409 for everyone; it is now a permission check.
        self.assertNotIn("409", save)
        self.assertIn("statements.edit_any_status", save)

    def test_editing_an_approved_statement_voids_the_approval(self):
        py = src("v7_features.py")
        # Employer decision is cleared on every edit, and the internal
        # approval is dropped whenever the document falls back to draft, so a
        # changed figure can never keep an old signature.
        self.assertIn("employer_decision_by=NULL", py)
        self.assertIn("employer_decision_at=NULL", py)
        self.assertIn("if preserve_status == 'draft' and old_status != 'draft':", py)
        self.assertIn("internal_approved_by=NULL", py)

    def test_ui_mirrors_the_server_rule_and_warns_before_opening(self):
        js = src("v7_ui.js")
        can_edit = js[js.index("function v7CanEditStatement"):]
        can_edit = can_edit[:can_edit.index("\nfunction ")]
        self.assertIn("can('statements.edit_any_status')", can_edit)
        self.assertIn("تأییدیه کارفرما", js)

    def test_extension_edit_in_any_status_remains_permission_gated(self):
        py = src("v7_features.py")
        self.assertIn("extensions.edit_any_status", py)
        js = src("v7_ui.js")
        self.assertIn("can('extensions.edit_any_status')", js)


class SourceHygieneTests(unittest.TestCase):
    def test_no_source_file_carries_a_utf8_bom(self):
        # A BOM makes ast.parse fail even though import still works, which is
        # exactly how it slipped in unnoticed once.
        offenders = []
        for pattern in ("*.py", "*.js", "*.css", "*.html"):
            for path in list(ROOT.glob(pattern)) + list((ROOT / "tests").glob(pattern)):
                if path.read_bytes()[:3] == b"\xef\xbb\xbf":
                    offenders.append(path.name)
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
