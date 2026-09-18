/* ------------------------------------------------------------------
   TaskHub demo data - for demonstrations and screenshots only.

   Before running it: start the application once against an *empty*
   database so the tables exist. Never run this on real data.

   Password for every demo user: Taskhub@1404
   Usernames: maryam.rezaei, saeed.kazemi, zahra.mousavi, nima.ahmadi …
   The admin account works too; its password is written to
   initial_admin_password.txt next to the executable.
------------------------------------------------------------------ */
SET NOCOUNT ON;
SET XACT_ABORT ON;

IF EXISTS(SELECT 1 FROM Users WHERE id BETWEEN 101 AND 110)
    THROW 51000, N'The demo data has already been loaded into this database.', 1;
IF EXISTS(SELECT 1 FROM Tasks)
    THROW 51001, N'This database already has tasks; the demo script only runs on an empty one.', 1;

BEGIN TRANSACTION;

-- Demo users (password for all: Taskhub@1404)
----------------------------------------------------------------------
SET IDENTITY_INSERT Users ON;
INSERT INTO Users(id,username,password_hash,role,display_name,position,phone,project_id,is_active,created_at) VALUES(101,N'maryam.rezaei',N'1ff81a225ac2beddedceadec84440d51$5c7f79aa46d94f73862851a4c287a45d45ee11bdd5ed7d78e145f049cb7aad63',N'manager',N'Maryam Rezaei',N'Company manager',N'09120000101',NULL,1,GETDATE());
INSERT INTO Users(id,username,password_hash,role,display_name,position,phone,project_id,is_active,created_at) VALUES(102,N'saeed.kazemi',N'1ff81a225ac2beddedceadec84440d51$5c7f79aa46d94f73862851a4c287a45d45ee11bdd5ed7d78e145f049cb7aad63',N'planner',N'Saeed Kazemi',N'Planner, development team',N'09120000102',NULL,1,GETDATE());
INSERT INTO Users(id,username,password_hash,role,display_name,position,phone,project_id,is_active,created_at) VALUES(103,N'zahra.mousavi',N'1ff81a225ac2beddedceadec84440d51$5c7f79aa46d94f73862851a4c287a45d45ee11bdd5ed7d78e145f049cb7aad63',N'finance',N'Zahra Mousavi',N'Finance specialist',N'09120000103',NULL,1,GETDATE());
INSERT INTO Users(id,username,password_hash,role,display_name,position,phone,project_id,is_active,created_at) VALUES(104,N'nima.ahmadi',N'1ff81a225ac2beddedceadec84440d51$5c7f79aa46d94f73862851a4c287a45d45ee11bdd5ed7d78e145f049cb7aad63',N'reporter',N'Nima Ahmadi',N'Operations specialist',N'09120000104',NULL,1,GETDATE());
INSERT INTO Users(id,username,password_hash,role,display_name,position,phone,project_id,is_active,created_at) VALUES(105,N'elham.karimi',N'1ff81a225ac2beddedceadec84440d51$5c7f79aa46d94f73862851a4c287a45d45ee11bdd5ed7d78e145f049cb7aad63',N'lead',N'Elham Karimi',N'Support group lead',N'09120000105',NULL,1,GETDATE());
INSERT INTO Users(id,username,password_hash,role,display_name,position,phone,project_id,is_active,created_at) VALUES(106,N'reza.heidari',N'1ff81a225ac2beddedceadec84440d51$5c7f79aa46d94f73862851a4c287a45d45ee11bdd5ed7d78e145f049cb7aad63',N'support',N'Reza Heidari',N'Support specialist',N'09120000106',NULL,1,GETDATE());
INSERT INTO Users(id,username,password_hash,role,display_name,position,phone,project_id,is_active,created_at) VALUES(107,N'sara.nouri',N'1ff81a225ac2beddedceadec84440d51$5c7f79aa46d94f73862851a4c287a45d45ee11bdd5ed7d78e145f049cb7aad63',N'support',N'Sara Nouri',N'Support specialist',N'09120000107',NULL,1,GETDATE());
INSERT INTO Users(id,username,password_hash,role,display_name,position,phone,project_id,is_active,created_at) VALUES(108,N'amir.sadeghi',N'1ff81a225ac2beddedceadec84440d51$5c7f79aa46d94f73862851a4c287a45d45ee11bdd5ed7d78e145f049cb7aad63',N'support',N'Amir Sadeghi',N'Support specialist',N'09120000108',NULL,1,GETDATE());
INSERT INTO Users(id,username,password_hash,role,display_name,position,phone,project_id,is_active,created_at) VALUES(109,N'farhad.yazdani',N'1ff81a225ac2beddedceadec84440d51$5c7f79aa46d94f73862851a4c287a45d45ee11bdd5ed7d78e145f049cb7aad63',N'supervisor',N'Farhad Yazdani',N'System supervisor',N'09120000109',1,1,GETDATE());
INSERT INTO Users(id,username,password_hash,role,display_name,position,phone,project_id,is_active,created_at) VALUES(110,N'leila.sharifi',N'1ff81a225ac2beddedceadec84440d51$5c7f79aa46d94f73862851a4c287a45d45ee11bdd5ed7d78e145f049cb7aad63',N'employer',N'Leila Sharifi',N'Client of the warehouse project',N'09120000110',1,1,GETDATE());
SET IDENTITY_INSERT Users OFF;

-- Cities, project types, projects and task categories
----------------------------------------------------------------------
SET IDENTITY_INSERT Cities ON;
INSERT INTO Cities(id,name,created_at) VALUES(1,N'Tehran',GETDATE());
INSERT INTO Cities(id,name,created_at) VALUES(2,N'Isfahan',GETDATE());
INSERT INTO Cities(id,name,created_at) VALUES(3,N'Mashhad',GETDATE());
INSERT INTO Cities(id,name,created_at) VALUES(4,N'Shiraz',GETDATE());
SET IDENTITY_INSERT Cities OFF;
MERGE ProjectTypes AS t USING (VALUES(1,N'Enterprise software'),(2,N'Mobile app')) AS v(id,name) ON t.id=v.id WHEN NOT MATCHED THEN INSERT(id,name,is_active) VALUES(v.id,v.name,1);
SET IDENTITY_INSERT Projects ON;
INSERT INTO Projects(id,city_id,name,project_type_id,created_at) VALUES(1,1,N'Warehouse management system',1,GETDATE());
INSERT INTO Projects(id,city_id,name,project_type_id,created_at) VALUES(2,1,N'Customer service portal',1,GETDATE());
INSERT INTO Projects(id,city_id,name,project_type_id,created_at) VALUES(3,2,N'Loyalty club app',2,GETDATE());
INSERT INTO Projects(id,city_id,name,project_type_id,created_at) VALUES(4,3,N'Financial reporting system',1,GETDATE());
INSERT INTO Projects(id,city_id,name,project_type_id,created_at) VALUES(5,4,N'Staff training portal',1,GETDATE());
INSERT INTO Projects(id,city_id,name,project_type_id,created_at) VALUES(6,1,N'Online store website',2,GETDATE());
SET IDENTITY_INSERT Projects OFF;
SET IDENTITY_INSERT TaskCategories ON;
INSERT INTO TaskCategories(id,name,description,created_at) VALUES(1,N'Development',N'Building a new feature',GETDATE());
INSERT INTO TaskCategories(id,name,description,created_at) VALUES(2,N'Bug fix',N'Fixing reported defects',GETDATE());
INSERT INTO TaskCategories(id,name,description,created_at) VALUES(3,N'Support',N'Answering user requests',GETDATE());
INSERT INTO TaskCategories(id,name,description,created_at) VALUES(4,N'Documentation',N'Writing guides and documentation',GETDATE());
INSERT INTO TaskCategories(id,name,description,created_at) VALUES(5,N'Meeting',N'Meeting with the client and the team',GETDATE());
SET IDENTITY_INSERT TaskCategories OFF;

-- Teams, members and groups
----------------------------------------------------------------------
SET IDENTITY_INSERT Teams ON;
INSERT INTO Teams(id,code,name,description,is_active,created_by,created_at) VALUES(1,N'DEV',N'Development team',N'Building and maintaining the systems',1,1,GETDATE());
INSERT INTO Teams(id,code,name,description,is_active,created_by,created_at) VALUES(2,N'SUP',N'Support team',N'User support and bug fixing',1,1,GETDATE());
SET IDENTITY_INSERT Teams OFF;
INSERT INTO TeamMembers(team_id,user_id,team_role,is_primary,is_active,joined_at,added_by) VALUES(1,101,N'manager',1,1,GETDATE(),1);
INSERT INTO TeamMembers(team_id,user_id,team_role,is_primary,is_active,joined_at,added_by) VALUES(1,102,N'planner',1,1,GETDATE(),1);
INSERT INTO TeamMembers(team_id,user_id,team_role,is_primary,is_active,joined_at,added_by) VALUES(1,106,N'member',1,1,GETDATE(),1);
INSERT INTO TeamMembers(team_id,user_id,team_role,is_primary,is_active,joined_at,added_by) VALUES(1,107,N'member',1,1,GETDATE(),1);
INSERT INTO TeamMembers(team_id,user_id,team_role,is_primary,is_active,joined_at,added_by) VALUES(2,101,N'manager',0,1,GETDATE(),1);
INSERT INTO TeamMembers(team_id,user_id,team_role,is_primary,is_active,joined_at,added_by) VALUES(2,105,N'member',1,1,GETDATE(),1);
INSERT INTO TeamMembers(team_id,user_id,team_role,is_primary,is_active,joined_at,added_by) VALUES(2,108,N'member',1,1,GETDATE(),1);
INSERT INTO TeamMembers(team_id,user_id,team_role,is_primary,is_active,joined_at,added_by) VALUES(2,104,N'member',1,1,GETDATE(),1);
INSERT INTO TeamMembers(team_id,user_id,team_role,is_primary,is_active,joined_at,added_by) VALUES(1,103,N'member',1,1,GETDATE(),1);
SET IDENTITY_INSERT WorkGroups ON;
INSERT INTO WorkGroups(id,team_id,name,description,lead_id,is_active,created_by,created_at) VALUES(1,2,N'Tehran support group',N'Support for the Tehran projects',105,1,1,GETDATE());
SET IDENTITY_INSERT WorkGroups OFF;
INSERT INTO WorkGroupMembers(group_id,user_id,added_by,added_at) VALUES(1,105,1,GETDATE());
INSERT INTO WorkGroupMembers(group_id,user_id,added_by,added_at) VALUES(1,108,1,GETDATE());
INSERT INTO WorkGroupProjects(group_id,project_id,added_by,added_at) VALUES(1,1,1,GETDATE());
INSERT INTO WorkGroupProjects(group_id,project_id,added_by,added_at) VALUES(1,2,1,GETDATE());
INSERT INTO ProjectTeams(project_id,team_id,title,is_primary,is_active,created_by,created_at) VALUES(1,1,N'Warehouse system development',1,1,1,GETDATE());
INSERT INTO ProjectTeams(project_id,team_id,title,is_primary,is_active,created_by,created_at) VALUES(2,1,N'Service portal development',1,1,1,GETDATE());
INSERT INTO ProjectTeams(project_id,team_id,title,is_primary,is_active,created_by,created_at) VALUES(3,1,N'Loyalty app development',1,1,1,GETDATE());
INSERT INTO ProjectTeams(project_id,team_id,title,is_primary,is_active,created_by,created_at) VALUES(4,2,N'Financial reporting support',1,1,1,GETDATE());
INSERT INTO ProjectTeams(project_id,team_id,title,is_primary,is_active,created_by,created_at) VALUES(5,2,N'Training portal support',1,1,1,GETDATE());
INSERT INTO ProjectTeams(project_id,team_id,title,is_primary,is_active,created_by,created_at) VALUES(6,1,N'Online store development',1,1,1,GETDATE());
INSERT INTO ProjectTeams(project_id,team_id,title,is_primary,is_active,created_by,created_at) VALUES(1,2,N'Warehouse system support',0,1,1,GETDATE());
INSERT INTO ProjectTeams(project_id,team_id,title,is_primary,is_active,created_by,created_at) VALUES(2,2,N'Service portal support',0,1,1,GETDATE());
DECLARE @team_project_1 INT = (SELECT TOP 1 id FROM ProjectTeams WHERE project_id=1 AND is_primary=1);
DECLARE @team_project_2 INT = (SELECT TOP 1 id FROM ProjectTeams WHERE project_id=2 AND is_primary=1);
DECLARE @team_project_3 INT = (SELECT TOP 1 id FROM ProjectTeams WHERE project_id=3 AND is_primary=1);
DECLARE @team_project_4 INT = (SELECT TOP 1 id FROM ProjectTeams WHERE project_id=4 AND is_primary=1);
DECLARE @team_project_5 INT = (SELECT TOP 1 id FROM ProjectTeams WHERE project_id=5 AND is_primary=1);
DECLARE @team_project_6 INT = (SELECT TOP 1 id FROM ProjectTeams WHERE project_id=6 AND is_primary=1);

-- Tasks in every status, with owners, work time and comments
----------------------------------------------------------------------
SET IDENTITY_INSERT Tasks ON;
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1001,N'Add a stock level report',N'dev',N'done',1,1,110,106,N'1405/05/18',N'1405/05/26',N'Sample description for “Add a stock level report” in project 1.',N'Completed and delivered to the client.',2,102,N'2026-08-10 09:30:00',N'2026-08-16 16:00:00',N'2026-08-17 11:15:00',10800,N'1405/05/26',N'1405/05/26',NULL,1,@team_project_1,1,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1002,N'Goods receipt cannot be saved',N'bug',N'done',2,1,110,107,N'1405/05/20',N'1405/05/28',N'Sample description for “Goods receipt cannot be saved” in project 1.',N'Completed and delivered to the client.',2,102,N'2026-08-12 09:30:00',N'2026-08-18 16:00:00',N'2026-08-19 11:15:00',5400,N'1405/05/28',N'1405/05/28',NULL,1,@team_project_1,1,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1003,N'Speed up the product search',N'devminor',N'done',1,1,110,108,N'1405/05/23',N'1405/05/30',N'Sample description for “Speed up the product search” in project 1.',N'Completed and delivered to the client.',3,102,N'2026-08-15 09:30:00',N'2026-08-20 16:00:00',N'2026-08-21 11:15:00',7200,N'1405/05/30',N'1405/05/30',NULL,1,@team_project_1,2,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1004,N'User guide for the warehouse module',N'dev',N'done',4,1,110,106,N'1405/05/25',N'1405/06/02',N'Sample description for “User guide for the warehouse module” in project 1.',N'Completed and delivered to the client.',1,102,N'2026-08-17 09:30:00',N'2026-08-23 16:00:00',N'2026-08-24 11:15:00',14400,N'1405/06/02',N'1405/06/02',NULL,1,@team_project_1,3,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1005,N'Invoice layout change request',N'dev',N'done',1,2,110,107,N'1405/05/28',N'1405/06/05',N'Sample description for “Invoice layout change request” in project 2.',N'Completed and delivered to the client.',3,102,N'2026-08-20 09:30:00',N'2026-08-26 16:00:00',N'2026-08-27 11:15:00',3600,N'1405/06/05',N'1405/06/05',NULL,2,@team_project_2,2,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1006,N'Portal users cannot sign in',N'bug',N'done',2,2,110,105,N'1405/05/30',N'1405/06/07',N'Sample description for “Portal users cannot sign in” in project 2.',N'Completed and delivered to the client.',2,102,N'2026-08-22 09:30:00',N'2026-08-28 16:00:00',N'2026-08-29 11:15:00',7200,N'1405/06/07',N'1405/06/07',NULL,2,@team_project_2,1,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1007,N'Phone support for portal users',N'dev',N'done',3,2,110,108,N'1405/06/02',N'1405/06/09',N'Sample description for “Phone support for portal users” in project 2.',N'Completed and delivered to the client.',2,102,N'2026-08-25 09:30:00',N'2026-08-30 16:00:00',N'2026-08-31 11:15:00',3600,N'1405/06/09',N'1405/06/09',NULL,2,@team_project_2,1,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1008,N'Add a date filter to the reports',N'dev',N'done',1,2,110,106,N'1405/06/05',N'1405/06/12',N'Sample description for “Add a date filter to the reports” in project 2.',N'Completed and delivered to the client.',2,102,N'2026-08-28 09:30:00',N'2026-09-02 16:00:00',N'2026-09-03 11:15:00',3600,N'1405/06/12',N'1405/06/12',NULL,2,@team_project_2,1,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1009,N'Design the loyalty points page',N'dev',N'done',1,3,NULL,107,N'1405/06/07',N'1405/06/15',N'Sample description for “Design the loyalty points page” in project 3.',N'Completed and delivered to the client.',1,102,N'2026-08-30 09:30:00',N'2026-09-05 16:00:00',N'2026-09-06 11:15:00',3600,N'1405/06/15',N'1405/06/15',NULL,3,@team_project_3,3,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1010,N'Fix the points display on mobile',N'bug',N'done',2,3,NULL,105,N'1405/06/09',N'1405/06/17',N'Sample description for “Fix the points display on mobile” in project 3.',N'Completed and delivered to the client.',1,102,N'2026-09-01 09:30:00',N'2026-09-07 16:00:00',N'2026-09-08 11:15:00',3600,N'1405/06/17',N'1405/06/17',NULL,3,@team_project_3,1,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1011,N'Connect the loyalty payment gateway',N'dev',N'done',1,3,NULL,108,N'1405/06/12',N'1405/06/19',N'Sample description for “Connect the loyalty payment gateway” in project 3.',N'Completed and delivered to the client.',2,102,N'2026-09-04 09:30:00',N'2026-09-09 16:00:00',N'2026-09-10 11:15:00',14400,N'1405/06/19',N'1405/06/19',NULL,3,@team_project_3,3,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1012,N'Monthly loyalty performance report',N'dev',N'done',4,3,NULL,106,N'1405/06/15',N'1405/06/22',N'Sample description for “Monthly loyalty performance report” in project 3.',N'Completed and delivered to the client.',2,102,N'2026-09-07 09:30:00',N'2026-09-12 16:00:00',N'2026-09-13 11:15:00',18000,N'1405/06/22',N'1405/06/22',NULL,3,@team_project_3,3,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1013,N'Add the balance sheet to the financial report',N'dev',N'pending_approval',1,4,NULL,107,N'1405/06/17',N'1405/06/25',N'Sample description for “Add the balance sheet to the financial report” in project 4.',NULL,3,102,N'2026-09-09 09:30:00',N'2026-09-15 16:00:00',NULL,14400,N'1405/06/25',N'1405/06/25',NULL,4,@team_project_4,1,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1014,N'Fix the tax calculation error',N'bug',N'pending_approval',2,4,NULL,108,N'1405/06/19',N'1405/06/28',N'Sample description for “Fix the tax calculation error” in project 4.',NULL,3,102,N'2026-09-11 09:30:00',N'2026-09-18 16:00:00',NULL,3600,N'1405/06/28',N'1405/06/28',NULL,4,@team_project_4,3,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1015,N'Finance requirements meeting',N'dev',N'returned',5,4,NULL,106,N'1405/06/18',N'1405/06/26',N'Sample description for “Finance requirements meeting” in project 4.',NULL,2,102,N'2026-09-10 09:30:00',N'2026-09-16 16:00:00',NULL,5400,N'1405/06/26',N'1405/06/26',NULL,4,@team_project_4,1,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1016,N'Excel export for the financial report',N'devminor',N'doing',1,4,NULL,107,N'1405/06/20',N'1405/06/30',N'Sample description for “Excel export for the financial report” in project 4.',NULL,2,102,N'2026-09-12 09:30:00',NULL,NULL,10800,N'1405/06/30',N'1405/06/30',NULL,4,@team_project_4,1,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1017,N'Upload the training videos',N'dev',N'doing',1,5,NULL,105,N'1405/06/21',N'1405/06/31',N'Sample description for “Upload the training videos” in project 5.',NULL,3,102,N'2026-09-13 09:30:00',NULL,NULL,3600,N'1405/06/31',N'1405/06/31',NULL,NULL,@team_project_5,3,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1018,N'Fix the slow courses page',N'bug',N'doing',2,5,NULL,108,N'1405/06/22',N'1405/06/29',N'Sample description for “Fix the slow courses page” in project 5.',NULL,1,102,N'2026-09-14 09:30:00',NULL,NULL,3600,N'1405/06/29',N'1405/06/29',NULL,NULL,@team_project_5,1,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1019,N'Document the sign-up process',N'dev',N'doing',4,5,NULL,106,N'1405/06/23',N'1405/07/02',N'Sample description for “Document the sign-up process” in project 5.',NULL,1,102,N'2026-09-15 09:30:00',NULL,NULL,18000,N'1405/07/02',N'1405/07/02',NULL,NULL,@team_project_5,3,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1020,N'Support for training portal users',N'dev',N'paused',3,5,NULL,107,N'1405/06/21',N'1405/06/28',N'Sample description for “Support for training portal users” in project 5.',NULL,2,102,N'2026-09-13 09:30:00',NULL,NULL,10800,N'1405/06/28',N'1405/06/28',NULL,NULL,@team_project_5,3,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1021,N'Add a multi-step shopping cart',N'dev',N'assigned',1,6,NULL,108,N'1405/06/24',N'1405/07/03',N'Sample description for “Add a multi-step shopping cart” in project 6.',NULL,3,102,NULL,NULL,NULL,0,N'1405/07/03',N'1405/07/03',NULL,NULL,@team_project_6,3,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1022,N'Shipping cost is calculated wrongly',N'bug',N'assigned',2,6,NULL,106,N'1405/06/25',N'1405/07/05',N'Sample description for “Shipping cost is calculated wrongly” in project 6.',NULL,2,102,NULL,NULL,NULL,0,N'1405/07/05',N'1405/07/05',NULL,NULL,@team_project_6,1,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1023,N'Improve the products page speed',N'devminor',N'assigned',1,6,NULL,107,N'1405/06/25',N'1405/07/01',N'Sample description for “Improve the products page speed” in project 6.',NULL,2,102,NULL,NULL,NULL,0,N'1405/07/01',N'1405/07/01',NULL,NULL,@team_project_6,3,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1024,N'Release coordination meeting',N'dev',N'approved',5,6,NULL,NULL,N'1405/06/26',N'1405/07/06',N'Sample description for “Release coordination meeting” in project 6.',NULL,2,102,NULL,NULL,NULL,0,N'1405/07/06',NULL,NULL,NULL,@team_project_6,1,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1025,N'Follow up on the client''s request',N'dev',N'approved',3,1,110,NULL,N'1405/06/26',N'1405/07/08',N'Sample description for “Follow up on the client''s request” in project 1.',NULL,2,102,NULL,NULL,NULL,0,N'1405/07/08',NULL,NULL,1,@team_project_1,1,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1026,N'Fix the support workload report',N'bug',N'registered',2,4,NULL,NULL,N'1405/06/27',N'1405/07/10',N'Sample description for “Fix the support workload report” in project 4.',NULL,3,102,NULL,NULL,NULL,0,N'1405/07/10',NULL,NULL,4,@team_project_4,2,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1027,N'Add SMS notifications',N'dev',N'registered',1,2,110,NULL,N'1405/06/27',N'1405/07/05',N'Sample description for “Add SMS notifications” in project 2.',NULL,3,102,NULL,NULL,NULL,0,N'1405/07/05',NULL,NULL,2,@team_project_2,3,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1028,N'Review the role permissions',N'dev',N'registered',3,4,NULL,NULL,N'1405/06/26',N'1405/07/04',N'Sample description for “Review the role permissions” in project 4.',NULL,3,102,NULL,NULL,NULL,0,N'1405/07/04',NULL,NULL,4,@team_project_4,3,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1029,N'Fix invoice printing',N'bug',N'rejected',2,6,NULL,NULL,N'1405/06/16',N'1405/06/23',N'Sample description for “Fix invoice printing” in project 6.',NULL,3,102,NULL,NULL,NULL,0,N'1405/06/23',NULL,N'Out of the contract''s scope.',NULL,@team_project_6,1,GETDATE());
INSERT INTO Tasks(id,title,type,status,category_id,project_id,contact_id,staff_id,date_recv,date_delivery,description,solution,priority,created_by,started_at,submitted_at,completed_at,work_seconds,due_jalali,due_at_assign,reject_reason,contract_id,project_team_id,progress_weight,created_at) VALUES(1030,N'Set up a weekly automatic backup',N'dev',N'done',1,1,110,105,N'1405/06/21',N'1405/06/26',N'Sample description for “Set up a weekly automatic backup” in project 1.',N'Completed and delivered to the client.',2,102,N'2026-09-13 09:30:00',N'2026-09-16 16:00:00',N'2026-09-17 11:15:00',3600,N'1405/06/26',N'1405/06/26',NULL,1,@team_project_1,1,GETDATE());
SET IDENTITY_INSERT Tasks OFF;
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1001,106,N'2026-08-09 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1002,107,N'2026-08-11 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1003,108,N'2026-08-14 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1004,106,N'2026-08-16 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1005,107,N'2026-08-19 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1006,105,N'2026-08-21 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1007,108,N'2026-08-24 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1008,106,N'2026-08-27 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1009,107,N'2026-08-29 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1010,105,N'2026-08-31 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1011,108,N'2026-09-03 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1012,106,N'2026-09-06 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1013,107,N'2026-09-08 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1014,108,N'2026-09-10 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1015,106,N'2026-09-09 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1016,107,N'2026-09-11 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1017,105,N'2026-09-12 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1018,108,N'2026-09-13 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1019,106,N'2026-09-14 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1020,107,N'2026-09-12 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1021,108,N'2026-09-15 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1022,106,N'2026-09-16 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1023,107,N'2026-09-16 10:00:00');
INSERT INTO TaskAssignees(task_id,user_id,assigned_at) VALUES(1030,105,N'2026-09-12 10:00:00');
INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) VALUES(1001,106,N'2026-08-10 09:30:00',N'2026-08-16 15:30:00',10800);
INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) VALUES(1002,107,N'2026-08-12 09:30:00',N'2026-08-18 15:30:00',5400);
INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) VALUES(1003,108,N'2026-08-15 09:30:00',N'2026-08-20 15:30:00',7200);
INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) VALUES(1004,106,N'2026-08-17 09:30:00',N'2026-08-23 15:30:00',14400);
INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) VALUES(1005,107,N'2026-08-20 09:30:00',N'2026-08-26 15:30:00',3600);
INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) VALUES(1006,105,N'2026-08-22 09:30:00',N'2026-08-28 15:30:00',7200);
INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) VALUES(1007,108,N'2026-08-25 09:30:00',N'2026-08-30 15:30:00',3600);
INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) VALUES(1008,106,N'2026-08-28 09:30:00',N'2026-09-02 15:30:00',3600);
INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) VALUES(1009,107,N'2026-08-30 09:30:00',N'2026-09-05 15:30:00',3600);
INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) VALUES(1010,105,N'2026-09-01 09:30:00',N'2026-09-07 15:30:00',3600);
INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) VALUES(1011,108,N'2026-09-04 09:30:00',N'2026-09-09 15:30:00',14400);
INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) VALUES(1012,106,N'2026-09-07 09:30:00',N'2026-09-12 15:30:00',18000);
INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) VALUES(1013,107,N'2026-09-09 09:30:00',N'2026-09-15 15:30:00',14400);
INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) VALUES(1014,108,N'2026-09-11 09:30:00',N'2026-09-18 15:30:00',3600);
INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) VALUES(1015,106,N'2026-09-10 09:30:00',N'2026-09-16 15:30:00',5400);
INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) VALUES(1016,107,N'2026-09-12 09:30:00',NULL,0);
INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) VALUES(1017,105,N'2026-09-13 09:30:00',NULL,0);
INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) VALUES(1018,108,N'2026-09-14 09:30:00',NULL,0);
INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) VALUES(1019,106,N'2026-09-15 09:30:00',NULL,0);
INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) VALUES(1020,107,N'2026-09-13 09:30:00',N'2026-09-18 15:30:00',10800);
INSERT INTO TaskTimeLog(task_id,user_id,started_at,ended_at,seconds) VALUES(1030,105,N'2026-09-13 09:30:00',N'2026-09-16 15:30:00',3600);
INSERT INTO TaskComments(task_id,user_id,author_name,author_role,body,created_at) VALUES(1005,102,N'Saeed Kazemi',N'planner',N'Please update the status of this task before the end of the week.',GETDATE());
INSERT INTO TaskComments(task_id,user_id,author_name,author_role,body,created_at) VALUES(1010,102,N'Saeed Kazemi',N'planner',N'Please update the status of this task before the end of the week.',GETDATE());
INSERT INTO TaskComments(task_id,user_id,author_name,author_role,body,created_at) VALUES(1015,102,N'Saeed Kazemi',N'planner',N'Please update the status of this task before the end of the week.',GETDATE());
INSERT INTO TaskComments(task_id,user_id,author_name,author_role,body,created_at) VALUES(1020,102,N'Saeed Kazemi',N'planner',N'Please update the status of this task before the end of the week.',GETDATE());
INSERT INTO TaskComments(task_id,user_id,author_name,author_role,body,created_at) VALUES(1025,102,N'Saeed Kazemi',N'planner',N'Please update the status of this task before the end of the week.',GETDATE());
INSERT INTO TaskComments(task_id,user_id,author_name,author_role,body,created_at) VALUES(1030,102,N'Saeed Kazemi',N'planner',N'Please update the status of this task before the end of the week.',GETDATE());
INSERT INTO TaskEvents(task_id,action,actor_id,due_jalali,created_at) VALUES(1001,N'approved',102,N'1405/05/26',N'2026-08-17 11:15:00');
INSERT INTO TaskEvents(task_id,action,actor_id,due_jalali,created_at) VALUES(1002,N'approved',102,N'1405/05/28',N'2026-08-19 11:15:00');
INSERT INTO TaskEvents(task_id,action,actor_id,due_jalali,created_at) VALUES(1003,N'approved',102,N'1405/05/30',N'2026-08-21 11:15:00');
INSERT INTO TaskEvents(task_id,action,actor_id,due_jalali,created_at) VALUES(1004,N'approved',102,N'1405/06/02',N'2026-08-24 11:15:00');
INSERT INTO TaskEvents(task_id,action,actor_id,due_jalali,created_at) VALUES(1005,N'approved',102,N'1405/06/05',N'2026-08-27 11:15:00');
INSERT INTO TaskEvents(task_id,action,actor_id,due_jalali,created_at) VALUES(1006,N'approved',102,N'1405/06/07',N'2026-08-29 11:15:00');
INSERT INTO TaskEvents(task_id,action,actor_id,due_jalali,created_at) VALUES(1007,N'approved',102,N'1405/06/09',N'2026-08-31 11:15:00');
INSERT INTO TaskEvents(task_id,action,actor_id,due_jalali,created_at) VALUES(1008,N'approved',102,N'1405/06/12',N'2026-09-03 11:15:00');
INSERT INTO TaskEvents(task_id,action,actor_id,due_jalali,created_at) VALUES(1009,N'approved',102,N'1405/06/15',N'2026-09-06 11:15:00');
INSERT INTO TaskEvents(task_id,action,actor_id,due_jalali,created_at) VALUES(1010,N'approved',102,N'1405/06/17',N'2026-09-08 11:15:00');
INSERT INTO TaskEvents(task_id,action,actor_id,due_jalali,created_at) VALUES(1011,N'approved',102,N'1405/06/19',N'2026-09-10 11:15:00');
INSERT INTO TaskEvents(task_id,action,actor_id,due_jalali,created_at) VALUES(1012,N'approved',102,N'1405/06/22',N'2026-09-13 11:15:00');
INSERT INTO TaskEvents(task_id,action,actor_id,due_jalali,created_at) VALUES(1030,N'approved',102,N'1405/06/26',N'2026-09-17 11:15:00');

-- Attendance, weekly schedule, leave and missions
----------------------------------------------------------------------
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(105,N'1405/06/14',N'2026-09-05 08:00:00',N'2026-09-05 16:30:00',N'2026-09-05 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(106,N'1405/06/14',N'2026-09-05 08:00:00',N'2026-09-05 16:45:00',N'2026-09-05 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(107,N'1405/06/14',N'2026-09-05 08:20:00',N'2026-09-05 16:30:00',N'2026-09-05 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(108,N'1405/06/14',N'2026-09-05 08:12:00',N'2026-09-05 16:50:00',N'2026-09-05 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(105,N'1405/06/15',N'2026-09-06 08:05:00',N'2026-09-06 16:45:00',N'2026-09-06 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(106,N'1405/06/15',N'2026-09-06 08:12:00',N'2026-09-06 16:50:00',N'2026-09-06 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(107,N'1405/06/15',N'2026-09-06 08:12:00',N'2026-09-06 16:30:00',N'2026-09-06 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(108,N'1405/06/15',N'2026-09-06 08:00:00',N'2026-09-06 16:45:00',N'2026-09-06 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(105,N'1405/06/16',N'2026-09-07 08:12:00',N'2026-09-07 16:50:00',N'2026-09-07 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(106,N'1405/06/16',N'2026-09-07 08:05:00',N'2026-09-07 16:30:00',N'2026-09-07 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(107,N'1405/06/16',N'2026-09-07 08:12:00',N'2026-09-07 16:50:00',N'2026-09-07 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(108,N'1405/06/16',N'2026-09-07 08:12:00',N'2026-09-07 16:45:00',N'2026-09-07 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(105,N'1405/06/17',N'2026-09-08 08:05:00',N'2026-09-08 16:50:00',N'2026-09-08 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(106,N'1405/06/17',N'2026-09-08 08:00:00',N'2026-09-08 16:30:00',N'2026-09-08 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(107,N'1405/06/17',N'2026-09-08 08:12:00',N'2026-09-08 16:30:00',N'2026-09-08 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(108,N'1405/06/17',N'2026-09-08 08:20:00',N'2026-09-08 16:50:00',N'2026-09-08 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(105,N'1405/06/18',N'2026-09-09 08:05:00',N'2026-09-09 16:45:00',N'2026-09-09 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(106,N'1405/06/18',N'2026-09-09 08:12:00',N'2026-09-09 16:30:00',N'2026-09-09 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(107,N'1405/06/18',N'2026-09-09 08:20:00',N'2026-09-09 16:45:00',N'2026-09-09 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(108,N'1405/06/18',N'2026-09-09 08:00:00',N'2026-09-09 16:30:00',N'2026-09-09 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(105,N'1405/06/21',N'2026-09-12 08:05:00',N'2026-09-12 16:30:00',N'2026-09-12 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(106,N'1405/06/21',N'2026-09-12 08:00:00',N'2026-09-12 16:50:00',N'2026-09-12 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(107,N'1405/06/21',N'2026-09-12 08:00:00',N'2026-09-12 16:50:00',N'2026-09-12 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(108,N'1405/06/21',N'2026-09-12 08:20:00',N'2026-09-12 16:45:00',N'2026-09-12 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(105,N'1405/06/22',N'2026-09-13 08:12:00',N'2026-09-13 16:45:00',N'2026-09-13 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(106,N'1405/06/22',N'2026-09-13 08:12:00',N'2026-09-13 16:45:00',N'2026-09-13 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(107,N'1405/06/22',N'2026-09-13 08:00:00',N'2026-09-13 16:30:00',N'2026-09-13 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(108,N'1405/06/22',N'2026-09-13 08:12:00',N'2026-09-13 16:30:00',N'2026-09-13 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(105,N'1405/06/23',N'2026-09-14 08:00:00',N'2026-09-14 16:50:00',N'2026-09-14 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(106,N'1405/06/23',N'2026-09-14 08:20:00',N'2026-09-14 16:50:00',N'2026-09-14 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(107,N'1405/06/23',N'2026-09-14 08:20:00',N'2026-09-14 16:30:00',N'2026-09-14 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(108,N'1405/06/23',N'2026-09-14 08:05:00',N'2026-09-14 16:30:00',N'2026-09-14 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(105,N'1405/06/24',N'2026-09-15 08:05:00',N'2026-09-15 16:30:00',N'2026-09-15 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(106,N'1405/06/24',N'2026-09-15 08:12:00',N'2026-09-15 16:50:00',N'2026-09-15 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(107,N'1405/06/24',N'2026-09-15 08:20:00',N'2026-09-15 16:50:00',N'2026-09-15 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(108,N'1405/06/24',N'2026-09-15 08:12:00',N'2026-09-15 16:30:00',N'2026-09-15 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(105,N'1405/06/25',N'2026-09-16 08:20:00',N'2026-09-16 16:30:00',N'2026-09-16 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(106,N'1405/06/25',N'2026-09-16 08:12:00',N'2026-09-16 16:50:00',N'2026-09-16 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(107,N'1405/06/25',N'2026-09-16 08:20:00',N'2026-09-16 16:30:00',N'2026-09-16 16:30:00',N'logout',GETDATE());
INSERT INTO Attendance(user_id,work_date,check_in,check_out,last_heartbeat,checkout_source,created_at) VALUES(108,N'1405/06/25',N'2026-09-16 08:20:00',N'2026-09-16 16:45:00',N'2026-09-16 16:30:00',N'logout',GETDATE());
INSERT INTO WeeklySchedule(staff_id,day_of_week,city_id,project_id,sort_order,created_by,created_at) VALUES(106,0,1,1,1,102,GETDATE());
INSERT INTO WeeklySchedule(staff_id,day_of_week,city_id,project_id,sort_order,created_by,created_at) VALUES(106,1,1,2,1,102,GETDATE());
INSERT INTO WeeklySchedule(staff_id,day_of_week,city_id,project_id,sort_order,created_by,created_at) VALUES(106,2,1,1,1,102,GETDATE());
INSERT INTO WeeklySchedule(staff_id,day_of_week,city_id,project_id,sort_order,created_by,created_at) VALUES(106,5,1,6,1,102,GETDATE());
INSERT INTO WeeklySchedule(staff_id,day_of_week,city_id,project_id,sort_order,created_by,created_at) VALUES(107,0,1,2,1,102,GETDATE());
INSERT INTO WeeklySchedule(staff_id,day_of_week,city_id,project_id,sort_order,created_by,created_at) VALUES(107,1,2,3,1,102,GETDATE());
INSERT INTO WeeklySchedule(staff_id,day_of_week,city_id,project_id,sort_order,created_by,created_at) VALUES(107,2,2,3,1,102,GETDATE());
INSERT INTO WeeklySchedule(staff_id,day_of_week,city_id,project_id,sort_order,created_by,created_at) VALUES(107,5,1,2,1,102,GETDATE());
INSERT INTO WeeklySchedule(staff_id,day_of_week,city_id,project_id,sort_order,created_by,created_at) VALUES(108,0,3,4,1,102,GETDATE());
INSERT INTO WeeklySchedule(staff_id,day_of_week,city_id,project_id,sort_order,created_by,created_at) VALUES(108,1,3,4,1,102,GETDATE());
INSERT INTO WeeklySchedule(staff_id,day_of_week,city_id,project_id,sort_order,created_by,created_at) VALUES(108,2,4,5,1,102,GETDATE());
INSERT INTO WeeklySchedule(staff_id,day_of_week,city_id,project_id,sort_order,created_by,created_at) VALUES(108,5,3,4,1,102,GETDATE());
INSERT INTO WeeklySchedule(staff_id,day_of_week,city_id,project_id,sort_order,created_by,created_at) VALUES(105,0,1,1,1,102,GETDATE());
INSERT INTO WeeklySchedule(staff_id,day_of_week,city_id,project_id,sort_order,created_by,created_at) VALUES(105,1,1,2,1,102,GETDATE());
INSERT INTO WeeklySchedule(staff_id,day_of_week,city_id,project_id,sort_order,created_by,created_at) VALUES(105,2,1,6,1,102,GETDATE());
INSERT INTO WeeklySchedule(staff_id,day_of_week,city_id,project_id,sort_order,created_by,created_at) VALUES(105,5,1,1,1,102,GETDATE());
INSERT INTO Leaves(staff_id,leave_date,leave_type,start_time,end_time,reason,created_by,status,reviewed_by,reviewed_at,created_at) VALUES(106,N'1405/06/21',N'daily',NULL,NULL,N'Annual leave',106,N'approved',102,GETDATE(),GETDATE());
INSERT INTO Leaves(staff_id,leave_date,leave_type,start_time,end_time,reason,created_by,status,reviewed_by,reviewed_at,created_at) VALUES(107,N'1405/06/29',N'hourly',N'10:00',N'13:00',N'Doctor''s appointment',107,N'pending',NULL,NULL,GETDATE());
INSERT INTO Leaves(staff_id,leave_date,leave_type,start_time,end_time,reason,created_by,status,reviewed_by,reviewed_at,created_at) VALUES(108,N'1405/07/01',N'daily',NULL,NULL,N'Personal leave',108,N'pending',NULL,NULL,GETDATE());
INSERT INTO Missions(staff_id,city_id,project_id,start_jalali,end_jalali,note,created_by,created_at) VALUES(108,3,4,N'1405/06/30',N'1405/07/01',N'Deploying the new release at the client site',102,GETDATE());
INSERT INTO Missions(staff_id,city_id,project_id,start_jalali,end_jalali,note,created_by,created_at) VALUES(107,2,3,N'1405/06/19',N'1405/06/20',N'User training session',102,GETDATE());

-- Contracts, addenda, statements and the financial plan
----------------------------------------------------------------------
MERGE ContractStatuses AS t USING (VALUES(1,N'Active'),(2,N'Closed')) AS v(id,name) ON t.id=v.id WHEN NOT MATCHED THEN INSERT(id,name,is_active) VALUES(v.id,v.name,1);
MERGE ContractStatementTypes AS t USING (VALUES(1,N'Interim'),(2,N'Final')) AS v(id,name) ON t.id=v.id WHEN NOT MATCHED THEN INSERT(id,name) VALUES(v.id,v.name);
SET IDENTITY_INSERT Contracts ON;
INSERT INTO Contracts(id,project_id,title,employer_name,contract_number,base_price,contract_type_id,contract_status_id,start_date,start_date_fa,end_date,end_date_fa,notification_date,notification_date_fa,notification_letter_number,work_order_code,financial_code,is_active,created_by,created_at) VALUES(1,1,N'Warehouse management system contract',N'Aria Distribution Co.',N'1405/A/11',4200000000,2,1,N'2025-11-22',N'1404/09/01',N'2026-03-22',N'1405/01/02',N'2025-11-12',N'1404/08/21',N'1405/1001',N'WO-140501',N'FIN-140501',1,103,GETDATE());
INSERT INTO Contracts(id,project_id,title,employer_name,contract_number,base_price,contract_type_id,contract_status_id,start_date,start_date_fa,end_date,end_date_fa,notification_date,notification_date_fa,notification_letter_number,work_order_code,financial_code,is_active,created_by,created_at) VALUES(2,2,N'Customer service portal contract',N'Sample Bank',N'1405/A/14',2650000000,1,1,N'2026-01-21',N'1404/11/01',N'2026-07-20',N'1405/04/29',N'2026-01-11',N'1404/10/21',N'1405/1002',N'WO-140502',N'FIN-140502',1,103,GETDATE());
INSERT INTO Contracts(id,project_id,title,employer_name,contract_number,base_price,contract_type_id,contract_status_id,start_date,start_date_fa,end_date,end_date_fa,notification_date,notification_date_fa,notification_letter_number,work_order_code,financial_code,is_active,created_by,created_at) VALUES(3,3,N'Loyalty club app contract',N'Mehr Retail Chain',N'1405/B/3',1850000000,2,1,N'2026-03-22',N'1405/01/02',N'2026-10-08',N'1405/07/16',N'2026-03-12',N'1404/12/21',N'1405/1003',N'WO-140503',N'FIN-140503',1,103,GETDATE());
INSERT INTO Contracts(id,project_id,title,employer_name,contract_number,base_price,contract_type_id,contract_status_id,start_date,start_date_fa,end_date,end_date_fa,notification_date,notification_date_fa,notification_letter_number,work_order_code,financial_code,is_active,created_by,created_at) VALUES(4,4,N'Financial reporting support contract',N'Pars Industrial Co.',N'1405/B/7',980000000,3,1,N'2026-05-21',N'1405/02/31',N'2027-01-16',N'1405/10/26',N'2026-05-11',N'1405/02/21',N'1405/1004',N'WO-140504',N'FIN-140504',1,103,GETDATE());
SET IDENTITY_INSERT Contracts OFF;
INSERT INTO ContractProjectTeams(contract_id,project_team_id,allocation_amount,is_active,linked_by,linked_at) VALUES(1,1,NULL,1,103,GETDATE());
INSERT INTO ContractProjectTeams(contract_id,project_team_id,allocation_amount,is_active,linked_by,linked_at) VALUES(2,1,NULL,1,103,GETDATE());
INSERT INTO ContractProjectTeams(contract_id,project_team_id,allocation_amount,is_active,linked_by,linked_at) VALUES(3,1,NULL,1,103,GETDATE());
INSERT INTO ContractProjectTeams(contract_id,project_team_id,allocation_amount,is_active,linked_by,linked_at) VALUES(4,2,NULL,1,103,GETDATE());
SET IDENTITY_INSERT ContractExtensions ON;
INSERT INTO ContractExtensions(id,contract_id,extension_number,letter_number,title,extension_date,extension_date_fa,start_date,start_date_fa,end_date,end_date_fa,price_mode,price_delta,resulting_price,internal_status,approved_by,approved_at,is_active,created_by,created_at) VALUES(1,1,N'1',N'1405/221',N'Wider scope for the warehouse reports',N'2026-05-21',N'1405/02/31',N'2026-05-21',N'1405/02/31',N'2026-11-17',N'1405/08/26',N'delta',350000000,4550000000,N'approved',101,GETDATE(),1,103,GETDATE());
INSERT INTO ContractExtensions(id,contract_id,extension_number,letter_number,title,extension_date,extension_date_fa,start_date,start_date_fa,end_date,end_date_fa,price_mode,price_delta,resulting_price,internal_status,approved_by,approved_at,is_active,created_by,created_at) VALUES(2,3,N'1',N'1405/239',N'Three-month extension of loyalty support',N'2026-08-04',N'1405/05/13',N'2026-08-04',N'1405/05/13',N'2026-11-02',N'1405/08/11',N'delta',180000000,2030000000,N'pending',NULL,NULL,1,103,GETDATE());
SET IDENTITY_INSERT ContractExtensions OFF;
SET IDENTITY_INSERT ContractStatements ON;
INSERT INTO ContractStatements(id,contract_id,statement_type_id,statement_number,title,statement_date,statement_date_fa,letter_number,start_date,start_date_fa,end_date,end_date_fa,requested_price,requested_without_vat,requested_vat,confirmed_price,confirmed_without_vat,confirmed_vat,business_status,progress_percentage,internal_approved_by,internal_approved_at,sent_at,employer_decision_by,employer_decision_at,is_current,is_active,project_team_id,created_by,created_at) VALUES(1,1,1,N'1',N'Interim statement no. 1',N'2026-04-21',N'1405/02/01',N'1405/2001',N'2026-03-22',N'1405/01/02',N'2026-04-21',N'1405/02/01',1250000000,1136363636,113636363,1250000000,1136363636,113636363,N'employer_approved',100,101,GETDATE(),GETDATE(),110,GETDATE(),1,1,@team_project_1,103,GETDATE());
INSERT INTO ContractStatements(id,contract_id,statement_type_id,statement_number,title,statement_date,statement_date_fa,letter_number,start_date,start_date_fa,end_date,end_date_fa,requested_price,requested_without_vat,requested_vat,confirmed_price,confirmed_without_vat,confirmed_vat,business_status,progress_percentage,internal_approved_by,internal_approved_at,sent_at,employer_decision_by,employer_decision_at,is_current,is_active,project_team_id,created_by,created_at) VALUES(2,1,1,N'2',N'Interim statement no. 2',N'2026-07-20',N'1405/04/29',N'1405/2002',N'2026-06-20',N'1405/03/30',N'2026-07-20',N'1405/04/29',1430000000,1300000000,130000000,1380000000,1254545454,125454545,N'employer_approved',100,101,GETDATE(),GETDATE(),110,GETDATE(),1,1,@team_project_1,103,GETDATE());
INSERT INTO ContractStatements(id,contract_id,statement_type_id,statement_number,title,statement_date,statement_date_fa,letter_number,start_date,start_date_fa,end_date,end_date_fa,requested_price,requested_without_vat,requested_vat,confirmed_price,confirmed_without_vat,confirmed_vat,business_status,progress_percentage,internal_approved_by,internal_approved_at,sent_at,employer_decision_by,employer_decision_at,is_current,is_active,project_team_id,created_by,created_at) VALUES(3,2,1,N'1',N'Interim statement no. 1',N'2026-06-20',N'1405/03/30',N'1405/2003',N'2026-05-21',N'1405/02/31',N'2026-06-20',N'1405/03/30',980000000,890909090,89090909,980000000,890909090,89090909,N'employer_approved',100,101,GETDATE(),GETDATE(),110,GETDATE(),1,1,@team_project_2,103,GETDATE());
INSERT INTO ContractStatements(id,contract_id,statement_type_id,statement_number,title,statement_date,statement_date_fa,letter_number,start_date,start_date_fa,end_date,end_date_fa,requested_price,requested_without_vat,requested_vat,confirmed_price,confirmed_without_vat,confirmed_vat,business_status,progress_percentage,internal_approved_by,internal_approved_at,sent_at,employer_decision_by,employer_decision_at,is_current,is_active,project_team_id,created_by,created_at) VALUES(4,3,1,N'1',N'Interim statement no. 1',N'2026-08-19',N'1405/05/28',N'1405/2004',N'2026-07-20',N'1405/04/29',N'2026-08-19',N'1405/05/28',640000000,581818181,58181818,NULL,NULL,NULL,N'sent',60,NULL,NULL,GETDATE(),NULL,NULL,1,1,@team_project_3,103,GETDATE());
INSERT INTO ContractStatements(id,contract_id,statement_type_id,statement_number,title,statement_date,statement_date_fa,letter_number,start_date,start_date_fa,end_date,end_date_fa,requested_price,requested_without_vat,requested_vat,confirmed_price,confirmed_without_vat,confirmed_vat,business_status,progress_percentage,internal_approved_by,internal_approved_at,sent_at,employer_decision_by,employer_decision_at,is_current,is_active,project_team_id,created_by,created_at) VALUES(5,4,2,N'1',N'Final support statement',N'2026-08-29',N'1405/06/07',N'1405/2005',N'2026-07-30',N'1405/05/08',N'2026-08-29',N'1405/06/07',310000000,281818181,28181818,NULL,NULL,NULL,N'internal_approved',60,101,GETDATE(),NULL,NULL,NULL,1,1,@team_project_4,103,GETDATE());
SET IDENTITY_INSERT ContractStatements OFF;
INSERT INTO ContractStatementItems(statement_id,item_code,title,quantity,unit_price,total_price,created_at) VALUES(1,N'R-1',N'Analysis and design of the warehouse module',1,450000000,450000000,GETDATE());
INSERT INTO ContractStatementItems(statement_id,item_code,title,quantity,unit_price,total_price,created_at) VALUES(1,N'R-2',N'Report implementation',2,400000000,800000000,GETDATE());
INSERT INTO ContractStatementItems(statement_id,item_code,title,quantity,unit_price,total_price,created_at) VALUES(3,N'R-1',N'Portal rollout',1,600000000,600000000,GETDATE());
INSERT INTO ContractStatementItems(statement_id,item_code,title,quantity,unit_price,total_price,created_at) VALUES(3,N'R-2',N'User training',2,190000000,380000000,GETDATE());
INSERT INTO ContractStatementItems(statement_id,item_code,title,quantity,unit_price,total_price,created_at) VALUES(4,N'R-1',N'App development',1,640000000,640000000,GETDATE());
SET IDENTITY_INSERT FinancialPlans ON;
INSERT INTO FinancialPlans(id,jalali_year,title,annual_target,approved_target,status,is_current,version_no,created_by,created_at) VALUES(1,1405,N'Financial plan 1405',9500000000,9500000000,N'approved',1,1,103,GETDATE());
SET IDENTITY_INSERT FinancialPlans OFF;
INSERT INTO FinancialPlanPeriods(plan_id,month_no,target_amount,allocation_mode,allocation_percent,is_locked,updated_by,updated_at) VALUES(1,1,700000000,N'manual',NULL,0,103,GETDATE());
INSERT INTO FinancialPlanPeriods(plan_id,month_no,target_amount,allocation_mode,allocation_percent,is_locked,updated_by,updated_at) VALUES(1,2,750000000,N'manual',NULL,0,103,GETDATE());
INSERT INTO FinancialPlanPeriods(plan_id,month_no,target_amount,allocation_mode,allocation_percent,is_locked,updated_by,updated_at) VALUES(1,3,800000000,N'manual',NULL,0,103,GETDATE());
INSERT INTO FinancialPlanPeriods(plan_id,month_no,target_amount,allocation_mode,allocation_percent,is_locked,updated_by,updated_at) VALUES(1,4,820000000,N'manual',NULL,0,103,GETDATE());
INSERT INTO FinancialPlanPeriods(plan_id,month_no,target_amount,allocation_mode,allocation_percent,is_locked,updated_by,updated_at) VALUES(1,5,780000000,N'manual',NULL,0,103,GETDATE());
INSERT INTO FinancialPlanPeriods(plan_id,month_no,target_amount,allocation_mode,allocation_percent,is_locked,updated_by,updated_at) VALUES(1,6,850000000,N'manual',NULL,0,103,GETDATE());
INSERT INTO FinancialPlanPeriods(plan_id,month_no,target_amount,allocation_mode,allocation_percent,is_locked,updated_by,updated_at) VALUES(1,7,900000000,N'manual',NULL,0,103,GETDATE());
INSERT INTO FinancialPlanPeriods(plan_id,month_no,target_amount,allocation_mode,allocation_percent,is_locked,updated_by,updated_at) VALUES(1,8,820000000,N'manual',NULL,0,103,GETDATE());
INSERT INTO FinancialPlanPeriods(plan_id,month_no,target_amount,allocation_mode,allocation_percent,is_locked,updated_by,updated_at) VALUES(1,9,760000000,N'manual',NULL,0,103,GETDATE());
INSERT INTO FinancialPlanPeriods(plan_id,month_no,target_amount,allocation_mode,allocation_percent,is_locked,updated_by,updated_at) VALUES(1,10,740000000,N'manual',NULL,0,103,GETDATE());
INSERT INTO FinancialPlanPeriods(plan_id,month_no,target_amount,allocation_mode,allocation_percent,is_locked,updated_by,updated_at) VALUES(1,11,780000000,N'manual',NULL,0,103,GETDATE());
INSERT INTO FinancialPlanPeriods(plan_id,month_no,target_amount,allocation_mode,allocation_percent,is_locked,updated_by,updated_at) VALUES(1,12,800000000,N'manual',NULL,0,103,GETDATE());

-- Points, coins, badges and the shop
----------------------------------------------------------------------
INSERT INTO GameWallets(user_id,updated_at) VALUES(105,GETDATE());
INSERT INTO GameWallets(user_id,updated_at) VALUES(106,GETDATE());
INSERT INTO GameWallets(user_id,updated_at) VALUES(107,GETDATE());
INSERT INTO GameWallets(user_id,updated_at) VALUES(108,GETDATE());
INSERT INTO GameWallets(user_id,updated_at) VALUES(102,GETDATE());
INSERT INTO GameWallets(user_id,updated_at) VALUES(103,GETDATE());
INSERT INTO GameWallets(user_id,updated_at) VALUES(104,GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(105,N'1405-2',N'task',1001,310,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(105,N'1405-2',N'task',1002,310,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(105,N'1405-2',N'task',1003,310,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(105,N'1405-2',N'task',1004,310,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(105,N'1405-3',N'task',1001,155,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(105,N'1405-3',N'task',1002,155,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(105,N'1405-3',N'task',1003,155,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(105,N'1405-3',N'task',1004,155,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(106,N'1405-2',N'task',1001,465,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(106,N'1405-2',N'task',1002,465,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(106,N'1405-2',N'task',1003,465,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(106,N'1405-2',N'task',1004,465,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(106,N'1405-3',N'task',1001,232,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(106,N'1405-3',N'task',1002,232,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(106,N'1405-3',N'task',1003,232,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(106,N'1405-3',N'task',1004,232,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(107,N'1405-2',N'task',1001,380,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(107,N'1405-2',N'task',1002,380,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(107,N'1405-2',N'task',1003,380,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(107,N'1405-2',N'task',1004,380,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(107,N'1405-3',N'task',1001,190,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(107,N'1405-3',N'task',1002,190,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(107,N'1405-3',N'task',1003,190,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(107,N'1405-3',N'task',1004,190,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(108,N'1405-2',N'task',1001,245,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(108,N'1405-2',N'task',1002,245,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(108,N'1405-2',N'task',1003,245,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(108,N'1405-2',N'task',1004,245,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(108,N'1405-3',N'task',1001,122,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(108,N'1405-3',N'task',1002,122,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(108,N'1405-3',N'task',1003,122,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(108,N'1405-3',N'task',1004,122,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(102,N'1405-2',N'task',1001,160,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(102,N'1405-2',N'task',1002,160,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(102,N'1405-2',N'task',1003,160,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(102,N'1405-2',N'task',1004,160,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(102,N'1405-3',N'task',1001,80,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(102,N'1405-3',N'task',1002,80,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(102,N'1405-3',N'task',1003,80,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(102,N'1405-3',N'task',1004,80,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(103,N'1405-2',N'task',1001,130,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(103,N'1405-2',N'task',1002,130,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(103,N'1405-2',N'task',1003,130,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(103,N'1405-2',N'task',1004,130,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(103,N'1405-3',N'task',1001,65,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(103,N'1405-3',N'task',1002,65,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(103,N'1405-3',N'task',1003,65,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(103,N'1405-3',N'task',1004,65,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(104,N'1405-2',N'task',1001,175,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(104,N'1405-2',N'task',1002,175,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(104,N'1405-2',N'task',1003,175,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(104,N'1405-2',N'task',1004,175,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(104,N'1405-3',N'task',1001,87,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(104,N'1405-3',N'task',1002,87,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(104,N'1405-3',N'task',1003,87,N'Points for an approved task',GETDATE());
INSERT INTO GameXpLedger(user_id,season_key,source_type,source_id,points,note,created_at) VALUES(104,N'1405-3',N'task',1004,87,N'Points for an approved task',GETDATE());
INSERT INTO GameCoinLedger(user_id,amount,kind,source_type,source_id,note,created_by,created_at) VALUES(106,420,N'earn',N'task',NULL,N'Coins for approved tasks',1,GETDATE());
INSERT INTO GameCoinLedger(user_id,amount,kind,source_type,source_id,note,created_by,created_at) VALUES(107,360,N'earn',N'task',NULL,N'Coins for approved tasks',1,GETDATE());
INSERT INTO GameCoinLedger(user_id,amount,kind,source_type,source_id,note,created_by,created_at) VALUES(108,240,N'earn',N'task',NULL,N'Coins for approved tasks',1,GETDATE());
INSERT INTO GameCoinLedger(user_id,amount,kind,source_type,source_id,note,created_by,created_at) VALUES(105,300,N'earn',N'task',NULL,N'Coins for approved tasks',1,GETDATE());
INSERT INTO GameCoinLedger(user_id,amount,kind,source_type,source_id,note,created_by,created_at) VALUES(106,-150,N'spend',N'task',NULL,N'Bought bonus leave',1,GETDATE());
INSERT INTO GameCoinLedger(user_id,amount,kind,source_type,source_id,note,created_by,created_at) VALUES(107,-80,N'spend',N'task',NULL,N'Bought a gift card',1,GETDATE());
SET IDENTITY_INSERT ShopItems ON;
INSERT INTO ShopItems(id,name,description,item_type,price,is_active,is_archived,show_in_public,leave_mode,leave_hours,reward_amount,created_by,created_at) VALUES(1,N'One day of bonus leave',N'A full day off, agreed with the group lead',N'leave',150,1,0,1,N'daily',NULL,NULL,1,GETDATE());
INSERT INTO ShopItems(id,name,description,item_type,price,is_active,is_archived,show_in_public,leave_mode,leave_hours,reward_amount,created_by,created_at) VALUES(2,N'Three hours of leave',N'Three hours off during a working day',N'leave',60,1,0,1,N'hourly',3,NULL,1,GETDATE());
INSERT INTO ShopItems(id,name,description,item_type,price,is_active,is_archived,show_in_public,leave_mode,leave_hours,reward_amount,created_by,created_at) VALUES(3,N'One day of remote work',N'Working from home for a day',N'remote',90,1,0,1,NULL,NULL,NULL,1,GETDATE());
INSERT INTO ShopItems(id,name,description,item_type,price,is_active,is_archived,show_in_public,leave_mode,leave_hours,reward_amount,created_by,created_at) VALUES(4,N'Gift card worth 5,000,000 IRR',N'Gift card for the partner stores',N'goods',200,1,0,1,NULL,NULL,NULL,1,GETDATE());
INSERT INTO ShopItems(id,name,description,item_type,price,is_active,is_archived,show_in_public,leave_mode,leave_hours,reward_amount,created_by,created_at) VALUES(5,N'Cash reward',N'Cash reward paid with next month''s salary',N'money',300,1,0,1,NULL,NULL,5000000,1,GETDATE());
INSERT INTO ShopItems(id,name,description,item_type,price,is_active,is_archived,show_in_public,leave_mode,leave_hours,reward_amount,created_by,created_at) VALUES(6,N'Gold avatar frame',N'A gold frame for the profile picture',N'cosmetic',80,1,0,1,NULL,NULL,NULL,1,GETDATE());
SET IDENTITY_INSERT ShopItems OFF;
INSERT INTO ShopOrders(item_id,user_id,item_type,item_name,base_price,price_paid,discount_percent,status,show_in_public,created_at) VALUES(1,106,N'leave',N'One day of bonus leave',150,150,0,N'scheduled',1,GETDATE());
INSERT INTO ShopOrders(item_id,user_id,item_type,item_name,base_price,price_paid,discount_percent,status,show_in_public,created_at) VALUES(4,107,N'goods',N'Gift card worth 5,000,000 IRR',200,200,0,N'pending_delivery',1,GETDATE());
INSERT INTO ShopOrders(item_id,user_id,item_type,item_name,base_price,price_paid,discount_percent,status,show_in_public,created_at) VALUES(6,105,N'cosmetic',N'Gold avatar frame',80,80,0,N'active',1,GETDATE());
INSERT INTO GameKudos(from_user,to_user,task_id,note,coins,created_at) VALUES(102,106,NULL,N'Thanks for fixing the portal error so quickly.',5,GETDATE());
INSERT INTO GameKudos(from_user,to_user,task_id,note,coins,created_at) VALUES(105,107,NULL,N'Thanks for following up on the client''s request.',5,GETDATE());
INSERT INTO GameKudos(from_user,to_user,task_id,note,coins,created_at) VALUES(101,108,NULL,N'Thanks for taking the Mashhad trip.',5,GETDATE());
INSERT INTO GameUserBadges(user_id,badge_key,period_key,coins,awarded_at) VALUES(106,N'steady',N'1405-2',20,GETDATE());
INSERT INTO GameUserBadges(user_id,badge_key,period_key,coins,awarded_at) VALUES(107,N'quick',N'1405-2',20,GETDATE());
INSERT INTO GameMonthlyRatings(user_id,month_key,stars,note,rated_by,rated_at,coins) VALUES(102,N'1405-06',5,N'Monthly review',101,GETDATE(),100);
INSERT INTO GameMonthlyRatings(user_id,month_key,stars,note,rated_by,rated_at,coins) VALUES(103,N'1405-06',4,N'Monthly review',101,GETDATE(),80);
INSERT INTO GameMonthlyRatings(user_id,month_key,stars,note,rated_by,rated_at,coins) VALUES(104,N'1405-06',4,N'Monthly review',101,GETDATE(),80);

-- Notifications
----------------------------------------------------------------------
INSERT INTO Notifications(user_id,kind,title,link_task_id,is_read,created_at) VALUES(106,N'task_assigned',N'The task “Add SMS notifications” was assigned to you',1027,0,GETDATE());
INSERT INTO Notifications(user_id,kind,title,link_task_id,is_read,created_at) VALUES(107,N'task_returned',N'The task “Portal users cannot sign in” was returned',1006,0,GETDATE());
INSERT INTO Notifications(user_id,kind,title,link_task_id,is_read,created_at) VALUES(102,N'task_submitted',N'The task “Phone support for portal users” is waiting for approval',1007,0,GETDATE());
COMMIT TRANSACTION;
PRINT N'--- demo data loaded ---';
SELECT * FROM (
    SELECT 'Attendance' AS [table], COUNT(*) AS [rows] FROM Attendance
    UNION ALL SELECT 'Cities' AS [table], COUNT(*) AS [rows] FROM Cities
    UNION ALL SELECT 'ContractExtensions' AS [table], COUNT(*) AS [rows] FROM ContractExtensions
    UNION ALL SELECT 'ContractProjectTeams' AS [table], COUNT(*) AS [rows] FROM ContractProjectTeams
    UNION ALL SELECT 'ContractStatementItems' AS [table], COUNT(*) AS [rows] FROM ContractStatementItems
    UNION ALL SELECT 'ContractStatements' AS [table], COUNT(*) AS [rows] FROM ContractStatements
    UNION ALL SELECT 'Contracts' AS [table], COUNT(*) AS [rows] FROM Contracts
    UNION ALL SELECT 'FinancialPlanPeriods' AS [table], COUNT(*) AS [rows] FROM FinancialPlanPeriods
    UNION ALL SELECT 'FinancialPlans' AS [table], COUNT(*) AS [rows] FROM FinancialPlans
    UNION ALL SELECT 'GameCoinLedger' AS [table], COUNT(*) AS [rows] FROM GameCoinLedger
    UNION ALL SELECT 'GameKudos' AS [table], COUNT(*) AS [rows] FROM GameKudos
    UNION ALL SELECT 'GameMonthlyRatings' AS [table], COUNT(*) AS [rows] FROM GameMonthlyRatings
    UNION ALL SELECT 'GameUserBadges' AS [table], COUNT(*) AS [rows] FROM GameUserBadges
    UNION ALL SELECT 'GameWallets' AS [table], COUNT(*) AS [rows] FROM GameWallets
    UNION ALL SELECT 'GameXpLedger' AS [table], COUNT(*) AS [rows] FROM GameXpLedger
    UNION ALL SELECT 'Leaves' AS [table], COUNT(*) AS [rows] FROM Leaves
    UNION ALL SELECT 'Missions' AS [table], COUNT(*) AS [rows] FROM Missions
    UNION ALL SELECT 'Notifications' AS [table], COUNT(*) AS [rows] FROM Notifications
    UNION ALL SELECT 'ProjectTeams' AS [table], COUNT(*) AS [rows] FROM ProjectTeams
    UNION ALL SELECT 'Projects' AS [table], COUNT(*) AS [rows] FROM Projects
    UNION ALL SELECT 'ShopItems' AS [table], COUNT(*) AS [rows] FROM ShopItems
    UNION ALL SELECT 'ShopOrders' AS [table], COUNT(*) AS [rows] FROM ShopOrders
    UNION ALL SELECT 'TaskAssignees' AS [table], COUNT(*) AS [rows] FROM TaskAssignees
    UNION ALL SELECT 'TaskCategories' AS [table], COUNT(*) AS [rows] FROM TaskCategories
    UNION ALL SELECT 'TaskComments' AS [table], COUNT(*) AS [rows] FROM TaskComments
    UNION ALL SELECT 'TaskEvents' AS [table], COUNT(*) AS [rows] FROM TaskEvents
    UNION ALL SELECT 'TaskTimeLog' AS [table], COUNT(*) AS [rows] FROM TaskTimeLog
    UNION ALL SELECT 'Tasks' AS [table], COUNT(*) AS [rows] FROM Tasks
    UNION ALL SELECT 'TeamMembers' AS [table], COUNT(*) AS [rows] FROM TeamMembers
    UNION ALL SELECT 'Teams' AS [table], COUNT(*) AS [rows] FROM Teams
    UNION ALL SELECT 'Users' AS [table], COUNT(*) AS [rows] FROM Users
    UNION ALL SELECT 'WeeklySchedule' AS [table], COUNT(*) AS [rows] FROM WeeklySchedule
    UNION ALL SELECT 'WorkGroupMembers' AS [table], COUNT(*) AS [rows] FROM WorkGroupMembers
    UNION ALL SELECT 'WorkGroupProjects' AS [table], COUNT(*) AS [rows] FROM WorkGroupProjects
    UNION ALL SELECT 'WorkGroups' AS [table], COUNT(*) AS [rows] FROM WorkGroups
) AS loaded ORDER BY [table];
