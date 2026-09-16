/*
    TaskHub 1.0.0
    Read-only verification for account, phonebook, shared cities,
    task-contract permissions and custom project types.
    This script does not change data.
*/
SET NOCOUNT ON;

PRINT N'1) R11 permission state for support';
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
          N'account.view',
          N'account.edit_identity',
          N'account.change_password',
          N'phonebook.view',
          N'phonebook.view_all',
          N'phonebook.edit',
          N'tasks.link_contract',
          N'project_notes.view',
          N'project_notes.manage'
      )
    ORDER BY permission_key;
END;

PRINT N'2) Duplicate city names after trimming';
IF OBJECT_ID(N'dbo.Cities', N'U') IS NOT NULL
BEGIN
    SELECT
        LTRIM(RTRIM(name)) AS NormalizedCityName,
        COUNT(*) AS DuplicateCount,
        MIN(id) AS FirstCityId,
        MAX(id) AS LastCityId
    FROM dbo.Cities
    GROUP BY LTRIM(RTRIM(name))
    HAVING COUNT(*) > 1
    ORDER BY NormalizedCityName;
END;

PRINT N'3) Active projects and their active team links';
IF OBJECT_ID(N'dbo.Projects', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.ProjectTeams', N'U') IS NOT NULL
BEGIN
    SELECT
        p.id AS ProjectId,
        p.name AS ProjectName,
        c.name AS CityName,
        COUNT(CASE WHEN pt.is_active = 1 THEN 1 END) AS ActiveTeamCount
    FROM dbo.Projects AS p
    INNER JOIN dbo.Cities AS c
        ON c.id = p.city_id
    LEFT JOIN dbo.ProjectTeams AS pt
        ON pt.project_id = p.id
    GROUP BY p.id, p.name, c.name
    ORDER BY c.name, p.name;
END;

PRINT N'4) Open contracts available for task linking';
IF OBJECT_ID(N'dbo.Contracts', N'U') IS NOT NULL
BEGIN
    SELECT
        co.id AS ContractId,
        co.title,
        co.contract_number,
        p.id AS ProjectId,
        p.name AS ProjectName,
        c.name AS CityName,
        ct.name AS ContractTypeName,
        cs.name AS ContractStatusName
    FROM dbo.Contracts AS co
    INNER JOIN dbo.Projects AS p
        ON p.id = co.project_id
    INNER JOIN dbo.Cities AS c
        ON c.id = p.city_id
    LEFT JOIN dbo.ContractTypes AS ct
        ON ct.id = co.contract_type_id
    LEFT JOIN dbo.ContractStatuses AS cs
        ON cs.id = co.contract_status_id
    WHERE co.is_active = 1
      AND ISNULL(co.contract_status_id, 0) NOT IN (3, 4)
    ORDER BY c.name, p.name, co.title;
END;

PRINT N'5) Custom project types 8 and 9';
IF OBJECT_ID(N'dbo.ProjectTypes', N'U') IS NOT NULL
BEGIN
    SELECT id, name, is_active
    FROM dbo.ProjectTypes
    WHERE id IN (8, 9)
    ORDER BY id;
END;

PRINT N'6) R11 migration state';
IF OBJECT_ID(N'dbo.RbacMigrations', N'U') IS NOT NULL
BEGIN
    SELECT migration_key, applied_at
    FROM dbo.RbacMigrations
    WHERE migration_key = N'r11_account_phonebook_contract_permissions_v1';
END;
