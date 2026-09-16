# -*- coding: utf-8 -*-
"""Behaviour tests for the 1.0.0 security fixes, run against a fake database."""
import json
import sys
import types
import unittest
from unittest import mock

from _paths import project_file  # also puts src on sys.path

import rbac
import taskhub
from api_errors import DB_ERROR_MESSAGE, SERVER_ERROR_MESSAGE, public_error

REMOTE = {"REMOTE_ADDR": "10.0.0.9"}
WRONG_LOGIN = "نام کاربری یا رمز عبور اشتباه است"


class FakeCursor:
    """Answers queries from a table name -> (columns, rows) map."""

    def __init__(self, tables=None, login_row=None):
        self.tables = tables or {}
        self.login_row = login_row
        self.executed = []
        self.description = None
        self._rows = []

    def execute(self, sql, *params):
        self.executed.append((sql, params))
        self.description, self._rows = None, []
        if sql.startswith("SELECT * FROM "):
            columns, rows = self.tables.get(sql[len("SELECT * FROM "):], (["id"], []))
            self.description = [(name,) for name in columns]
            self._rows = list(rows)
        elif "FROM Users WHERE username=?" in sql and self.login_row:
            self._rows = [self.login_row]
        return self

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def commit(self):
        pass


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.client = taskhub.flask_app.test_client()
        taskhub._login_fails.clear()
        for name in ("_audit", "_close_stale_attendance", "_attendance_check_in"):
            patcher = mock.patch.object(taskhub, name, lambda *a, **k: None)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(taskhub._login_fails.clear)

    def use_db(self, cursor):
        patcher = mock.patch.object(taskhub, "get_conn", lambda: FakeConnection(cursor))
        patcher.start()
        self.addCleanup(patcher.stop)

    def login(self, password, forwarded_for=None):
        headers = {"X-Forwarded-For": forwarded_for} if forwarded_for else {}
        response = self.client.post("/api/login", json={"username": "ali", "password": password},
                                    headers=headers, environ_base=REMOTE)
        return response.get_json()


class ClientAddressTests(AppTestCase):
    def test_forwarded_for_header_is_ignored(self):
        with taskhub.flask_app.test_request_context(
                "/", headers={"X-Forwarded-For": "1.2.3.4"}, environ_base=REMOTE):
            self.assertEqual(taskhub._client_ip(), "10.0.0.9")

    def test_rotating_forwarded_for_does_not_escape_the_lockout(self):
        self.use_db(FakeCursor())
        for attempt in range(taskhub._LOGIN_MAX_FAILS):
            self.assertEqual(self.login("guess", "203.0.113.%d" % attempt)["error"], WRONG_LOGIN)
        blocked = self.login("guess", "198.51.100.77")
        self.assertIn("تلاش‌های ناموفق زیاد", blocked["error"])


class LoginTests(AppTestCase):
    def setUp(self):
        super().setUp()
        disabled = (7, "ali", taskhub._hash_pw("correct-password"), "support", "Ali",
                    None, None, None, 0)
        self.use_db(FakeCursor(login_row=disabled))

    def test_disabled_account_is_not_revealed_without_the_password(self):
        self.assertEqual(self.login("wrong-password")["error"], WRONG_LOGIN)

    def test_disabled_account_is_reported_after_the_right_password(self):
        self.assertEqual(self.login("correct-password")["error"], "این حساب غیرفعال شده است")

    def test_password_check(self):
        stored = taskhub._hash_pw("s3cret-pass")
        self.assertTrue(taskhub._verify_pw("s3cret-pass", stored))
        self.assertFalse(taskhub._verify_pw("s3cret-pasS", stored))
        self.assertFalse(taskhub._verify_pw("s3cret-pass", "not-a-hash"))


class GenericSqlEndpointTests(AppTestCase):
    def test_endpoints_are_gone(self):
        routes = {rule.rule for rule in taskhub.flask_app.url_map.iter_rules()}
        self.assertNotIn("/api/query", routes)
        self.assertNotIn("/api/run", routes)
        self.assertEqual(self.client.post("/api/run", json={"sql": "SELECT 1"}).status_code, 404)

    def test_permission_is_retired_and_cleaned_from_the_database(self):
        self.assertNotIn("system.sql", rbac.ALL_PERMISSION_KEYS)
        cursor = FakeCursor()
        cursor.fetchone = lambda: (1,)  # every one-time migration counts as applied
        rbac.init_rbac_tables(FakeConnection(cursor))
        self.assertIn(("DELETE FROM RolePermissions WHERE permission_key=?", ("system.sql",)),
                      cursor.executed)

    def test_ui_no_longer_sends_raw_sql(self):
        html = project_file("ui.html").read_text(encoding="utf-8")
        self.assertNotIn("api('/query'", html)
        self.assertNotIn("api('/run'", html)


class DataExportTests(AppTestCase):
    def test_export_leaves_out_password_hashes(self):
        admin = {"id": 1, "username": "admin", "role": "admin",
                 "permissions": sorted(rbac.ALL_PERMISSION_KEYS)}
        patcher = mock.patch.object(taskhub, "_current_user", lambda: admin)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.use_db(FakeCursor(tables={
            "Users": (["id", "username", "password_hash"], [(1, "admin", "salt$hash")]),
        }))
        response = self.client.post("/api/data_export", json={}, environ_base=REMOTE)
        self.assertEqual(response.status_code, 200)
        dump = json.loads(response.get_data(as_text=True))
        response.close()
        self.assertEqual(dump["Users"], [{"id": 1, "username": "admin"}])


class PublicErrorTests(unittest.TestCase):
    def message(self, exc, remote_addr="10.0.0.9", logged=True):
        with taskhub.flask_app.test_request_context("/", environ_base={"REMOTE_ADDR": remote_addr}):
            if not logged:
                return public_error(exc)
            with self.assertLogs("taskhub", level="ERROR"):
                return public_error(exc)

    def test_database_details_stay_out_of_remote_responses(self):
        # Other tests replace pyodbc with a stub, so stand in a driver module here.
        class DriverError(Exception):
            pass
        with mock.patch.dict(sys.modules, {"pyodbc": types.SimpleNamespace(Error=DriverError)}):
            exc = DriverError("08001", "[SQL Server] Login failed for user 'taskhub_app' on SQL01")
            self.assertEqual(self.message(exc), DB_ERROR_MESSAGE)

    def test_unexpected_errors_are_generic_for_remote_clients(self):
        self.assertEqual(self.message(OSError(r"D:\taskhub\data\files missing")), SERVER_ERROR_MESSAGE)

    def test_messages_written_for_users_pass_through(self):
        self.assertEqual(self.message(ValueError("عنوان الزامی است"), logged=False), "عنوان الزامی است")
        self.assertEqual(self.message(PermissionError("دسترسی ندارید"), logged=False), "دسترسی ندارید")

    def test_the_server_machine_still_sees_the_real_error(self):
        exc = RuntimeError("database name is empty")
        self.assertEqual(self.message(exc, remote_addr="127.0.0.1"), "database name is empty")


if __name__ == "__main__":
    unittest.main()
