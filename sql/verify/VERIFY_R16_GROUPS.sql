-- TaskHub 1.0.0 - read-only checks for groups (گروه) and the
-- split permissions. Run on the application database after the first start
-- of R16. Nothing in this script writes.
SET NOCOUNT ON;
GO

-- 1) The group tables exist.
SELECT CASE WHEN OBJECT_ID('WorkGroups','U') IS NULL THEN 'MISSING' ELSE 'OK' END AS work_groups,
       CASE WHEN OBJECT_ID('WorkGroupMembers','U') IS NULL THEN 'MISSING' ELSE 'OK' END AS work_group_members,
       CASE WHEN OBJECT_ID('WorkGroupProjects','U') IS NULL THEN 'MISSING' ELSE 'OK' END AS work_group_projects;
GO

-- 2) The R14/R15 sub-groups were moved once. Expect one row.
SELECT * FROM V8MigrationState WHERE migration_key='r16_lead_members_to_groups_v1';
-- Expect 0: an active lead in a team who had a sub-group but has no group now.
SELECT COUNT(*) AS leads_left_without_group
FROM Users u
WHERE u.role=N'lead' AND u.is_active=1
  AND EXISTS(SELECT 1 FROM LeadMembers lm WHERE lm.lead_id=u.id)
  AND EXISTS(SELECT 1 FROM TeamMembers tm WHERE tm.user_id=u.id AND tm.is_active=1)
  AND NOT EXISTS(SELECT 1 FROM WorkGroups wg WHERE wg.lead_id=u.id AND wg.is_active=1);
GO

-- 3) Every active group with its lead, member and project counts.
SELECT wg.id, t.name AS team_name, wg.name AS group_name, lu.display_name AS lead_name,
       (SELECT COUNT(*) FROM WorkGroupMembers gm WHERE gm.group_id=wg.id) AS members,
       (SELECT COUNT(*) FROM WorkGroupProjects gp WHERE gp.group_id=wg.id) AS projects
FROM WorkGroups wg
JOIN Teams t ON t.id=wg.team_id
LEFT JOIN Users lu ON lu.id=wg.lead_id
WHERE wg.is_active=1
ORDER BY t.name, wg.name;
GO

-- 4) Expect 0 in each. One active group per person; the lead is a lead of the
-- group's team; members are support staff or leads of that team; projects are
-- linked to that team. A person who has since left the team, or a member an
-- R14 sub-group had in another team, shows here: fix it on the groups page.
SELECT COUNT(*) AS people_in_two_groups FROM (
  SELECT x.user_id FROM (
    SELECT gm.user_id FROM WorkGroupMembers gm
    JOIN WorkGroups wg ON wg.id=gm.group_id AND wg.is_active=1
    UNION ALL
    SELECT wg.lead_id FROM WorkGroups wg WHERE wg.is_active=1 AND wg.lead_id IS NOT NULL) x
  GROUP BY x.user_id HAVING COUNT(*)>1) d;
SELECT COUNT(*) AS invalid_leads
FROM WorkGroups wg
LEFT JOIN Users u ON u.id=wg.lead_id
WHERE wg.is_active=1 AND wg.lead_id IS NOT NULL
  AND (u.id IS NULL OR u.role<>N'lead' OR NOT EXISTS(SELECT 1 FROM TeamMembers tm
       WHERE tm.user_id=wg.lead_id AND tm.team_id=wg.team_id AND tm.is_active=1));
SELECT COUNT(*) AS invalid_members
FROM WorkGroupMembers gm
JOIN WorkGroups wg ON wg.id=gm.group_id AND wg.is_active=1
LEFT JOIN Users u ON u.id=gm.user_id
WHERE u.id IS NULL OR u.role NOT IN (N'support', N'lead')
   OR NOT EXISTS(SELECT 1 FROM TeamMembers tm
       WHERE tm.user_id=gm.user_id AND tm.team_id=wg.team_id AND tm.is_active=1);
SELECT COUNT(*) AS projects_outside_team
FROM WorkGroupProjects gp
JOIN WorkGroups wg ON wg.id=gp.group_id AND wg.is_active=1
WHERE NOT EXISTS(SELECT 1 FROM ProjectTeams pt
      WHERE pt.project_id=gp.project_id AND pt.team_id=wg.team_id AND pt.is_active=1);
GO

-- 5) Expect 0 rows: the split permissions started where the old ones were
-- (rows an administrator has saved since are left out).
SELECT n.role, n.permission_key, n.is_allowed,
       o.permission_key AS from_key, o.is_allowed AS from_allowed
FROM RolePermissions n
JOIN RolePermissions o ON o.role=n.role AND o.permission_key =
     CASE n.permission_key WHEN N'holidays.manage' THEN N'schedule.manage' ELSE N'leave.manage' END
WHERE n.permission_key IN (N'holidays.manage', N'missions.manage', N'leave.approve')
  AND n.is_allowed<>o.is_allowed AND n.updated_by IS NULL AND o.updated_by IS NULL;
GO

-- 6) Expect 0: the admin-only tools are granted to nobody else.
SELECT COUNT(*) AS delegated_admin_tools
FROM RolePermissions
WHERE role<>N'admin' AND is_allowed=1
  AND permission_key IN (N'access_control.manage', N'system.sql', N'system.data_export',
                         N'system.backup', N'system.sessions', N'system.autostart');
GO
