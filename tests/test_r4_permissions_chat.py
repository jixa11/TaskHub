# -*- coding: utf-8 -*-
import ast
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from cryptography.fernet import Fernet

from _paths import ROOT, SRC, project_file  # noqa: E402

from lan_chat_crypto import ServerChatCrypto
from rbac import (
    ALL_PERMISSION_KEYS,
    ENDPOINT_PERMISSIONS,
    MENU_PERMISSION_BY_PAGE,
    NON_DELEGABLE,
    default_permissions,
    permission_for_request,
)


def src(name):
    return project_file(name).read_text(encoding="utf-8")


class R5PermissionMatrixTests(unittest.TestCase):
    def test_manager_runs_a_team_and_reads_but_never_writes_the_ledger(self):
        # R12: the manager kept every operational permission but hands the
        # writing of financial records to the finance specialist. Their view
        # of those records is narrowed to their own team by team_scope, not by
        # a permission.
        from rbac import _MANAGER_EXCLUDED

        manager = default_permissions("manager")
        self.assertEqual(manager,
                         set(ALL_PERMISSION_KEYS) - set(NON_DELEGABLE) - set(_MANAGER_EXCLUDED))
        # R16: the admin-only tools are locked on the access screen too.
        self.assertEqual(NON_DELEGABLE, {"access_control.manage", "system.data_export",
                                         "system.backup", "system.sessions", "system.autostart"})
        for key in ("contracts.view", "extensions.view", "statements.view",
                    "financial_plan.view", "reports.financial",
                    "dashboard.financial", "team_financial.manage"):
            self.assertIn(key, manager, key)
        for key in ("contracts.manage", "contracts.approve", "contracts.archive",
                    "statements.manage", "statements.internal_approve",
                    "statements.employer_status", "extensions.approve",
                    "financial_plan.manage"):
            self.assertNotIn(key, manager, key)
        # Running the team is untouched: create work, do it, and judge it.
        for key in ("tasks.create", "tasks.work", "tasks.assign",
                    "tasks.triage", "tasks.approve", "tasks.evaluate"):
            self.assertIn(key, manager, key)

    def test_planner_mirrors_the_manager_except_money_and_leave_approval(self):
        # R12 narrowed the planner. Everything outside the two documented
        # carve-outs must still match the manager exactly, so a permission
        # added later is not silently withheld from the planner.
        from rbac import _PLANNER_EXCLUDED

        manager = default_permissions("manager")
        planner = default_permissions("planner")
        # R13: the planner holds a wallet and the manager does not.
        wallet = {"gamification.view_own", "shop.buy"}
        self.assertEqual(planner, (manager - set(_PLANNER_EXCLUDED)) | wallet)
        self.assertNotIn("leave.manage", planner)
        self.assertIn("leave.view", planner)
        self.assertIn("leave.request", planner)
        # Planning still links a contract to a task; that exposes no amounts.
        self.assertIn("tasks.link_contract", planner)
        for key in planner:
            self.assertFalse(
                key.startswith(("contracts.", "extensions.", "statements.",
                                "financial_plan.", "archives.")),
                key,
            )

    def test_catalog_covers_menus_and_major_operation_types(self):
        required = {
            "menu.dashboard", "menu.projects", "menu.tasks", "menu.users",
            "menu.contracts", "menu.reports", "tasks.create", "tasks.edit",
            "tasks.delete", "tasks.assign", "tasks.approve", "tasks.evaluate",
            "users.create", "users.edit", "users.delete", "users.reset_password",
            "projects.manage", "contracts.manage", "contracts.approve",
            "contracts.archive", "attachments.upload", "attachments.archive",
            "reports.view", "reports.export", "system.backup", "system.audit",
            "chat.use", "chat.manage_groups", "access_control.manage",
        }
        self.assertTrue(required.issubset(ALL_PERMISSION_KEYS))
        self.assertTrue(set(ENDPOINT_PERMISSIONS.values()).issubset(ALL_PERMISSION_KEYS))
        self.assertTrue(set(MENU_PERMISSION_BY_PAGE.values()).issubset(ALL_PERMISSION_KEYS))

    def test_task_create_and_edit_resolve_to_distinct_server_permissions(self):
        manager = {"role": "manager", "permissions": sorted(default_permissions("manager"))}
        self.assertEqual(permission_for_request("api_v7_task_save", {}, manager), "tasks.create")
        self.assertEqual(permission_for_request("api_v7_task_save", {"id": 12}, manager), "tasks.edit")
        self.assertEqual(permission_for_request("api_v7_task_delete", {"id": 12}, manager), "tasks.delete")
        self.assertEqual(permission_for_request("api_task_transition", {"action": "assign"}, manager), "tasks.assign")
        self.assertEqual(permission_for_request("api_task_transition", {"action": "approve"}, manager), "tasks.approve")

    def test_admin_only_access_control_cannot_be_delegated(self):
        py = src("taskhub.py")
        js = src("v8_ui.js")
        self.assertIn("@flask_app.route('/api/role_permissions'", py)
        self.assertIn("@flask_app.route('/api/role_permissions_save'", py)
        self.assertGreaterEqual(py.count("@require_roles('admin')"), 2)
        self.assertIn("selected.difference_update(NON_DELEGABLE)", py)
        self.assertIn('data-permission="access_control.manage"', js)
        self.assertIn("منوی مدیریت دسترسی‌ها فقط برای مدیر سیستم است", js)

    def test_permission_ui_controls_task_menu_dashboard_button_and_edit_button(self):
        html = src("ui.html")
        self.assertIn("6:'menu.tasks'", html)
        # R14: the group lead opens the same task form through tasks.create_for_group.
        self.assertIn("mt:'tasks.create,tasks.create_for_group'", html)
        self.assertIn('data-open="mt"', html)
        self.assertIn("if(can('tasks.edit')) return true", html)
        self.assertIn("${canEditTask(t)?", html)
        self.assertIn("if(can('tasks.triage'))", html)
        self.assertIn("if(can('tasks.assign'))actionButtons.push", html)
        self.assertIn("@flask_app.before_request", src("taskhub.py"))
        self.assertIn("permission_for_request(endpoint, data, user)", src("taskhub.py"))


    def test_frontend_and_task_scopes_are_permission_driven(self):
        html = src("ui.html")
        v7 = src("v7_ui.js")
        py = src("v7_features.py")
        self.assertIn("function defaultLandingPage()", html)
        self.assertIn("function canAny(value)", html)
        self.assertIn('data-permission-any="tasks.create,tasks.self_manage,tasks.create_for_group"', html)
        self.assertIn("if(el.hasAttribute('data-permission')||el.hasAttribute('data-permission-any')", html)
        self.assertIn("if(can('tasks.self_manage')) return", html)
        self.assertIn("can('tasks.work')&&isOnTask", v7)
        self.assertIn("user_has_permission(u, 'tasks.self_manage')", py)
        self.assertIn("user_has_permission(u, 'tasks.work')", py)
        self.assertIn("Visibility is permission-driven", py)

    def test_all_role_guarded_endpoints_are_permission_mapped_except_admin_acl(self):
        dynamic = {
            "api_user_save", "api_v7_master_save", "api_v7_master_delete",
            "api_v7_task_save", "api_v7_task_delete", "api_task_transition",
            "api_autostart", "api_leave_save", "api_leave_update",
            "api_leave_delete", "api_v8_team_financial_plan",
            "api_contract_task_weights", "api_v8_chat_conversation_create",
        }
        admin_only = {"api_role_permissions", "api_role_permissions_save"}
        missing = []
        for filename in ("taskhub.py", "v7_features.py", "v8_features.py", "v802_features.py"):
            tree = ast.parse(src(filename))
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                guarded = any(
                    isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name)
                    and dec.func.id == "require_roles"
                    for dec in node.decorator_list
                )
                if guarded and node.name not in ENDPOINT_PERMISSIONS and node.name not in dynamic and node.name not in admin_only:
                    missing.append((filename, node.lineno, node.name))
        self.assertEqual(missing, [])

    def test_all_frontend_permission_keys_exist_in_catalog(self):
        combined = src("ui.html") + src("v7_ui.js") + src("v8_ui.js")
        referenced = set(re.findall(r"data-permission=['\"]([^'\"]+)", combined))
        referenced.update(re.findall(r"can\(['\"]([^'\"]+)", combined))
        unknown = sorted(x for x in referenced if x not in ALL_PERMISSION_KEYS)
        self.assertEqual(unknown, [])

    def test_manager_planner_parity_migration_is_once_only(self):
        rbac = src("rbac.py")
        self.assertIn("r4_manager_planner_admin_parity_v1", rbac)
        self.assertIn("if not cur.fetchone():", rbac)
        self.assertIn("for role in ('manager', 'planner')", rbac)
        # Every role migration must stay once-only so an administrator's later
        # choices survive a restart.
        self.assertIn("so later administrator choices are preserved", rbac)

    def test_admin_account_is_protected_from_delegated_roles(self):
        py = src("taskhub.py")
        html = src("ui.html")
        self.assertIn("ساخت یا تغییر نقش‌های سراسری فقط برای مدیر سیستم مجاز است", py)
        self.assertIn("if(['admin','finance','reporter'].indexOf(u.role)>=0)return CU&&CU.role==='admin'", html)
        self.assertIn("if(['admin','finance','reporter'].indexOf(role)>=0)return CU&&CU.role==='admin'", html)

    def test_r5_version_and_build_output(self):
        self.assertIn("APP_VERSION = '1.0.0'", src("config.py"))
        self.assertIn("TaskHub.exe", src("build.bat"))
        self.assertIn("TaskHub.exe", src("Run_TaskHub.cmd"))


class R5DurableChatTests(unittest.TestCase):
    def test_server_crypto_survives_restart_using_authoritative_provider(self):
        key = Fernet.generate_key()
        with tempfile.TemporaryDirectory() as temp:
            first = ServerChatCrypto(temp, key_provider=lambda: key)
            message_token = first.encrypt_json({"text": "سلام", "id": 42})
            file_token = first.encrypt_bytes(b"chat-file\x00\xff")

            # Simulate a fresh process/login. Even if the compatibility mirror
            # is unavailable, the durable provider returns the same SQL key.
            mirror = Path(temp) / "taskhub_data" / "server_chat_fernet.key"
            if mirror.exists():
                mirror.unlink()
            second = ServerChatCrypto(temp, key_provider=lambda: key)
            self.assertEqual(second.decrypt_json(message_token), {"text": "سلام", "id": 42})
            self.assertEqual(second.decrypt_bytes(file_token), b"chat-file\x00\xff")

    def test_lan_config_forces_server_chat_even_with_stale_e2e_setting(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "taskhub_config.json"
            config_path.write_text(json.dumps({
                "TASKHUB_CHAT_MODE": "e2e",
                "TASKHUB_HOST": "127.0.0.1",
                "TASKHUB_LAN_HTTP_ONLY": True,
            }), encoding="utf-8")
            probe = subprocess.run(
                [sys.executable, "-c", "import config; print(config.CHAT_MODE, config.HOST, config.URL_SCHEME)"],
                cwd=str(SRC),
                env={**os.environ, "TASKHUB_CONFIG": str(config_path)},
                capture_output=True,
                text=True,
            )
            self.assertEqual(probe.returncode, 0, probe.stderr)
            self.assertEqual(probe.stdout.strip(), "server 0.0.0.0 http")

    def test_database_key_is_authoritative_and_old_lan_key_is_imported(self):
        py = src("v8_features.py")
        crypto = src("lan_chat_crypto.py")
        for marker in (
            "ApplicationSecrets", "server_chat_fernet_v1", "legacy_key or Fernet.generate_key()",
            "WITH (UPDLOCK,HOLDLOCK)", "_LazyServerChat", "key_provider=durable_server_chat_key",
        ):
            self.assertIn(marker, py)
        self.assertIn("Atomically mirror the authoritative key", crypto)
        self.assertIn("os.replace(temp_path, self.key_path)", crypto)

    def test_help_explains_durable_server_chat_and_removes_old_device_key_guidance(self):
        combined = src("ui.html") + src("v8_ui.js")
        self.assertIn("کلید پایدار ذخیره‌شده در دیتابیس", combined)
        self.assertIn("پس از ورود مجدد یا راه‌اندازی دوباره سرور قابل خواندن باقی می‌مانند", combined)
        self.assertNotIn("کلید خصوصی فقط در فضای امن همان مرورگر", combined)
        self.assertNotIn("برای اینکه Web Crypto", combined)


if __name__ == "__main__":
    unittest.main(verbosity=2)
