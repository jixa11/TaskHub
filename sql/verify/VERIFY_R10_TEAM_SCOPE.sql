/*
    TaskHub 8.1.0 LAN R10
    Read-only verification for team scope, permissions and custom project types.
    This script does not change data.
*/
SET NOCOUNT ON;

PRINT N'1) Active team-scoped users without an active team';
IF OBJECT_ID(N'dbo.Users', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.TeamMembers', N'U') IS NOT NULL
BEGIN
    SELECT
        u.id,
        u.username,
        u.display_name,
        u.role,
        u.project_id
    FROM dbo.Users AS u
    WHERE u.is_active = 1
      AND u.role IN (N'manager', N'planner', N'support', N'supervisor', N'employer')
      AND NOT EXISTS
      (
          SELECT 1
          FROM dbo.TeamMembers AS tm
          WHERE tm.user_id = u.id
            AND tm.is_active = 1
      )
    ORDER BY u.role, u.username;
END;

PRINT N'2) Users with zero or more than one active primary team';
IF OBJECT_ID(N'dbo.Users', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.TeamMembers', N'U') IS NOT NULL
BEGIN
    SELECT
        u.id,
        u.username,
        u.role,
        SUM(CASE WHEN tm.is_active = 1 AND tm.is_primary = 1 THEN 1 ELSE 0 END) AS ActivePrimaryTeamCount
    FROM dbo.Users AS u
    LEFT JOIN dbo.TeamMembers AS tm
        ON tm.user_id = u.id
    WHERE u.is_active = 1
      AND u.role IN (N'manager', N'planner', N'support', N'supervisor', N'employer')
    GROUP BY u.id, u.username, u.role
    HAVING SUM(CASE WHEN tm.is_active = 1 AND tm.is_primary = 1 THEN 1 ELSE 0 END) <> 1
    ORDER BY u.role, u.username;
END;

PRINT N'3) Active projects without an active team link';
IF OBJECT_ID(N'dbo.Projects', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.ProjectTeams', N'U') IS NOT NULL
BEGIN
    SELECT
        p.id,
        p.name,
        p.project_type_id
    FROM dbo.Projects AS p
    WHERE p.is_active = 1
      AND NOT EXISTS
      (
          SELECT 1
          FROM dbo.ProjectTeams AS pt
          WHERE pt.project_id = p.id
            AND pt.is_active = 1
      )
    ORDER BY p.id;
END;

PRINT N'4) Support permissions for sensitive project notes and chat files';
IF OBJECT_ID(N'dbo.RolePermissions', N'U') IS NOT NULL
BEGIN
    SELECT
        role,
        permission_key,
        is_allowed,
        updated_at
    FROM dbo.RolePermissions
    WHERE role = N'support'
      AND permission_key IN
      (
          N'project_notes.view',
          N'project_notes.manage',
          N'chat.file_upload',
          N'chat.file_download'
      )
    ORDER BY permission_key;
END;

PRINT N'5) Custom project types 8 and 9';
IF OBJECT_ID(N'dbo.ProjectTypes', N'U') IS NOT NULL
BEGIN
    SELECT
        id,
        name,
        is_active
    FROM dbo.ProjectTypes
    WHERE id IN (8, 9)
    ORDER BY id;
END;

PRINT N'6) R10 migration/index state';
SELECT
    i.name AS IndexName,
    OBJECT_SCHEMA_NAME(i.object_id) AS SchemaName,
    OBJECT_NAME(i.object_id) AS TableName,
    i.is_unique,
    i.has_filter,
    i.filter_definition
FROM sys.indexes AS i
WHERE i.name = N'UX_TeamMembers_ActivePrimaryUser';
