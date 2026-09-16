# -*- coding: utf-8 -*-
"""Database bootstrap: tables are created at startup and the log says where."""
import ast
import pathlib
import unittest

from _paths import ROOT, SRC, project_file  # noqa: E402
SRC = (project_file("taskhub.py")).read_text(encoding="utf-8")
TREE = ast.parse(SRC)


def function(name):
    for node in TREE.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError("top-level function not found: " + name)


def source(name):
    return ast.get_source_segment(SRC, function(name))


class SystemDatabaseGuardTests(unittest.TestCase):
    def setUp(self):
        ns = {"_SYSTEM_DATABASES": ("master", "model", "msdb", "tempdb")}
        module = ast.Module(body=[function("_system_database_error")], type_ignores=[])
        exec(compile(module, "taskhub.py", "exec"), ns)
        self.check = ns["_system_database_error"]

    def test_the_real_list_covers_every_system_database(self):
        self.assertIn("_SYSTEM_DATABASES = ('master', 'model', 'msdb', 'tempdb')", SRC)

    def test_system_databases_are_refused(self):
        # An empty TASKHUB_DB_NAME lands in the login's default database.
        for name in ("master", "MASTER", "tempdb", " msdb "):
            self.assertIn("TASKHUB_DB_NAME", self.check(name), name)

    def test_the_application_database_is_accepted(self):
        for name in ("TaskHub", "TaskHub"):
            self.assertIsNone(self.check(name), name)


class BootstrapTests(unittest.TestCase):
    def test_connect_goes_through_the_shared_initializer(self):
        body = source("api_connect")
        self.assertIn("_initialize_database(log)", body)
        self.assertNotIn("init_tables()", body)

    def test_initializer_is_serialized_and_reports_its_target(self):
        body = source("_initialize_database")
        # Waiting callers must not hold one of the DB concurrency slots.
        self.assertLess(body.index("with _init_lock:"), body.index("with _db_lock:"))
        for token in ("@@SERVERNAME", "DB_NAME()", "SUSER_SNAME()", "SCHEMA_NAME()",
                      "database=", "default_schema=", "_system_database_error(",
                      "init_tables()", "Tables initialized OK"):
            self.assertIn(token, body, token)
        # The guard runs before anything is created.
        self.assertLess(body.index("_system_database_error("), body.index("init_tables()"))

    def test_tables_are_prepared_when_the_server_starts(self):
        body = source("main")
        self.assertIn("_initialize_database(log)", body)
        self.assertIn("threading.Thread(target=_startup_db_init", body)
        # Started before the headless branch hands over to the blocking server.
        self.assertLess(body.index("_startup_db_init"), body.index("if server_only:"))

    def test_lost_admin_password_file_is_logged(self):
        body = source("init_tables")
        block = body[body.index("pw_file = "):body.index("init_rbac_tables(c)")]
        self.assertIn("Could not write initial_admin_password.txt", block)
        self.assertNotRegex(block, r"\bpass\b")


if __name__ == "__main__":
    unittest.main()
