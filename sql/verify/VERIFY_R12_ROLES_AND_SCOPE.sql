/*
  TaskHub R12 - read-only pre/post deployment check.

  Run this on a COPY of the production database before upgrading, and again on
  the server after the first run of the new EXE. It only SELECTs; nothing here
  writes, and it is safe to run at any time.

  R12 changes two things that depend on existing data rather than on code:

    1. Contract and extension lists became team-scoped, like the statement list
       already was. A manager now sees a contract only if the finance
       specialist linked it to one of their teams (ContractProjectTeams).
       Section 1 shows how many records currently have no team link at all -
       those become invisible to every manager until finance links them.

    2. The company financial target became the sum of the team targets.
       Section 3 shows what the roll-up will produce for each year and what the
       previous hand-entered figure was, so the change is not a surprise.
*/
SET NOCOUNT ON;

PRINT '--- 1. Financial records with no team link (invisible to managers) ---';

SELECT
    N'قرارداد بدون اتصال تیم' AS [مورد],
    COUNT(*) AS [تعداد]
FROM Contracts co
WHERE co.is_active = 1
  AND NOT EXISTS (SELECT 1 FROM ContractProjectTeams cpt
                  JOIN ProjectTeams pt ON pt.id = cpt.project_team_id
                  WHERE cpt.contract_id = co.id AND cpt.is_active = 1
                    AND pt.is_active = 1)
UNION ALL
SELECT
    N'قرارداد بدون پروژه (هرگز خودکار به تیم وصل نمی‌شود)',
    COUNT(*)
FROM Contracts co
WHERE co.is_active = 1 AND co.project_id IS NULL
UNION ALL
SELECT
    N'صورت‌وضعیت بدون اتصال تیم',
    COUNT(*)
FROM ContractStatements s
WHERE s.is_active = 1 AND s.is_current = 1
  AND NOT EXISTS (SELECT 1 FROM ContractStatementTeams cst
                  JOIN ProjectTeams pt ON pt.id = cst.project_team_id
                  WHERE cst.statement_id = s.id AND cst.is_active = 1
                    AND pt.is_active = 1);

PRINT '--- 1b. The unlinked contracts themselves (first 100) ---';

SELECT TOP (100)
    co.id            AS [شناسه],
    co.title         AS [عنوان قرارداد],
    co.contract_number AS [شماره],
    p.name           AS [پروژه],
    CASE WHEN co.project_id IS NULL THEN N'بدون پروژه' ELSE N'پروژه دارد' END AS [وضعیت پروژه]
FROM Contracts co
LEFT JOIN Projects p ON p.id = co.project_id
WHERE co.is_active = 1
  AND NOT EXISTS (SELECT 1 FROM ContractProjectTeams cpt
                  JOIN ProjectTeams pt ON pt.id = cpt.project_team_id
                  WHERE cpt.contract_id = co.id AND cpt.is_active = 1
                    AND pt.is_active = 1)
ORDER BY co.id;

PRINT '--- 2. What each manager will actually see after the upgrade ---';

SELECT
    u.username           AS [کاربر],
    u.display_name       AS [نام],
    COUNT(DISTINCT tm.team_id) AS [تعداد تیم فعال],
    (SELECT COUNT(DISTINCT co.id)
       FROM Contracts co
       JOIN ContractProjectTeams cpt ON cpt.contract_id = co.id AND cpt.is_active = 1
       JOIN ProjectTeams pt ON pt.id = cpt.project_team_id AND pt.is_active = 1
       JOIN TeamMembers me ON me.team_id = pt.team_id AND me.user_id = u.id AND me.is_active = 1
      WHERE co.is_active = 1) AS [قرارداد قابل مشاهده],
    (SELECT COUNT(DISTINCT s.id)
       FROM ContractStatements s
       JOIN ContractStatementTeams cst ON cst.statement_id = s.id AND cst.is_active = 1
       JOIN ProjectTeams pt ON pt.id = cst.project_team_id AND pt.is_active = 1
       JOIN TeamMembers me ON me.team_id = pt.team_id AND me.user_id = u.id AND me.is_active = 1
      WHERE s.is_active = 1 AND s.is_current = 1) AS [صورت‌وضعیت قابل مشاهده]
FROM Users u
LEFT JOIN TeamMembers tm ON tm.user_id = u.id AND tm.is_active = 1
WHERE u.is_active = 1 AND u.role IN (N'manager', N'planner')
GROUP BY u.id, u.username, u.display_name
ORDER BY u.username;

PRINT '--- 3. Company target before and after the roll-up ---';

SELECT
    fp.jalali_year                       AS [سال],
    fp.annual_target                     AS [هدف فعلی شرکت (دستی)],
    ISNULL(t.total, 0)                   AS [هدف بعد از بازمحاسبه (جمع تیم‌ها)],
    ISNULL(fp.approved_target, fp.annual_target) AS [عددی که در هدف مصوب نگه داشته می‌شود],
    ISNULL(t.teams, 0)                   AS [تعداد تیم دارای هدف]
FROM FinancialPlans fp
OUTER APPLY (SELECT SUM(tf.annual_target) AS total, COUNT(*) AS teams
             FROM TeamFinancialTargets tf
             WHERE tf.plan_id = fp.id AND tf.is_current = 1) t
WHERE fp.is_current = 1
ORDER BY fp.jalali_year DESC;

PRINT '--- 4. Team-required accounts with no active team (they would see nothing) ---';

SELECT
    u.username     AS [کاربر],
    u.display_name AS [نام],
    u.role         AS [نقش]
FROM Users u
WHERE u.is_active = 1
  AND u.role IN (N'manager', N'planner', N'support', N'supervisor', N'employer')
  AND NOT EXISTS (SELECT 1 FROM TeamMembers tm
                  WHERE tm.user_id = u.id AND tm.is_active = 1)
ORDER BY u.role, u.username;

PRINT '--- 5. R12 migrations recorded (empty before the first run) ---';

SELECT migration_key AS [کلید], applied_at AS [زمان اجرا]
FROM RbacMigrations
WHERE migration_key LIKE 'r12%'
ORDER BY applied_at;

SELECT migration_key AS [کلید], completed_at AS [زمان اجرا], detail AS [توضیح]
FROM V8MigrationState
WHERE migration_key LIKE 'r12%'
ORDER BY completed_at;

PRINT '--- 6. Permission counts per role after the upgrade (expected: manager 125, planner 110, finance 58, reporter 66) ---';

SELECT
    role                                        AS [نقش],
    SUM(CASE WHEN is_allowed = 1 THEN 1 ELSE 0 END) AS [مجوز فعال],
    COUNT(*)                                    AS [کل مجوزها]
FROM RolePermissions
GROUP BY role
ORDER BY role;
