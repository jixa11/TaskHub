# -*- coding: utf-8 -*-
"""Regression checks for the R8 task-report approval-date filter."""
from pathlib import Path
import unittest

from _paths import ROOT, SRC, project_file  # noqa: E402

def src(name):
    return project_file(name).read_text(encoding="utf-8")

class R8TaskReportDateTests(unittest.TestCase):
    def test_report_filter_uses_completed_at_not_registration_date(self):
        ui = src("ui.html")
        report = ui[ui.index("// ── Report"):ui.index("// ── Time report")]
        self.assertIn("task&&task.completed_at", report)
        self.assertIn("const approvalDate=taskApprovalJalaliDate(t)", report)
        self.assertIn("if((rfKey||rtoKey)&&!approvalDate)return false", report)
        self.assertNotIn("t.date_recv<rf", report)
        self.assertNotIn("t.date_recv>rto", report)

    def test_unapproved_tasks_are_excluded_only_when_a_date_range_is_used(self):
        ui = src("ui.html")
        self.assertIn("if((rfKey||rtoKey)&&!approvalDate)return false", ui)
        self.assertIn("if(rfKey&&approvalDate<rfKey)return false", ui)
        self.assertIn("if(rtoKey&&approvalDate>rtoKey)return false", ui)

    def test_grid_and_exports_show_final_approval_date(self):
        ui = src("ui.html")
        py = src("taskhub.py")
        self.assertIn("تاریخ تأیید تسک", ui)
        self.assertIn("t.report_completed_date = taskApprovalJalaliDate(t)", ui)
        self.assertIn("تاریخ تأیید تسک", py)
        self.assertIn("t.get('report_completed_date','')", py)

    def test_release_cache_is_r8(self):
        self.assertIn("APP_VERSION = '1.0.0'", src("config.py"))
        self.assertIn("TaskHub.exe", src("build.bat"))
        self.assertIn("taskhub-v1-0-0-static", src("service-worker.js"))

if __name__ == "__main__":
    unittest.main()
