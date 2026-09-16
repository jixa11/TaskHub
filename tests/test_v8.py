# -*- coding: utf-8 -*-
import ast
import pathlib
import subprocess
import unittest
from decimal import Decimal


from _paths import ROOT, SRC, project_file  # noqa: E402

from v8_domain import (  # noqa: E402
    person_output_shares,
    project_progress,
    team_completion_shares,
    validate_team_allocations,
)


class V8BusinessRulesTests(unittest.TestCase):
    def test_shared_contract_allocations_may_be_partial_but_not_overrun(self):
        ok, message, gap = validate_team_allocations(1_000, [400, 300])
        self.assertTrue(ok)
        self.assertIsNone(message)
        self.assertEqual(gap, Decimal("300"))
        self.assertFalse(validate_team_allocations(1_000, [800, 300])[0])

    def test_project_progress_is_weighted_and_non_monetary(self):
        result = project_progress([
            {"status": "done", "progress_weight": 3},
            {"status": "doing", "progress_weight": 1},
        ])
        self.assertEqual(result["progress_percent"], Decimal("75.00"))

    def test_team_output_share_counts_each_task_once(self):
        result = team_completion_shares([
            {"status": "done", "team_id": 1, "progress_weight": 3},
            {"status": "done", "team_id": 2, "progress_weight": 1},
        ])
        self.assertEqual(result[1]["share_percent"], Decimal("75.00"))
        self.assertEqual(result[2]["share_percent"], Decimal("25.00"))

    def test_person_output_uses_time_and_never_guesses_multi_assignee(self):
        tasks = [
            {"id": 1, "status": "done", "progress_weight": 4,
             "staff_id": 10, "helper_ids": [11]},
            {"id": 2, "status": "done", "progress_weight": 2,
             "staff_id": 10, "helper_ids": [11]},
            {"id": 3, "status": "done", "progress_weight": 1,
             "staff_id": 12, "helper_ids": []},
        ]
        result = person_output_shares(tasks, [
            {"task_id": 1, "user_id": 10, "seconds": 3},
            {"task_id": 1, "user_id": 11, "seconds": 1},
        ])
        self.assertEqual(result["rows"][10]["output_weight"], Decimal("3.0000"))
        self.assertEqual(result["rows"][11]["output_weight"], Decimal("1.0000"))
        self.assertEqual(result["rows"][12]["output_weight"], Decimal("1.0000"))
        self.assertEqual(result["incomplete_task_ids"], [2])


class V8StructuralTests(unittest.TestCase):
    def source(self, name):
        return project_file(name).read_text(encoding="utf-8")

    def function_ast(self, path, function):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        node = next(
            x for x in tree.body
            if isinstance(x, ast.FunctionDef) and x.name == function
        )
        return ast.dump(node, include_attributes=False)

    def test_connection_string_function_is_still_621_compatible(self):
        old = ROOT.parent / "review-v621" / "TaskHub_v6.2.1_fixed" / "config.py"
        if not old.exists():
            self.skipTest("v6.2.1 comparison source is outside package")
        self.assertEqual(
            self.function_ast(old, "connection_string"),
            self.function_ast(project_file("config.py"), "connection_string"),
        )

    def test_normalized_team_schema_and_default_migration_exist(self):
        py = self.source("v8_features.py")
        for table in (
            "Teams", "TeamMembers", "TeamProjectTypes", "ProjectTeams",
            "ContractProjectTeams", "ContractStatementTeams",
            "TeamFinancialTargets",
        ):
            self.assertIn("OBJECT_ID('%s','U')" % table, py)
        self.assertIn("code='legacy-default'", py)
        self.assertIn("N'تیم فعلی'", py)
        self.assertIn("UPDATE t SET project_team_id=pt.id", py)
        self.assertIn("allocation_percent DECIMAL(9,4) NOT NULL", py)
        self.assertIn("migration_key='default_team_v1'", py)

    def test_joint_statement_allocations_prevent_double_counting(self):
        py = self.source("v7_features.py") + self.source("v8_features.py")
        js = self.source("v8_ui.js")
        self.assertIn("جمع سهم درصدی تیم‌های صورت‌وضعیت باید دقیقاً ۱۰۰ باشد", py)
        self.assertIn("*cst.allocation_percent/100", py)
        self.assertIn("COUNT(DISTINCT s.id) AS statement_count", py)
        self.assertIn("statement_allocation_invalid", py)
        self.assertIn("function v8StatementEqualSplit", js)
        self.assertIn("function v8SaveStatementTeams", js)
        self.assertIn("/api/statement_teams_save", py)
        self.assertIn("statement_teams", self.source("v7_ui.js"))

    def test_team_distinction_is_only_on_operational_entities(self):
        py = self.source("v8_features.py")
        self.assertIn("Tasks','project_team_id", py)
        self.assertIn("ContractStatements','project_team_id", py)
        self.assertIn("PlannedStatements','project_team_id", py)
        self.assertNotIn("Contracts','ResponsibleTeamId", py)
        self.assertNotIn("Tasks','planned_amount", py)

    def test_shared_project_report_uses_independent_aggregates(self):
        py = self.source("v8_features.py")
        block = py[py.index("def shared_projects_report"):
                   py.index("def data_quality_report")]
        self.assertGreaterEqual(block.count("OUTER APPLY"), 3)
        self.assertIn("Every metric is aggregated in its own APPLY", block)

    def test_e2ee_schema_has_no_private_key_or_plaintext_body(self):
        py = self.source("v8_features.py")
        schema = py[py.index("IF OBJECT_ID('ChatDevices'"):
                    py.index("IF OBJECT_ID('V8MigrationState'")]
        self.assertIn("public_key_jwk", schema)
        self.assertIn("ciphertext NVARCHAR(MAX)", schema)
        self.assertNotIn("private_key", schema.lower())
        self.assertNotIn("plaintext", schema.lower())
        self.assertIn("if any(x in public_obj", py)
        self.assertIn("ارسال کلید خصوصی به سرور ممنوع است", py)

    def test_browser_crypto_and_local_search_are_present(self):
        js = self.source("v8_ui.js")
        self.assertIn("RSA-OAEP", js)
        self.assertIn("AES-GCM", js)
        self.assertIn("indexedDB.open('TaskHubChatCryptoV8'", js)
        self.assertIn("جستجو در همین گفتگو", js)
        self.assertNotIn("/chat/search", js)
        self.assertIn("v8ChatSaveMembers", js)
        self.assertIn("/v8/chat/conversation_members_save", js)

    def test_team_mutations_preserve_operational_history(self):
        py = self.source("v8_features.py")
        self.assertIn("این تیم سابقه عملیاتی یا مالی دارد", py)
        self.assertIn("جریان کاری دارای سابقه است", py)
        self.assertIn("این جریان کاری سابقه عملیاتی یا مالی دارد", py)
        self.assertIn("هنوز روی تسک باز این تیم مسئولیت دارد", py)
        self.assertIn("اتصال تیمی دارای سابقه است و قابل حذف نیست", py)

    def test_team_financial_save_does_not_audit_inside_db_lock(self):
        py = self.source("v8_features.py")
        block = py[py.index("def api_v8_team_financial_plan"):
                   py.index("def dashboard_report")]
        commit = block.index("c.commit()")
        audit = block.index('audit("v8_team_financial_target"')
        self.assertGreater(audit, commit)
        self.assertIn("if audit_detail:", block)

    def test_report_export_mirrors_configured_report_permissions(self):
        py = self.source("v8_features.py")
        block = py[py.index("def api_v8_report_export"):
                   py.index("# ── Organizational chat")]
        self.assertIn('user_has_permission(g.user, "reports.export")', block)
        self.assertIn('user_has_permission(g.user, "reports.financial")', block)
        self.assertIn('user_has_permission(g.user, "reports.capacity")', block)
        self.assertIn('Export uses the same authorized team rows as the UI', block)

    def test_imported_tasks_receive_a_team_workstream(self):
        py = self.source("taskhub.py")
        block = py[py.index("@flask_app.route('/api/import'"):
                   py.index("def api_winaction")]
        self.assertIn("project_team_id", block)
        self.assertIn("ProjectTeams", block)
        # R16: import can be granted to other roles, so it keeps to their teams.
        self.assertIn("project_teams = [x for x in project_teams if x[1] in actor_teams]", block)

    def test_active_sessions_have_presence_columns_and_stale_cleanup(self):
        py = self.source("taskhub.py")
        self.assertIn("COL_LENGTH('Sessions','last_seen')", py)
        self.assertIn("COL_LENGTH('Sessions','ip_address')", py)
        self.assertIn("COL_LENGTH('Sessions','user_agent')", py)
        self.assertIn(
            "last_seen < DATEADD(hour,-2,GETDATE())", py
        )
        self.assertIn("grouped.setdefault(uid", py)
        self.assertIn("item['session_count'] += 1", py)

    def test_menu_help_changelog_and_new_version_are_wired(self):
        js = self.source("v8_ui.js")
        html = self.source("ui.html")
        self.assertIn("data-pg=\"22\"", js)
        self.assertIn("data-pg=\"23\"", js)
        self.assertIn("data-pg=\"24\"", js)
        self.assertIn("data-pg=\"25\"", js)
        self.assertIn("initV7UI();initV8UI();initGameUI();boot();", html)
        self.assertIn("در نسخه LAN، پیام‌های جدید روی سرور مدیریت می‌شوند", js)
        self.assertIn("APP_VERSION = '1.0.0'", self.source("config.py"))
        self.assertIn("run_lan_checks.py", self.source("build.bat"))
        self.assertIn("TaskHubBackup_v8.exe", self.source("backup.bat"))


    def test_801_messenger_bootstrap_mobile_and_pwa_are_wired(self):
        js = self.source("v8_ui.js")
        py = self.source("v8_features.py")
        html = self.source("ui.html")
        config = self.source("config.py")
        self.assertIn("function v8ChatEnsureDevice", js)
        self.assertIn("function v8ChatEnsureConversationReady", js)
        self.assertIn("v8ChatUserPrefix", js)
        self.assertIn("user:'+(CU&&CU.id", js)
        bootstrap = js[js.index("async function v8ChatEnsureDevice"):js.index("function v8ChatCopyApprovalCode") ]
        self.assertNotIn("confirm(", bootstrap)
        self.assertIn("key_rotation_begin", py)
        self.assertIn("ارسال کلید خصوصی به سرور ممنوع است", py)
        self.assertIn("پیامرسان", js)
        self.assertIn("گروه تیم", js)
        self.assertIn("rel=\"manifest\"", html)
        self.assertIn("serviceWorker.register", html)
        self.assertIn("SSL_CERT_FILE", config)
        self.assertIn("SSL_KEY_FILE", config)
        self.assertTrue((project_file("manifest.webmanifest")).exists())
        self.assertTrue((project_file("service-worker.js")).exists())

    def test_801_device_approval_and_rotation_claim_are_server_enforced(self):
        py = self.source("v8_features.py")
        js = self.source("v8_ui.js")
        for endpoint in (
            "/api/v8/chat/devices",
            "/api/v8/chat/device_approval_challenge",
            "/api/v8/chat/device_approve",
            "/api/v8/chat/key_rotation_claim",
        ):
            self.assertIn(endpoint, py)
        self.assertIn("approval_challenge_hash", py)
        self.assertIn("rotation_claim_hash", py)
        self.assertIn("reset_device_uuid=True", py)
        self.assertIn("Never replace an approved browser key silently", py)
        self.assertIn("مجوز ساخت کلید متعلق به این دستگاه نیست", py)
        self.assertIn("device_id:V8.chat.device.id", js)
        self.assertIn("v8ChatApproveDevice", js)
        self.assertIn("encrypted_challenge", js)

    def test_801_private_key_is_persisted_as_non_extractable_cryptokey(self):
        js = self.source("v8_ui.js")
        block = js[js.index("async function v8ChatDeviceKeys"):
                   js.index("async function v8ChatEnsureDevice")]
        self.assertIn("privateKey:privateKey", block)
        self.assertIn("false,['decrypt']", block)
        self.assertIn("migratedAt", block)
        self.assertNotIn("privatePkcs8:v8B64", block)

    def test_801_mobile_header_and_secure_pwa_styles_exist(self):
        css = self.source("v8_ui.css")
        html = self.source("ui.html")
        py = self.source("taskhub.py")
        self.assertIn(".v8-user-copy", css)
        self.assertIn(".v8-chat-shell.mobile-open", css)
        self.assertIn("100dvh", css)
        self.assertIn("env(safe-area-inset-bottom)", css)
        self.assertIn("viewport-fit=cover", html)
        self.assertNotIn("maximum-scale=1", html)
        self.assertIn("Strict-Transport-Security", py)
        self.assertIn("url.pathname.startsWith('/api/')", self.source("service-worker.js"))

    def test_801_messenger_documentation_is_present(self):
        readme = self.source("README_V8_0_2_FA.md")
        guide = self.source("docs/MESSENGER_SETUP_FA.md")
        report = self.source("docs/history/TEST_REPORT_V8_FA.md")
        self.assertIn("TaskHub 8.0.2", readme)
        self.assertIn("هیچ برنامه، افزونه یا ابزار جداگانه‌ای", readme)
        self.assertIn("کد شش‌رقمی", guide)
        self.assertIn("کنترل کامل سرور", guide)
        self.assertIn("آزمون‌هایی که در این محیط اجرا نشدند", report)

    def test_v8_literal_sql_execute_marker_counts(self):
        tree = ast.parse(self.source("v8_features.py"))
        mismatches = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and
                    isinstance(node.func, ast.Attribute) and
                    node.func.attr == "execute" and node.args):
                continue
            sql_node = node.args[0]
            if not (isinstance(sql_node, ast.Constant) and
                    isinstance(sql_node.value, str)):
                continue
            marker_count = sql_node.value.count("?")
            supplied = len(node.args) - 1
            if supplied == 1 and not isinstance(node.args[1], ast.Constant):
                continue
            if marker_count != supplied:
                mismatches.append((node.lineno, marker_count, supplied))
        self.assertEqual(mismatches, [])

    def test_project_type_migration_is_split_across_execute_calls(self):
        py = self.source("v7_features.py")
        self.assertIn("These statements are intentionally", py)
        self.assertIn('"UPDATE Projects SET project_type_id=0 WHERE project_type_id IS NULL"', py)
        block = py[py.index("IF OBJECT_ID('ProjectTypes'"):py.index("IF OBJECT_ID('ContractTypes'")]
        self.assertNotIn("ALTER TABLE Projects ADD project_type_id INT NOT NULL\n                  CONSTRAINT DF_Projects_project_type DEFAULT 0 WITH VALUES\n           UPDATE Projects", block)

    def test_javascript_parses(self):
        try:
            for name in ("v7_ui.js", "v8_ui.js"):
                result = subprocess.run(
                    ["node", "--check", str(project_file(name))],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
        except FileNotFoundError:
            self.skipTest("node is unavailable")


if __name__ == "__main__":
    unittest.main()
