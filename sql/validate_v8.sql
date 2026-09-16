/*
  TaskHub 8.0.0 - read-only validation
  این فایل هیچ تغییری در دیتابیس ایجاد نمی‌کند.
  آن را پس از اولین اجرای نسخه ۸ روی دیتابیس مقصد اجرا کنید.
*/
SET NOCOUNT ON;

SELECT
    RequiredObject.ObjectName,
    CASE WHEN OBJECT_ID(RequiredObject.ObjectName, 'U') IS NULL
         THEN N'MISSING' ELSE N'OK' END AS ValidationStatus
FROM (VALUES
    ('Teams'),('TeamMembers'),('TeamProjectTypes'),('ProjectTeams'),
    ('ContractProjectTeams'),('ContractExtensionTeams'),
    ('ContractStatementTeams'),
    ('TeamFinancialTargets'),('TeamFinancialTargetPeriods'),
    ('ChatDevices'),('ChatConversations'),('ChatMembers'),
    ('ChatConversationKeys'),('ChatMessages'),('ChatEncryptedFiles'),
    ('ChatReadReceipts'),('V8MigrationState')
) AS RequiredObject(ObjectName)
ORDER BY RequiredObject.ObjectName;

SELECT
    (SELECT COUNT(*) FROM Teams WHERE is_active=1) AS ActiveTeams,
    (SELECT COUNT(*) FROM TeamMembers WHERE is_active=1) AS ActiveMemberships,
    (SELECT COUNT(*) FROM ProjectTeams WHERE is_active=1) AS ActiveProjectTeams,
    (SELECT COUNT(*) FROM ContractProjectTeams WHERE is_active=1) AS ActiveContractTeams,
    (SELECT COUNT(*) FROM ChatConversations WHERE is_active=1) AS ActiveConversations;

SELECT u.id, u.username, u.display_name, u.role
FROM Users AS u
WHERE u.is_active=1
  AND u.role IN ('admin','manager','planner','finance','reporter','support')
  AND NOT EXISTS (
      SELECT 1 FROM TeamMembers AS tm
      WHERE tm.user_id=u.id AND tm.is_active=1
  );

SELECT p.id, p.name, p.project_type_id
FROM Projects AS p
WHERE p.project_type_id IS NULL OR p.project_type_id=0;

SELECT t.id, t.title, t.project_id, t.project_team_id
FROM Tasks AS t
LEFT JOIN ProjectTeams AS pt ON pt.id=t.project_team_id
WHERE t.project_team_id IS NULL
   OR pt.id IS NULL
   OR pt.is_active=0
   OR pt.project_id<>t.project_id;

SELECT s.id, s.contract_id, c.project_id,
       cst.project_team_id, pt.project_id AS TeamProjectId,
       cst.allocation_percent
FROM ContractStatements AS s
JOIN Contracts AS c ON c.id=s.contract_id
LEFT JOIN ContractStatementTeams AS cst
  ON cst.statement_id=s.id AND cst.is_active=1
LEFT JOIN ProjectTeams AS pt ON pt.id=cst.project_team_id
WHERE s.is_active=1
  AND s.is_current=1
  AND (
      cst.project_team_id IS NULL
      OR pt.id IS NULL
      OR pt.is_active=0
      OR (c.project_id IS NOT NULL AND pt.project_id<>c.project_id)
  );

SELECT s.id AS StatementId,
       SUM(cst.allocation_percent) AS TeamAllocationPercent
FROM ContractStatements AS s
JOIN ContractStatementTeams AS cst
  ON cst.statement_id=s.id AND cst.is_active=1
WHERE s.is_active=1 AND s.is_current=1
GROUP BY s.id
HAVING ABS(SUM(cst.allocation_percent)-100)>0.01;

SELECT c.id, c.title, c.project_id
FROM Contracts AS c
WHERE c.is_active=1
  AND c.project_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM ContractProjectTeams AS cpt
      JOIN ProjectTeams AS pt ON pt.id=cpt.project_team_id
      WHERE cpt.contract_id=c.id
        AND cpt.is_active=1
        AND pt.is_active=1
        AND pt.project_id=c.project_id
  );

WITH EffectiveContract AS (
    SELECT c.id,
           ISNULL(c.base_price,0)
           + ISNULL(SUM(CASE
               WHEN e.is_active=1
                AND e.internal_status='approved'
                AND e.extension_type_id IN (2,3)
               THEN ISNULL(e.price_delta,0)
               ELSE 0 END),0) AS EffectivePrice
    FROM Contracts AS c
    LEFT JOIN ContractExtensions AS e ON e.contract_id=c.id
    WHERE c.is_active=1
    GROUP BY c.id,c.base_price
),
Allocated AS (
    SELECT cpt.contract_id,
           SUM(ISNULL(cpt.allocation_amount,0)) AS AllocatedAmount
    FROM ContractProjectTeams AS cpt
    WHERE cpt.is_active=1
      AND cpt.allocation_amount IS NOT NULL
    GROUP BY cpt.contract_id
)
SELECT ec.id AS ContractId, ec.EffectivePrice, a.AllocatedAmount,
       a.AllocatedAmount-ec.EffectivePrice AS OverAllocatedAmount
FROM EffectiveContract AS ec
JOIN Allocated AS a ON a.contract_id=ec.id
WHERE a.AllocatedAmount>ec.EffectivePrice;

SELECT tft.id AS TargetId, tft.plan_id, tft.team_id,
       tft.annual_target, SUM(ISNULL(p.target_amount,0)) AS MonthlyTotal
FROM TeamFinancialTargets AS tft
LEFT JOIN TeamFinancialTargetPeriods AS p ON p.target_id=tft.id
WHERE tft.is_current=1
GROUP BY tft.id,tft.plan_id,tft.team_id,tft.annual_target
HAVING SUM(ISNULL(p.target_amount,0))>tft.annual_target;

SELECT s.user_id, u.username, COUNT(*) AS OpenDeviceSessions,
       MAX(ISNULL(s.last_seen,s.created_at)) AS LastSeen
FROM Sessions AS s
JOIN Users AS u ON u.id=s.user_id
WHERE s.expires_at>=GETDATE()
  AND ISNULL(s.last_seen,s.created_at)>=DATEADD(hour,-2,GETDATE())
GROUP BY s.user_id,u.username
ORDER BY OpenDeviceSessions DESC,u.username;

SELECT t.name AS TableName, c.name AS SuspiciousColumn
FROM sys.tables AS t
JOIN sys.columns AS c ON c.object_id=t.object_id
WHERE t.name IN (
    'ChatDevices','ChatConversations','ChatMembers',
    'ChatConversationKeys','ChatMessages','ChatEncryptedFiles'
)
AND (
    LOWER(c.name) LIKE '%private%key%'
    OR LOWER(c.name) IN ('plaintext','body','message_text','file_name','mime_type')
);

SELECT migration_key, completed_at, detail
FROM V8MigrationState
ORDER BY completed_at;
