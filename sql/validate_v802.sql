/*
  TaskHub 8.0.2 - read-only validation
  این فایل فقط SELECT اجرا می‌کند و هیچ تغییری در دیتابیس ایجاد نمی‌کند.
*/
SET NOCOUNT ON;

SELECT DB_NAME() AS DatabaseName, @@SERVERNAME AS SqlServerName, GETDATE() AS CheckedAt;

SELECT RequiredObject.ObjectName,
       CASE WHEN OBJECT_ID(RequiredObject.ObjectName, 'U') IS NULL THEN N'MISSING' ELSE N'OK' END AS ValidationStatus
FROM (VALUES
    ('Projects'),('Contracts'),('ContractTypes'),('Tasks'),('TaskCategories'),
    ('Teams'),('TeamMembers'),('ProjectTeams'),('ContractProjectTeams'),
    ('ContractStatements'),('ContractTaskCategoryWeights')
) AS RequiredObject(ObjectName)
ORDER BY RequiredObject.ObjectName;

SELECT id,name,is_active
FROM ContractTypes
ORDER BY id;

SELECT setting_key,setting_value,updated_at
FROM AppSettings
WHERE setting_key='v802_contract_types_migrated';

SELECT c.id,c.title,c.contract_type_id
FROM Contracts AS c
LEFT JOIN ContractTypes AS ct ON ct.id=ISNULL(c.contract_type_id,0)
WHERE c.is_active=1
  AND (ct.id IS NULL OR ISNULL(c.contract_type_id,0) NOT IN (0,1,2,3));

SELECT ct.id AS ContractTypeId,ct.name AS ContractTypeName,
       tc.id AS TaskCategoryId,tc.name AS TaskCategoryName
FROM ContractTypes AS ct
CROSS JOIN TaskCategories AS tc
LEFT JOIN ContractTaskCategoryWeights AS w
  ON w.contract_type_id=ct.id
 AND w.task_category_id=tc.id
 AND w.is_active=1
WHERE ct.id IN (0,1,2,3)
  AND w.task_category_id IS NULL
ORDER BY ct.id,tc.name;

SELECT t.id AS TaskId,t.title,t.project_id,t.contract_id,c.project_id AS ContractProjectId
FROM Tasks AS t
JOIN Contracts AS c ON c.id=t.contract_id
WHERE t.contract_id IS NOT NULL
  AND t.project_id<>c.project_id;

SELECT t.id AS TaskId,t.title,t.status,t.project_id,t.contract_id,t.project_team_id
FROM Tasks AS t
WHERE t.status='done'
  AND (t.contract_id IS NULL OR t.project_team_id IS NULL)
ORDER BY t.id;

WITH TaskPeople AS (
    SELECT t.id AS TaskId,
           COUNT(DISTINCT p.UserId) AS PersonCount,
           SUM(ISNULL(tt.Seconds,0)) AS TimeSeconds
    FROM Tasks AS t
    OUTER APPLY (
        SELECT t.staff_id AS UserId WHERE t.staff_id IS NOT NULL
        UNION
        SELECT ta.user_id FROM TaskAssignees AS ta WHERE ta.task_id=t.id
    ) AS p
    OUTER APPLY (
        SELECT SUM(ISNULL(tl.seconds,DATEDIFF(second,tl.started_at,ISNULL(tl.ended_at,GETDATE())))) AS Seconds
        FROM TaskTimeLog AS tl
        WHERE tl.task_id=t.id AND tl.user_id=p.UserId
    ) AS tt
    WHERE t.status='done' AND t.contract_id IS NOT NULL
    GROUP BY t.id
)
SELECT TaskId,PersonCount,TimeSeconds
FROM TaskPeople
WHERE PersonCount>1 AND ISNULL(TimeSeconds,0)<=0
ORDER BY TaskId;

SELECT u.id,u.username,u.display_name,u.role
FROM Users AS u
WHERE u.is_active=1
  AND u.role IN ('manager','planner')
  AND NOT EXISTS (
      SELECT 1 FROM TeamMembers AS tm
      WHERE tm.user_id=u.id AND tm.is_active=1
  )
ORDER BY u.role,u.username;
