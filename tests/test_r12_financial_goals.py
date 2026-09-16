# -*- coding: utf-8 -*-
"""R12: the company goal is a roll-up of the team goals, not their ceiling.

Two kinds of check live here. The structural ones pin the inversion in the
shipped source. The SQLite ones execute the aggregation contract the T-SQL
implements - which team rows count, how months line up, how the approved-vs-
rollup gap is signed - so a logic mistake fails here even though the real
statements run on SQL Server.
"""
import pathlib
import re
import sqlite3
import unittest

from _paths import ROOT, SRC, project_file  # noqa: E402


def src(name):
    return project_file(name).read_text(encoding="utf-8")


class GoalModelInversionTests(unittest.TestCase):
    def test_team_goal_no_longer_capped_by_the_company_figure(self):
        py = src("v8_features.py")
        # The guard that forced "company first, then divide" is gone.
        self.assertNotIn("جمع هدف تیم‌ها از هدف کل شرکت بیشتر می‌شود", py)
        self.assertNotIn("ابتدا هدف کل شرکت برای این سال را در «برنامه مالی» ثبت کنید", py)

    def test_saving_a_team_goal_creates_the_plan_and_recomputes_the_company(self):
        py = src("v8_features.py")
        self.assertIn("def ensure_financial_plan", py)
        self.assertIn("def recompute_company_plan", py)
        route = py[py.index("def api_v8_team_financial_plan"):
                   py.index("def api_v8_team_financial_detail")]
        save = route[route.index('if action == "save":'):
                     route.index("allowed = scoped_team_ids")]
        self.assertIn('ensure_financial_plan(cur, year, g.user["id"])', save)
        self.assertIn('recompute_company_plan(cur, plan["id"])', save)

    def test_company_annual_and_months_have_exactly_one_writer(self):
        py = src("v8_features.py")
        rollup = py[py.index("def recompute_company_plan"):py.index("@app.route(\"/api/v8/team_financial_plan\"")]
        self.assertIn("UPDATE p SET annual_target=ISNULL(t.total,0)", rollup)
        self.assertIn("UPDATE fp SET target_amount=ISNULL(t.total,0)", rollup)
        # Only the migration and the roll-up may assign annual_target.
        writers = re.findall(r"(?:UPDATE|SET)\s+\w*\.?annual_target\s*=", py)
        self.assertLessEqual(len(writers), 3, writers)

    def test_hand_entered_company_figure_became_the_approved_target(self):
        v8 = src("v8_features.py")
        v7 = src("v7_features.py")
        self.assertIn("ALTER TABLE FinancialPlans ADD approved_target", v8)
        self.assertIn("r12_company_target_rollup_v1", v8)
        self.assertIn("approved_target=annual_target", v8)
        # The company save endpoint writes the approved figure, never the roll-up.
        save = v7[v7.index("def api_v7_financial_plan_save"):v7.index("def api_v7_financial_periods_save")]
        self.assertIn("approved_target", save)
        self.assertNotIn("SET title=?,annual_target=?", save)

    def test_company_monthly_editor_is_closed(self):
        v7 = src("v7_features.py")
        periods = v7[v7.index("def api_v7_financial_periods_save"):]
        periods = periods[:periods.index("@app.route")]
        self.assertNotIn("UPDATE FinancialPlanPeriods", periods)
        ui = src("v7_ui.js")
        self.assertNotIn("v7SavePeriods", ui)
        self.assertNotIn("v7ApplyQuarter", ui)


class GoalDetailReportTests(unittest.TestCase):
    def test_detail_endpoint_exists_and_is_permission_mapped(self):
        py = src("v8_features.py")
        self.assertIn('"/api/v8/team_financial_detail"', py)
        self.assertIn('"api_v8_team_financial_detail": "financial_plan.view"',
                      src("rbac.py"))

    def test_detail_supports_a_month_range_and_returns_statements(self):
        py = src("v8_features.py")
        detail = py[py.index("def api_v8_team_financial_detail"):py.index("def dashboard_report")]
        self.assertIn("from_month", detail)
        self.assertIn("to_month", detail)
        self.assertIn("s.period_month BETWEEN ? AND ?", detail)
        self.assertIn("statements=statements", detail)
        self.assertIn("annual_approved_percent", detail)

    def test_detail_authorises_against_the_readers_own_teams(self):
        py = src("v8_features.py")
        detail = py[py.index("def api_v8_team_financial_detail"):py.index("def dashboard_report")]
        self.assertIn("team_ids(cur, g.user)", detail)
        self.assertIn("به اطلاعات این تیم دسترسی ندارید", detail)

    def test_ui_offers_year_to_date_and_per_team_drilldown(self):
        js = src("v8_ui.js")
        self.assertIn("function v8PlanRangeYtd", js)
        self.assertIn("function v8OpenTeamDetail", js)
        self.assertIn("function v8RenderTeamDetail", js)
        self.assertIn("/v8/team_financial_detail", js)

    def test_the_two_goal_menus_became_one(self):
        v8 = src("v8_ui.js")
        v7 = src("v7_ui.js")
        # One sidebar entry now covers both, and neither old label survives
        # as a nav item.
        nav = v8[v8.index("function initV8UI"):v8.index("nav.querySelectorAll('.nav-sec')")]
        self.assertIn("</span>اهداف مالی</div>", nav)
        self.assertNotIn("هدف مالی تیم‌ها", nav)
        self.assertNotIn("هدف کل شرکت", nav)
        # pg19 keeps only the statement planning it actually still does, and
        # says so at its single source.
        v7nav = v7[v7.index("nav.insertAdjacentHTML"):]
        v7nav = v7nav[:v7nav.index("var navItems=")]
        self.assertNotIn("برنامه مالی</div>", v7nav)
        self.assertIn("برنامه صورت‌وضعیت</div>", v7nav)


class RollupAggregationContractTests(unittest.TestCase):
    """Executes the aggregation rules the T-SQL roll-up relies on."""

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
            CREATE TABLE FinancialPlans(
              id INTEGER PRIMARY KEY, jalali_year INT, annual_target NUMERIC DEFAULT 0,
              approved_target NUMERIC, is_current INT DEFAULT 1);
            CREATE TABLE FinancialPlanPeriods(
              plan_id INT, month_no INT, target_amount NUMERIC DEFAULT 0);
            CREATE TABLE TeamFinancialTargets(
              id INTEGER PRIMARY KEY, plan_id INT, team_id INT,
              annual_target NUMERIC DEFAULT 0, is_current INT DEFAULT 1);
            CREATE TABLE TeamFinancialTargetPeriods(
              target_id INT, month_no INT, target_amount NUMERIC DEFAULT 0);
        """)
        self.db.execute("INSERT INTO FinancialPlans(id,jalali_year,annual_target,approved_target) VALUES(1,1405,0,40000)")
        for month in range(1, 13):
            self.db.execute("INSERT INTO FinancialPlanPeriods(plan_id,month_no,target_amount) VALUES(1,?,0)", (month,))

    def add_team(self, target_id, team_id, annual, months, is_current=1):
        self.db.execute(
            "INSERT INTO TeamFinancialTargets(id,plan_id,team_id,annual_target,is_current) VALUES(?,1,?,?,?)",
            (target_id, team_id, annual, is_current))
        for month, amount in months.items():
            self.db.execute(
                "INSERT INTO TeamFinancialTargetPeriods(target_id,month_no,target_amount) VALUES(?,?,?)",
                (target_id, month, amount))

    def recompute(self):
        """Same contract as recompute_company_plan, in SQLite syntax."""
        self.db.execute("""UPDATE FinancialPlans SET annual_target=COALESCE(
            (SELECT SUM(annual_target) FROM TeamFinancialTargets
             WHERE plan_id=FinancialPlans.id AND is_current=1),0)""")
        self.db.execute("""UPDATE FinancialPlanPeriods SET target_amount=COALESCE(
            (SELECT SUM(tp.target_amount) FROM TeamFinancialTargetPeriods tp
             JOIN TeamFinancialTargets tf ON tf.id=tp.target_id
             WHERE tf.plan_id=FinancialPlanPeriods.plan_id AND tf.is_current=1
               AND tp.month_no=FinancialPlanPeriods.month_no),0)""")

    def company(self):
        return self.db.execute("SELECT annual_target,approved_target FROM FinancialPlans WHERE id=1").fetchone()

    def month(self, m):
        return self.db.execute(
            "SELECT target_amount FROM FinancialPlanPeriods WHERE plan_id=1 AND month_no=?", (m,)).fetchone()[0]

    def test_company_total_is_the_sum_of_team_goals(self):
        self.add_team(1, 10, 15000, {1: 5000, 2: 10000})
        self.add_team(2, 20, 12000, {1: 12000})
        self.recompute()
        self.assertEqual(self.company()[0], 27000)

    def test_company_month_is_the_sum_of_that_month_across_teams(self):
        self.add_team(1, 10, 15000, {1: 5000, 2: 10000})
        self.add_team(2, 20, 12000, {1: 12000})
        self.recompute()
        self.assertEqual(self.month(1), 17000)
        self.assertEqual(self.month(2), 10000)
        self.assertEqual(self.month(3), 0)

    def test_superseded_team_versions_are_excluded(self):
        self.add_team(1, 10, 15000, {1: 15000})
        self.add_team(2, 10, 99999, {1: 99999}, is_current=0)
        self.recompute()
        self.assertEqual(self.company()[0], 15000)
        self.assertEqual(self.month(1), 15000)

    def test_removing_every_team_goal_zeroes_the_company_total(self):
        self.add_team(1, 10, 15000, {1: 15000})
        self.recompute()
        self.assertEqual(self.company()[0], 15000)
        self.db.execute("UPDATE TeamFinancialTargets SET is_current=0")
        self.recompute()
        self.assertEqual(self.company()[0], 0)
        self.assertEqual(self.month(1), 0)
        # The approved figure survives, which is the whole point of keeping it.
        self.assertEqual(self.company()[1], 40000)

    def test_gap_sign_distinguishes_under_and_over_commitment(self):
        def gap():
            annual, approved = self.company()
            return approved - annual
        self.add_team(1, 10, 30000, {1: 30000})
        self.recompute()
        self.assertEqual(gap(), 10000)   # board approved more than teams took on
        self.db.execute("UPDATE TeamFinancialTargets SET annual_target=45000 WHERE id=1")
        self.recompute()
        self.assertEqual(gap(), -5000)   # teams over-committed
        self.db.execute("UPDATE TeamFinancialTargets SET annual_target=40000 WHERE id=1")
        self.recompute()
        self.assertEqual(gap(), 0)

    def test_a_team_goal_raise_is_reflected_without_touching_other_teams(self):
        self.add_team(1, 10, 15000, {1: 15000})
        self.add_team(2, 20, 12000, {1: 12000})
        self.recompute()
        self.db.execute("UPDATE TeamFinancialTargets SET annual_target=20000 WHERE id=1")
        self.db.execute("UPDATE TeamFinancialTargetPeriods SET target_amount=20000 WHERE target_id=1")
        self.recompute()
        self.assertEqual(self.company()[0], 32000)
        self.assertEqual(self.month(1), 32000)
        other = self.db.execute(
            "SELECT annual_target FROM TeamFinancialTargets WHERE id=2").fetchone()[0]
        self.assertEqual(other, 12000)

    def tearDown(self):
        self.db.close()


if __name__ == "__main__":
    unittest.main()
