-- TaskHub 1.0.0 - read-only checks for the group lead (سرگروه)
-- and the client messenger rule. Run on the application database after the
-- first start of R14. Nothing in this script writes.
SET NOCOUNT ON;
GO

-- 1) The sub-group table exists.
SELECT CASE WHEN OBJECT_ID('LeadMembers','U') IS NULL THEN 'MISSING' ELSE 'OK' END AS lead_members_table;
GO

-- 2) The new role is seeded like support, plus the new permission.
SELECT role, COUNT(*) AS permission_rows,
       SUM(CASE WHEN is_allowed=1 THEN 1 ELSE 0 END) AS allowed_rows
FROM RolePermissions WHERE role IN (N'lead', N'support') GROUP BY role;
-- R15: the four group-lead keys. Expect is_allowed=1 for lead only on a new
-- install (an R14 install keeps its earlier manager/planner rows).
SELECT permission_key, role, is_allowed FROM RolePermissions
WHERE permission_key IN (N'tasks.create_for_group', N'tasks.edit_group',
                         N'tasks.delete_group', N'tasks.approve_group')
ORDER BY permission_key, role;
GO

-- 3) Every lead and their sub-group.
SELECT l.id AS lead_id, l.display_name AS lead_name,
       m.id AS member_id, m.display_name AS member_name,
       m.role AS member_role, m.is_active AS member_active
FROM LeadMembers lm
JOIN Users l ON l.id=lm.lead_id
JOIN Users m ON m.id=lm.member_id
ORDER BY l.display_name, m.display_name;
-- Expect 0: rows whose lead is no longer a lead or whose member is not
-- support staff or a lead.
SELECT COUNT(*) AS invalid_sub_group_rows
FROM LeadMembers lm
LEFT JOIN Users l ON l.id=lm.lead_id
LEFT JOIN Users m ON m.id=lm.member_id
WHERE l.id IS NULL OR m.id IS NULL OR l.role<>N'lead'
   OR m.role NOT IN (N'support', N'lead');
GO

-- 4) Expect 0: every active lead belongs to a team, like support staff.
SELECT COUNT(*) AS leads_without_team
FROM Users u
WHERE u.role=N'lead' AND u.is_active=1
  AND NOT EXISTS(SELECT 1 FROM TeamMembers tm WHERE tm.user_id=u.id AND tm.is_active=1);
GO

-- 5) Expect 0: employers and supervisors are out of the staff team channels
-- and the company announcements.
SELECT COUNT(*) AS clients_in_staff_channels
FROM ChatMembers cm
JOIN ChatConversations c ON c.id=cm.conversation_id
JOIN Users u ON u.id=cm.user_id
WHERE cm.is_active=1 AND c.kind IN ('team','announcement')
  AND u.role IN (N'employer', N'supervisor');
GO
