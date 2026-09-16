# -*- coding: utf-8 -*-
"""Team, reporting and end-to-end encrypted chat layer for TaskHub 8.

This module receives the already configured connection factory from
``taskhub.py``.  It never imports or changes database connection settings.
All schema changes are additive and idempotent.
"""
from __future__ import annotations

import base64
import datetime as _dt
import decimal as _decimal
import hashlib
import io
import json
import os
import secrets
import threading

from flask import g, jsonify, request, send_file
from cryptography.fernet import Fernet

import fa_font
from config import CHAT_MODE
from lan_chat_crypto import ServerChatCrypto
from rbac import user_has_permission
from team_scope import CHAT_CLIENT_ROLES, chat_pair_allowed, has_company_scope
import datetime as _datetime
import gamification_domain as _gd
from v8_domain import (
    GLOBAL_TEAM_VIEW_ROLES,
    REPORT_ROLES,
    percent,
    person_output_shares,
    validate_team_allocations,
)


TEAM_ROLES = ("manager", "planner", "member")
CHAT_INTERNAL_ROLES = (
    "admin", "manager", "planner", "finance", "reporter", "support", "lead"
)
CHAT_CLIENT_RULE = ("کارفرما و راهبر فقط با کاربران شرکت خودشان (همان پروژه) "
                    "و پلنر تیم آن پروژه گفتگو می‌کنند")


def _b64url_int(value):
    raw = str(value or "")
    raw += "=" * (-len(raw) % 4)
    return int.from_bytes(base64.urlsafe_b64decode(raw.encode("ascii")), "big")


def _mgf1(seed, length):
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(hashlib.sha256(seed + counter.to_bytes(4, "big")).digest())
        counter += 1
    return bytes(out[:length])


def _rsa_oaep_encrypt(public_jwk, message):
    """Encrypt a short challenge using an RSA-OAEP-256 public JWK.

    This tiny standards-based encoder avoids adding a server crypto package.
    It is used only to prove that an already-approved browser still owns its
    private key before it may approve another device. Conversation keys and
    message plaintext never pass through this helper or the server.
    """
    jwk = json.loads(public_jwk) if isinstance(public_jwk, str) else public_jwk
    n = _b64url_int(jwk.get("n")); e = _b64url_int(jwk.get("e"))
    k = (n.bit_length() + 7) // 8
    hlen = hashlib.sha256().digest_size
    if len(message) > k - 2 * hlen - 2:
        raise ValueError("RSA OAEP challenge is too long")
    lhash = hashlib.sha256(b"").digest()
    padding = b"\x00" * (k - len(message) - 2 * hlen - 2)
    db = lhash + padding + b"\x01" + message
    seed = secrets.token_bytes(hlen)
    db_mask = _mgf1(seed, k - hlen - 1)
    masked_db = bytes(a ^ b for a, b in zip(db, db_mask))
    seed_mask = _mgf1(masked_db, hlen)
    masked_seed = bytes(a ^ b for a, b in zip(seed, seed_mask))
    encoded = b"\x00" + masked_seed + masked_db
    encrypted = pow(int.from_bytes(encoded, "big"), e, n).to_bytes(k, "big")
    return base64.b64encode(encrypted).decode("ascii")


def init_v8_tables(conn):
    """Apply the v8 schema and migrate current records to a safe default team."""
    cur = conn.cursor()
    sqls = [
        """IF OBJECT_ID('Teams','U') IS NULL CREATE TABLE Teams(
            id INT IDENTITY PRIMARY KEY,code NVARCHAR(50) NULL,name NVARCHAR(160) NOT NULL,
            description NVARCHAR(1000) NULL,is_active BIT NOT NULL DEFAULT 1,
            created_by INT NULL,created_at DATETIME NOT NULL DEFAULT GETDATE(),
            updated_by INT NULL,updated_at DATETIME NULL)""",
        """IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='UX_Teams_code'
            AND object_id=OBJECT_ID('Teams'))
            CREATE UNIQUE INDEX UX_Teams_code ON Teams(code) WHERE code IS NOT NULL""",
        """IF OBJECT_ID('TeamMembers','U') IS NULL CREATE TABLE TeamMembers(
            team_id INT NOT NULL REFERENCES Teams(id) ON DELETE CASCADE,
            user_id INT NOT NULL REFERENCES Users(id) ON DELETE CASCADE,
            team_role NVARCHAR(20) NOT NULL DEFAULT 'member',
            is_primary BIT NOT NULL DEFAULT 0,is_active BIT NOT NULL DEFAULT 1,
            joined_at DATETIME NOT NULL DEFAULT GETDATE(),left_at DATETIME NULL,
            added_by INT NULL,
            CONSTRAINT PK_TeamMembers PRIMARY KEY(team_id,user_id),
            CONSTRAINT CK_TeamMembers_role CHECK(team_role IN ('manager','planner','member')))""",
        "IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_TeamMembers_user' AND object_id=OBJECT_ID('TeamMembers')) CREATE INDEX IX_TeamMembers_user ON TeamMembers(user_id,is_active,team_id)",
        """IF OBJECT_ID('TeamProjectTypes','U') IS NULL CREATE TABLE TeamProjectTypes(
            team_id INT NOT NULL REFERENCES Teams(id) ON DELETE CASCADE,
            project_type_id INT NOT NULL REFERENCES ProjectTypes(id),
            assignment_role NVARCHAR(20) NOT NULL DEFAULT 'primary',
            is_active BIT NOT NULL DEFAULT 1,assigned_by INT NULL,
            assigned_at DATETIME NOT NULL DEFAULT GETDATE(),
            CONSTRAINT PK_TeamProjectTypes PRIMARY KEY(team_id,project_type_id),
            CONSTRAINT CK_TeamProjectTypes_role CHECK(assignment_role IN ('primary','collaborator')))""",
        """IF OBJECT_ID('ProjectTeams','U') IS NULL CREATE TABLE ProjectTeams(
            id INT IDENTITY PRIMARY KEY,project_id INT NOT NULL REFERENCES Projects(id),
            team_id INT NOT NULL REFERENCES Teams(id),title NVARCHAR(200) NULL,
            is_primary BIT NOT NULL DEFAULT 0,is_active BIT NOT NULL DEFAULT 1,
            start_date DATE NULL,end_date DATE NULL,created_by INT NULL,
            created_at DATETIME NOT NULL DEFAULT GETDATE(),updated_by INT NULL,
            updated_at DATETIME NULL)""",
        """IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='UX_ProjectTeams_active'
            AND object_id=OBJECT_ID('ProjectTeams'))
            CREATE UNIQUE INDEX UX_ProjectTeams_active ON ProjectTeams(project_id,team_id)
            WHERE is_active=1""",
        "IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_ProjectTeams_team' AND object_id=OBJECT_ID('ProjectTeams')) CREATE INDEX IX_ProjectTeams_team ON ProjectTeams(team_id,is_active,project_id)",
        """IF OBJECT_ID('ContractProjectTeams','U') IS NULL CREATE TABLE ContractProjectTeams(
            contract_id INT NOT NULL REFERENCES Contracts(id),
            project_team_id INT NOT NULL REFERENCES ProjectTeams(id),
            allocation_amount DECIMAL(18,0) NULL,is_active BIT NOT NULL DEFAULT 1,
            linked_by INT NULL,linked_at DATETIME NOT NULL DEFAULT GETDATE(),
            CONSTRAINT PK_ContractProjectTeams PRIMARY KEY(contract_id,project_team_id))""",
        "IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_ContractProjectTeams_workstream' AND object_id=OBJECT_ID('ContractProjectTeams')) CREATE INDEX IX_ContractProjectTeams_workstream ON ContractProjectTeams(project_team_id,is_active,contract_id)",
        """IF OBJECT_ID('ContractExtensionTeams','U') IS NULL CREATE TABLE ContractExtensionTeams(
            extension_id INT NOT NULL REFERENCES ContractExtensions(id),
            project_team_id INT NOT NULL REFERENCES ProjectTeams(id),
            CONSTRAINT PK_ContractExtensionTeams PRIMARY KEY(extension_id,project_team_id))""",
        """IF OBJECT_ID('ContractStatementTeams','U') IS NULL CREATE TABLE ContractStatementTeams(
            statement_id INT NOT NULL REFERENCES ContractStatements(id),
            project_team_id INT NOT NULL REFERENCES ProjectTeams(id),
            allocation_percent DECIMAL(9,4) NOT NULL,
            is_active BIT NOT NULL DEFAULT 1,linked_by INT NULL,
            linked_at DATETIME NOT NULL DEFAULT GETDATE(),
            CONSTRAINT PK_ContractStatementTeams PRIMARY KEY(statement_id,project_team_id),
            CONSTRAINT CK_ContractStatementTeams_percent
              CHECK(allocation_percent>0 AND allocation_percent<=100))""",
        "IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_ContractStatementTeams_workstream' AND object_id=OBJECT_ID('ContractStatementTeams')) CREATE INDEX IX_ContractStatementTeams_workstream ON ContractStatementTeams(project_team_id,is_active,statement_id) INCLUDE(allocation_percent)",
        "IF COL_LENGTH('Tasks','project_team_id') IS NULL ALTER TABLE Tasks ADD project_team_id INT NULL",
        "IF COL_LENGTH('Tasks','progress_weight') IS NULL ALTER TABLE Tasks ADD progress_weight DECIMAL(9,2) NOT NULL CONSTRAINT DF_Tasks_progress_weight DEFAULT 1 WITH VALUES",
        "IF NOT EXISTS(SELECT 1 FROM sys.foreign_keys WHERE name='FK_Tasks_ProjectTeams') ALTER TABLE Tasks ADD CONSTRAINT FK_Tasks_ProjectTeams FOREIGN KEY(project_team_id) REFERENCES ProjectTeams(id)",
        "IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_Tasks_project_team' AND object_id=OBJECT_ID('Tasks')) CREATE INDEX IX_Tasks_project_team ON Tasks(project_team_id,status,project_id) INCLUDE(progress_weight,staff_id)",
        "IF COL_LENGTH('ContractStatements','project_team_id') IS NULL ALTER TABLE ContractStatements ADD project_team_id INT NULL",
        "IF NOT EXISTS(SELECT 1 FROM sys.foreign_keys WHERE name='FK_Statements_ProjectTeams') ALTER TABLE ContractStatements ADD CONSTRAINT FK_Statements_ProjectTeams FOREIGN KEY(project_team_id) REFERENCES ProjectTeams(id)",
        "IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_Statements_project_team' AND object_id=OBJECT_ID('ContractStatements')) CREATE INDEX IX_Statements_project_team ON ContractStatements(project_team_id,business_status,is_active,is_current)",
        "IF COL_LENGTH('PlannedStatements','project_team_id') IS NULL ALTER TABLE PlannedStatements ADD project_team_id INT NULL",
        "IF NOT EXISTS(SELECT 1 FROM sys.foreign_keys WHERE name='FK_PlannedStatements_ProjectTeams') ALTER TABLE PlannedStatements ADD CONSTRAINT FK_PlannedStatements_ProjectTeams FOREIGN KEY(project_team_id) REFERENCES ProjectTeams(id)",
        """IF OBJECT_ID('TeamFinancialTargets','U') IS NULL CREATE TABLE TeamFinancialTargets(
            id INT IDENTITY PRIMARY KEY,plan_id INT NOT NULL REFERENCES FinancialPlans(id),
            team_id INT NOT NULL REFERENCES Teams(id),annual_target DECIMAL(18,0) NOT NULL DEFAULT 0,
            change_reason NVARCHAR(500) NULL,version_no INT NOT NULL DEFAULT 1,
            is_current BIT NOT NULL DEFAULT 1,created_by INT NULL,
            created_at DATETIME NOT NULL DEFAULT GETDATE(),updated_by INT NULL,
            updated_at DATETIME NULL)""",
        """IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='UX_TeamFinancialTargets_current'
            AND object_id=OBJECT_ID('TeamFinancialTargets'))
            CREATE UNIQUE INDEX UX_TeamFinancialTargets_current
            ON TeamFinancialTargets(plan_id,team_id) WHERE is_current=1""",
        """IF OBJECT_ID('TeamFinancialTargetPeriods','U') IS NULL CREATE TABLE TeamFinancialTargetPeriods(
            id INT IDENTITY PRIMARY KEY,target_id INT NOT NULL REFERENCES TeamFinancialTargets(id),
            month_no TINYINT NOT NULL,target_amount DECIMAL(18,0) NOT NULL DEFAULT 0,
            allocation_mode NVARCHAR(10) NOT NULL DEFAULT 'amount',
            allocation_percent DECIMAL(9,4) NULL,is_locked BIT NOT NULL DEFAULT 0,
            updated_by INT NULL,updated_at DATETIME NULL,
            CONSTRAINT UQ_TeamFinancialTargetPeriods UNIQUE(target_id,month_no),
            CONSTRAINT CK_TeamFinancialTargetPeriods_month CHECK(month_no BETWEEN 1 AND 12))""",
        # Device public keys and encrypted conversation keys.  Private keys
        # never have a server column by design.
        """IF OBJECT_ID('ChatDevices','U') IS NULL CREATE TABLE ChatDevices(
            id INT IDENTITY PRIMARY KEY,user_id INT NOT NULL REFERENCES Users(id),
            device_uuid NVARCHAR(100) NOT NULL,label NVARCHAR(160) NULL,
            public_key_jwk NVARCHAR(MAX) NOT NULL,key_algorithm NVARCHAR(40) NOT NULL DEFAULT 'RSA-OAEP-256',
            is_active BIT NOT NULL DEFAULT 1,created_at DATETIME NOT NULL DEFAULT GETDATE(),
            last_seen DATETIME NULL,revoked_at DATETIME NULL,
            CONSTRAINT UQ_ChatDevices_user_uuid UNIQUE(user_id,device_uuid))""",
        """IF OBJECT_ID('ChatConversations','U') IS NULL CREATE TABLE ChatConversations(
            id INT IDENTITY PRIMARY KEY,kind NVARCHAR(20) NOT NULL,
            title NVARCHAR(200) NULL,team_id INT NULL REFERENCES Teams(id),
            created_by INT NOT NULL REFERENCES Users(id),key_version INT NOT NULL DEFAULT 1,
            needs_key_rotation BIT NOT NULL DEFAULT 0,is_active BIT NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT GETDATE(),updated_at DATETIME NULL,
            CONSTRAINT CK_ChatConversations_kind CHECK(kind IN ('direct','team','group','announcement')))""",
        "IF COL_LENGTH('ChatConversations','rotation_owner_device_id') IS NULL ALTER TABLE ChatConversations ADD rotation_owner_device_id INT NULL",
        "IF COL_LENGTH('ChatConversations','rotation_claim_hash') IS NULL ALTER TABLE ChatConversations ADD rotation_claim_hash CHAR(64) NULL",
        "IF COL_LENGTH('ChatConversations','rotation_claimed_at') IS NULL ALTER TABLE ChatConversations ADD rotation_claimed_at DATETIME NULL",
        "IF COL_LENGTH('ChatDevices','approval_code_hash') IS NULL ALTER TABLE ChatDevices ADD approval_code_hash CHAR(64) NULL",
        "IF COL_LENGTH('ChatDevices','approval_expires_at') IS NULL ALTER TABLE ChatDevices ADD approval_expires_at DATETIME NULL",
        "IF COL_LENGTH('ChatDevices','approval_challenge_hash') IS NULL ALTER TABLE ChatDevices ADD approval_challenge_hash CHAR(64) NULL",
        "IF COL_LENGTH('ChatDevices','approval_challenge_expires_at') IS NULL ALTER TABLE ChatDevices ADD approval_challenge_expires_at DATETIME NULL",
        "IF COL_LENGTH('ChatDevices','approved_at') IS NULL ALTER TABLE ChatDevices ADD approved_at DATETIME NULL",
        """IF OBJECT_ID('ChatMembers','U') IS NULL CREATE TABLE ChatMembers(
            conversation_id INT NOT NULL REFERENCES ChatConversations(id),
            user_id INT NOT NULL REFERENCES Users(id),member_role NVARCHAR(15) NOT NULL DEFAULT 'member',
            can_post BIT NOT NULL DEFAULT 1,is_active BIT NOT NULL DEFAULT 1,
            joined_at DATETIME NOT NULL DEFAULT GETDATE(),left_at DATETIME NULL,
            CONSTRAINT PK_ChatMembers PRIMARY KEY(conversation_id,user_id))""",
        """IF OBJECT_ID('ChatConversationKeys','U') IS NULL CREATE TABLE ChatConversationKeys(
            conversation_id INT NOT NULL REFERENCES ChatConversations(id),
            key_version INT NOT NULL,device_id INT NOT NULL REFERENCES ChatDevices(id),
            wrapped_key NVARCHAR(MAX) NOT NULL,wrap_algorithm NVARCHAR(40) NOT NULL DEFAULT 'RSA-OAEP-256',
            created_at DATETIME NOT NULL DEFAULT GETDATE(),
            CONSTRAINT PK_ChatConversationKeys PRIMARY KEY(conversation_id,key_version,device_id))""",
        """IF OBJECT_ID('ChatMessages','U') IS NULL CREATE TABLE ChatMessages(
            id BIGINT IDENTITY PRIMARY KEY,conversation_id INT NOT NULL REFERENCES ChatConversations(id),
            sender_user_id INT NOT NULL REFERENCES Users(id),sender_device_id INT NOT NULL REFERENCES ChatDevices(id),
            key_version INT NOT NULL,message_kind NVARCHAR(12) NOT NULL DEFAULT 'text',
            ciphertext NVARCHAR(MAX) NOT NULL,iv NVARCHAR(100) NOT NULL,aad NVARCHAR(500) NULL,
            client_message_id NVARCHAR(80) NOT NULL,encrypted_file_id BIGINT NULL,
            is_deleted BIT NOT NULL DEFAULT 0,created_at DATETIME NOT NULL DEFAULT GETDATE(),
            CONSTRAINT UQ_ChatMessages_client UNIQUE(sender_user_id,client_message_id))""",
        "IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_ChatMessages_conversation' AND object_id=OBJECT_ID('ChatMessages')) CREATE INDEX IX_ChatMessages_conversation ON ChatMessages(conversation_id,id)",
        """IF OBJECT_ID('ChatEncryptedFiles','U') IS NULL CREATE TABLE ChatEncryptedFiles(
            id BIGINT IDENTITY PRIMARY KEY,conversation_id INT NOT NULL REFERENCES ChatConversations(id),
            uploaded_by INT NOT NULL REFERENCES Users(id),storage_name NVARCHAR(260) NOT NULL,
            ciphertext_sha256 CHAR(64) NOT NULL,size_bytes BIGINT NOT NULL,
            encrypted_meta NVARCHAR(MAX) NULL,key_version INT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT GETDATE(),is_active BIT NOT NULL DEFAULT 1)""",
        """IF OBJECT_ID('ChatReadReceipts','U') IS NULL CREATE TABLE ChatReadReceipts(
            conversation_id INT NOT NULL REFERENCES ChatConversations(id),
            user_id INT NOT NULL REFERENCES Users(id),last_message_id BIGINT NULL,
            read_at DATETIME NULL,
            CONSTRAINT PK_ChatReadReceipts PRIMARY KEY(conversation_id,user_id))""",
        """IF OBJECT_ID('ApplicationSecrets','U') IS NULL CREATE TABLE ApplicationSecrets(
            secret_name NVARCHAR(100) NOT NULL PRIMARY KEY,
            secret_value VARBINARY(MAX) NOT NULL,
            created_at DATETIME NOT NULL DEFAULT GETDATE(),
            updated_at DATETIME NOT NULL DEFAULT GETDATE())""",
        """IF OBJECT_ID('V8MigrationState','U') IS NULL CREATE TABLE V8MigrationState(
            migration_key NVARCHAR(80) NOT NULL PRIMARY KEY,completed_at DATETIME NOT NULL DEFAULT GETDATE(),
            detail NVARCHAR(1000) NULL)""",
        # R12: the company figure is now derived from the team goals, so
        # FinancialPlans.annual_target became a computed roll-up. The number an
        # administrator types by hand moves here, where it is only ever
        # compared against the roll-up and never constrains a team.
        "IF COL_LENGTH('FinancialPlans','approved_target') IS NULL ALTER TABLE FinancialPlans ADD approved_target DECIMAL(18,0) NULL",
        # R12: archiving a contract now archives its extensions and statements
        # too, because otherwise those children stayed is_active=1 and kept
        # counting in every financial total. The flag records which rows were
        # archived by that cascade, so restoring the contract restores exactly
        # those and leaves anything archived on its own merits alone.
        "IF COL_LENGTH('ContractStatements','archived_with_contract') IS NULL ALTER TABLE ContractStatements ADD archived_with_contract BIT NOT NULL CONSTRAINT DF_Statements_archived_with_contract DEFAULT 0 WITH VALUES",
        "IF COL_LENGTH('ContractExtensions','archived_with_contract') IS NULL ALTER TABLE ContractExtensions ADD archived_with_contract BIT NOT NULL CONSTRAINT DF_Extensions_archived_with_contract DEFAULT 0 WITH VALUES",
        # R16: groups (گروه) inside a team - a lead, members and the projects
        # the group answers for. A person belongs to one active group; the
        # route handlers enforce that, since it spans the lead and member rows.
        """IF OBJECT_ID('WorkGroups','U') IS NULL CREATE TABLE WorkGroups(
            id INT IDENTITY PRIMARY KEY,team_id INT NOT NULL REFERENCES Teams(id),
            name NVARCHAR(160) NOT NULL,description NVARCHAR(1000) NULL,
            lead_id INT NULL,is_active BIT NOT NULL DEFAULT 1,
            created_by INT NULL,created_at DATETIME NOT NULL DEFAULT GETDATE(),
            updated_by INT NULL,updated_at DATETIME NULL)""",
        "IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_WorkGroups_team' AND object_id=OBJECT_ID('WorkGroups')) CREATE INDEX IX_WorkGroups_team ON WorkGroups(team_id,is_active)",
        """IF OBJECT_ID('WorkGroupMembers','U') IS NULL CREATE TABLE WorkGroupMembers(
            group_id INT NOT NULL REFERENCES WorkGroups(id) ON DELETE CASCADE,
            user_id INT NOT NULL,added_by INT NULL,
            added_at DATETIME NOT NULL DEFAULT GETDATE(),
            CONSTRAINT PK_WorkGroupMembers PRIMARY KEY(group_id,user_id))""",
        "IF NOT EXISTS(SELECT 1 FROM sys.indexes WHERE name='IX_WorkGroupMembers_user' AND object_id=OBJECT_ID('WorkGroupMembers')) CREATE INDEX IX_WorkGroupMembers_user ON WorkGroupMembers(user_id,group_id)",
        """IF OBJECT_ID('WorkGroupProjects','U') IS NULL CREATE TABLE WorkGroupProjects(
            group_id INT NOT NULL REFERENCES WorkGroups(id) ON DELETE CASCADE,
            project_id INT NOT NULL,added_by INT NULL,
            added_at DATETIME NOT NULL DEFAULT GETDATE(),
            CONSTRAINT PK_WorkGroupProjects PRIMARY KEY(group_id,project_id))""",
    ]
    for sql in sqls:
        cur.execute(sql)

    # R16, once only: each lead's R14/R15 sub-group (LeadMembers) becomes a
    # named group in the lead's primary team, so nothing set up earlier is
    # lost. A member listed under two leads joins only the first group.
    cur.execute("""IF OBJECT_ID('LeadMembers','U') IS NOT NULL
        AND NOT EXISTS(SELECT 1 FROM V8MigrationState
          WHERE migration_key='r16_lead_members_to_groups_v1')
        BEGIN
          INSERT INTO WorkGroups(team_id,name,lead_id)
          SELECT tm.team_id,N'گروه '+ISNULL(NULLIF(u.display_name,N''),u.username),u.id
          FROM Users u
          CROSS APPLY(SELECT TOP 1 x.team_id FROM TeamMembers x
            WHERE x.user_id=u.id AND x.is_active=1
            ORDER BY x.is_primary DESC,x.team_id) tm
          WHERE u.role=N'lead' AND u.is_active=1
            AND EXISTS(SELECT 1 FROM LeadMembers lm WHERE lm.lead_id=u.id)
            AND NOT EXISTS(SELECT 1 FROM WorkGroups wg WHERE wg.lead_id=u.id AND wg.is_active=1);
          INSERT INTO WorkGroupMembers(group_id,user_id)
          SELECT q.group_id,q.member_id FROM(
            SELECT wg.id AS group_id,lm.member_id,
              ROW_NUMBER() OVER(PARTITION BY lm.member_id ORDER BY wg.id) AS rn
            FROM LeadMembers lm JOIN WorkGroups wg ON wg.lead_id=lm.lead_id AND wg.is_active=1
            WHERE lm.member_id<>lm.lead_id
              AND NOT EXISTS(SELECT 1 FROM WorkGroupMembers gm JOIN WorkGroups g2
                ON g2.id=gm.group_id AND g2.is_active=1 WHERE gm.user_id=lm.member_id)
              AND NOT EXISTS(SELECT 1 FROM WorkGroups g3
                WHERE g3.lead_id=lm.member_id AND g3.is_active=1)) q
          WHERE q.rn=1;
          INSERT INTO V8MigrationState(migration_key,detail)
          VALUES('r16_lead_members_to_groups_v1',N'R14 sub-groups became named groups');
        END""")

    # R12, once only: preserve the hand-entered company figure as the approved
    # target before annual_target starts being recomputed from the team goals.
    # Team goals themselves are never touched, so nothing an administrator
    # allocated is lost; a year whose teams have no goals simply rolls up to
    # zero until somebody enters them, with the old number still visible.
    cur.execute("""UPDATE FinancialPlans SET approved_target=annual_target
        WHERE approved_target IS NULL
          AND NOT EXISTS(SELECT 1 FROM V8MigrationState
            WHERE migration_key='r12_company_target_rollup_v1')""")
    cur.execute("""UPDATE p SET annual_target=ISNULL(t.total,0)
        FROM FinancialPlans p
        OUTER APPLY(SELECT SUM(tf.annual_target) AS total
          FROM TeamFinancialTargets tf
          WHERE tf.plan_id=p.id AND tf.is_current=1) t
        WHERE NOT EXISTS(SELECT 1 FROM V8MigrationState
          WHERE migration_key='r12_company_target_rollup_v1')""")
    cur.execute("""UPDATE fp SET target_amount=ISNULL(t.total,0)
        FROM FinancialPlanPeriods fp
        OUTER APPLY(SELECT SUM(tp.target_amount) AS total
          FROM TeamFinancialTargetPeriods tp
          JOIN TeamFinancialTargets tf ON tf.id=tp.target_id
          WHERE tf.plan_id=fp.plan_id AND tf.is_current=1
            AND tp.month_no=fp.month_no) t
        WHERE NOT EXISTS(SELECT 1 FROM V8MigrationState
          WHERE migration_key='r12_company_target_rollup_v1')""")
    cur.execute("""IF NOT EXISTS(SELECT 1 FROM V8MigrationState
          WHERE migration_key='r12_company_target_rollup_v1')
        INSERT INTO V8MigrationState(migration_key,detail)
        VALUES('r12_company_target_rollup_v1',
          N'company annual target derived from team goals; previous value kept as approved_target')""")

    # R12, once only: contracts archived before this release left their
    # statements and extensions active, so archived work kept appearing in
    # financial totals. Bring those children into line and mark them as
    # cascade-archived so a later restore puts them back.
    cur.execute("""UPDATE s SET is_active=0,archived_with_contract=1
        FROM ContractStatements s JOIN Contracts co ON co.id=s.contract_id
        WHERE co.is_active=0 AND s.is_active=1
          AND NOT EXISTS(SELECT 1 FROM V8MigrationState
            WHERE migration_key='r12_archive_cascade_v1')""")
    cur.execute("""UPDATE e SET is_active=0,archived_with_contract=1
        FROM ContractExtensions e JOIN Contracts co ON co.id=e.contract_id
        WHERE co.is_active=0 AND e.is_active=1
          AND NOT EXISTS(SELECT 1 FROM V8MigrationState
            WHERE migration_key='r12_archive_cascade_v1')""")
    cur.execute("""IF NOT EXISTS(SELECT 1 FROM V8MigrationState
          WHERE migration_key='r12_archive_cascade_v1')
        INSERT INTO V8MigrationState(migration_key,detail)
        VALUES('r12_archive_cascade_v1',
          N'statements and extensions of already-archived contracts were archived with them')""")

    if CHAT_MODE == 'server':
        # The zero-configuration LAN chat uses one server-managed encryption
        # key, so browser device rotations are not part of this mode.
        cur.execute("""UPDATE ChatConversations SET needs_key_rotation=0,
            rotation_owner_device_id=NULL,rotation_claim_hash=NULL,
            rotation_claimed_at=NULL WHERE is_active=1""")

    # Normalize the automatic team conversation title introduced in 8.0.1.
    # This is presentation-only and never touches encrypted messages or keys.
    cur.execute("""UPDATE ChatConversations SET title=N'گروه تیم',updated_at=GETDATE()
        WHERE kind='team' AND is_active=1
          AND (title IS NULL OR LTRIM(RTRIM(title)) IN
            (N'',N'گفتگوی تیم فعلی',N'گفتگوی تیم',N'پیام‌های تیم'))""")

    # Existing records intentionally stay together in a clearly named default
    # team.  This is not a guess about a future organizational structure: it
    # preserves the exact pre-v8 visibility until an administrator reassigns
    # workstreams.
    # The seed team is created once, during the original migration only. It used
    # to be recreated on every startup whenever no row carried the
    # 'legacy-default' code, so renaming or recoding it made a fresh copy
    # reappear after the next restart and it could never be retired.
    cur.execute("""IF NOT EXISTS(SELECT 1 FROM Teams WHERE code='legacy-default')
        AND NOT EXISTS(SELECT 1 FROM V8MigrationState WHERE migration_key='default_team_v1')
        INSERT INTO Teams(code,name,description,is_active)
        VALUES('legacy-default',N'تیم فعلی',N'داده‌های منتقل‌شده از نسخه‌های قبل',1)""")
    cur.execute("SELECT TOP 1 id FROM Teams WHERE code='legacy-default'")
    seed_row = cur.fetchone()
    default_team_id = seed_row[0] if seed_row else None

    # Once the seed team has been renamed, recoded or archived, there is
    # nothing left to back-fill into and the whole block is skipped. Each
    # statement below is additionally guarded by the default_team_v1 marker,
    # so this only ever runs on a database that has never been migrated.
    if default_team_id is not None:
      cur.execute("""INSERT INTO TeamMembers(team_id,user_id,team_role,is_primary,is_active)
        SELECT ?,u.id,
          CASE WHEN u.role='manager' THEN 'manager' WHEN u.role='planner' THEN 'planner' ELSE 'member' END,
          1,1
        FROM Users u
        WHERE u.is_active=1 AND (u.role=N'admin' OR EXISTS(SELECT 1 FROM RolePermissions rp WHERE rp.role=u.role AND rp.permission_key=N'chat.use' AND rp.is_allowed=1))
          AND NOT EXISTS(SELECT 1 FROM V8MigrationState
            WHERE migration_key='default_team_v1')
          AND NOT EXISTS(SELECT 1 FROM TeamMembers tm WHERE tm.team_id=? AND tm.user_id=u.id)""",
                default_team_id, default_team_id)
      cur.execute("""INSERT INTO TeamProjectTypes(team_id,project_type_id,assignment_role,is_active)
          SELECT ?,pt.id,'primary',1 FROM ProjectTypes pt WHERE pt.id>0 AND pt.is_active=1
            AND NOT EXISTS(SELECT 1 FROM V8MigrationState
              WHERE migration_key='default_team_v1')
            AND NOT EXISTS(SELECT 1 FROM TeamProjectTypes x
                WHERE x.team_id=? AND x.project_type_id=pt.id)""",
                  default_team_id, default_team_id)
      cur.execute("""INSERT INTO ProjectTeams(project_id,team_id,title,is_primary,is_active)
          SELECT p.id,?,N'جریان منتقل‌شده',1,1 FROM Projects p
          WHERE NOT EXISTS(SELECT 1 FROM V8MigrationState
              WHERE migration_key='default_team_v1')
            AND NOT EXISTS(SELECT 1 FROM ProjectTeams x
              WHERE x.project_id=p.id AND x.team_id=? AND x.is_active=1)""",
                  default_team_id, default_team_id)
      cur.execute("""UPDATE t SET project_team_id=pt.id
          FROM Tasks t JOIN ProjectTeams pt ON pt.project_id=t.project_id
            AND pt.team_id=? AND pt.is_active=1
          WHERE t.project_team_id IS NULL
            AND NOT EXISTS(SELECT 1 FROM V8MigrationState
              WHERE migration_key='default_team_v1')""", default_team_id)
      cur.execute("""INSERT INTO ContractProjectTeams(contract_id,project_team_id,is_active)
          SELECT co.id,pt.id,1 FROM Contracts co
          JOIN ProjectTeams pt ON pt.project_id=co.project_id
            AND pt.team_id=? AND pt.is_active=1
          WHERE co.project_id IS NOT NULL
            AND NOT EXISTS(SELECT 1 FROM V8MigrationState
              WHERE migration_key='default_team_v1')
            AND NOT EXISTS(SELECT 1 FROM ContractProjectTeams x
                WHERE x.contract_id=co.id AND x.project_team_id=pt.id)""",
                  default_team_id)
      cur.execute("""UPDATE s SET project_team_id=pt.id
          FROM ContractStatements s JOIN Contracts co ON co.id=s.contract_id
          JOIN ProjectTeams pt ON pt.project_id=co.project_id
            AND pt.team_id=? AND pt.is_active=1
          WHERE s.project_team_id IS NULL
            AND NOT EXISTS(SELECT 1 FROM V8MigrationState
              WHERE migration_key='default_team_v1')""", default_team_id)
      cur.execute("""INSERT INTO ContractStatementTeams(statement_id,
              project_team_id,allocation_percent,is_active)
          SELECT s.id,s.project_team_id,100,1
          FROM ContractStatements s
          WHERE s.project_team_id IS NOT NULL
            AND NOT EXISTS(SELECT 1 FROM ContractStatementTeams x
              WHERE x.statement_id=s.id AND x.project_team_id=s.project_team_id)""")
      cur.execute("""UPDATE ps SET project_team_id=pt.id
          FROM PlannedStatements ps JOIN Contracts co ON co.id=ps.contract_id
          JOIN ProjectTeams pt ON pt.project_id=co.project_id
            AND pt.team_id=? AND pt.is_active=1
          WHERE ps.project_team_id IS NULL
            AND NOT EXISTS(SELECT 1 FROM V8MigrationState
              WHERE migration_key='default_team_v1')""", default_team_id)
      cur.execute("""IF NOT EXISTS(SELECT 1 FROM V8MigrationState WHERE migration_key='default_team_v1')
          INSERT INTO V8MigrationState(migration_key,detail)
          VALUES('default_team_v1',N'Existing users, projects, tasks, contracts, statements and plans preserved in تیم فعلی')""")
    cur.execute("""SELECT TOP 1 id FROM Users WHERE is_active=1
        AND (role=N'admin' OR EXISTS(SELECT 1 FROM RolePermissions rp WHERE rp.role=Users.role AND rp.permission_key=N'chat.use' AND rp.is_allowed=1))
        ORDER BY CASE WHEN role='admin' THEN 0 ELSE 1 END,id""")
    owner_row = cur.fetchone()
    if owner_row:
        owner_id = owner_row[0]
        cur.execute("""IF NOT EXISTS(SELECT 1 FROM ChatConversations
              WHERE kind='team' AND team_id=? AND is_active=1)
            INSERT INTO ChatConversations(kind,title,team_id,created_by,needs_key_rotation)
              VALUES('team',N'گروه تیم',?,?,1)""",
                    default_team_id, default_team_id, owner_id)
        cur.execute("""IF NOT EXISTS(SELECT 1 FROM ChatConversations
              WHERE kind='announcement' AND team_id IS NULL AND is_active=1)
            INSERT INTO ChatConversations(kind,title,created_by,needs_key_rotation)
              VALUES('announcement',N'اطلاعیه‌های سازمان',?,1)""", owner_id)
        cur.execute("""INSERT INTO ChatMembers(conversation_id,user_id,member_role,can_post)
            SELECT c.id,u.id,
              CASE WHEN u.id=c.created_by THEN 'owner' ELSE 'member' END,
              CASE WHEN c.kind='announcement' AND u.role<>'admin' THEN 0 ELSE 1 END
            FROM ChatConversations c CROSS JOIN Users u
            WHERE c.is_active=1
              AND u.is_active=1
              AND u.role NOT IN (N'employer',N'supervisor')
              AND (u.role=N'admin' OR EXISTS(SELECT 1 FROM RolePermissions rp WHERE rp.role=u.role AND rp.permission_key=N'chat.use' AND rp.is_allowed=1))
              AND ((c.kind='announcement' AND c.team_id IS NULL)
                OR (c.kind='team' AND EXISTS(SELECT 1 FROM TeamMembers tm
                  WHERE tm.team_id=c.team_id AND tm.user_id=u.id AND tm.is_active=1)))
              AND NOT EXISTS(SELECT 1 FROM ChatMembers m
                WHERE m.conversation_id=c.id AND m.user_id=u.id)""")
    # R14: clients (employers and supervisors) are not members of the staff
    # team channels or the company announcements. Earlier releases added them
    # along with every team member; this takes them out again on each start.
    cur.execute("""UPDATE m SET is_active=0,left_at=GETDATE()
        FROM ChatMembers m
        JOIN ChatConversations c ON c.id=m.conversation_id
        JOIN Users u ON u.id=m.user_id
        WHERE m.is_active=1 AND c.kind IN ('team','announcement')
          AND u.role IN (N'employer',N'supervisor')""")
    conn.commit()


def _int(value, default=None):
    if value in (None, ""):
        return default
    try:
        return int(str(value).translate(str.maketrans(
            "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"
        )))
    except Exception:
        return default


def _dec(value, default=None):
    if value in (None, ""):
        return default
    try:
        return _decimal.Decimal(str(value).replace(",", ""))
    except Exception:
        return default


def _date(value):
    if value in (None, ""):
        return None
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    try:
        return _dt.date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (_dt.date, _dt.datetime)):
        return value.isoformat()
    if isinstance(value, _decimal.Decimal):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(x) for x in value]
    return str(value)


def register_v8_routes(app, get_conn, db_lock, require_auth, require_roles,
                       rows_to_list, audit, base_dir):
    """Register v8 API routes without duplicating any v7 URL."""

    chat_dir = os.path.join(base_dir, "taskhub_data", "chat_cipher")
    os.makedirs(chat_dir, exist_ok=True)
    server_chat_mode = CHAT_MODE == "server"

    def durable_server_chat_key():
        """Return one stable key whose source of truth is SQL Server.

        On the first R4 startup an existing R1/R2/R3 key file is imported, so
        already readable LAN-chat messages remain readable. Subsequent login,
        browser, service and machine restarts always load the same DB key.
        """
        key_path = os.path.join(base_dir, "taskhub_data", "server_chat_fernet.key")
        legacy_key = None
        try:
            with open(key_path, "rb") as handle:
                legacy_key = ServerChatCrypto.validate_key(handle.read())
        except FileNotFoundError:
            pass
        except Exception as exc:
            raise RuntimeError("کلید قبلی پیامرسان معتبر نیست: %s" % key_path) from exc

        with db_lock:
            conn = get_conn(); cur = conn.cursor()
            try:
                # Keep the key provider independently safe. Route registration
                # happens before /api/connect on a fresh installation, so the
                # table must not be assumed to exist yet.
                cur.execute("""IF OBJECT_ID('ApplicationSecrets','U') IS NULL CREATE TABLE ApplicationSecrets(
                    secret_name NVARCHAR(120) NOT NULL PRIMARY KEY,
                    secret_value VARBINARY(MAX) NOT NULL,
                    created_at DATETIME NOT NULL DEFAULT GETDATE(),
                    updated_at DATETIME NOT NULL DEFAULT GETDATE())""")
                cur.execute("""SELECT secret_value FROM ApplicationSecrets WITH (UPDLOCK,HOLDLOCK)
                    WHERE secret_name=N'server_chat_fernet_v1'""")
                row = cur.fetchone()
                if row:
                    key = ServerChatCrypto.validate_key(bytes(row[0]))
                else:
                    key = legacy_key or Fernet.generate_key()
                    cur.execute("""INSERT INTO ApplicationSecrets(secret_name,secret_value)
                        VALUES(N'server_chat_fernet_v1',?)""", key)
                conn.commit()
                return key
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise

    # Initialize the crypto object on the first actual chat request, not at
    # module import. This lets the web app start even when SQL Server is still
    # warming up and avoids generating/replacing a key during route setup.
    _server_chat_holder = {"value": None}
    _server_chat_lock = threading.RLock()

    def _server_chat_instance():
        if not server_chat_mode:
            return None
        with _server_chat_lock:
            if _server_chat_holder["value"] is None:
                _server_chat_holder["value"] = ServerChatCrypto(
                    base_dir, key_provider=durable_server_chat_key)
            return _server_chat_holder["value"]

    class _LazyServerChat:
        def __getattr__(self, name):
            instance = _server_chat_instance()
            if instance is None:
                raise RuntimeError("پیامرسان مدیریت‌شده سرور فعال نیست")
            return getattr(instance, name)

    server_chat = _LazyServerChat() if server_chat_mode else None

    def ok(**kwargs):
        payload = {"ok": True}
        payload.update(kwargs)
        return jsonify(_jsonable(payload))

    def err(message, status=200, **kwargs):
        payload = {"ok": False, "error": message}
        payload.update(kwargs)
        return jsonify(_jsonable(payload)), status

    def one(cur, sql, *params):
        cur.execute(sql, *params)
        row = cur.fetchone()
        if not row:
            return None
        cols = [x[0] for x in cur.description]
        return {cols[i]: _jsonable(row[i]) for i in range(len(cols))}

    def team_ids(cur, user):
        # Permissions decide operations; role decides whether the data scope is
        # company-wide. Manager/planner/support can never escape their teams by
        # receiving a broad legacy permission such as teams.view_all.
        if has_company_scope(user):
            cur.execute("SELECT id FROM Teams WHERE is_active=1")
        else:
            cur.execute("""SELECT tm.team_id FROM TeamMembers tm JOIN Teams t ON t.id=tm.team_id
                WHERE tm.user_id=? AND tm.is_active=1 AND t.is_active=1""", user["id"])
        return [int(x[0]) for x in cur.fetchall()]

    def selected_team(cur, user, data=None):
        data = data or request.get_json(silent=True) or {}
        raw = data.get("_team_scope", data.get("team_id"))
        if raw in (None, "", "mine", "all"):
            return None
        selected = _int(raw)
        if not selected:
            raise PermissionError("تیم انتخاب‌شده معتبر نیست")
        allowed = team_ids(cur, user)
        if selected not in allowed:
            raise PermissionError("به تیم انتخاب‌شده دسترسی ندارید")
        return selected

    def can_manage_team(cur, user, tid):
        if has_company_scope(user):
            return True
        cur.execute("""SELECT 1 FROM TeamMembers WHERE team_id=? AND user_id=?
            AND is_active=1 AND team_role IN ('manager','planner')""", tid, user["id"])
        return cur.fetchone() is not None

    def can_plan_team(cur, user, tid):
        if not user_has_permission(user, "team_financial.manage"):
            return False
        if has_company_scope(user):
            return True
        cur.execute("""SELECT 1 FROM TeamMembers WHERE team_id=? AND user_id=?
            AND is_active=1 AND team_role IN ('manager','planner')""", tid, user["id"])
        return cur.fetchone() is not None

    def ensure_internal_chat_user(user):
        if not user_has_permission(user, "chat.use"):
            raise PermissionError("دسترسی پیامرسان برای این نقش فعال نیست")

    def client_projects(cur, user_id):
        """The projects a client account (employer or supervisor) belongs to:
        its own project when one is set, otherwise the projects of its teams."""
        row = one(cur, "SELECT project_id FROM Users WHERE id=?", user_id)
        if row and row.get("project_id"):
            return {int(row["project_id"])}
        cur.execute("""SELECT DISTINCT pt.project_id FROM TeamMembers tm
            JOIN ProjectTeams pt ON pt.team_id=tm.team_id AND pt.is_active=1
            WHERE tm.user_id=? AND tm.is_active=1""", user_id)
        return {int(x[0]) for x in cur.fetchall() if x[0] is not None}

    def client_contact_ids(cur, user_id):
        """Everyone a client account may talk to (R14): the other client
        accounts of the same project and the planners of the teams running it."""
        projects = sorted(client_projects(cur, user_id))
        if not projects:
            return set()
        marks = ",".join("?" for _ in projects)
        cur.execute("""SELECT u.id FROM Users u
            WHERE u.is_active=1 AND u.role IN (N'employer',N'supervisor')
              AND (u.project_id IN (%s) OR (u.project_id IS NULL AND EXISTS(
                SELECT 1 FROM TeamMembers tm JOIN ProjectTeams pt
                  ON pt.team_id=tm.team_id AND pt.is_active=1
                WHERE tm.user_id=u.id AND tm.is_active=1 AND pt.project_id IN (%s))))""" % (marks, marks),
                    projects + projects)
        ids = {int(x[0]) for x in cur.fetchall()}
        cur.execute("""SELECT DISTINCT tm.user_id FROM ProjectTeams pt
            JOIN TeamMembers tm ON tm.team_id=pt.team_id AND tm.is_active=1
            JOIN Users u ON u.id=tm.user_id AND u.is_active=1
            WHERE pt.is_active=1 AND pt.project_id IN (%s)
              AND (tm.team_role='planner' OR u.role='planner')""" % marks, projects)
        ids |= {int(x[0]) for x in cur.fetchall()}
        ids.discard(int(user_id))
        return ids

    def chat_members_error(cur, member_ids):
        """None when these people may share a conversation, else the reason."""
        ids = sorted({int(x) for x in member_ids})
        if len(ids) < 2:
            return None
        cur.execute("SELECT id,role FROM Users WHERE id IN (%s)" % ",".join("?" for _ in ids), ids)
        roles = {int(r[0]): r[1] for r in cur.fetchall()}
        if not any(role in CHAT_CLIENT_ROLES for role in roles.values()):
            return None
        known = {}

        def contacts_of(uid):
            if uid not in known:
                known[uid] = client_contact_ids(cur, uid)
            return known[uid]
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if not chat_pair_allowed(a, roles.get(a), b, roles.get(b), contacts_of):
                    return CHAT_CLIENT_RULE
        return None

    def ensure_server_chat_device(conn, cur, user_id):
        """Return one durable synthetic sender device for LAN chat.

        MERGE with HOLDLOCK prevents two simultaneous first requests from
        inserting duplicate synthetic devices. Committing here is intentional:
        read-only chat endpoints also call this helper and their next request
        may be handled by another Waitress thread/connection.
        """
        public_stub = json.dumps({"kty": "server", "mode": "managed-v1"},
                                 separators=(",", ":"))
        cur.execute("""MERGE ChatDevices WITH (HOLDLOCK) AS target
            USING (SELECT CAST(? AS INT) AS user_id) AS source
              ON target.user_id=source.user_id
             AND target.device_uuid=N'server-managed-v1'
            WHEN MATCHED THEN UPDATE SET is_active=1,revoked_at=NULL,
              label=N'حالت شبکه داخلی',last_seen=GETDATE(),
              approved_at=ISNULL(target.approved_at,GETDATE())
            WHEN NOT MATCHED THEN INSERT(user_id,device_uuid,label,
              public_key_jwk,key_algorithm,is_active,last_seen,approved_at)
              VALUES(source.user_id,N'server-managed-v1',N'حالت شبکه داخلی',
                ?,N'SERVER-FERNET',1,GETDATE(),GETDATE());""",
                    user_id, public_stub)
        row = one(cur, """SELECT id FROM ChatDevices
            WHERE user_id=? AND device_uuid=N'server-managed-v1'""", user_id)
        if not row:
            raise RuntimeError("ساخت دستگاه داخلی پیامرسان انجام نشد")
        conn.commit()
        return int(row["id"])

    def ensure_conversation_member(cur, conversation_id, user_id):
        row = one(cur, """SELECT c.id,c.kind,c.title,c.team_id,c.key_version,
            c.needs_key_rotation,m.member_role,m.can_post
            FROM ChatConversations c JOIN ChatMembers m ON m.conversation_id=c.id
            WHERE c.id=? AND c.is_active=1 AND m.user_id=? AND m.is_active=1""",
                  conversation_id, user_id)
        if not row:
            raise PermissionError("به این گفتگو دسترسی ندارید")
        return row

    @app.route("/api/v8/context", methods=["POST"])
    @require_auth
    def api_v8_context():
        try:
            with db_lock:
                c = get_conn(); cur = c.cursor()
                allowed = team_ids(cur, g.user)
                if allowed:
                    marks = ",".join("?" for _ in allowed)
                    cur.execute("""SELECT t.id,t.code,t.name,t.description,t.is_active,
                        tm.team_role,tm.is_primary,
                        (SELECT COUNT(*) FROM TeamMembers x WHERE x.team_id=t.id AND x.is_active=1) AS member_count,
                        (SELECT COUNT(*) FROM ProjectTeams x WHERE x.team_id=t.id AND x.is_active=1) AS project_count
                        FROM Teams t LEFT JOIN TeamMembers tm ON tm.team_id=t.id AND tm.user_id=?
                        WHERE t.is_active=1 AND t.id IN (%s) ORDER BY tm.is_primary DESC,t.name""" % marks,
                                *([g.user["id"]] + allowed))
                    teams = rows_to_list(cur)
                else:
                    teams = []
                cur.execute("""SELECT ptm.id AS project_team_id,ptm.project_id,ptm.team_id,
                    ptm.title,ptm.is_primary,t.name AS team_name,p.name AS project_name,
                    p.project_type_id,ptype.name AS project_type_name,c.name AS city_name
                    FROM ProjectTeams ptm JOIN Teams t ON t.id=ptm.team_id
                    JOIN Projects p ON p.id=ptm.project_id JOIN Cities c ON c.id=p.city_id
                    JOIN ProjectTypes ptype ON ptype.id=p.project_type_id
                    WHERE ptm.is_active=1 AND t.is_active=1
                    AND (?=1 OR ptm.team_id IN (
                        SELECT team_id FROM TeamMembers WHERE user_id=? AND is_active=1))
                    ORDER BY c.name,p.name,t.name""",
                            1 if has_company_scope(g.user) else 0,
                            g.user["id"])
                workstreams = rows_to_list(cur)
                cur.execute("""SELECT tm.team_id,tm.user_id,tm.team_role,u.display_name,
                    u.username,u.role AS global_role FROM TeamMembers tm
                    JOIN Users u ON u.id=tm.user_id
                    WHERE tm.is_active=1 AND u.is_active=1
                      AND (?=1 OR tm.team_id IN (
                        SELECT team_id FROM TeamMembers WHERE user_id=? AND is_active=1))
                    ORDER BY tm.team_id,u.display_name""",
                            1 if has_company_scope(g.user) else 0,
                            g.user["id"])
                members = rows_to_list(cur)
                can_manage_members = user_has_permission(g.user, "teams.members_manage")
                candidates = []
                if can_manage_members:
                    cur.execute("""SELECT DISTINCT u.id,u.username,u.display_name,u.role AS global_role
                        FROM Users u
                        WHERE u.is_active=1
                          AND (?=1 OR u.id=? OR EXISTS(
                            SELECT 1 FROM TeamMembers target JOIN TeamMembers mine
                              ON mine.team_id=target.team_id AND mine.is_active=1
                            WHERE target.user_id=u.id AND target.is_active=1
                              AND mine.user_id=?))
                        ORDER BY u.display_name,u.username""",
                                1 if has_company_scope(g.user) else 0,
                                g.user["id"], g.user["id"])
                    candidates = rows_to_list(cur)
                # R16: the groups in the user's teams, for the group filters.
                groups = []
                if user_has_permission(g.user, "groups.view"):
                    groups = [{"id": x["id"], "team_id": x["team_id"], "name": x["name"],
                               "team_name": x["team_name"], "lead_id": x["lead_id"],
                               "member_ids": x["member_ids"], "project_ids": x["project_ids"]}
                              for x in load_groups(cur, g.user)]
            return ok(
                version="1.0.0", teams=teams, project_teams=workstreams,
                team_members=members, groups=groups,
                user_candidates=candidates,
                can_all_teams=has_company_scope(g.user),
                can_manage_all=(has_company_scope(g.user) and user_has_permission(g.user, "teams.members_manage")),
            )
        except Exception as exc:
            return err(str(exc), teams=[], project_teams=[])

    @app.route("/api/v8/teams", methods=["POST"])
    @require_auth
    def api_v8_teams():
        try:
            if not user_has_permission(g.user, "teams.view"):
                return err("اجازه مشاهده تیم‌ها را ندارید", 403)
            data = request.get_json() or {}
            with db_lock:
                c = get_conn(); cur = c.cursor()
                allowed = team_ids(cur, g.user)
                selected = selected_team(cur, g.user, data)
                if selected:
                    allowed = [selected]
                if not allowed:
                    return ok(rows=[])
                marks = ",".join("?" for _ in allowed)
                cur.execute("""SELECT t.*,
                    (SELECT COUNT(*) FROM TeamMembers m WHERE m.team_id=t.id AND m.is_active=1) AS member_count,
                    (SELECT COUNT(*) FROM TeamProjectTypes x WHERE x.team_id=t.id AND x.is_active=1) AS type_count,
                    (SELECT COUNT(*) FROM ProjectTeams x WHERE x.team_id=t.id AND x.is_active=1) AS project_count
                    FROM Teams t WHERE t.is_active=1 AND t.id IN (%s) ORDER BY t.name""" % marks,
                            allowed)
                teams = rows_to_list(cur)
                cur.execute("""SELECT tm.team_id,tm.user_id,tm.team_role,tm.is_primary,
                    u.username,u.display_name,u.role AS global_role,u.is_active
                    FROM TeamMembers tm JOIN Users u ON u.id=tm.user_id
                    WHERE tm.is_active=1 AND tm.team_id IN (%s)
                    ORDER BY tm.team_id,
                      CASE tm.team_role WHEN 'manager' THEN 0 WHEN 'planner' THEN 1 ELSE 2 END,
                      u.display_name""" % marks, allowed)
                members = rows_to_list(cur)
                cur.execute("""SELECT x.team_id,x.project_type_id,x.assignment_role,
                    pt.name AS project_type_name
                    FROM TeamProjectTypes x JOIN ProjectTypes pt ON pt.id=x.project_type_id
                    WHERE x.is_active=1 AND x.team_id IN (%s)
                    ORDER BY x.team_id,pt.name""" % marks, allowed)
                types = rows_to_list(cur)
                cur.execute("""SELECT x.id,x.team_id,x.project_id,x.title,x.is_primary,
                    p.name AS project_name,c.name AS city_name,pt.name AS project_type_name
                    FROM ProjectTeams x JOIN Projects p ON p.id=x.project_id
                    JOIN Cities c ON c.id=p.city_id JOIN ProjectTypes pt ON pt.id=p.project_type_id
                    WHERE x.is_active=1 AND x.team_id IN (%s)
                    ORDER BY x.team_id,c.name,p.name""" % marks, allowed)
                projects = rows_to_list(cur)
            by_id = {int(x["id"]): x for x in teams}
            for row in teams:
                row["members"] = []
                row["project_types"] = []
                row["projects"] = []
            for row in members:
                if int(row["team_id"]) in by_id:
                    by_id[int(row["team_id"])]["members"].append(row)
            for row in types:
                if int(row["team_id"]) in by_id:
                    by_id[int(row["team_id"])]["project_types"].append(row)
            for row in projects:
                if int(row["team_id"]) in by_id:
                    by_id[int(row["team_id"])]["projects"].append(row)
            return ok(rows=teams)
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc), rows=[])

    @app.route("/api/v8/team_save", methods=["POST"])
    @require_auth
    def api_v8_team_save():
        try:
            data = request.get_json() or {}
            tid = _int(data.get("id"))
            name = (data.get("name") or "").strip()
            if not name:
                return err("نام تیم الزامی است")
            with db_lock:
                c = get_conn(); cur = c.cursor()
                if tid and not can_manage_team(cur, g.user, tid):
                    return err("فقط مدیر همان تیم یا مدیر سیستم اجازه ویرایش دارد", 403)
                if not tid and not user_has_permission(g.user, "teams.create"):
                    return err("دسترسی ساخت تیم جدید را ندارید", 403)
                if tid:
                    cur.execute("""UPDATE Teams SET name=?,code=?,description=?,
                        updated_by=?,updated_at=GETDATE() WHERE id=?""",
                                name, (data.get("code") or "").strip() or None,
                                (data.get("description") or "").strip() or None,
                                g.user["id"], tid)
                else:
                    cur.execute("""INSERT INTO Teams(code,name,description,created_by)
                        OUTPUT INSERTED.id VALUES(?,?,?,?)""",
                                (data.get("code") or "").strip() or None, name,
                                (data.get("description") or "").strip() or None,
                                g.user["id"])
                    tid = cur.fetchone()[0]
                    creator_team_role = ('manager' if g.user.get('role') in ('admin','manager')
                                         else 'planner' if g.user.get('role') == 'planner'
                                         else 'member')
                    cur.execute("""INSERT INTO TeamMembers(team_id,user_id,team_role,is_primary,added_by)
                        VALUES(?,?,?,?,?)""", tid, g.user["id"], creator_team_role, 1, g.user["id"])
                    cur.execute("""INSERT INTO ChatConversations(kind,title,team_id,created_by)
                        OUTPUT INSERTED.id VALUES('team',?,?,?)""",
                                "گفتگوی " + name, tid, g.user["id"])
                    conversation_id = cur.fetchone()[0]
                    cur.execute("""INSERT INTO ChatMembers(conversation_id,user_id,member_role)
                        VALUES(?,?,'owner')""", conversation_id, g.user["id"])
                c.commit()
            audit("v8_team_save", "team #%s" % tid)
            return ok(id=tid)
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/team_archive", methods=["POST"])
    @require_auth
    def api_v8_team_archive():
        try:
            tid = _int((request.get_json() or {}).get("id"))
            with db_lock:
                c = get_conn(); cur = c.cursor()
                # R16: governed by teams.archive now, so the team boundary that
                # the admin-only decorator used to make unnecessary applies here.
                if not can_manage_team(cur, g.user, tid):
                    return err("فقط مدیر یا پلنر همان تیم آن را بایگانی می‌کند", 403)
                row = one(cur, "SELECT code FROM Teams WHERE id=? AND is_active=1", tid)
                if not row:
                    return err("تیم یافت نشد")
                if row.get("code") == "legacy-default":
                    return err("تیم پیش‌فرض تا زمانی که داده منتقل‌شده دارد قابل بایگانی نیست")
                usage = one(cur, """SELECT
                    (SELECT COUNT(*) FROM ProjectTeams pt JOIN Tasks x
                      ON x.project_team_id=pt.id WHERE pt.team_id=?) AS tasks,
                    (SELECT COUNT(*) FROM ProjectTeams pt JOIN ContractProjectTeams x
                      ON x.project_team_id=pt.id AND x.is_active=1
                      WHERE pt.team_id=?) AS contracts,
                    (SELECT COUNT(DISTINCT s.id) FROM ProjectTeams pt
                      JOIN ContractStatementTeams x
                        ON x.project_team_id=pt.id AND x.is_active=1
                      JOIN ContractStatements s
                        ON s.id=x.statement_id AND s.is_active=1
                      WHERE pt.team_id=?) AS statements,
                    (SELECT COUNT(*) FROM ProjectTeams pt
                      JOIN PlannedStatements x
                        ON x.project_team_id=pt.id AND x.is_active=1
                      WHERE pt.team_id=?) AS plans,
                    (SELECT COUNT(*) FROM TeamFinancialTargets x
                      WHERE x.team_id=? AND x.is_current=1) AS targets""",
                            tid, tid, tid, tid, tid) or {}
                if any(int(usage.get(x) or 0) for x in
                       ("tasks", "contracts", "statements", "plans", "targets")):
                    return err("این تیم سابقه عملیاتی یا مالی دارد؛ ابتدا داده‌ها را به تیم دیگری منتقل کنید")
                cur.execute("UPDATE Teams SET is_active=0,updated_by=?,updated_at=GETDATE() WHERE id=?",
                            g.user["id"], tid)
                cur.execute("UPDATE ProjectTeams SET is_active=0,updated_by=?,updated_at=GETDATE() WHERE team_id=?",
                            g.user["id"], tid)
                cur.execute("UPDATE TeamMembers SET is_active=0,left_at=GETDATE() WHERE team_id=?", tid)
                cur.execute("UPDATE WorkGroups SET is_active=0,updated_at=GETDATE() WHERE team_id=?", tid)
                c.commit()
            return ok()
        except Exception as exc:
            return err(str(exc))

    # ── R16 groups (گروه) ─────────────────────────────────────────────
    # A group lives inside one team: a lead (سرگروه), members, and the
    # projects the group answers for. Everyone in a group with projects sees
    # only those projects; a person belongs to one active group at a time.
    def load_groups(cur, user, team_filter=None, only_mine=False):
        allowed = team_ids(cur, user)
        if team_filter:
            allowed = [t for t in allowed if t == int(team_filter)]
        if not allowed:
            return []
        marks = ",".join("?" for _ in allowed)
        params = list(allowed)
        mine_sql = ""
        if only_mine:
            mine_sql = (" AND (wg.lead_id=? OR EXISTS(SELECT 1 FROM WorkGroupMembers mx"
                        " WHERE mx.group_id=wg.id AND mx.user_id=?))")
            params += [user["id"], user["id"]]
        cur.execute("""SELECT wg.id,wg.team_id,t.name AS team_name,wg.name,wg.description,
            wg.lead_id,lu.display_name AS lead_name,lu.username AS lead_username
            FROM WorkGroups wg JOIN Teams t ON t.id=wg.team_id
            LEFT JOIN Users lu ON lu.id=wg.lead_id
            WHERE wg.is_active=1 AND t.is_active=1 AND wg.team_id IN (%s)%s
            ORDER BY t.name,wg.name""" % (marks, mine_sql), params)
        groups = rows_to_list(cur)
        if not groups:
            return []
        ids = [int(x["id"]) for x in groups]
        gmarks = ",".join("?" for _ in ids)
        cur.execute("""SELECT gm.group_id,gm.user_id,u.display_name,u.username,u.role
            FROM WorkGroupMembers gm JOIN Users u ON u.id=gm.user_id
            WHERE u.is_active=1 AND gm.group_id IN (%s)
            ORDER BY u.display_name""" % gmarks, ids)
        members = rows_to_list(cur)
        cur.execute("""SELECT gp.group_id,gp.project_id,p.name AS project_name,c.name AS city_name
            FROM WorkGroupProjects gp JOIN Projects p ON p.id=gp.project_id
            JOIN Cities c ON c.id=p.city_id
            WHERE gp.group_id IN (%s) ORDER BY c.name,p.name""" % gmarks, ids)
        projects = rows_to_list(cur)
        by_id = {int(x["id"]): x for x in groups}
        for x in groups:
            x["members"], x["projects"] = [], []
        for row in members:
            by_id[int(row["group_id"])]["members"].append(row)
        for row in projects:
            by_id[int(row["group_id"])]["projects"].append(row)
        for x in groups:
            x["member_ids"] = [int(m["user_id"]) for m in x["members"]]
            x["project_ids"] = [int(p["project_id"]) for p in x["projects"]]
        return groups

    def group_row(cur, gid):
        return one(cur, "SELECT id,team_id,name,lead_id FROM WorkGroups WHERE id=? AND is_active=1", gid)

    def other_group_of(cur, uid, gid):
        """The name of another active group the person already leads or belongs to."""
        row = one(cur, """SELECT TOP 1 wg.name FROM WorkGroups wg
            WHERE wg.is_active=1 AND wg.id<>? AND (wg.lead_id=? OR EXISTS(
              SELECT 1 FROM WorkGroupMembers gm WHERE gm.group_id=wg.id AND gm.user_id=?))""",
                  gid or 0, uid, uid)
        return row["name"] if row else None

    @app.route("/api/v8/groups", methods=["POST"])
    @require_auth
    def api_v8_groups():
        try:
            data = request.get_json() or {}
            with db_lock:
                c = get_conn(); cur = c.cursor()
                rows = load_groups(cur, g.user, _int(data.get("team_id")))
            return ok(rows=rows)
        except Exception as exc:
            return err(str(exc), rows=[])

    @app.route("/api/v8/group_save", methods=["POST"])
    @require_auth
    def api_v8_group_save():
        try:
            data = request.get_json() or {}
            gid = _int(data.get("id"))
            name = (data.get("name") or "").strip()
            lead_id = _int(data.get("lead_id"))
            description = (data.get("description") or "").strip() or None
            if not name:
                return err("نام گروه الزامی است")
            with db_lock:
                c = get_conn(); cur = c.cursor()
                if gid:
                    current = group_row(cur, gid)
                    if not current:
                        return err("گروه یافت نشد")
                    team_id = int(current["team_id"])
                else:
                    team_id = _int(data.get("team_id"))
                    if not team_id or not one(cur, "SELECT id FROM Teams WHERE id=? AND is_active=1", team_id):
                        return err("تیم گروه را انتخاب کنید")
                if not can_manage_team(cur, g.user, team_id):
                    return err("فقط مدیر یا پلنر همان تیم گروه‌هایش را تعریف می‌کند", 403)
                if lead_id:
                    lead = one(cur, """SELECT u.id,u.role FROM Users u JOIN TeamMembers tm
                        ON tm.user_id=u.id AND tm.team_id=? AND tm.is_active=1
                        WHERE u.id=? AND u.is_active=1""", team_id, lead_id)
                    if not lead or lead["role"] != "lead":
                        return err("سرگروه باید کاربر فعالی با نقش «سرگروه» در همین تیم باشد")
                    taken = other_group_of(cur, lead_id, gid)
                    if taken:
                        return err("این سرگروه در گروه «%s» است؛ هر نفر فقط در یک گروه است" % taken)
                if gid:
                    cur.execute("""UPDATE WorkGroups SET name=?,description=?,lead_id=?,
                        updated_by=?,updated_at=GETDATE() WHERE id=?""",
                                name, description, lead_id, g.user["id"], gid)
                else:
                    cur.execute("""INSERT INTO WorkGroups(team_id,name,description,lead_id,created_by)
                        OUTPUT INSERTED.id VALUES(?,?,?,?,?)""",
                                team_id, name, description, lead_id, g.user["id"])
                    gid = int(cur.fetchone()[0])
                if lead_id:
                    # The lead belongs to the group by leading it, not as a member row.
                    cur.execute("DELETE FROM WorkGroupMembers WHERE group_id=? AND user_id=?", gid, lead_id)
                c.commit()
            audit("v8_group_save", "group #%s" % gid)
            return ok(id=gid)
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/group_members_save", methods=["POST"])
    @require_auth
    def api_v8_group_members_save():
        try:
            data = request.get_json() or {}
            gid = _int(data.get("group_id"))
            wanted = sorted({x for x in (_int(v) for v in (data.get("member_ids") or [])) if x})
            with db_lock:
                c = get_conn(); cur = c.cursor()
                grp = group_row(cur, gid)
                if not grp:
                    return err("گروه یافت نشد")
                if not can_manage_team(cur, g.user, grp["team_id"]):
                    return err("فقط مدیر یا پلنر همان تیم اعضای گروه را تعیین می‌کند", 403)
                lead_id = _int(grp.get("lead_id"))
                wanted = [x for x in wanted if x != lead_id]
                if wanted:
                    marks = ",".join("?" for _ in wanted)
                    cur.execute("""SELECT u.id,u.display_name FROM Users u JOIN TeamMembers tm
                        ON tm.user_id=u.id AND tm.team_id=? AND tm.is_active=1
                        WHERE u.is_active=1 AND u.role IN ('support','lead') AND u.id IN (%s)""" % marks,
                                [grp["team_id"]] + wanted)
                    found = {int(r[0]): r[1] for r in cur.fetchall()}
                    if set(found) != set(wanted):
                        return err("اعضای گروه باید پشتیبان یا سرگروه فعال همین تیم باشند")
                    for uid in wanted:
                        taken = other_group_of(cur, uid, gid)
                        if taken:
                            return err("«%s» در گروه «%s» است؛ هر نفر فقط در یک گروه است" % (found[uid], taken))
                cur.execute("DELETE FROM WorkGroupMembers WHERE group_id=?", gid)
                for uid in wanted:
                    cur.execute("INSERT INTO WorkGroupMembers(group_id,user_id,added_by) VALUES(?,?,?)",
                                gid, uid, g.user["id"])
                c.commit()
            audit("v8_group_members_save", "group #%s: %s members" % (gid, len(wanted)))
            return ok(count=len(wanted))
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/group_projects_save", methods=["POST"])
    @require_auth
    def api_v8_group_projects_save():
        try:
            data = request.get_json() or {}
            gid = _int(data.get("group_id"))
            wanted = sorted({x for x in (_int(v) for v in (data.get("project_ids") or [])) if x})
            with db_lock:
                c = get_conn(); cur = c.cursor()
                grp = group_row(cur, gid)
                if not grp:
                    return err("گروه یافت نشد")
                if not can_manage_team(cur, g.user, grp["team_id"]):
                    return err("فقط مدیر یا پلنر همان تیم پروژه‌های گروه را تعیین می‌کند", 403)
                if wanted:
                    marks = ",".join("?" for _ in wanted)
                    cur.execute("""SELECT DISTINCT project_id FROM ProjectTeams
                        WHERE team_id=? AND is_active=1 AND project_id IN (%s)""" % marks,
                                [grp["team_id"]] + wanted)
                    if {int(r[0]) for r in cur.fetchall()} != set(wanted):
                        return err("پروژه‌های گروه باید از پروژه‌های متصل به همین تیم باشند")
                cur.execute("DELETE FROM WorkGroupProjects WHERE group_id=?", gid)
                for pid in wanted:
                    cur.execute("INSERT INTO WorkGroupProjects(group_id,project_id,added_by) VALUES(?,?,?)",
                                gid, pid, g.user["id"])
                c.commit()
            audit("v8_group_projects_save", "group #%s: %s projects" % (gid, len(wanted)))
            return ok(count=len(wanted))
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/group_archive", methods=["POST"])
    @require_auth
    def api_v8_group_archive():
        try:
            gid = _int((request.get_json() or {}).get("id"))
            with db_lock:
                c = get_conn(); cur = c.cursor()
                grp = group_row(cur, gid)
                if not grp:
                    return err("گروه یافت نشد")
                if not can_manage_team(cur, g.user, grp["team_id"]):
                    return err("فقط مدیر یا پلنر همان تیم گروه را بایگانی می‌کند", 403)
                cur.execute("UPDATE WorkGroups SET is_active=0,updated_by=?,updated_at=GETDATE() WHERE id=?",
                            g.user["id"], gid)
                c.commit()
            audit("v8_group_archive", "group #%s" % gid)
            return ok()
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/team_members_save", methods=["POST"])
    @require_auth
    def api_v8_team_members_save():
        try:
            data = request.get_json() or {}; tid = _int(data.get("team_id"))
            members = data.get("members") or []
            seen = set()
            clean = []
            for item in members:
                uid = _int(item.get("user_id")); role = item.get("team_role") or "member"
                if not uid or uid in seen or role not in TEAM_ROLES:
                    return err("فهرست اعضای تیم معتبر نیست")
                seen.add(uid); clean.append((uid, role, bool(item.get("is_primary"))))
            if not any(x[1] == "manager" for x in clean):
                return err("هر تیم باید حداقل یک مدیر تیم فعال داشته باشد")
            with db_lock:
                c = get_conn(); cur = c.cursor()
                if not can_manage_team(cur, g.user, tid):
                    return err("اجازه مدیریت اعضای این تیم را ندارید", 403)
                marks = ",".join("?" for _ in seen)
                cur.execute("""SELECT id,role FROM Users WHERE id IN (%s)
                    AND is_active=1 AND role IN
                    ('admin','manager','planner','finance','reporter','support','lead','supervisor','employer')""" %
                            marks, list(seen))
                user_roles = {int(x[0]): x[1] for x in cur.fetchall()}
                if set(user_roles) != seen:
                    return err("یکی از اعضای تیم، کاربر داخلی فعال نیست")
                for uid, team_role, _ in clean:
                    global_role = user_roles.get(uid)
                    if team_role == "manager" and global_role not in (
                            "admin", "manager"):
                        return err("نقش «مدیر تیم» فقط برای کاربر مدیر قابل انتخاب است")
                    if team_role == "planner" and global_role not in (
                            "admin", "manager", "planner"):
                        return err("نقش «پلنر تیم» فقط برای کاربر مدیر یا پلنر قابل انتخاب است")
                cur.execute("""SELECT user_id FROM TeamMembers
                    WHERE team_id=? AND is_active=1""", tid)
                removed = {int(x[0]) for x in cur.fetchall()} - seen
                if removed:
                    removed_marks = ",".join("?" for _ in removed)
                    cur.execute("""SELECT COUNT(*) FROM Tasks task
                        JOIN ProjectTeams pt ON pt.id=task.project_team_id
                        WHERE pt.team_id=? AND task.status NOT IN ('done','rejected')
                          AND (task.staff_id IN (%s) OR EXISTS(
                            SELECT 1 FROM TaskAssignees a WHERE a.task_id=task.id
                              AND a.user_id IN (%s)))""" %
                                (removed_marks, removed_marks),
                                *([tid] + list(removed) + list(removed)))
                    if int((cur.fetchone() or [0])[0] or 0):
                        return err("یکی از اعضای حذف‌شده هنوز روی تسک باز این تیم مسئولیت دارد")
                cur.execute("UPDATE TeamMembers SET is_active=0,left_at=GETDATE() WHERE team_id=?", tid)
                for uid, role, primary in clean:
                    cur.execute("""IF EXISTS(SELECT 1 FROM TeamMembers WHERE team_id=? AND user_id=?)
                        UPDATE TeamMembers SET team_role=?,is_primary=?,is_active=1,left_at=NULL,
                            added_by=? WHERE team_id=? AND user_id=?
                        ELSE INSERT INTO TeamMembers(team_id,user_id,team_role,is_primary,added_by)
                            VALUES(?,?,?,?,?)""",
                                tid, uid, role, primary, g.user["id"], tid, uid,
                                tid, uid, role, primary, g.user["id"])
                # Keep automatic team chat membership aligned. Content is
                # still unreadable to the server; membership changes require
                # clients to rotate and re-wrap the conversation key.
                conv = one(cur, "SELECT id FROM ChatConversations WHERE kind='team' AND team_id=? AND is_active=1", tid)
                if not conv:
                    team = one(cur, "SELECT name FROM Teams WHERE id=?", tid) or {"name": "تیم"}
                    cur.execute("""INSERT INTO ChatConversations(kind,title,team_id,created_by,needs_key_rotation)
                        OUTPUT INSERTED.id VALUES('team',?,?,?,1)""",
                                "گروه تیم", tid, g.user["id"])
                    conv_id = cur.fetchone()[0]
                else:
                    conv_id = conv["id"]
                    cur.execute("""UPDATE ChatConversations SET needs_key_rotation=1,
                        key_version=key_version+1,rotation_owner_device_id=NULL,
                        rotation_claim_hash=NULL,rotation_claimed_at=NULL,updated_at=GETDATE() WHERE id=?""", conv_id)
                cur.execute("UPDATE ChatMembers SET is_active=0,left_at=GETDATE() WHERE conversation_id=?", conv_id)
                for uid, role, _ in clean:
                    if user_roles.get(uid) in CHAT_CLIENT_ROLES:
                        continue  # R14: clients stay out of the staff team channel
                    member_role = "admin" if role == "manager" else "member"
                    cur.execute("""IF EXISTS(SELECT 1 FROM ChatMembers WHERE conversation_id=? AND user_id=?)
                        UPDATE ChatMembers SET member_role=?,can_post=1,is_active=1,left_at=NULL
                          WHERE conversation_id=? AND user_id=?
                        ELSE INSERT INTO ChatMembers(conversation_id,user_id,member_role)
                          VALUES(?,?,?)""",
                                conv_id, uid, member_role, conv_id, uid,
                                conv_id, uid, member_role)
                c.commit()
            audit("v8_team_members", "team #%s members=%s" % (tid, len(clean)))
            return ok(conversation_id=conv_id, needs_key_rotation=True)
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/team_types_save", methods=["POST"])
    @require_auth
    def api_v8_team_types_save():
        try:
            data = request.get_json() or {}; tid = _int(data.get("team_id"))
            entries = data.get("project_types") or []
            clean = []
            seen_types = set()
            for item in entries:
                pid = _int(item.get("project_type_id"))
                role = item.get("assignment_role") or "primary"
                if (not pid or pid in seen_types
                        or role not in ("primary", "collaborator")):
                    return err("نوع پروژه یا نقش تخصیص معتبر نیست")
                seen_types.add(pid)
                clean.append((pid, role))
            if not clean:
                return err("حداقل یک نوع پروژه باید برای تیم انتخاب شود")
            with db_lock:
                c = get_conn(); cur = c.cursor()
                if not can_manage_team(cur, g.user, tid):
                    return err("اجازه تغییر حوزه پروژه این تیم را ندارید", 403)
                type_ids = {x[0] for x in clean}
                marks = ",".join("?" for _ in type_ids)
                cur.execute("""SELECT id FROM ProjectTypes WHERE id IN (%s)
                    AND id>0 AND is_active=1""" % marks, list(type_ids))
                if {int(x[0]) for x in cur.fetchall()} != type_ids:
                    return err("یکی از انواع پروژه فعال یا معتبر نیست")
                cur.execute("""SELECT project_type_id FROM TeamProjectTypes
                    WHERE team_id=? AND is_active=1""", tid)
                removed_types = {int(x[0]) for x in cur.fetchall()} - type_ids
                if removed_types:
                    removed_marks = ",".join("?" for _ in removed_types)
                    cur.execute("""SELECT COUNT(*) FROM ProjectTeams ptm
                        JOIN Projects p ON p.id=ptm.project_id
                        WHERE ptm.team_id=? AND ptm.is_active=1
                          AND p.project_type_id IN (%s)""" % removed_marks,
                                *([tid] + list(removed_types)))
                    if int((cur.fetchone() or [0])[0] or 0):
                        return err("نوع پروژه‌ای که جریان کاری فعال دارد قابل حذف از تیم نیست")
                cur.execute("UPDATE TeamProjectTypes SET is_active=0 WHERE team_id=?", tid)
                for pid, role in clean:
                    cur.execute("""IF EXISTS(SELECT 1 FROM TeamProjectTypes WHERE team_id=? AND project_type_id=?)
                        UPDATE TeamProjectTypes SET assignment_role=?,is_active=1,assigned_by=?,
                            assigned_at=GETDATE() WHERE team_id=? AND project_type_id=?
                        ELSE INSERT INTO TeamProjectTypes(team_id,project_type_id,assignment_role,assigned_by)
                            VALUES(?,?,?,?)""",
                                tid, pid, role, g.user["id"], tid, pid,
                                tid, pid, role, g.user["id"])
                c.commit()
            return ok()
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/project_team_save", methods=["POST"])
    @require_auth
    def api_v8_project_team_save():
        try:
            data = request.get_json() or {}; ident = _int(data.get("id"))
            project_id = _int(data.get("project_id")); tid = _int(data.get("team_id"))
            if not project_id or not tid:
                return err("پروژه و تیم الزامی است")
            with db_lock:
                c = get_conn(); cur = c.cursor()
                if ident:
                    previous = one(cur, """SELECT project_id,team_id FROM ProjectTeams
                        WHERE id=? AND is_active=1""", ident)
                    if not previous:
                        return err("جریان کاری یافت نشد")
                    if not can_manage_team(cur, g.user, int(previous["team_id"])):
                        return err("اجازه جابه‌جایی جریان کاری تیم دیگری را ندارید", 403)
                    if (int(previous["project_id"]) != project_id or
                            int(previous["team_id"]) != tid):
                        usage = one(cur, """SELECT
                            (SELECT COUNT(*) FROM Tasks WHERE project_team_id=?) AS tasks,
                            (SELECT COUNT(*) FROM ContractProjectTeams
                              WHERE project_team_id=? AND is_active=1) AS contracts,
                            (SELECT COUNT(*) FROM ContractStatementTeams cst
                              JOIN ContractStatements s ON s.id=cst.statement_id
                              WHERE cst.project_team_id=? AND cst.is_active=1
                                AND s.is_active=1) AS statements,
                            (SELECT COUNT(*) FROM PlannedStatements
                              WHERE project_team_id=? AND is_active=1) AS plans""",
                                    ident, ident, ident, ident) or {}
                        if any(int(usage.get(x) or 0) for x in
                               ("tasks", "contracts", "statements", "plans")):
                            return err("جریان کاری دارای سابقه است؛ پروژه یا تیم آن قابل جابه‌جایی نیست")
                if not can_manage_team(cur, g.user, tid):
                    return err("اجازه ساخت جریان کاری برای این تیم را ندارید", 403)
                valid = one(cur, """SELECT 1 AS ok FROM Projects p JOIN TeamProjectTypes x
                    ON x.project_type_id=p.project_type_id AND x.team_id=?
                    WHERE p.id=? AND x.is_active=1""", tid, project_id)
                if not valid:
                    return err("نوع این پروژه هنوز به تیم انتخاب‌شده تخصیص داده نشده است")
                if bool(data.get("is_primary")):
                    cur.execute("""UPDATE ProjectTeams SET is_primary=0,
                        updated_by=?,updated_at=GETDATE()
                        WHERE project_id=? AND is_active=1 AND id<>ISNULL(?,0)""",
                                g.user["id"], project_id, ident)
                if ident:
                    cur.execute("""UPDATE ProjectTeams SET project_id=?,team_id=?,title=?,
                        is_primary=?,start_date=?,end_date=?,updated_by=?,updated_at=GETDATE()
                        WHERE id=?""", project_id, tid, (data.get("title") or "").strip() or None,
                                bool(data.get("is_primary")), _date(data.get("start_date")),
                                _date(data.get("end_date")), g.user["id"], ident)
                else:
                    cur.execute("""INSERT INTO ProjectTeams(project_id,team_id,title,is_primary,
                        start_date,end_date,created_by) OUTPUT INSERTED.id
                        VALUES(?,?,?,?,?,?,?)""",
                                project_id, tid, (data.get("title") or "").strip() or None,
                                bool(data.get("is_primary")), _date(data.get("start_date")),
                                _date(data.get("end_date")), g.user["id"])
                    ident = cur.fetchone()[0]
                c.commit()
            return ok(id=ident)
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/project_team_archive", methods=["POST"])
    @require_auth
    def api_v8_project_team_archive():
        try:
            ident = _int((request.get_json() or {}).get("id"))
            with db_lock:
                c = get_conn(); cur = c.cursor()
                row = one(cur, "SELECT team_id FROM ProjectTeams WHERE id=? AND is_active=1", ident)
                if not row:
                    return err("جریان کاری یافت نشد")
                counts = one(cur, """SELECT
                    (SELECT COUNT(*) FROM Tasks WHERE project_team_id=?) AS tasks,
                    (SELECT COUNT(*) FROM ContractProjectTeams
                      WHERE project_team_id=? AND is_active=1) AS contracts,
                    (SELECT COUNT(*) FROM ContractStatementTeams cst
                      JOIN ContractStatements s ON s.id=cst.statement_id
                      WHERE cst.project_team_id=? AND cst.is_active=1
                        AND s.is_active=1) AS statements,
                    (SELECT COUNT(*) FROM PlannedStatements
                      WHERE project_team_id=? AND is_active=1) AS plans""",
                             ident, ident, ident, ident) or {}
                if any(int(counts.get(x) or 0) for x in
                       ("tasks", "contracts", "statements", "plans")):
                    return err("این جریان کاری سابقه عملیاتی یا مالی دارد و قابل بایگانی نیست")
                cur.execute("UPDATE ProjectTeams SET is_active=0,updated_by=?,updated_at=GETDATE() WHERE id=?",
                            g.user["id"], ident)
                c.commit()
            return ok()
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/contract_teams", methods=["POST"])
    @require_auth
    def api_v8_contract_teams():
        try:
            data = request.get_json() or {}
            cid = _int(data.get("contract_id"))
            with db_lock:
                c = get_conn(); cur = c.cursor()
                allowed = scoped_team_ids(cur, g.user, data)
                if not allowed:
                    return ok(rows=[])
                marks = ",".join("?" for _ in allowed)
                cur.execute("""SELECT x.contract_id,x.project_team_id,x.allocation_amount,
                    ptm.project_id,ptm.team_id,t.name AS team_name,p.name AS project_name,
                    ISNULL((SELECT SUM(COALESCE(s.confirmed_without_vat,s.confirmed_price,
                        s.requested_without_vat,s.requested_price,0)
                          *cst.allocation_percent/100)
                      FROM ContractStatementTeams cst
                      JOIN ContractStatements s ON s.id=cst.statement_id
                      WHERE s.contract_id=x.contract_id
                        AND cst.project_team_id=x.project_team_id
                        AND cst.is_active=1 AND s.is_active=1
                        AND s.is_current=1 AND (s.business_status='employer_approved' OR (s.employer_decision_at IS NOT NULL AND ISNULL(s.business_status,'') NOT IN ('employer_rejected','revised','void') AND COALESCE(s.confirmed_without_vat,s.confirmed_price,0)>0))),0) AS approved_amount
                    FROM ContractProjectTeams x JOIN ProjectTeams ptm ON ptm.id=x.project_team_id
                    JOIN Teams t ON t.id=ptm.team_id JOIN Projects p ON p.id=ptm.project_id
                    WHERE x.is_active=1 AND (? IS NULL OR x.contract_id=?)
                      AND ptm.team_id IN (%s)
                    ORDER BY x.contract_id,t.name""" % marks, *([cid, cid] + allowed))
                rows = rows_to_list(cur)
            for row in rows:
                allocation = _dec(row.get("allocation_amount"))
                approved = _dec(row.get("approved_amount"), _decimal.Decimal(0))
                row["team_remaining"] = None if allocation is None else allocation - approved
            return ok(rows=rows)
        except Exception as exc:
            return err(str(exc), rows=[])

    @app.route("/api/v8/contract_teams_save", methods=["POST"])
    @require_auth
    def api_v8_contract_teams_save():
        try:
            data = request.get_json() or {}; cid = _int(data.get("contract_id"))
            entries = data.get("project_teams") or []
            with db_lock:
                c = get_conn(); cur = c.cursor()
                contract = one(cur, """SELECT co.id,co.project_id,
                    ISNULL(co.base_price,0)+ISNULL((SELECT SUM(ISNULL(e.price_delta,0))
                      FROM ContractExtensions e WHERE e.contract_id=co.id AND e.is_active=1
                      AND e.internal_status='approved' AND e.extension_type_id IN (2,3)),0) AS effective_price
                    FROM Contracts co WHERE co.id=? AND co.is_active=1""", cid)
                if not contract:
                    return err("قرارداد فعال یافت نشد")
                if contract.get("project_id") and not entries:
                    return err("قرارداد پروژه‌دار باید حداقل یک تیم فعال داشته باشد")
                clean = []
                seen_workstreams = set()
                for item in entries:
                    ptid = _int(item.get("project_team_id"))
                    amount = _dec(item.get("allocation_amount"))
                    if not ptid or ptid in seen_workstreams:
                        return err("جریان کاری تیم معتبر نیست")
                    seen_workstreams.add(ptid)
                    valid = one(cur, """SELECT id,team_id FROM ProjectTeams WHERE id=? AND project_id=?
                        AND is_active=1""", ptid, contract.get("project_id"))
                    if not valid:
                        return err("تیم انتخاب‌شده روی پروژه این قرارداد فعال نیست")
                    clean.append((ptid, amount))
                valid, message, gap = validate_team_allocations(
                    contract.get("effective_price"), [x[1] for x in clean if x[1] is not None]
                )
                if not valid:
                    return err(message)
                cur.execute("""SELECT project_team_id FROM ContractProjectTeams
                    WHERE contract_id=? AND is_active=1""", cid)
                current_workstreams = {int(x[0]) for x in cur.fetchall()}
                removed_workstreams = current_workstreams - seen_workstreams
                if removed_workstreams:
                    removed_marks = ",".join("?" for _ in removed_workstreams)
                    removed_params = list(removed_workstreams)
                    usage = one(cur, """SELECT
                        (SELECT COUNT(*) FROM ContractStatementTeams cst
                          JOIN ContractStatements s ON s.id=cst.statement_id
                          WHERE s.contract_id=? AND s.is_active=1
                            AND cst.is_active=1
                            AND cst.project_team_id IN (%s)) AS statements,
                        (SELECT COUNT(*) FROM PlannedStatements ps
                          WHERE ps.contract_id=? AND ps.is_active=1
                            AND ps.project_team_id IN (%s)) AS plans,
                        (SELECT COUNT(*) FROM Tasks t
                          WHERE t.contract_id=?
                            AND t.project_team_id IN (%s)) AS tasks,
                        (SELECT COUNT(*) FROM ContractExtensionTeams cet
                          JOIN ContractExtensions e ON e.id=cet.extension_id
                          WHERE e.contract_id=? AND e.is_active=1
                            AND cet.project_team_id IN (%s)) AS extensions""" % (
                                removed_marks, removed_marks,
                                removed_marks, removed_marks),
                                *([cid] + removed_params + [cid] +
                                  removed_params + [cid] + removed_params +
                                  [cid] + removed_params)) or {}
                    if any(int(usage.get(x) or 0) for x in
                           ("statements", "plans", "tasks", "extensions")):
                        return err(
                            "اتصال تیمی دارای سابقه است و قابل حذف نیست؛ "
                            "ابتدا رکوردهای وابسته را اصلاح یا بایگانی کنید"
                        )
                cur.execute("UPDATE ContractProjectTeams SET is_active=0 WHERE contract_id=?", cid)
                for ptid, amount in clean:
                    cur.execute("""IF EXISTS(SELECT 1 FROM ContractProjectTeams
                            WHERE contract_id=? AND project_team_id=?)
                        UPDATE ContractProjectTeams SET allocation_amount=?,is_active=1,linked_by=?,
                            linked_at=GETDATE() WHERE contract_id=? AND project_team_id=?
                        ELSE INSERT INTO ContractProjectTeams(contract_id,project_team_id,
                            allocation_amount,linked_by) VALUES(?,?,?,?)""",
                                cid, ptid, amount, g.user["id"], cid, ptid,
                                cid, ptid, amount, g.user["id"])
                if len(clean) == 1:
                    legacy_team_id = clean[0][0]
                    cur.execute("""UPDATE s SET project_team_id=?
                        FROM ContractStatements s
                        WHERE s.contract_id=? AND s.is_active=1
                          AND NOT EXISTS(SELECT 1
                            FROM ContractStatementTeams cst
                            WHERE cst.statement_id=s.id
                              AND cst.is_active=1)""",
                                legacy_team_id, cid)
                    cur.execute("""UPDATE existing SET
                          allocation_percent=100,is_active=1,
                          linked_by=?,linked_at=GETDATE()
                        FROM ContractStatementTeams existing
                        JOIN ContractStatements s
                          ON s.id=existing.statement_id
                        WHERE s.contract_id=? AND s.is_active=1
                          AND existing.project_team_id=?
                          AND NOT EXISTS(SELECT 1
                            FROM ContractStatementTeams active_link
                            WHERE active_link.statement_id=s.id
                              AND active_link.is_active=1)""",
                                g.user["id"], cid, legacy_team_id)
                    cur.execute("""INSERT INTO ContractStatementTeams(
                          statement_id,project_team_id,allocation_percent,
                          is_active,linked_by)
                        SELECT s.id,?,100,1,?
                        FROM ContractStatements s
                        WHERE s.contract_id=? AND s.is_active=1
                          AND NOT EXISTS(SELECT 1
                            FROM ContractStatementTeams active_link
                            WHERE active_link.statement_id=s.id
                              AND active_link.is_active=1)
                          AND NOT EXISTS(SELECT 1
                            FROM ContractStatementTeams same_link
                            WHERE same_link.statement_id=s.id
                              AND same_link.project_team_id=?)""",
                                legacy_team_id, g.user["id"], cid,
                                legacy_team_id)
                c.commit()
            audit("v8_contract_teams", "contract #%s workstreams=%s" % (cid, len(clean)))
            return ok(unallocated_amount=gap)
        except Exception as exc:
            return err(str(exc))

    def scoped_team_ids(cur, user, data):
        allowed = team_ids(cur, user)
        chosen = selected_team(cur, user, data)
        return [chosen] if chosen else allowed

    def parse_range(data):
        start = _date(data.get("from_date"))
        end = _date(data.get("to_date"))
        if start and end and end < start:
            raise ValueError("تاریخ پایان گزارش قبل از تاریخ شروع است")
        return start, end

    def ensure_financial_plan(cur, year, user_id):
        """Return the current plan row for a year, creating an empty one.

        Team goals no longer wait for somebody to declare a company figure
        first; the company row exists purely to hang the roll-up and the
        approved target on, so it is created on demand.
        """
        plan = one(cur, """SELECT TOP 1 id,jalali_year,title,annual_target,
            approved_target,version_no,status FROM FinancialPlans
            WHERE jalali_year=? AND is_current=1 ORDER BY id DESC""", year)
        if plan:
            return plan
        cur.execute("""INSERT INTO FinancialPlans(jalali_year,title,annual_target,created_by)
            OUTPUT INSERTED.id VALUES(?,?,0,?)""",
                    year, "هدف مالی %s" % year, user_id)
        plan_id = cur.fetchone()[0]
        for month in range(1, 13):
            cur.execute("""INSERT INTO FinancialPlanPeriods(plan_id,month_no,target_amount)
                VALUES(?,?,0)""", plan_id, month)
        return one(cur, """SELECT id,jalali_year,title,annual_target,approved_target,
            version_no,status FROM FinancialPlans WHERE id=?""", plan_id)

    def recompute_company_plan(cur, plan_id):
        """Roll the team goals up into the company plan.

        This is the single writer of FinancialPlans.annual_target and of the
        company monthly periods. Every consumer - dashboard, plan page, exports
        - keeps reading the same columns it always did, so the inversion of the
        goal model needed no change on the reading side.
        """
        cur.execute("""UPDATE p SET annual_target=ISNULL(t.total,0),updated_at=GETDATE()
            FROM FinancialPlans p
            OUTER APPLY(SELECT SUM(tf.annual_target) AS total
              FROM TeamFinancialTargets tf
              WHERE tf.plan_id=p.id AND tf.is_current=1) t
            WHERE p.id=?""", plan_id)
        cur.execute("""UPDATE fp SET target_amount=ISNULL(t.total,0),updated_at=GETDATE()
            FROM FinancialPlanPeriods fp
            OUTER APPLY(SELECT SUM(tp.target_amount) AS total
              FROM TeamFinancialTargetPeriods tp
              JOIN TeamFinancialTargets tf ON tf.id=tp.target_id
              WHERE tf.plan_id=fp.plan_id AND tf.is_current=1
                AND tp.month_no=fp.month_no) t
            WHERE fp.plan_id=?""", plan_id)

    @app.route("/api/v8/team_financial_plan", methods=["POST"])
    @require_auth
    def api_v8_team_financial_plan():
        """Read or update team financial goals; the company total is derived."""
        try:
            if not user_has_permission(g.user, "financial_plan.view"):
                return err("اجازه مشاهده هدف مالی تیم‌ها را ندارید", 403)
            data = request.get_json() or {}
            action = data.get("action") or "read"
            year = _int(data.get("year"), 1405)
            if year < 1300 or year > 1600:
                return err("سال مالی نامعتبر است")
            audit_detail = None
            empty_payload = None
            with db_lock:
                c = get_conn(); cur = c.cursor()
                plan = one(cur, """SELECT TOP 1 id,jalali_year,title,annual_target,
                    approved_target,version_no,status FROM FinancialPlans
                    WHERE jalali_year=? AND is_current=1 ORDER BY id DESC""", year)
                if action == "save":
                    tid = _int(data.get("team_id"))
                    if not tid or not can_plan_team(cur, g.user, tid):
                        return err("فقط مدیر یا پلنر همان تیم اجازه تغییر هدف را دارد", 403)
                    # The company plan is a container for the roll-up now, so a
                    # missing one is created rather than blocking the team.
                    plan = ensure_financial_plan(cur, year, g.user["id"])
                    target = _dec(data.get("annual_target"))
                    if target is None or target < 0:
                        return err("هدف تیم باید عددی نامنفی باشد")
                    reason = (data.get("reason") or "").strip()
                    old = one(cur, """SELECT id,annual_target,version_no FROM TeamFinancialTargets
                        WHERE plan_id=? AND team_id=? AND is_current=1""", plan["id"], tid)
                    if old and target != _dec(old.get("annual_target")) and not reason:
                        return err("برای تغییر هدف تیم، دلیل تغییر الزامی است")
                    periods = data.get("periods") or []
                    if len(periods) != 12:
                        return err("برای هر ۱۲ ماه باید مقدار تعیین شود")
                    clean_periods = []
                    seen_months = set()
                    period_total = _decimal.Decimal(0)
                    for item in periods:
                        month = _int(item.get("month_no"))
                        amount = _dec(item.get("target_amount"))
                        mode = item.get("allocation_mode") or "amount"
                        allocation_percent = _dec(item.get("allocation_percent"))
                        if (not month or month in seen_months
                                or not 1 <= month <= 12
                                or amount is None or amount < 0):
                            return err("تقسیم ماهانه معتبر نیست")
                        seen_months.add(month)
                        if mode not in ("amount", "percent"):
                            return err("روش تقسیم ماهانه معتبر نیست")
                        if mode == "percent":
                            if allocation_percent is None or not 0 <= allocation_percent <= 100:
                                return err("درصد ماهانه نامعتبر است")
                            amount = (target * allocation_percent / _decimal.Decimal(100)).quantize(
                                _decimal.Decimal("1"), rounding=_decimal.ROUND_HALF_UP
                            )
                        clean_periods.append((month, amount, mode, allocation_percent))
                        period_total += amount
                    if seen_months != set(range(1, 13)):
                        return err("برای هر ماه باید دقیقاً یک مقدار ثبت شود")
                    if period_total > target:
                        return err("جمع هدف ماه‌ها از هدف سالانه تیم بیشتر است")
                    if old:
                        target_id = int(old["id"])
                        cur.execute("""UPDATE TeamFinancialTargets SET annual_target=?,
                            change_reason=?,version_no=version_no+1,updated_by=?,
                            updated_at=GETDATE() WHERE id=?""",
                                    target, reason or None, g.user["id"], target_id)
                    else:
                        cur.execute("""INSERT INTO TeamFinancialTargets(plan_id,team_id,
                            annual_target,change_reason,created_by)
                            OUTPUT INSERTED.id VALUES(?,?,?,?,?)""",
                                    plan["id"], tid, target, reason or None, g.user["id"])
                        target_id = cur.fetchone()[0]
                    for month, amount, mode, allocation_percent in clean_periods:
                        cur.execute("""IF EXISTS(SELECT 1 FROM TeamFinancialTargetPeriods
                                WHERE target_id=? AND month_no=?)
                            UPDATE TeamFinancialTargetPeriods SET target_amount=?,
                              allocation_mode=?,allocation_percent=?,updated_by=?,
                              updated_at=GETDATE() WHERE target_id=? AND month_no=?
                            ELSE INSERT INTO TeamFinancialTargetPeriods(target_id,month_no,
                              target_amount,allocation_mode,allocation_percent,updated_by)
                              VALUES(?,?,?,?,?,?)""",
                                    target_id, month, amount, mode, allocation_percent,
                                    g.user["id"], target_id, month,
                                    target_id, month, amount, mode, allocation_percent,
                                    g.user["id"])
                    # The company total is only ever written here, straight
                    # after the team goal it is derived from.
                    recompute_company_plan(cur, plan["id"])
                    c.commit()
                    plan = one(cur, """SELECT id,jalali_year,title,annual_target,
                        approved_target,version_no,status FROM FinancialPlans
                        WHERE id=?""", plan["id"])
                    audit_detail = "team #%s year=%s target=%s" % (
                        tid, year, target
                    )

                allowed = scoped_team_ids(cur, g.user, data)
                if not plan or not allowed:
                    empty_payload = {
                        "plan": plan, "teams": [],
                        "company_rollup": 0,
                        "company_approved": plan.get("approved_target") if plan else None,
                        "company_unallocated": 0,
                    }
                    team_rows = []
                    periods = []
                    company_unallocated = 0
                else:
                    marks = ",".join("?" for _ in allowed)
                    cur.execute("""SELECT t.id AS team_id,t.name AS team_name,
                        tf.id AS target_id,ISNULL(tf.annual_target,0) AS annual_target,
                        tf.version_no,tf.change_reason,
                        ISNULL(a.sent_amount,0) AS sent_amount,
                        ISNULL(a.approved_amount,0) AS approved_amount,
                        ISNULL(a.sent_count,0) AS sent_count,
                        ISNULL(a.approved_count,0) AS approved_count
                        FROM Teams t
                        LEFT JOIN TeamFinancialTargets tf ON tf.team_id=t.id
                          AND tf.plan_id=? AND tf.is_current=1
                        OUTER APPLY(SELECT
                          SUM(CASE WHEN s.business_status IN
                            ('sent','employer_approved','employer_rejected')
                            THEN COALESCE(s.requested_without_vat,s.requested_price,0)
                              *cst.allocation_percent/100 ELSE 0 END) AS sent_amount,
                          SUM(CASE WHEN (s.business_status='employer_approved' OR (s.employer_decision_at IS NOT NULL AND ISNULL(s.business_status,'') NOT IN ('employer_rejected','revised','void') AND COALESCE(s.confirmed_without_vat,s.confirmed_price,0)>0))
                            THEN COALESCE(s.confirmed_without_vat,s.confirmed_price,
                              s.requested_without_vat,s.requested_price,0)
                              *cst.allocation_percent/100 ELSE 0 END) AS approved_amount,
                          SUM(CASE WHEN s.business_status IN
                            ('sent','employer_approved','employer_rejected') THEN 1 ELSE 0 END) AS sent_count,
                          SUM(CASE WHEN (s.business_status='employer_approved' OR (s.employer_decision_at IS NOT NULL AND ISNULL(s.business_status,'') NOT IN ('employer_rejected','revised','void') AND COALESCE(s.confirmed_without_vat,s.confirmed_price,0)>0)) THEN 1 ELSE 0 END) AS approved_count
                          FROM ContractStatementTeams cst
                          JOIN ContractStatements s ON s.id=cst.statement_id
                          JOIN ProjectTeams ptm ON ptm.id=cst.project_team_id
                          WHERE cst.is_active=1 AND ptm.team_id=t.id
                            AND s.is_active=1 AND s.is_current=1
                            AND s.period_year=?) a
                        WHERE t.is_active=1 AND t.id IN (%s) ORDER BY t.name""" % marks,
                                *([plan["id"], year] + allowed))
                    team_rows = rows_to_list(cur)
                    target_ids = [int(x["target_id"]) for x in team_rows if x.get("target_id")]
                    periods = []
                    if target_ids:
                        pm = ",".join("?" for _ in target_ids)
                        cur.execute("""SELECT p.*,tf.team_id FROM TeamFinancialTargetPeriods p
                            JOIN TeamFinancialTargets tf ON tf.id=p.target_id
                            WHERE p.target_id IN (%s) ORDER BY tf.team_id,p.month_no""" % pm,
                                    target_ids)
                        periods = rows_to_list(cur)
                    # The roll-up covers every team, not just the ones this
                    # user may see, otherwise a team-scoped reader would be
                    # shown a company total that silently omits other teams.
                    rollup = one(cur, """SELECT ISNULL(SUM(annual_target),0) AS total,
                        COUNT(*) AS teams_with_target
                        FROM TeamFinancialTargets
                        WHERE plan_id=? AND is_current=1""", plan["id"]) or {}
                    company_rollup = _dec(rollup.get("total"), _decimal.Decimal(0))
                    approved_target = _dec(plan.get("approved_target"))
                    # Positive means the board approved more than the teams
                    # have taken on; negative means they over-committed.
                    company_unallocated = (
                        (approved_target - company_rollup)
                        if approved_target is not None else _decimal.Decimal(0)
                    )
            if audit_detail:
                audit("v8_team_financial_target", audit_detail)
            if empty_payload is not None:
                return ok(**empty_payload)
            by_team = {}
            for row in periods:
                by_team.setdefault(int(row["team_id"]), []).append(row)
            for row in team_rows:
                target = _dec(row.get("annual_target"), _decimal.Decimal(0))
                sent = _dec(row.get("sent_amount"), _decimal.Decimal(0))
                approved = _dec(row.get("approved_amount"), _decimal.Decimal(0))
                row["sent_percent"] = percent(sent, target)
                row["approved_percent"] = percent(approved, target)
                row["remaining_to_send"] = target - sent
                row["periods"] = by_team.get(int(row["team_id"]), [])
            return ok(plan=plan, teams=team_rows,
                      company_rollup=company_rollup,
                      company_approved=plan.get("approved_target"),
                      company_teams_with_target=_int(rollup.get("teams_with_target"), 0),
                      company_unallocated=company_unallocated)
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/team_financial_detail", methods=["POST"])
    @require_auth
    def api_v8_team_financial_detail():
        """Month-by-month and statement-by-statement detail for one team.

        The goal screen could only ever show a whole-year total per team, so
        'how is this team doing from the start of the year until now' had no
        answer. This returns the monthly goal/sent/approved series plus the
        individual statements behind those numbers, optionally narrowed to a
        month range.
        """
        try:
            if not user_has_permission(g.user, "financial_plan.view"):
                return err("اجازه مشاهده هدف مالی تیم‌ها را ندارید", 403)
            data = request.get_json() or {}
            year = _int(data.get("year"), 1405)
            team_id = _int(data.get("team_id"))
            from_month = min(12, max(1, _int(data.get("from_month"), 1)))
            to_month = min(12, max(from_month, _int(data.get("to_month"), 12)))
            if year < 1300 or year > 1600:
                return err("سال مالی نامعتبر است")
            if not team_id:
                return err("تیم انتخاب نشده است")
            with db_lock:
                c = get_conn(); cur = c.cursor()
                # Checked directly against the reader's own teams. Going
                # through scoped_team_ids would be circular here, because this
                # payload carries team_id and that helper treats team_id as the
                # chosen scope rather than as the thing being authorised.
                if team_id not in team_ids(cur, g.user):
                    return err("به اطلاعات این تیم دسترسی ندارید", 403)
                team = one(cur, "SELECT id,name FROM Teams WHERE id=?", team_id)
                if not team:
                    return err("تیم یافت نشد")
                plan = one(cur, """SELECT TOP 1 id,jalali_year,annual_target,approved_target
                    FROM FinancialPlans WHERE jalali_year=? AND is_current=1
                    ORDER BY id DESC""", year)
                target_row = None
                goal_months = []
                if plan:
                    target_row = one(cur, """SELECT id,annual_target,version_no,change_reason,
                        updated_at FROM TeamFinancialTargets
                        WHERE plan_id=? AND team_id=? AND is_current=1""", plan["id"], team_id)
                    if target_row:
                        cur.execute("""SELECT month_no,target_amount,allocation_mode,
                            allocation_percent FROM TeamFinancialTargetPeriods
                            WHERE target_id=? AND month_no BETWEEN ? AND ?
                            ORDER BY month_no""", target_row["id"], from_month, to_month)
                        goal_months = rows_to_list(cur)
                # Actuals are split by the team's allocation share on each
                # statement, exactly as the team goal grid already does, so the
                # detail always adds up to the summary row.
                cur.execute("""SELECT s.period_month AS month_no,
                    SUM(CASE WHEN s.business_status IN
                      ('sent','employer_approved','employer_rejected')
                      THEN COALESCE(s.requested_without_vat,s.requested_price,0)
                        *cst.allocation_percent/100 ELSE 0 END) AS sent_amount,
                    SUM(CASE WHEN (s.business_status='employer_approved' OR (s.employer_decision_at IS NOT NULL AND ISNULL(s.business_status,'') NOT IN ('employer_rejected','revised','void') AND COALESCE(s.confirmed_without_vat,s.confirmed_price,0)>0))
                      THEN COALESCE(s.confirmed_without_vat,s.confirmed_price,
                        s.requested_without_vat,s.requested_price,0)
                        *cst.allocation_percent/100 ELSE 0 END) AS approved_amount,
                    COUNT(*) AS statement_count
                    FROM ContractStatementTeams cst
                    JOIN ContractStatements s ON s.id=cst.statement_id
                    JOIN ProjectTeams ptm ON ptm.id=cst.project_team_id
                    WHERE cst.is_active=1 AND ptm.team_id=? AND s.is_active=1
                      AND s.is_current=1 AND s.period_year=?
                      AND s.period_month BETWEEN ? AND ?
                    GROUP BY s.period_month ORDER BY s.period_month""",
                            team_id, year, from_month, to_month)
                actual_months = rows_to_list(cur)
                cur.execute("""SELECT TOP 300 s.id,s.period_month,s.title,s.statement_number,
                    s.statement_date_fa,s.business_status,
                    cst.allocation_percent,
                    COALESCE(s.requested_without_vat,s.requested_price,0) AS requested_amount,
                    COALESCE(s.confirmed_without_vat,s.confirmed_price,0) AS confirmed_amount,
                    COALESCE(s.requested_without_vat,s.requested_price,0)
                      *cst.allocation_percent/100 AS team_requested_amount,
                    CASE WHEN (s.business_status='employer_approved' OR (s.employer_decision_at IS NOT NULL AND ISNULL(s.business_status,'') NOT IN ('employer_rejected','revised','void') AND COALESCE(s.confirmed_without_vat,s.confirmed_price,0)>0))
                      THEN COALESCE(s.confirmed_without_vat,s.confirmed_price,
                        s.requested_without_vat,s.requested_price,0)
                        *cst.allocation_percent/100 ELSE 0 END AS team_approved_amount,
                    co.title AS contract_title,co.contract_number,
                    p.name AS project_name,ci.name AS city_name
                    FROM ContractStatementTeams cst
                    JOIN ContractStatements s ON s.id=cst.statement_id
                    JOIN ProjectTeams ptm ON ptm.id=cst.project_team_id
                    JOIN Contracts co ON co.id=s.contract_id
                    LEFT JOIN Projects p ON p.id=co.project_id
                    LEFT JOIN Cities ci ON ci.id=p.city_id
                    WHERE cst.is_active=1 AND ptm.team_id=? AND s.is_active=1
                      AND s.is_current=1 AND s.period_year=?
                      AND s.period_month BETWEEN ? AND ?
                    ORDER BY s.period_month,s.id""",
                            team_id, year, from_month, to_month)
                statements = rows_to_list(cur)
            goal_by_month = {_int(x["month_no"]): x for x in goal_months}
            actual_by_month = {_int(x["month_no"]): x for x in actual_months}
            months = []
            goal_total = sent_total = approved_total = _decimal.Decimal(0)
            for month in range(from_month, to_month + 1):
                goal = _dec((goal_by_month.get(month) or {}).get("target_amount"), _decimal.Decimal(0))
                actual = actual_by_month.get(month) or {}
                sent = _dec(actual.get("sent_amount"), _decimal.Decimal(0))
                approved = _dec(actual.get("approved_amount"), _decimal.Decimal(0))
                goal_total += goal; sent_total += sent; approved_total += approved
                months.append({
                    "month_no": month, "target_amount": goal,
                    "sent_amount": sent, "approved_amount": approved,
                    "statement_count": _int(actual.get("statement_count"), 0),
                    "sent_percent": percent(sent, goal),
                    "approved_percent": percent(approved, goal),
                    "gap": goal - approved,
                })
            annual_goal = _dec((target_row or {}).get("annual_target"), _decimal.Decimal(0))
            return ok(team=team, year=year, from_month=from_month, to_month=to_month,
                      months=months, statements=statements,
                      has_target=bool(target_row),
                      totals={
                          "annual_target": annual_goal,
                          "range_target": goal_total,
                          "sent_amount": sent_total,
                          "approved_amount": approved_total,
                          "sent_percent": percent(sent_total, goal_total),
                          "approved_percent": percent(approved_total, goal_total),
                          "annual_approved_percent": percent(approved_total, annual_goal),
                          "gap": goal_total - approved_total,
                          "statement_count": len(statements),
                      })
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc))

    def dashboard_report(cur, tids, start, end):
        if not tids:
            return {"totals": {}, "teams": []}
        marks = ",".join("?" for _ in tids)
        date_task = []
        date_task_params = []
        if start:
            date_task.append("CAST(t.created_at AS DATE)>=?")
            date_task_params.append(start)
        if end:
            date_task.append("CAST(t.created_at AS DATE)<=?")
            date_task_params.append(end)
        task_date_sql = (" AND " + " AND ".join(date_task)) if date_task else ""
        cur.execute("""SELECT tm.id AS team_id,tm.name AS team_name,
            COUNT(t.id) AS task_count,
            SUM(CASE WHEN t.status='done' THEN 1 ELSE 0 END) AS done_count,
            SUM(CASE WHEN t.status NOT IN ('done','rejected')
              AND t.date_delivery IS NOT NULL THEN 1 ELSE 0 END) AS open_due_count,
            SUM(CASE WHEN t.status='returned' THEN 1 ELSE 0 END) AS returned_count,
            SUM(CASE WHEN t.status='done' THEN ISNULL(t.progress_weight,1) ELSE 0 END) AS completed_weight,
            SUM(ISNULL(t.progress_weight,1)) AS total_weight,
            SUM(ISNULL(t.work_seconds,0)) AS task_seconds
            FROM Teams tm LEFT JOIN ProjectTeams ptm ON ptm.team_id=tm.id AND ptm.is_active=1
            LEFT JOIN Tasks t ON t.project_team_id=ptm.id %s
            WHERE tm.id IN (%s) GROUP BY tm.id,tm.name ORDER BY tm.name""" %
                    (task_date_sql, marks), *(date_task_params + tids))
        rows = rows_to_list(cur)
        # Event dates for financial numbers are intentionally independent.
        sent_filter = []
        approved_filter = []
        sent_params = []
        approved_params = []
        if start:
            sent_filter.append("CAST(COALESCE(s.sent_at,s.statement_date) AS DATE)>=?")
            sent_params.append(start)
            approved_filter.append("CAST(COALESCE(s.employer_decision_at,s.statement_date) AS DATE)>=?")
            approved_params.append(start)
        if end:
            sent_filter.append("CAST(COALESCE(s.sent_at,s.statement_date) AS DATE)<=?")
            sent_params.append(end)
            approved_filter.append("CAST(COALESCE(s.employer_decision_at,s.statement_date) AS DATE)<=?")
            approved_params.append(end)
        sent_sql = (" AND " + " AND ".join(sent_filter)) if sent_filter else ""
        approved_sql = (" AND " + " AND ".join(approved_filter)) if approved_filter else ""
        cur.execute("""SELECT ptm.team_id,
            SUM(CASE WHEN s.business_status IN ('sent','employer_approved','employer_rejected') %s
              THEN COALESCE(s.requested_without_vat,s.requested_price,0)
                *cst.allocation_percent/100 ELSE 0 END) AS sent_amount,
            SUM(CASE WHEN (s.business_status='employer_approved' OR (s.employer_decision_at IS NOT NULL AND ISNULL(s.business_status,'') NOT IN ('employer_rejected','revised','void') AND COALESCE(s.confirmed_without_vat,s.confirmed_price,0)>0)) %s
              THEN COALESCE(s.confirmed_without_vat,s.confirmed_price,
                s.requested_without_vat,s.requested_price,0)
                *cst.allocation_percent/100 ELSE 0 END) AS approved_amount
            FROM ContractStatementTeams cst
            JOIN ContractStatements s ON s.id=cst.statement_id
            JOIN ProjectTeams ptm ON ptm.id=cst.project_team_id
            WHERE cst.is_active=1 AND s.is_active=1 AND s.is_current=1
              AND ptm.team_id IN (%s)
            GROUP BY ptm.team_id""" % (sent_sql, approved_sql, marks),
                    *(sent_params + approved_params + tids))
        financial = {int(x["team_id"]): x for x in rows_to_list(cur)}
        for row in rows:
            total_weight = _dec(row.get("total_weight"), _decimal.Decimal(0))
            done_weight = _dec(row.get("completed_weight"), _decimal.Decimal(0))
            row["progress_percent"] = percent(done_weight, total_weight)
            f = financial.get(int(row["team_id"]), {})
            row["sent_amount"] = f.get("sent_amount") or 0
            row["approved_amount"] = f.get("approved_amount") or 0
        totals = {
            "task_count": sum(int(x.get("task_count") or 0) for x in rows),
            "done_count": sum(int(x.get("done_count") or 0) for x in rows),
            "returned_count": sum(int(x.get("returned_count") or 0) for x in rows),
            "work_seconds": sum(int(x.get("task_seconds") or 0) for x in rows),
            "sent_amount": sum((_dec(x.get("sent_amount"), _decimal.Decimal(0))
                                for x in rows), _decimal.Decimal(0)),
            "approved_amount": sum((_dec(x.get("approved_amount"), _decimal.Decimal(0))
                                    for x in rows), _decimal.Decimal(0)),
        }
        return {"totals": totals, "teams": rows}

    def contribution_report(cur, tids, start, end):
        if not tids:
            return {"people": [], "projects": [], "incomplete_task_ids": []}
        marks = ",".join("?" for _ in tids)
        date_sql = ""
        params = list(tids)
        if start:
            date_sql += " AND CAST(COALESCE(t.completed_at,t.created_at) AS DATE)>=?"
            params.append(start)
        if end:
            date_sql += " AND CAST(COALESCE(t.completed_at,t.created_at) AS DATE)<=?"
            params.append(end)
        cur.execute("""SELECT t.id,t.status,t.progress_weight,t.staff_id,
            ptm.team_id,tm.name AS team_name,t.project_id,p.name AS project_name
            FROM Tasks t JOIN ProjectTeams ptm ON ptm.id=t.project_team_id
            JOIN Teams tm ON tm.id=ptm.team_id JOIN Projects p ON p.id=t.project_id
            WHERE ptm.team_id IN (%s) %s""" % (marks, date_sql), params)
        tasks = rows_to_list(cur)
        task_ids = [int(x["id"]) for x in tasks]
        helpers = {}
        time_rows = []
        if task_ids:
            task_marks = ",".join("?" for _ in task_ids)
            cur.execute("SELECT task_id,user_id FROM TaskAssignees WHERE task_id IN (%s)" %
                        task_marks, task_ids)
            for row in rows_to_list(cur):
                helpers.setdefault(int(row["task_id"]), []).append(int(row["user_id"]))
            cur.execute("""SELECT task_id,user_id,SUM(ISNULL(seconds,
                DATEDIFF(second,started_at,ISNULL(ended_at,GETDATE())))) AS seconds
                FROM TaskTimeLog WHERE task_id IN (%s)
                GROUP BY task_id,user_id""" % task_marks, task_ids)
            time_rows = rows_to_list(cur)
        for task in tasks:
            task["helper_ids"] = helpers.get(int(task["id"]), [])
        output = person_output_shares(tasks, time_rows)
        time_by_user = {}
        for row in time_rows:
            uid = int(row["user_id"])
            time_by_user[uid] = time_by_user.get(uid, 0) + int(row.get("seconds") or 0)
        user_ids = sorted(set(time_by_user) | set(output["rows"]))
        users = {}
        if user_ids:
            um = ",".join("?" for _ in user_ids)
            cur.execute("""SELECT id,display_name,username FROM Users WHERE id IN (%s)""" % um,
                        user_ids)
            users = {int(x["id"]): x for x in rows_to_list(cur)}
        total_seconds = sum(time_by_user.values())
        people = []
        for uid in user_ids:
            out = output["rows"].get(uid, {})
            person = users.get(uid, {})
            people.append({
                "user_id": uid,
                "display_name": person.get("display_name") or person.get("username") or str(uid),
                "work_seconds": time_by_user.get(uid, 0),
                "time_share_percent": percent(time_by_user.get(uid, 0), total_seconds),
                "output_weight": out.get("output_weight") or 0,
                "output_share_percent": out.get("share_percent") or 0,
            })
        people.sort(key=lambda x: (-int(x["work_seconds"]), str(x["display_name"])))
        project_map = {}
        for task in tasks:
            key = (task.get("project_id"), task.get("team_id"))
            row = project_map.setdefault(key, {
                "project_id": task.get("project_id"), "project_name": task.get("project_name"),
                "team_id": task.get("team_id"), "team_name": task.get("team_name"),
                "task_count": 0, "done_count": 0, "total_weight": _decimal.Decimal(0),
                "completed_weight": _decimal.Decimal(0),
            })
            row["task_count"] += 1
            weight = _dec(task.get("progress_weight"), _decimal.Decimal(1))
            row["total_weight"] += weight
            if task.get("status") == "done":
                row["done_count"] += 1
                row["completed_weight"] += weight
        projects = []
        for row in project_map.values():
            row["progress_percent"] = percent(row["completed_weight"], row["total_weight"])
            projects.append(row)
        projects.sort(key=lambda x: (str(x["project_name"]), str(x["team_name"])))
        return {
            "people": people, "projects": projects,
            "incomplete_task_ids": output["incomplete_task_ids"],
        }

    def capacity_report(cur, tids, start, end):
        if not tids:
            return []
        marks = ",".join("?" for _ in tids)
        date_sql = ""
        date_params = []
        if start:
            date_sql += " AND CAST(l.started_at AS DATE)>=?"
            date_params.append(start)
        if end:
            date_sql += " AND CAST(l.started_at AS DATE)<=?"
            date_params.append(end)
        cur.execute("""SELECT u.id AS user_id,u.display_name,u.username,
            COUNT(DISTINCT tm.team_id) AS team_count,
            COUNT(DISTINCT CASE WHEN t.status NOT IN ('done','rejected') THEN t.id END) AS open_tasks,
            COUNT(DISTINCT CASE WHEN t.status='doing' THEN t.id END) AS doing_tasks,
            ISNULL(SUM(CASE WHEN l.id IS NOT NULL %s
              THEN ISNULL(l.seconds,DATEDIFF(second,l.started_at,ISNULL(l.ended_at,GETDATE())))
              ELSE 0 END),0) AS work_seconds
            FROM Users u JOIN TeamMembers tm ON tm.user_id=u.id AND tm.is_active=1
            LEFT JOIN ProjectTeams ptm ON ptm.team_id=tm.team_id AND ptm.is_active=1
            LEFT JOIN Tasks t ON t.project_team_id=ptm.id
              AND (t.staff_id=u.id OR EXISTS(SELECT 1 FROM TaskAssignees ta
                WHERE ta.task_id=t.id AND ta.user_id=u.id))
            LEFT JOIN TaskTimeLog l ON l.task_id=t.id AND l.user_id=u.id
            WHERE tm.team_id IN (%s) AND u.is_active=1
            GROUP BY u.id,u.display_name,u.username
            ORDER BY team_count DESC,open_tasks DESC,work_seconds DESC""" %
                    (date_sql, marks), *(date_params + tids))
        rows = rows_to_list(cur)
        for row in rows:
            row["capacity_warning"] = (
                int(row.get("team_count") or 0) > 1
                and (int(row.get("doing_tasks") or 0) > 1
                     or int(row.get("open_tasks") or 0) >= 8)
            )
        return rows

    def shared_projects_report(cur, tids):
        if not tids:
            return []
        marks = ",".join("?" for _ in tids)
        # Every metric is aggregated in its own APPLY.  Joining tasks,
        # contracts and statements into one rowset would multiply amounts.
        sql = """SELECT p.id AS project_id,p.name AS project_name,c.name AS city_name,
            ptype.name AS project_type_name,scope.team_count,
            ISNULL(task_stats.task_count,0) AS task_count,
            ISNULL(task_stats.done_count,0) AS done_count,
            ISNULL(contract_stats.contract_count,0) AS contract_count,
            ISNULL(statement_stats.statement_count,0) AS statement_count,
            ISNULL(statement_stats.sent_amount,0) AS sent_amount,
            ISNULL(statement_stats.approved_amount,0) AS approved_amount
            FROM Projects p JOIN Cities c ON c.id=p.city_id
            JOIN ProjectTypes ptype ON ptype.id=p.project_type_id
            CROSS APPLY(SELECT COUNT(DISTINCT ptm.team_id) AS team_count
              FROM ProjectTeams ptm WHERE ptm.project_id=p.id AND ptm.is_active=1
                AND ptm.team_id IN (%s)) scope
            OUTER APPLY(SELECT COUNT(*) AS task_count,
                SUM(CASE WHEN t.status='done' THEN 1 ELSE 0 END) AS done_count
              FROM Tasks t JOIN ProjectTeams ptm ON ptm.id=t.project_team_id
              WHERE t.project_id=p.id AND ptm.team_id IN (%s)) task_stats
            OUTER APPLY(SELECT COUNT(DISTINCT cpt.contract_id) AS contract_count
              FROM ContractProjectTeams cpt JOIN ProjectTeams ptm
                ON ptm.id=cpt.project_team_id
              JOIN Contracts co ON co.id=cpt.contract_id
              WHERE co.project_id=p.id AND cpt.is_active=1
                AND ptm.team_id IN (%s)) contract_stats
            OUTER APPLY(SELECT COUNT(DISTINCT s.id) AS statement_count,
                SUM(CASE WHEN s.business_status IN
                    ('sent','employer_approved','employer_rejected')
                  THEN COALESCE(s.requested_without_vat,s.requested_price,0)
                    *cst.allocation_percent/100
                  ELSE 0 END) AS sent_amount,
                SUM(CASE WHEN (s.business_status='employer_approved' OR (s.employer_decision_at IS NOT NULL AND ISNULL(s.business_status,'') NOT IN ('employer_rejected','revised','void') AND COALESCE(s.confirmed_without_vat,s.confirmed_price,0)>0))
                  THEN COALESCE(s.confirmed_without_vat,s.confirmed_price,
                    s.requested_without_vat,s.requested_price,0)
                    *cst.allocation_percent/100 ELSE 0 END) AS approved_amount
              FROM ContractStatementTeams cst
              JOIN ContractStatements s ON s.id=cst.statement_id
              JOIN ProjectTeams ptm ON ptm.id=cst.project_team_id
              JOIN Contracts co ON co.id=s.contract_id
              WHERE co.project_id=p.id AND cst.is_active=1
                AND s.is_active=1 AND s.is_current=1
                AND ptm.team_id IN (%s)) statement_stats
            WHERE scope.team_count>1
            ORDER BY scope.team_count DESC,c.name,p.name""" % (
                marks, marks, marks, marks
            )
        cur.execute(sql, *(tids + tids + tids + tids))
        return rows_to_list(cur)

    def data_quality_report(cur, tids, include_global=False):
        if not tids:
            return []
        marks = ",".join("?" for _ in tids)
        checks = []
        queries = []
        if include_global:
            queries.extend([
                ("project_without_team", "پروژه بدون تیم فعال",
                 """SELECT COUNT(*) FROM Projects p WHERE NOT EXISTS(
                    SELECT 1 FROM ProjectTeams ptm
                    WHERE ptm.project_id=p.id AND ptm.is_active=1)""", []),
                ("task_without_team", "تسک بدون جریان تیمی",
                 "SELECT COUNT(*) FROM Tasks WHERE project_team_id IS NULL", []),
                ("statement_without_team", "صورت‌وضعیت بدون جریان تیمی",
                 """SELECT COUNT(*) FROM ContractStatements s
                    WHERE s.is_active=1 AND s.is_current=1
                      AND NOT EXISTS(SELECT 1
                        FROM ContractStatementTeams cst
                        WHERE cst.statement_id=s.id AND cst.is_active=1)""", []),
                ("statement_allocation_invalid",
                 "جمع سهم تیم‌های صورت‌وضعیت نابرابر با ۱۰۰",
                 """SELECT COUNT(*) FROM (
                    SELECT s.id
                    FROM ContractStatements s
                    JOIN ContractStatementTeams cst
                      ON cst.statement_id=s.id AND cst.is_active=1
                    WHERE s.is_active=1 AND s.is_current=1
                    GROUP BY s.id
                    HAVING ABS(SUM(cst.allocation_percent)-100)>0.01
                  ) q""", []),
                ("active_user_without_team", "کاربر داخلی فعال بدون تیم",
                 """SELECT COUNT(*) FROM Users u WHERE u.is_active=1
                    AND u.role IN
                      ('manager','planner','finance','reporter','support','lead')
                    AND NOT EXISTS(SELECT 1 FROM TeamMembers tm
                      WHERE tm.user_id=u.id AND tm.is_active=1)""", []),
                ("shared_contract_without_team", "قرارداد پروژه‌دار بدون تیم",
                 """SELECT COUNT(*) FROM Contracts co WHERE co.is_active=1
                    AND co.project_id IS NOT NULL AND NOT EXISTS(
                      SELECT 1 FROM ContractProjectTeams x
                      WHERE x.contract_id=co.id AND x.is_active=1)""", []),
            ])
        else:
            queries.append((
                "statement_allocation_invalid",
                "جمع سهم تیم‌های صورت‌وضعیت نابرابر با ۱۰۰",
                """SELECT COUNT(*) FROM (
                    SELECT s.id
                    FROM ContractStatements s
                    JOIN ContractStatementTeams cst
                      ON cst.statement_id=s.id AND cst.is_active=1
                    WHERE s.is_active=1 AND s.is_current=1
                      AND EXISTS(SELECT 1
                        FROM ContractStatementTeams scoped_cst
                        JOIN ProjectTeams scoped_pt
                          ON scoped_pt.id=scoped_cst.project_team_id
                        WHERE scoped_cst.statement_id=s.id
                          AND scoped_cst.is_active=1
                          AND scoped_pt.team_id IN (%s))
                    GROUP BY s.id
                    HAVING ABS(SUM(cst.allocation_percent)-100)>0.01
                  ) q""" % marks,
                tids,
            ))
        queries.extend([
            ("task_project_mismatch", "تسک متصل به جریان پروژه دیگر",
             """SELECT COUNT(*) FROM Tasks t JOIN ProjectTeams ptm
                ON ptm.id=t.project_team_id
                WHERE ptm.team_id IN (%s)
                  AND t.project_id<>ptm.project_id""" % marks, tids),
            ("statement_project_mismatch",
             "صورت‌وضعیت متصل به جریان پروژه دیگر",
             """SELECT COUNT(DISTINCT s.id) FROM ContractStatements s
                JOIN ContractStatementTeams cst
                  ON cst.statement_id=s.id AND cst.is_active=1
                JOIN ProjectTeams ptm ON ptm.id=cst.project_team_id
                JOIN Contracts scope_contract
                  ON scope_contract.id=s.contract_id
                WHERE ptm.team_id IN (%s) AND s.is_active=1
                  AND ISNULL(scope_contract.project_id,-1)<>ptm.project_id""" % marks,
             tids),
            ("allocation_overrun", "جمع سهم تیم‌ها بیشتر از قرارداد",
             """SELECT COUNT(*) FROM (
                SELECT co.id,ISNULL(co.base_price,0)+ISNULL(SUM(CASE WHEN e.internal_status='approved'
                  AND e.extension_type_id IN (2,3) THEN ISNULL(e.price_delta,0) ELSE 0 END),0) AS price,
                  (SELECT ISNULL(SUM(x.allocation_amount),0) FROM ContractProjectTeams x
                    WHERE x.contract_id=co.id AND x.is_active=1) AS allocated
                FROM Contracts co LEFT JOIN ContractExtensions e ON e.contract_id=co.id AND e.is_active=1
                WHERE co.is_active=1 AND EXISTS(
                  SELECT 1 FROM ContractProjectTeams cpt
                  JOIN ProjectTeams ptm ON ptm.id=cpt.project_team_id
                  WHERE cpt.contract_id=co.id AND cpt.is_active=1
                    AND ptm.team_id IN (%s))
                GROUP BY co.id,co.base_price
              ) q WHERE q.allocated>q.price""" % marks, tids),
            ("shared_contract_allocation_missing",
             "قرارداد مشترک با سهم ریالی تعیین‌نشده",
             """SELECT COUNT(DISTINCT co.id)
                FROM Contracts co
                WHERE co.is_active=1
                  AND (SELECT COUNT(*) FROM ContractProjectTeams all_links
                    WHERE all_links.contract_id=co.id
                      AND all_links.is_active=1)>1
                  AND EXISTS(SELECT 1 FROM ContractProjectTeams missing_link
                    WHERE missing_link.contract_id=co.id
                      AND missing_link.is_active=1
                      AND missing_link.allocation_amount IS NULL)
                  AND EXISTS(SELECT 1 FROM ContractProjectTeams scoped_link
                    JOIN ProjectTeams scoped_pt
                      ON scoped_pt.id=scoped_link.project_team_id
                    WHERE scoped_link.contract_id=co.id
                      AND scoped_link.is_active=1
                      AND scoped_pt.team_id IN (%s))""" % marks, tids),
            ("multi_team_open_load", "همکار چندتیمی با بیش از یک کار درحال‌انجام",
             """SELECT COUNT(*) FROM (
                SELECT u.id FROM Users u JOIN TeamMembers tm ON tm.user_id=u.id AND tm.is_active=1
                JOIN ProjectTeams ptm ON ptm.team_id=tm.team_id AND ptm.is_active=1
                JOIN Tasks t ON t.project_team_id=ptm.id AND t.status='doing'
                  AND (t.staff_id=u.id OR EXISTS(SELECT 1 FROM TaskAssignees a
                    WHERE a.task_id=t.id AND a.user_id=u.id))
                WHERE tm.team_id IN (%s)
                GROUP BY u.id HAVING COUNT(DISTINCT tm.team_id)>1 AND COUNT(DISTINCT t.id)>1
              ) q""" % marks, tids),
        ])
        for code, title, sql, params in queries:
            cur.execute(sql, *params)
            count = int((cur.fetchone() or [0])[0] or 0)
            checks.append({
                "code": code, "title": title, "count": count,
                "severity": "critical" if code in (
                "allocation_overrun", "statement_without_team"
                , "statement_allocation_invalid"
                ) and count else ("warning" if count else "ok"),
            })
        return checks

    def groups_report(cur, user, tids, start, end):
        """What each group did (R16): output, open work, lateness, returns and
        time, per group, per person and per project, inside the team scope.
        A lead or support member sees only the group they belong to."""
        mine_only = not (has_company_scope(user) or user_has_permission(user, "teams.view"))
        allowed_teams = set(int(x) for x in (tids or []))
        groups = [x for x in load_groups(cur, user, only_mine=mine_only)
                  if int(x["team_id"]) in allowed_teams]
        today = _datetime.date.today()
        out_groups, flat = [], []
        for grp in groups:
            lead_id = _int(grp.get("lead_id"))
            people = list(dict.fromkeys(([lead_id] if lead_id else []) + grp["member_ids"]))
            names = {int(m["user_id"]): (m.get("display_name") or m.get("username") or "")
                     for m in grp["members"]}
            if lead_id:
                names[lead_id] = grp.get("lead_name") or grp.get("lead_username") or ""
            project_ids = set(grp["project_ids"])
            summary = {"group_id": grp["id"], "group_name": grp["name"],
                       "team_name": grp["team_name"], "lead_name": grp.get("lead_name") or "",
                       "member_count": len(people), "project_count": len(project_ids),
                       "done_count": 0, "active_count": 0, "overdue_count": 0,
                       "pending_count": 0, "returned_count": 0, "on_time_percent": None,
                       "in_scope_percent": None, "work_hours": 0.0,
                       "people": [], "projects": [], "recent": []}
            if people:
                marks = ",".join("?" for _ in people)
                done_sql, done_params = "", []
                if start:
                    done_sql += " AND CAST(t.completed_at AS DATE)>=?"
                    done_params.append(start)
                if end:
                    done_sql += " AND CAST(t.completed_at AS DATE)<=?"
                    done_params.append(end)
                cur.execute("""SELECT t.id,t.title,t.staff_id,t.project_id,p.name AS project_name,
                    t.completed_at,t.date_delivery FROM Tasks t
                    LEFT JOIN Projects p ON p.id=t.project_id
                    WHERE t.status='done' AND t.completed_at IS NOT NULL
                      AND t.staff_id IN (%s)%s
                    ORDER BY t.completed_at DESC""" % (marks, done_sql), people + done_params)
                done = rows_to_list(cur)
                cur.execute("""SELECT t.id,t.staff_id,t.project_id,p.name AS project_name,
                    t.status,t.date_delivery FROM Tasks t LEFT JOIN Projects p ON p.id=t.project_id
                    WHERE t.status NOT IN ('done','rejected') AND t.staff_id IN (%s)""" % marks, people)
                active = rows_to_list(cur)
                time_sql, time_params = "", []
                if start:
                    time_sql += " AND CAST(l.started_at AS DATE)>=?"
                    time_params.append(start)
                if end:
                    time_sql += " AND CAST(l.started_at AS DATE)<=?"
                    time_params.append(end)
                cur.execute("""SELECT l.user_id,SUM(ISNULL(l.seconds,0)) AS seconds FROM TaskTimeLog l
                    WHERE l.ended_at IS NOT NULL AND l.user_id IN (%s)%s
                    GROUP BY l.user_id""" % (marks, time_sql), people + time_params)
                seconds = {int(r["user_id"]): int(r["seconds"] or 0) for r in rows_to_list(cur)}
                returned = {}
                try:
                    ev_sql, ev_params = "", []
                    if start:
                        ev_sql += " AND CAST(e.created_at AS DATE)>=?"
                        ev_params.append(start)
                    if end:
                        ev_sql += " AND CAST(e.created_at AS DATE)<=?"
                        ev_params.append(end)
                    cur.execute("""SELECT t.staff_id,COUNT(*) AS n FROM TaskEvents e
                        JOIN Tasks t ON t.id=e.task_id
                        WHERE e.action='send_back' AND t.staff_id IN (%s)%s
                        GROUP BY t.staff_id""" % (marks, ev_sql), people + ev_params)
                    returned = {int(r["staff_id"]): int(r["n"] or 0) for r in rows_to_list(cur)}
                except Exception:
                    returned = {}
                per_person = {uid: {"done": 0, "active": 0, "overdue": 0, "with_due": 0, "on_time": 0}
                              for uid in people}
                per_project = {}

                def project_entry(task):
                    key = _int(task.get("project_id")) or 0
                    return per_project.setdefault(key, {
                        "project_id": key, "project_name": task.get("project_name") or "بدون پروژه",
                        "done": 0, "active": 0,
                        "in_scope": (key in project_ids) if project_ids else True})
                for task in done:
                    due = _gd.parse_jalali(task.get("date_delivery"))
                    finished = _gd.as_date(task.get("completed_at"))
                    person = per_person.get(_int(task.get("staff_id")))
                    if person is not None:
                        person["done"] += 1
                        if due:
                            person["with_due"] += 1
                            if finished and finished <= due:
                                person["on_time"] += 1
                    project_entry(task)["done"] += 1
                for task in active:
                    due = _gd.parse_jalali(task.get("date_delivery"))
                    late = bool(due and due < today)
                    person = per_person.get(_int(task.get("staff_id")))
                    if person is not None:
                        person["active"] += 1
                        if late:
                            person["overdue"] += 1
                    project_entry(task)["active"] += 1
                    if late:
                        summary["overdue_count"] += 1
                    if task.get("status") == "pending_approval":
                        summary["pending_count"] += 1
                summary["done_count"] = len(done)
                summary["active_count"] = len(active)
                with_due = sum(p["with_due"] for p in per_person.values())
                on_time = sum(p["on_time"] for p in per_person.values())
                summary["on_time_percent"] = round(on_time * 100.0 / with_due) if with_due else None
                if project_ids and done:
                    inside = sum(1 for t in done if _int(t.get("project_id")) in project_ids)
                    summary["in_scope_percent"] = round(inside * 100.0 / len(done))
                summary["returned_count"] = sum(returned.values())
                summary["work_hours"] = round(sum(seconds.values()) / 3600.0, 1)
                for uid in people:
                    stats = per_person[uid]
                    row = {"group_name": grp["name"], "team_name": grp["team_name"],
                           "lead_name": summary["lead_name"], "display_name": names.get(uid, ""),
                           "member_role": "سرگروه" if uid == lead_id else "عضو",
                           "done_count": stats["done"], "active_count": stats["active"],
                           "overdue_count": stats["overdue"], "returned_count": returned.get(uid, 0),
                           "on_time_percent": (round(stats["on_time"] * 100.0 / stats["with_due"])
                                               if stats["with_due"] else None),
                           "work_hours": round(seconds.get(uid, 0) / 3600.0, 1)}
                    summary["people"].append(row)
                    flat.append(row)
                summary["projects"] = sorted(per_project.values(), key=lambda r: (-r["done"], -r["active"]))
                summary["recent"] = [{"title": t.get("title") or "",
                                      "staff_name": names.get(_int(t.get("staff_id")), ""),
                                      "project_name": t.get("project_name") or "",
                                      "completed": _gd.jalali_text(t["completed_at"])}
                                     for t in done[:12]]
            out_groups.append(summary)
        return {"groups": out_groups, "rows": flat}

    @app.route("/api/v8/reports", methods=["POST"])
    @require_auth
    def api_v8_reports():
        try:
            if not user_has_permission(g.user, "reports.view"):
                return err("اجازه مشاهده گزارش‌های تیمی را ندارید", 403)
            data = request.get_json() or {}
            kind = data.get("kind") or "dashboard"
            start, end = parse_range(data)
            with db_lock:
                c = get_conn(); cur = c.cursor()
                tids = scoped_team_ids(cur, g.user, data)
                if kind == "dashboard":
                    if not user_has_permission(g.user, "reports.team_dashboard"):
                        return err("گزارش داشبورد تیم‌ها برای این نقش در دسترس نیست", 403)
                    result = dashboard_report(cur, tids, start, end)
                    result["financial_visible"] = user_has_permission(g.user, "reports.financial")
                    if not result["financial_visible"]:
                        result["totals"].pop("sent_amount", None)
                        result["totals"].pop("approved_amount", None)
                        for team_row in result["teams"]:
                            team_row.pop("sent_amount", None)
                            team_row.pop("approved_amount", None)
                elif kind == "contribution":
                    if not user_has_permission(g.user, "reports.contribution"):
                        return err("گزارش سهم زمان و خروجی برای این نقش در دسترس نیست", 403)
                    result = contribution_report(cur, tids, start, end)
                    # scoped_team_ids is the authoritative R10 boundary;
                    # teammates remain visible inside the selected/authorized teams.
                elif kind == "capacity":
                    if not user_has_permission(g.user, "reports.capacity"):
                        return err("گزارش ظرفیت برای این نقش در دسترس نیست", 403)
                    result = {"rows": capacity_report(cur, tids, start, end)}
                elif kind == "shared_projects":
                    if not user_has_permission(g.user, "reports.shared_projects"):
                        return err("گزارش مالی پروژه‌های مشترک برای این نقش در دسترس نیست", 403)
                    result = {"rows": shared_projects_report(cur, tids)}
                elif kind == "data_quality":
                    if not user_has_permission(g.user, "reports.data_quality"):
                        return err("گزارش کیفیت داده برای این نقش در دسترس نیست", 403)
                    result = {"rows": data_quality_report(
                        cur, tids,
                        include_global=has_company_scope(g.user),
                    )}
                elif kind == "groups":
                    if not user_has_permission(g.user, "reports.groups"):
                        return err("گزارش گروه‌ها برای این نقش در دسترس نیست", 403)
                    result = groups_report(cur, g.user, tids, start, end)
                else:
                    return err("نوع گزارش نامعتبر است")
            return ok(kind=kind, from_date=start, to_date=end, **result)
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc))

    def _report_pdf(raw, kind, start_date, end_date):
        """Build a scoped Persian PDF from the same rows used by Excel."""
        import arabic_reshaper
        from bidi.algorithm import get_display
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

        def fa(value):
            text = str(value if value is not None else "")
            return get_display(arabic_reshaper.reshape(text))

        titles = {
            "dashboard": "داشبورد تیم‌ها",
            "contribution": "سهم زمان و خروجی افراد",
            "capacity": "ظرفیت چندتیمی",
            "shared_projects": "پروژه‌های مشترک",
            "data_quality": "کیفیت داده",
            "groups": "گروه‌ها",
        }
        labels = {
            "team_name": "تیم", "group_name": "گروه", "lead_name": "سرگروه",
            "display_name": "همکار", "member_role": "جایگاه", "username": "نام کاربری",
            "project_name": "پروژه", "city_name": "شهر", "role": "نقش",
            "task_count": "تعداد تسک", "done_count": "تسک تکمیل‌شده",
            "completed_task_count": "تسک تکمیل‌شده", "active_task_count": "تسک فعال",
            "work_seconds": "زمان واقعی", "seconds": "زمان واقعی",
            "time_share_percent": "سهم زمانی (%)", "output_share_percent": "سهم خروجی (%)",
            "sent_amount": "مبلغ ارسال‌شده", "approved_amount": "درآمد تاییدشده",
            "allocated_amount": "مبلغ تخصیص", "remaining_amount": "مانده",
            "project_count": "تعداد پروژه", "member_count": "تعداد عضو",
            "capacity_percent": "ظرفیت (%)", "code": "کد کنترل", "title": "عنوان",
            "count": "تعداد", "severity": "شدت", "team_count": "تعداد تیم",
            "financial_share_amount": "سهم مالی", "share_percent": "سهم (%)",
            "active_count": "تسک باز", "overdue_count": "معوق", "returned_count": "برگشتی",
            "on_time_percent": "سروقت (%)", "work_hours": "ساعت کار",
        }
        columns = list(raw[0].keys()) if raw else ["result"]
        # Keep PDFs readable even when internal report rows contain many fields.
        preferred = [key for key in labels if key in columns]
        columns = preferred[:10] or columns[:10]
        font_name = fa_font.register()
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4), rightMargin=16,
                                leftMargin=16, topMargin=16, bottomMargin=16)
        title_style = ParagraphStyle("report-title", fontName=font_name, fontSize=12,
                                     leading=18, alignment=2)
        range_text = "%s تا %s" % (start_date or "ابتدا", end_date or "امروز")
        story = [Paragraph(fa("گزارش %s" % titles.get(kind, kind)), title_style),
                 Paragraph(fa("بازه: %s" % range_text), title_style), Spacer(1, 8)]
        table_rows = [[fa(labels.get(col, col)) for col in columns]]
        for row in raw:
            table_rows.append([fa(_jsonable(row.get(col))) for col in columns])
        if len(table_rows) == 1:
            table_rows.append([fa("داده‌ای وجود ندارد")] + [""] * (len(columns)-1))
        table = Table(table_rows, repeatRows=1)
        table.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), font_name, 7),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#263C78")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), .25, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(table)
        doc.build(story)
        buf.seek(0)
        return buf

    @app.route("/api/v8/report_export", methods=["POST"])
    @require_auth
    def api_v8_report_export():
        """PDF/Excel export using exactly the same scoped rows as the UI."""
        try:
            if not user_has_permission(g.user, "reports.export"):
                return err("اجازه خروجی گزارش را ندارید", 403)
            data = request.get_json() or {}
            kind = data.get("kind") or "dashboard"
            fmt = (data.get("format") or "xlsx").lower()
            if fmt not in ("xlsx", "pdf"):
                return err("فرمت خروجی نامعتبر است")
            start, end = parse_range(data)
            with db_lock:
                c = get_conn(); cur = c.cursor(); tids = scoped_team_ids(cur, g.user, data)
                if kind == "dashboard":
                    raw = dashboard_report(cur, tids, start, end)["teams"]
                    if not user_has_permission(g.user, "reports.financial"):
                        for row in raw:
                            row.pop("sent_amount", None)
                            row.pop("approved_amount", None)
                elif kind == "contribution":
                    raw = contribution_report(cur, tids, start, end)["people"]
                    # Export uses the same authorized team rows as the UI.
                elif kind == "capacity":
                    if not user_has_permission(g.user, "reports.capacity"):
                        return err("گزارش ظرفیت برای این نقش در دسترس نیست", 403)
                    raw = capacity_report(cur, tids, start, end)
                elif kind == "shared_projects":
                    if not user_has_permission(g.user, "reports.shared_projects"):
                        return err("گزارش مالی پروژه‌های مشترک برای این نقش در دسترس نیست", 403)
                    raw = shared_projects_report(cur, tids)
                elif kind == "data_quality":
                    if not user_has_permission(g.user, "reports.data_quality"):
                        return err("گزارش کیفیت داده برای این نقش در دسترس نیست", 403)
                    raw = data_quality_report(
                        cur, tids,
                        include_global=has_company_scope(g.user),
                    )
                elif kind == "groups":
                    if not user_has_permission(g.user, "reports.groups"):
                        return err("گزارش گروه‌ها برای این نقش در دسترس نیست", 403)
                    raw = groups_report(cur, g.user, tids, start, end)["rows"]
                else:
                    return err("نوع گزارش نامعتبر است")
            if fmt == "pdf":
                buf = _report_pdf(raw, kind, start, end)
                return send_file(buf, as_attachment=True,
                                 download_name="TaskHub_v8_%s.pdf" % kind,
                                 mimetype="application/pdf")
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font, PatternFill
            wb = Workbook(); ws = wb.active; ws.title = "گزارش تیمی"
            ws.sheet_view.rightToLeft = True
            columns = list(raw[0].keys()) if raw else ["نتیجه"]
            for idx, col in enumerate(columns, 1):
                cell = ws.cell(1, idx, col)
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="263C78")
                cell.alignment = Alignment(horizontal="center")
            for r_idx, row in enumerate(raw, 2):
                for c_idx, col in enumerate(columns, 1):
                    value = _jsonable(row.get(col))
                    if isinstance(value, (dict, list)):
                        value = json.dumps(value, ensure_ascii=False)
                    ws.cell(r_idx, c_idx, value)
            ws.freeze_panes = "A2"
            for col_cells in ws.columns:
                letter = col_cells[0].column_letter
                width = max((len(str(c.value or "")) for c in col_cells), default=10)
                ws.column_dimensions[letter].width = min(45, max(12, width + 2))
            buf = io.BytesIO(); wb.save(buf); buf.seek(0)
            return send_file(buf, as_attachment=True,
                             download_name="TaskHub_v8_%s.xlsx" % kind,
                             mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/chat/config", methods=["POST"])
    @require_auth
    def api_v8_chat_config():
        try:
            ensure_internal_chat_user(g.user)
            return ok(mode=CHAT_MODE, secure_transport=bool(request.is_secure),
                      server_managed=server_chat_mode)
        except PermissionError as exc:
            return err(str(exc), 403)

    # ── Organizational chat ─────────────────────────────────────────────
    # The server only stores public keys, wrapped conversation keys and
    # ciphertext.  It intentionally has no decrypt endpoint and no content
    # search endpoint.  Operational admins can manage membership/ciphertext
    # lifecycle, not read message bodies.

    @app.route("/api/v8/chat/device", methods=["POST"])
    @require_auth
    def api_v8_chat_device():
        """Register a browser public key without ever receiving its private key.

        The first device is approved automatically. Every later device remains
        pending until an already-approved browser proves possession of its
        local private key and confirms the six-digit code shown on the new
        device. This prevents ordinary application/API access from approving a device
        without an existing private key. A malicious server operator remains
        outside the threat model of a browser-delivered client.
        """
        try:
            ensure_internal_chat_user(g.user)
            data = request.get_json() or {}
            device_uuid = (data.get("device_uuid") or "").strip()
            label = (data.get("label") or "").strip() or None
            known_code = (data.get("approval_code") or "").strip()
            public_text = data.get("public_key_jwk")
            if not device_uuid or len(device_uuid) > 100 or not public_text:
                return err("شناسه دستگاه و کلید عمومی الزامی است")
            if isinstance(public_text, dict):
                public_obj = public_text
            else:
                public_obj = json.loads(public_text)
            public_text = json.dumps(public_obj, separators=(",", ":"), sort_keys=True)
            if public_obj.get("kty") != "RSA" or not public_obj.get("n") or not public_obj.get("e"):
                return err("کلید عمومی RSA معتبر نیست")
            if any(x in public_obj for x in ("d", "p", "q", "dp", "dq", "qi")):
                return err("ارسال کلید خصوصی به سرور ممنوع است")

            with db_lock:
                c = get_conn(); cur = c.cursor()
                existing = one(cur, """SELECT id,public_key_jwk,is_active,
                    approval_code_hash,approval_expires_at FROM ChatDevices
                    WHERE user_id=? AND device_uuid=?""", g.user["id"], device_uuid)
                active_count_row = one(cur, """SELECT COUNT(*) AS cnt FROM ChatDevices
                    WHERE user_id=? AND is_active=1""", g.user["id"])
                active_count = int((active_count_row or {}).get("cnt") or 0)
                is_new = existing is None
                key_changed = False
                approval_code = None
                now = _dt.datetime.now()

                if existing:
                    did = int(existing["id"])
                    try:
                        old_obj = json.loads(existing.get("public_key_jwk") or "{}")
                        old_text = json.dumps(old_obj, separators=(",", ":"), sort_keys=True)
                    except Exception:
                        old_text = existing.get("public_key_jwk") or ""
                    key_changed = old_text != public_text
                    was_active = bool(existing.get("is_active"))
                    # Never replace an approved browser key silently. If the
                    # browser lost its private material, it must register as a
                    # distinct pending device and be approved by an existing
                    # private key. The device UUID is not treated as a secret.
                    if was_active and key_changed:
                        return err(
                            "کلید محلی این دستگاه تغییر کرده است؛ دستگاه به‌صورت جدید ثبت می‌شود و باید از یک دستگاه قبلی تأیید شود.",
                            409,
                            reset_device_uuid=True,
                        )
                    approve_now = was_active and not key_changed
                    pending = not approve_now
                    if pending:
                        valid_known = False
                        if known_code and existing.get("approval_code_hash"):
                            valid_known = secrets.compare_digest(
                                hashlib.sha256(known_code.encode("utf-8")).hexdigest(),
                                str(existing.get("approval_code_hash") or ""),
                            )
                            expiry = existing.get("approval_expires_at")
                            if isinstance(expiry, str):
                                try:
                                    expiry = _dt.datetime.fromisoformat(expiry)
                                except ValueError:
                                    expiry = None
                            valid_known = valid_known and (not expiry or expiry > now)
                        approval_code = known_code if valid_known else "%06d" % secrets.randbelow(1000000)
                        code_hash = hashlib.sha256(approval_code.encode("utf-8")).hexdigest()
                        cur.execute("""UPDATE ChatDevices SET label=?,public_key_jwk=?,
                            key_algorithm='RSA-OAEP-256',is_active=0,revoked_at=NULL,
                            approval_code_hash=?,approval_expires_at=DATEADD(minute,15,GETDATE()),
                            approval_challenge_hash=NULL,approval_challenge_expires_at=NULL,
                            last_seen=GETDATE() WHERE id=?""",
                                    label, public_text, code_hash, did)
                    else:
                        cur.execute("""UPDATE ChatDevices SET label=?,public_key_jwk=?,
                            key_algorithm='RSA-OAEP-256',is_active=1,revoked_at=NULL,
                            approval_code_hash=NULL,approval_expires_at=NULL,
                            last_seen=GETDATE(),approved_at=ISNULL(approved_at,GETDATE())
                            WHERE id=?""", label, public_text, did)
                else:
                    pending = active_count > 0
                    if pending:
                        approval_code = "%06d" % secrets.randbelow(1000000)
                        code_hash = hashlib.sha256(approval_code.encode("utf-8")).hexdigest()
                        cur.execute("""INSERT INTO ChatDevices(user_id,device_uuid,label,
                            public_key_jwk,is_active,last_seen,approval_code_hash,
                            approval_expires_at) OUTPUT INSERTED.id
                            VALUES(?,?,?,?,0,GETDATE(),?,DATEADD(minute,15,GETDATE()))""",
                                    g.user["id"], device_uuid, label, public_text, code_hash)
                    else:
                        cur.execute("""INSERT INTO ChatDevices(user_id,device_uuid,label,
                            public_key_jwk,is_active,last_seen,approved_at)
                            OUTPUT INSERTED.id VALUES(?,?,?,?,1,GETDATE(),GETDATE())""",
                                    g.user["id"], device_uuid, label, public_text)
                    did = cur.fetchone()[0]

                affected = 0
                # Only an approved new/re-keyed device participates in future
                # conversation keys. Pending devices receive no envelopes.
                if not pending and (is_new or key_changed):
                    cur.execute("""UPDATE c SET needs_key_rotation=1,
                        key_version=key_version+1,rotation_owner_device_id=NULL,
                        rotation_claim_hash=NULL,rotation_claimed_at=NULL,updated_at=GETDATE()
                        FROM ChatConversations c JOIN ChatMembers m
                          ON m.conversation_id=c.id
                        WHERE m.user_id=? AND m.is_active=1 AND c.is_active=1""",
                                g.user["id"])
                    affected = int(cur.rowcount or 0)
                c.commit()
            return ok(device_id=did, pending=pending, approval_code=approval_code,
                      is_new_device=is_new, key_changed=key_changed,
                      affected_conversations=affected)
        except PermissionError as exc:
            return err(str(exc), 403)
        except (ValueError, TypeError, json.JSONDecodeError):
            return err("کلید عمومی دستگاه معتبر نیست")
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/chat/device_revoke", methods=["POST"])
    @require_auth
    def api_v8_chat_device_revoke():
        try:
            did = _int((request.get_json() or {}).get("device_id"))
            with db_lock:
                c = get_conn(); cur = c.cursor()
                row = one(cur, "SELECT id FROM ChatDevices WHERE id=? AND user_id=? AND is_active=1",
                          did, g.user["id"])
                if not row:
                    return err("دستگاه یافت نشد")
                cur.execute("""UPDATE ChatDevices SET is_active=0,revoked_at=GETDATE()
                    WHERE id=?""", did)
                # Every affected conversation now needs a fresh key that is
                # not wrapped for the revoked device.
                cur.execute("""UPDATE c SET needs_key_rotation=1,
                    key_version=key_version+1,rotation_owner_device_id=NULL,
                    rotation_claim_hash=NULL,rotation_claimed_at=NULL,updated_at=GETDATE()
                    FROM ChatConversations c JOIN ChatMembers m
                      ON m.conversation_id=c.id AND m.user_id=? AND m.is_active=1
                    WHERE c.is_active=1""", g.user["id"])
                c.commit()
            return ok()
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/chat/devices", methods=["POST"])
    @require_auth
    def api_v8_chat_devices():
        try:
            data = request.get_json() or {}
            current_id = _int(data.get("current_device_id"))
            with db_lock:
                c = get_conn(); cur = c.cursor()
                current = one(cur, """SELECT id FROM ChatDevices
                    WHERE id=? AND user_id=? AND is_active=1""",
                              current_id, g.user["id"])
                if not current:
                    return err("این دستگاه هنوز تأیید نشده است", 403)
                cur.execute("""SELECT id,label,is_active,created_at,last_seen,
                    approval_expires_at FROM ChatDevices
                    WHERE user_id=? AND revoked_at IS NULL
                    ORDER BY is_active ASC,created_at DESC""", g.user["id"])
                rows = rows_to_list(cur)
            return ok(rows=rows,
                      pending_count=sum(1 for x in rows if not bool(x.get("is_active"))))
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc), rows=[])

    @app.route("/api/v8/chat/device_approval_challenge", methods=["POST"])
    @require_auth
    def api_v8_chat_device_approval_challenge():
        try:
            data = request.get_json() or {}
            current_id = _int(data.get("current_device_id"))
            pending_id = _int(data.get("pending_device_id"))
            code = (data.get("approval_code") or "").strip()
            if len(code) != 6 or not code.isdigit():
                return err("کد شش‌رقمی دستگاه جدید را وارد کنید")
            code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
            with db_lock:
                c = get_conn(); cur = c.cursor()
                current = one(cur, """SELECT id,public_key_jwk FROM ChatDevices
                    WHERE id=? AND user_id=? AND is_active=1""",
                              current_id, g.user["id"])
                if not current:
                    return err("دستگاه تأییدکننده معتبر نیست", 403)
                pending = one(cur, """SELECT id FROM ChatDevices
                    WHERE id=? AND user_id=? AND is_active=0 AND revoked_at IS NULL
                      AND approval_code_hash=? AND approval_expires_at>GETDATE()""",
                              pending_id, g.user["id"], code_hash)
                if not pending:
                    return err("کد دستگاه نادرست یا منقضی شده است")
                challenge = secrets.token_bytes(32)
                challenge_hash = hashlib.sha256(challenge).hexdigest()
                encrypted = _rsa_oaep_encrypt(current["public_key_jwk"], challenge)
                cur.execute("""UPDATE ChatDevices SET approval_challenge_hash=?,
                    approval_challenge_expires_at=DATEADD(minute,2,GETDATE())
                    WHERE id=?""", challenge_hash, pending_id)
                c.commit()
            return ok(encrypted_challenge=encrypted, pending_device_id=pending_id)
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/chat/device_approve", methods=["POST"])
    @require_auth
    def api_v8_chat_device_approve():
        try:
            data = request.get_json() or {}
            current_id = _int(data.get("current_device_id"))
            pending_id = _int(data.get("pending_device_id"))
            challenge_text = (data.get("challenge") or "").strip()
            try:
                challenge = base64.b64decode(challenge_text, validate=True)
            except Exception:
                return err("پاسخ تأیید دستگاه معتبر نیست")
            challenge_hash = hashlib.sha256(challenge).hexdigest()
            with db_lock:
                c = get_conn(); cur = c.cursor()
                current = one(cur, """SELECT id FROM ChatDevices
                    WHERE id=? AND user_id=? AND is_active=1""",
                              current_id, g.user["id"])
                if not current:
                    return err("دستگاه تأییدکننده معتبر نیست", 403)
                pending = one(cur, """SELECT id FROM ChatDevices
                    WHERE id=? AND user_id=? AND is_active=0 AND revoked_at IS NULL
                      AND approval_challenge_hash=?
                      AND approval_challenge_expires_at>GETDATE()""",
                              pending_id, g.user["id"], challenge_hash)
                if not pending:
                    return err("درخواست تأیید دستگاه منقضی یا نامعتبر است")
                cur.execute("""UPDATE ChatDevices SET is_active=1,approved_at=GETDATE(),
                    approval_code_hash=NULL,approval_expires_at=NULL,
                    approval_challenge_hash=NULL,approval_challenge_expires_at=NULL,
                    last_seen=GETDATE() WHERE id=?""", pending_id)
                cur.execute("""UPDATE c SET needs_key_rotation=1,
                    key_version=key_version+1,rotation_owner_device_id=NULL,
                    rotation_claim_hash=NULL,rotation_claimed_at=NULL,updated_at=GETDATE()
                    FROM ChatConversations c JOIN ChatMembers m
                      ON m.conversation_id=c.id
                    WHERE m.user_id=? AND m.is_active=1 AND c.is_active=1""",
                            g.user["id"])
                affected = int(cur.rowcount or 0)
                c.commit()
            return ok(affected_conversations=affected)
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/chat/users", methods=["POST"])
    @require_auth
    def api_v8_chat_users():
        try:
            ensure_internal_chat_user(g.user)
            with db_lock:
                c = get_conn(); cur = c.cursor()
                head = """SELECT DISTINCT u.id,u.username,u.display_name,u.role,
                    STUFF((SELECT N'، '+t.name FROM TeamMembers tm JOIN Teams t
                      ON t.id=tm.team_id WHERE tm.user_id=u.id AND tm.is_active=1
                      AND t.is_active=1 ORDER BY t.name FOR XML PATH(''),TYPE
                    ).value('.','NVARCHAR(MAX)'),1,2,N'') AS team_names,
                    (SELECT COUNT(*) FROM ChatDevices d WHERE d.user_id=u.id
                      AND d.is_active=1) AS device_count
                    FROM Users u WHERE u.is_active=1
                      AND (u.role=N'admin' OR EXISTS(SELECT 1 FROM RolePermissions rp WHERE rp.role=u.role AND rp.permission_key=N'chat.use' AND rp.is_allowed=1))"""
                if g.user.get("role") in CHAT_CLIENT_ROLES:
                    # R14: a client reaches the other client accounts of its
                    # own project and the planners of the teams running it.
                    allowed = sorted(client_contact_ids(cur, g.user["id"]) | {int(g.user["id"])})
                    cur.execute(head + " AND u.id IN (" + ",".join("?" for _ in allowed) +
                                ") ORDER BY u.display_name,u.username", allowed)
                else:
                    cur.execute(head + """
                      AND (?=1 OR u.id=? OR EXISTS(
                        SELECT 1 FROM TeamMembers target JOIN TeamMembers mine
                          ON mine.team_id=target.team_id AND mine.is_active=1
                        WHERE target.user_id=u.id AND target.is_active=1
                          AND mine.user_id=?)
                      OR EXISTS(
                        -- The team that runs my project, for an employer who
                        -- belongs to no team of their own.
                        SELECT 1 FROM Users me
                        JOIN ProjectTeams mine_pt ON mine_pt.project_id=me.project_id
                          AND mine_pt.is_active=1
                        JOIN TeamMembers target ON target.team_id=mine_pt.team_id
                          AND target.is_active=1
                        WHERE me.id=? AND target.user_id=u.id)
                      OR EXISTS(
                        -- Whoever is actually working on a task I raised, and
                        -- whoever raised a task I am working on.
                        SELECT 1 FROM Tasks t
                        WHERE (t.contact_id=? AND (t.staff_id=u.id
                                OR EXISTS(SELECT 1 FROM TaskAssignees ta
                                  WHERE ta.task_id=t.id AND ta.user_id=u.id)))
                           OR ((t.staff_id=? OR EXISTS(SELECT 1 FROM TaskAssignees ta2
                                  WHERE ta2.task_id=t.id AND ta2.user_id=?))
                               AND (t.contact_id=u.id OR t.staff_id=u.id))))
                      -- R14: staff see a client account only when they plan
                      -- one of that client's projects.
                      AND (u.role NOT IN (N'employer',N'supervisor') OR EXISTS(
                        SELECT 1 FROM TeamMembers vtm
                        JOIN Users vu ON vu.id=vtm.user_id
                        JOIN ProjectTeams vpt ON vpt.team_id=vtm.team_id AND vpt.is_active=1
                        WHERE vtm.user_id=? AND vtm.is_active=1
                          AND (vtm.team_role='planner' OR vu.role='planner')
                          AND (vpt.project_id=u.project_id OR (u.project_id IS NULL AND EXISTS(
                            SELECT 1 FROM TeamMembers xtm JOIN ProjectTeams xpt
                              ON xpt.team_id=xtm.team_id AND xpt.is_active=1
                            WHERE xtm.user_id=u.id AND xtm.is_active=1
                              AND xpt.project_id=vpt.project_id)))))
                    ORDER BY u.display_name,u.username""",
                            1 if has_company_scope(g.user) else 0,
                            g.user["id"], g.user["id"], g.user["id"],
                            g.user["id"], g.user["id"], g.user["id"], g.user["id"])
                rows = rows_to_list(cur)
                if server_chat_mode:
                    for row in rows:
                        row["device_count"] = 1
            return ok(rows=rows, chat_mode=CHAT_MODE)
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc), rows=[])

    @app.route("/api/v8/chat/conversations", methods=["POST"])
    @require_auth
    def api_v8_chat_conversations():
        try:
            ensure_internal_chat_user(g.user)
            data = request.get_json() or {}
            device_id = _int(data.get("device_id"))
            with db_lock:
                c = get_conn(); cur = c.cursor()
                if server_chat_mode:
                    device_id = ensure_server_chat_device(c, cur, g.user["id"])
                else:
                    active_device = one(cur, """SELECT id FROM ChatDevices
                        WHERE id=? AND user_id=? AND is_active=1""",
                                        device_id, g.user["id"])
                    if not active_device:
                        return err("این دستگاه هنوز برای پیامرسان تأیید نشده است", 403)
                cur.execute("""SELECT c.id,c.kind,c.title,c.team_id,c.created_by,c.key_version,
                    c.needs_key_rotation,m.member_role,m.can_post,
                    (SELECT COUNT(*) FROM ChatMembers x WHERE x.conversation_id=c.id
                      AND x.is_active=1) AS member_count,
                    (SELECT MAX(x.created_at) FROM ChatMessages x
                      WHERE x.conversation_id=c.id AND x.is_deleted=0) AS last_message_at,
                    (SELECT COUNT(*) FROM ChatMessages x
                      WHERE x.conversation_id=c.id AND x.is_deleted=0
                        AND x.sender_user_id<>m.user_id
                        AND x.id>ISNULL(r.last_message_id,0)) AS unread_count
                    FROM ChatConversations c JOIN ChatMembers m ON m.conversation_id=c.id
                      AND m.user_id=? AND m.is_active=1
                    LEFT JOIN ChatReadReceipts r ON r.conversation_id=c.id
                      AND r.user_id=m.user_id
                    WHERE c.is_active=1
                    ORDER BY CASE WHEN c.kind='announcement' THEN 0 ELSE 1 END,
                      last_message_at DESC,c.id DESC""", g.user["id"])
                rows = rows_to_list(cur)
                cur.execute("""SELECT cm.conversation_id,cm.user_id,cm.member_role,
                    cm.can_post,u.display_name,u.username,
                    (SELECT COUNT(*) FROM ChatDevices d WHERE d.user_id=cm.user_id
                      AND d.is_active=1) AS device_count
                    FROM ChatMembers cm JOIN Users u ON u.id=cm.user_id
                    WHERE cm.is_active=1 AND EXISTS(SELECT 1 FROM ChatMembers mine
                      WHERE mine.conversation_id=cm.conversation_id
                        AND mine.user_id=? AND mine.is_active=1)
                    ORDER BY cm.conversation_id,u.display_name""", g.user["id"])
                members = rows_to_list(cur)
                cur.execute("""SELECT d.id,d.device_uuid,d.label,d.public_key_jwk,
                    d.key_algorithm,d.last_seen
                    FROM ChatDevices d WHERE d.user_id=? AND d.is_active=1
                    ORDER BY d.last_seen DESC,d.id DESC""", g.user["id"])
                devices = rows_to_list(cur)
            by_conv = {}
            if server_chat_mode:
                for row in members:
                    row["device_count"] = 1
                for row in rows:
                    row["needs_key_rotation"] = False
            for row in members:
                by_conv.setdefault(int(row["conversation_id"]), []).append(row)
            for row in rows:
                row["members"] = by_conv.get(int(row["id"]), [])
            return ok(rows=rows, my_devices=devices, chat_mode=CHAT_MODE,
                      server_device_id=device_id if server_chat_mode else None)
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc), rows=[])

    @app.route("/api/v8/chat/conversation_create", methods=["POST"])
    @require_auth
    def api_v8_chat_conversation_create():
        try:
            ensure_internal_chat_user(g.user)
            data = request.get_json() or {}
            kind = data.get("kind") or "group"
            if kind not in ("direct", "group"):
                return err("این نوع گفتگو از این مسیر قابل ساخت نیست")
            member_ids = {_int(x) for x in (data.get("member_ids") or [])}
            member_ids.discard(None); member_ids.add(int(g.user["id"]))
            if kind == "direct" and len(member_ids) != 2:
                return err("گفتگوی خصوصی باید دقیقاً دو عضو داشته باشد")
            if kind == "group" and len(member_ids) < 2:
                return err("گروه باید حداقل دو عضو داشته باشد")
            title = (data.get("title") or "").strip()
            if kind == "group" and not title:
                return err("نام گروه الزامی است")
            with db_lock:
                c = get_conn(); cur = c.cursor()
                marks = ",".join("?" for _ in member_ids)
                cur.execute("""SELECT id FROM Users WHERE id IN (%s) AND is_active=1
                    AND (role=N'admin' OR EXISTS(SELECT 1 FROM RolePermissions rp WHERE rp.role=Users.role AND rp.permission_key=N'chat.use' AND rp.is_allowed=1))""" % marks,
                            list(member_ids))
                valid_ids = {int(x[0]) for x in cur.fetchall()}
                if valid_ids != member_ids:
                    return err("یکی از اعضای انتخاب‌شده مجاز یا فعال نیست")
                problem = chat_members_error(cur, member_ids)
                if problem:
                    return err(problem, 403)
                if kind == "direct":
                    # Reuse an existing exact two-person direct conversation.
                    other_id = next(x for x in member_ids if x != int(g.user["id"]))
                    existing = one(cur, """SELECT TOP 1 c.id FROM ChatConversations c
                        JOIN ChatMembers a ON a.conversation_id=c.id AND a.user_id=? AND a.is_active=1
                        JOIN ChatMembers b ON b.conversation_id=c.id AND b.user_id=? AND b.is_active=1
                        WHERE c.kind='direct' AND c.is_active=1
                          AND (SELECT COUNT(*) FROM ChatMembers x
                            WHERE x.conversation_id=c.id AND x.is_active=1)=2""",
                                   g.user["id"], other_id)
                    if existing:
                        return ok(id=existing["id"], existing=True)
                cur.execute("""INSERT INTO ChatConversations(kind,title,created_by,
                    needs_key_rotation) OUTPUT INSERTED.id VALUES(?,?,?,?)""",
                            kind, title or None, g.user["id"],
                            0 if server_chat_mode else 1)
                cid = cur.fetchone()[0]
                for uid in sorted(member_ids):
                    cur.execute("""INSERT INTO ChatMembers(conversation_id,user_id,
                        member_role) VALUES(?,?,?)""",
                                cid, uid, "owner" if uid == int(g.user["id"]) else "member")
                c.commit()
            return ok(id=cid, existing=False)
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/chat/conversation_update", methods=["POST"])
    @require_auth
    def api_v8_chat_conversation_update():
        """Rename a user-created group; automatic team channels stay immutable."""
        try:
            data = request.get_json() or {}
            cid = _int(data.get("conversation_id"))
            title = (data.get("title") or "").strip()
            if not title:
                return err("نام گروه الزامی است")
            if len(title) > 200:
                return err("نام گروه حداکثر ۲۰۰ نویسه است")
            with db_lock:
                c = get_conn(); cur = c.cursor()
                conv = ensure_conversation_member(cur, cid, g.user["id"])
                if conv["kind"] != "group":
                    return err("فقط نام گروه‌های دستی قابل ویرایش است")
                can_manage = conv["member_role"] in ("owner", "admin")
                if not can_manage or not user_has_permission(g.user, "chat.manage_groups"):
                    return err("فقط مدیر گروه اجازه ویرایش نام را دارد", 403)
                cur.execute("""UPDATE ChatConversations SET title=?,updated_at=GETDATE()
                    WHERE id=? AND kind='group' AND is_active=1""", title, cid)
                c.commit()
            audit("v8_chat_conversation_update", "conversation #%s" % cid)
            return ok(id=cid, title=title)
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/chat/conversation_delete", methods=["POST"])
    @require_auth
    def api_v8_chat_conversation_delete():
        """Soft-delete a group or remove a direct/group conversation for one member."""
        try:
            data = request.get_json() or {}
            cid = _int(data.get("conversation_id"))
            deleted_for_all = False
            with db_lock:
                c = get_conn(); cur = c.cursor()
                conv = ensure_conversation_member(cur, cid, g.user["id"])
                if conv["kind"] in ("team", "announcement"):
                    return err("گفتگوهای خودکار تیم و اطلاعیه از پیامرسان حذف نمی‌شوند")
                can_delete_group = (conv["kind"] == "group" and
                    conv["member_role"] in ("owner", "admin") and
                    user_has_permission(g.user, "chat.manage_groups"))
                if can_delete_group:
                    cur.execute("""UPDATE ChatConversations SET is_active=0,
                        updated_at=GETDATE() WHERE id=?""", cid)
                    cur.execute("""UPDATE ChatMembers SET is_active=0,
                        left_at=GETDATE() WHERE conversation_id=? AND is_active=1""", cid)
                    deleted_for_all = True
                else:
                    # A group owner whose role no longer has manage permission may
                    # still leave. Promote another active member first so the group
                    # never becomes orphaned.
                    if conv["kind"] == "group" and conv["member_role"] in ("owner", "admin"):
                        successor = one(cur, """SELECT TOP 1 user_id FROM ChatMembers
                            WHERE conversation_id=? AND user_id<>? AND is_active=1
                            ORDER BY CASE WHEN member_role='admin' THEN 0 ELSE 1 END,joined_at,user_id""",
                                        cid, g.user["id"])
                        if successor:
                            cur.execute("""UPDATE ChatMembers SET member_role='owner'
                                WHERE conversation_id=? AND user_id=? AND is_active=1""",
                                        cid, successor["user_id"])
                    cur.execute("""UPDATE ChatMembers SET is_active=0,
                        left_at=GETDATE() WHERE conversation_id=? AND user_id=?""",
                                cid, g.user["id"])
                    cur.execute("""IF NOT EXISTS(SELECT 1 FROM ChatMembers
                          WHERE conversation_id=? AND is_active=1)
                        UPDATE ChatConversations SET is_active=0,updated_at=GETDATE()
                          WHERE id=?""", cid, cid)
                c.commit()
            audit("v8_chat_conversation_delete",
                  "conversation #%s all=%s" % (cid, int(deleted_for_all)))
            return ok(id=cid, deleted_for_all=deleted_for_all)
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/chat/key_rotation_begin", methods=["POST"])
    @require_auth
    def api_v8_chat_key_rotation_begin():
        """Start a new future-message key version without exposing any key.

        This recovery path is used when a browser has lost its local private
        material or has no envelope for the active key.  Any active member may
        request it, but the request must come from that member's active device.
        """
        try:
            data = request.get_json() or {}
            cid = _int(data.get("conversation_id"))
            did = _int(data.get("device_id"))
            with db_lock:
                c = get_conn(); cur = c.cursor()
                conv = ensure_conversation_member(cur, cid, g.user["id"])
                device = one(cur, """SELECT id FROM ChatDevices
                    WHERE id=? AND user_id=? AND is_active=1""",
                             did, g.user["id"])
                if not device:
                    return err("این دستگاه برای پیامرسان فعال نیست", 403)
                if not conv.get("needs_key_rotation"):
                    # The predicate makes simultaneous requests idempotent: only
                    # one request advances the version and all others observe it.
                    cur.execute("""UPDATE ChatConversations
                        SET key_version=key_version+1,needs_key_rotation=1,
                            rotation_owner_device_id=NULL,rotation_claim_hash=NULL,
                            rotation_claimed_at=NULL,updated_at=GETDATE()
                        WHERE id=? AND needs_key_rotation=0""", cid)
                c.commit()
                current = one(cur, """SELECT key_version,needs_key_rotation
                    FROM ChatConversations WHERE id=?""", cid)
            return ok(key_version=current["key_version"],
                      needs_key_rotation=bool(current["needs_key_rotation"]))
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/chat/key_rotation_claim", methods=["POST"])
    @require_auth
    def api_v8_chat_key_rotation_claim():
        """Elect exactly one active member device to create a key version.

        The claim token is random and only its SHA-256 hash is stored.  This
        prevents two browsers from creating different AES keys for the same
        version, which would make messages intermittently undecryptable.
        """
        try:
            data = request.get_json() or {}
            cid = _int(data.get("conversation_id")); did = _int(data.get("device_id"))
            token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            with db_lock:
                c = get_conn(); cur = c.cursor()
                conv = ensure_conversation_member(cur, cid, g.user["id"])
                device = one(cur, """SELECT id FROM ChatDevices
                    WHERE id=? AND user_id=? AND is_active=1""", did, g.user["id"])
                if not device:
                    return err("این دستگاه برای پیامرسان فعال نیست", 403)
                if not conv.get("needs_key_rotation"):
                    return ok(claimed=False, key_version=conv["key_version"], ready=True)
                cur.execute("""UPDATE ChatConversations
                    SET rotation_owner_device_id=?,rotation_claim_hash=?,
                        rotation_claimed_at=GETDATE(),updated_at=GETDATE()
                    WHERE id=? AND needs_key_rotation=1 AND
                      (rotation_owner_device_id IS NULL OR rotation_owner_device_id=?
                       OR rotation_claimed_at<DATEADD(second,-45,GETDATE()))""",
                            did, token_hash, cid, did)
                claimed = int(cur.rowcount or 0) > 0
                c.commit()
                current = one(cur, """SELECT key_version,needs_key_rotation,
                    rotation_owner_device_id FROM ChatConversations WHERE id=?""", cid)
            return ok(claimed=claimed, claim_token=token if claimed else None,
                      key_version=current["key_version"],
                      ready=not bool(current["needs_key_rotation"]))
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/chat/member_devices", methods=["POST"])
    @require_auth
    def api_v8_chat_member_devices():
        try:
            data = request.get_json() or {}; cid = _int(data.get("conversation_id"))
            with db_lock:
                c = get_conn(); cur = c.cursor()
                conversation = ensure_conversation_member(cur, cid, g.user["id"])
                cur.execute("""SELECT d.id AS device_id,d.user_id,d.device_uuid,d.label,
                    d.public_key_jwk,d.key_algorithm,u.display_name,u.username
                    FROM ChatMembers m JOIN Users u ON u.id=m.user_id
                    JOIN ChatDevices d ON d.user_id=m.user_id AND d.is_active=1
                    WHERE m.conversation_id=? AND m.is_active=1
                    ORDER BY u.display_name,d.id""", cid)
                rows = rows_to_list(cur)
            return ok(rows=rows, key_version=conversation["key_version"],
                      needs_key_rotation=conversation["needs_key_rotation"])
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/chat/keys_save", methods=["POST"])
    @require_auth
    def api_v8_chat_keys_save():
        try:
            data = request.get_json() or {}; cid = _int(data.get("conversation_id"))
            version = _int(data.get("key_version")); envelopes = data.get("envelopes") or []
            device_id = _int(data.get("device_id"))
            claim_token = (data.get("claim_token") or "").strip()
            claim_hash = hashlib.sha256(claim_token.encode("utf-8")).hexdigest() if claim_token else ""
            with db_lock:
                c = get_conn(); cur = c.cursor()
                conv = ensure_conversation_member(cur, cid, g.user["id"])
                if int(conv["key_version"]) != version:
                    return err("نسخه کلید گفتگو تغییر کرده؛ فهرست را تازه کنید")
                active_device = one(cur, """SELECT id FROM ChatDevices
                    WHERE id=? AND user_id=? AND is_active=1""",
                                    device_id, g.user["id"])
                if not active_device:
                    return err("این دستگاه برای پیامرسان فعال نیست", 403)
                owner = one(cur, """SELECT rotation_owner_device_id,rotation_claim_hash
                    FROM ChatConversations WHERE id=?""", cid) or {}
                if int(owner.get("rotation_owner_device_id") or 0) != int(device_id or 0):
                    return err("مجوز ساخت کلید متعلق به این دستگاه نیست", 409)
                if not claim_token or not secrets.compare_digest(
                        str(owner.get("rotation_claim_hash") or ""), claim_hash):
                    return err("مجوز ساخت کلید گفتگو معتبر نیست؛ دوباره تلاش کنید", 409)
                cur.execute("""SELECT d.id FROM ChatDevices d JOIN ChatMembers m
                    ON m.user_id=d.user_id AND m.conversation_id=? AND m.is_active=1
                    WHERE d.is_active=1""", cid)
                valid_devices = {int(x[0]) for x in cur.fetchall()}
                supplied = set()
                for item in envelopes:
                    did = _int(item.get("device_id"))
                    wrapped = (item.get("wrapped_key") or "").strip()
                    if did not in valid_devices or not wrapped or len(wrapped) > 20000:
                        return err("پاکت کلید گفتگو معتبر نیست")
                    supplied.add(did)
                    cur.execute("""IF EXISTS(SELECT 1 FROM ChatConversationKeys
                          WHERE conversation_id=? AND key_version=? AND device_id=?)
                        UPDATE ChatConversationKeys SET wrapped_key=?,
                          wrap_algorithm='RSA-OAEP-256',created_at=GETDATE()
                          WHERE conversation_id=? AND key_version=? AND device_id=?
                        ELSE INSERT INTO ChatConversationKeys(conversation_id,key_version,
                          device_id,wrapped_key) VALUES(?,?,?,?)""",
                                cid, version, did, wrapped, cid, version, did,
                                cid, version, did, wrapped)
                missing = sorted(valid_devices - supplied)
                if not missing:
                    cur.execute("""UPDATE ChatConversations SET needs_key_rotation=0,
                        rotation_owner_device_id=NULL,rotation_claim_hash=NULL,
                        rotation_claimed_at=NULL,updated_at=GETDATE() WHERE id=?""", cid)
                c.commit()
            return ok(missing_device_ids=missing, rotation_complete=not missing)
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/chat/conversation_members_save", methods=["POST"])
    @require_auth
    def api_v8_chat_conversation_members_save():
        try:
            data = request.get_json() or {}; cid = _int(data.get("conversation_id"))
            member_ids = {_int(x) for x in (data.get("member_ids") or [])}
            member_ids.discard(None); member_ids.add(int(g.user["id"]))
            with db_lock:
                c = get_conn(); cur = c.cursor()
                conv = ensure_conversation_member(cur, cid, g.user["id"])
                if conv["kind"] not in ("group", "team"):
                    return err("عضویت این نوع گفتگو قابل ویرایش نیست")
                if conv["member_role"] not in ("owner", "admin"):
                    return err("فقط مدیر گروه اجازه تغییر اعضا را دارد", 403)
                marks = ",".join("?" for _ in member_ids)
                cur.execute("""SELECT id FROM Users WHERE id IN (%s)
                    AND is_active=1 AND role IN
                    ('admin','manager','planner','finance','reporter','support','lead','supervisor','employer')""" %
                            marks, list(member_ids))
                valid_ids = {int(x[0]) for x in cur.fetchall()}
                if valid_ids != member_ids:
                    return err("یکی از اعضای انتخاب‌شده مجاز یا فعال نیست")
                if conv["kind"] == "team":
                    cur.execute("""SELECT tm.user_id FROM TeamMembers tm JOIN Users u ON u.id=tm.user_id
                        WHERE tm.team_id=? AND tm.is_active=1
                          AND u.role NOT IN (N'employer',N'supervisor')""", conv["team_id"])
                    expected = {int(x[0]) for x in cur.fetchall()}
                    if member_ids != expected:
                        return err("اعضای گفتگوی خودکار تیم از صفحه مدیریت تیم تعیین می‌شوند")
                else:
                    problem = chat_members_error(cur, member_ids)
                    if problem:
                        return err(problem, 403)
                cur.execute("""UPDATE ChatMembers SET is_active=0,left_at=GETDATE()
                    WHERE conversation_id=?""", cid)
                for uid in member_ids:
                    cur.execute("""IF EXISTS(SELECT 1 FROM ChatMembers
                          WHERE conversation_id=? AND user_id=?)
                        UPDATE ChatMembers SET is_active=1,left_at=NULL
                          WHERE conversation_id=? AND user_id=?
                        ELSE INSERT INTO ChatMembers(conversation_id,user_id,member_role)
                          VALUES(?,?,'member')""",
                                cid, uid, cid, uid, cid, uid)
                if server_chat_mode:
                    cur.execute("""UPDATE ChatConversations SET needs_key_rotation=0,
                        rotation_owner_device_id=NULL,rotation_claim_hash=NULL,
                        rotation_claimed_at=NULL,updated_at=GETDATE() WHERE id=?""", cid)
                else:
                    cur.execute("""UPDATE ChatConversations SET key_version=key_version+1,
                        needs_key_rotation=1,rotation_owner_device_id=NULL,
                        rotation_claim_hash=NULL,rotation_claimed_at=NULL,updated_at=GETDATE() WHERE id=?""", cid)
                c.commit()
                updated = one(cur, "SELECT key_version FROM ChatConversations WHERE id=?", cid)
            return ok(key_version=updated["key_version"],
                      needs_key_rotation=not server_chat_mode)
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/chat/unread_summary", methods=["POST"])
    @require_auth
    def api_v8_chat_unread_summary():
        """Cheap unread counter for the sidebar badge and new-message alerts.

        The badge used to be refreshed only by the full conversations payload,
        which the client fetches only while the messenger page is open - so a
        user working anywhere else in the app never saw that a message had
        arrived. This runs on the global poll instead, and stays deliberately
        small: two aggregates and the newest sender, no member or device lists.
        """
        try:
            if not user_has_permission(g.user, "chat.use"):
                return ok(total=0, conversations=0, latest_id=0, latest_title="",
                          latest_sender="")
            with db_lock:
                c = get_conn(); cur = c.cursor()
                row = one(cur, """SELECT ISNULL(SUM(x.unread),0) AS total,
                    ISNULL(SUM(CASE WHEN x.unread>0 THEN 1 ELSE 0 END),0) AS conversations,
                    ISNULL(MAX(x.latest_id),0) AS latest_id
                    FROM (SELECT (SELECT COUNT(*) FROM ChatMessages n
                            WHERE n.conversation_id=c.id AND n.is_deleted=0
                              AND n.sender_user_id<>m.user_id
                              AND n.id>ISNULL(r.last_message_id,0)) AS unread,
                        (SELECT MAX(n.id) FROM ChatMessages n
                            WHERE n.conversation_id=c.id AND n.is_deleted=0
                              AND n.sender_user_id<>m.user_id
                              AND n.id>ISNULL(r.last_message_id,0)) AS latest_id
                        FROM ChatConversations c
                        JOIN ChatMembers m ON m.conversation_id=c.id
                          AND m.user_id=? AND m.is_active=1
                        LEFT JOIN ChatReadReceipts r ON r.conversation_id=c.id
                          AND r.user_id=m.user_id
                        WHERE c.is_active=1) x""", g.user["id"])
                total = _int((row or {}).get("total"), 0)
                latest_id = _int((row or {}).get("latest_id"), 0)
                title = ""; sender = ""
                if latest_id:
                    newest = one(cur, """SELECT c.kind,c.title,u.display_name,u.username
                        FROM ChatMessages m JOIN ChatConversations c ON c.id=m.conversation_id
                        JOIN Users u ON u.id=m.sender_user_id WHERE m.id=?""", latest_id)
                    if newest:
                        sender = newest.get("display_name") or newest.get("username") or ""
                        title = newest.get("title") or ""
                        if not title:
                            title = {"team": "گروه تیم",
                                     "announcement": "اطلاعیه‌های سازمان"}.get(
                                         newest.get("kind"), sender)
            return ok(total=total, conversations=_int((row or {}).get("conversations"), 0),
                      latest_id=latest_id, latest_title=title, latest_sender=sender)
        except Exception as exc:
            return err(str(exc), total=0, conversations=0, latest_id=0)

    @app.route("/api/v8/chat/messages", methods=["POST"])
    @require_auth
    def api_v8_chat_messages():
        try:
            data = request.get_json() or {}; cid = _int(data.get("conversation_id"))
            after = _int(data.get("after_id"), 0); limit = min(200, max(1, _int(data.get("limit"), 80)))
            before = _int(data.get("before_id"), 0)
            device_id = _int(data.get("device_id"))
            with db_lock:
                c = get_conn(); cur = c.cursor()
                conv = ensure_conversation_member(cur, cid, g.user["id"])
                key_rows = []
                if server_chat_mode:
                    device_id = ensure_server_chat_device(c, cur, g.user["id"])
                    conv["needs_key_rotation"] = False
                else:
                    active_device = one(cur, """SELECT id FROM ChatDevices
                        WHERE id=? AND user_id=? AND is_active=1""",
                                        device_id, g.user["id"])
                    if not active_device:
                        return err("این دستگاه هنوز برای پیامرسان تأیید نشده است", 403)
                    if device_id:
                        cur.execute("""SELECT k.key_version,k.wrapped_key,k.wrap_algorithm
                            FROM ChatConversationKeys k WHERE k.conversation_id=?
                              AND k.device_id=? AND EXISTS(SELECT 1 FROM ChatDevices d
                                WHERE d.id=k.device_id AND d.user_id=? AND d.is_active=1)
                            ORDER BY k.key_version""", cid, device_id, g.user["id"])
                        key_rows = rows_to_list(cur)
                # after_id>0 is the polling path and stays chronological.
                # Opening a conversation (after_id=0) must return the NEWEST
                # page instead: this used to take the oldest rows, so a
                # conversation with more messages than one page opened on its
                # first 200 and the recent messages were unreachable.
                # before_id pages further back through the history.
                if after:
                    cur.execute("""SELECT TOP (?) m.id,m.conversation_id,m.sender_user_id,
                        m.sender_device_id,m.key_version,m.message_kind,m.ciphertext,
                        m.iv,m.aad,m.client_message_id,m.encrypted_file_id,m.created_at,
                        u.display_name,u.username
                        FROM ChatMessages m JOIN Users u ON u.id=m.sender_user_id
                        WHERE m.conversation_id=? AND m.id>? AND m.is_deleted=0
                        ORDER BY m.id ASC""", limit, cid, after)
                elif before:
                    cur.execute("""SELECT t.* FROM (SELECT TOP (?) m.id,m.conversation_id,
                        m.sender_user_id,m.sender_device_id,m.key_version,m.message_kind,
                        m.ciphertext,m.iv,m.aad,m.client_message_id,m.encrypted_file_id,
                        m.created_at,u.display_name,u.username
                        FROM ChatMessages m JOIN Users u ON u.id=m.sender_user_id
                        WHERE m.conversation_id=? AND m.id<? AND m.is_deleted=0
                        ORDER BY m.id DESC) t ORDER BY t.id ASC""", limit, cid, before)
                else:
                    cur.execute("""SELECT t.* FROM (SELECT TOP (?) m.id,m.conversation_id,
                        m.sender_user_id,m.sender_device_id,m.key_version,m.message_kind,
                        m.ciphertext,m.iv,m.aad,m.client_message_id,m.encrypted_file_id,
                        m.created_at,u.display_name,u.username
                        FROM ChatMessages m JOIN Users u ON u.id=m.sender_user_id
                        WHERE m.conversation_id=? AND m.is_deleted=0
                        ORDER BY m.id DESC) t ORDER BY t.id ASC""", limit, cid)
                rows = rows_to_list(cur)
                # Tells the UI whether an older page is still available, so it
                # can offer "load earlier messages" instead of silently hiding
                # the rest of the history.
                has_more = False
                if rows and not after:
                    has_more = bool(one(cur, """SELECT TOP 1 id FROM ChatMessages
                        WHERE conversation_id=? AND id<? AND is_deleted=0
                        ORDER BY id DESC""", cid, rows[0]["id"]))
            if server_chat_mode:
                for row in rows:
                    if row.get("aad") == server_chat.marker:
                        try:
                            row["plain"] = server_chat.decrypt_json(row.get("ciphertext"))
                        except ValueError:
                            row["plain"] = None
                    else:
                        # Old end-to-end rows cannot be decrypted by the server.
                        row["plain"] = None
            return ok(rows=rows, conversation=conv, wrapped_keys=key_rows,
                      chat_mode=CHAT_MODE, server_device_id=device_id,
                      has_more=has_more)
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc), rows=[])

    @app.route("/api/v8/chat/message_send", methods=["POST"])
    @require_auth
    def api_v8_chat_message_send():
        try:
            data = request.get_json() or {}
            cid = _int(data.get("conversation_id"))
            kind = data.get("message_kind") or "text"
            file_id = _int(data.get("encrypted_file_id"))
            client_id = (data.get("client_message_id") or "").strip()
            if kind not in ("text", "file") or not client_id or len(client_id) > 80:
                return err("پیام کامل نیست")

            if server_chat_mode:
                payload = data.get("plain")
                if not isinstance(payload, dict):
                    return err("متن پیام معتبر نیست")
                text = str(payload.get("text") or "").strip()
                if kind == "text" and not text:
                    return err("متن پیام خالی است")
                encoded = json.dumps(payload, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")
                if len(encoded) > 1_000_000:
                    return err("اندازه پیام معتبر نیست")
                ciphertext = server_chat.encrypt_json(payload)
                iv = "server-managed"
                aad = server_chat.marker
                version = 0
                did = None
            else:
                did = _int(data.get("device_id"))
                version = _int(data.get("key_version"))
                ciphertext = (data.get("ciphertext") or "").strip()
                iv = (data.get("iv") or "").strip()
                aad = (data.get("aad") or "").strip() or None
                if not ciphertext or not iv:
                    return err("پیام رمز‌شده کامل نیست")
                if len(ciphertext) > 1_500_000 or len(iv) > 100:
                    return err("اندازه پیام معتبر نیست")

            with db_lock:
                c = get_conn(); cur = c.cursor()
                conv = ensure_conversation_member(cur, cid, g.user["id"])
                if not conv.get("can_post"):
                    return err("در این گفتگو اجازه ارسال ندارید", 403)
                if conv["kind"] == "announcement" and not user_has_permission(g.user, "chat.manage_groups"):
                    return err("دسترسی ارسال اطلاعیه عمومی را ندارید", 403)
                if conv["kind"] in ("direct", "group"):
                    # R14: a conversation opened before the client rule may
                    # join a client with someone outside their circle.
                    cur.execute("""SELECT user_id FROM ChatMembers
                        WHERE conversation_id=? AND is_active=1""", cid)
                    problem = chat_members_error(cur, [int(x[0]) for x in cur.fetchall()])
                    if problem:
                        return err(problem, 403)

                if server_chat_mode:
                    did = ensure_server_chat_device(c, cur, g.user["id"])
                else:
                    if conv.get("needs_key_rotation") or int(conv["key_version"]) != version:
                        return err("ابتدا کلید جدید گفتگو باید بین اعضا توزیع شود")
                    device = one(cur, """SELECT d.id FROM ChatDevices d
                        JOIN ChatConversationKeys k ON k.device_id=d.id
                          AND k.conversation_id=? AND k.key_version=?
                        WHERE d.id=? AND d.user_id=? AND d.is_active=1""",
                                 cid, version, did, g.user["id"])
                    if not device:
                        return err("این دستگاه کلید فعال گفتگو را ندارد")

                if kind == "file":
                    valid_file = one(cur, """SELECT id FROM ChatEncryptedFiles
                        WHERE id=? AND conversation_id=? AND uploaded_by=?
                          AND key_version=? AND is_active=1""",
                                     file_id, cid, g.user["id"], version)
                    if not valid_file:
                        return err("فایل رمز‌شده معتبر نیست")

                existing = one(cur, """SELECT id FROM ChatMessages
                    WHERE sender_user_id=? AND client_message_id=?""",
                               g.user["id"], client_id)
                if existing:
                    return ok(id=existing["id"], duplicate=True)
                cur.execute("""INSERT INTO ChatMessages(conversation_id,sender_user_id,
                    sender_device_id,key_version,message_kind,ciphertext,iv,aad,
                    client_message_id,encrypted_file_id)
                    OUTPUT INSERTED.id VALUES(?,?,?,?,?,?,?,?,?,?)""",
                            cid, g.user["id"], did, version, kind, ciphertext, iv,
                            aad, client_id, file_id)
                mid = cur.fetchone()[0]
                c.commit()
            return ok(id=mid, duplicate=False, chat_mode=CHAT_MODE)
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/chat/read", methods=["POST"])
    @require_auth
    def api_v8_chat_read():
        try:
            data = request.get_json() or {}; cid = _int(data.get("conversation_id"))
            mid = _int(data.get("message_id"))
            with db_lock:
                c = get_conn(); cur = c.cursor()
                ensure_conversation_member(cur, cid, g.user["id"])
                cur.execute("""IF EXISTS(SELECT 1 FROM ChatReadReceipts
                      WHERE conversation_id=? AND user_id=?)
                    UPDATE ChatReadReceipts SET last_message_id=
                      CASE WHEN ISNULL(last_message_id,0)<? THEN ? ELSE last_message_id END,
                      read_at=GETDATE() WHERE conversation_id=? AND user_id=?
                    ELSE INSERT INTO ChatReadReceipts(conversation_id,user_id,
                      last_message_id,read_at) VALUES(?,?,?,GETDATE())""",
                            cid, g.user["id"], mid, mid, cid, g.user["id"],
                            cid, g.user["id"], mid)
                c.commit()
            return ok()
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/chat/file_upload", methods=["POST"])
    @require_auth
    def api_v8_chat_file_upload():
        try:
            ensure_internal_chat_user(g.user)
            if os.path.exists(os.path.join(base_dir, "data", "backup.lock")):
                return err(
                    "پشتیبان‌گیری در حال انجام است؛ چند دقیقه دیگر دوباره تلاش کنید",
                    423,
                )
            cid = _int(request.form.get("conversation_id"))
            upload = request.files.get("file")
            if not upload:
                return err("فایل دریافت نشد")
            raw = upload.read(25 * 1024 * 1024 + 1)
            if len(raw) > 25 * 1024 * 1024:
                return err("حداکثر اندازه فایل ۲۵ مگابایت است")

            version = _int(request.form.get("key_version"))
            device_id = _int(request.form.get("device_id"))
            encrypted_meta = request.form.get("encrypted_meta") or None
            stored_raw = raw
            if server_chat_mode:
                version = 0
                stored_raw = server_chat.encrypt_bytes(raw)
                meta = {
                    "file_name": (request.form.get("file_name") or upload.filename or "file")[:240],
                    "file_type": (request.form.get("file_type") or upload.mimetype or
                                  "application/octet-stream")[:160],
                    "original_size": len(raw),
                }
                encrypted_meta = server_chat.marker + ":" + server_chat.encrypt_json(meta)

            with db_lock:
                c = get_conn(); cur = c.cursor()
                conv = ensure_conversation_member(cur, cid, g.user["id"])
                if server_chat_mode:
                    device_id = ensure_server_chat_device(c, cur, g.user["id"])
                else:
                    if conv.get("needs_key_rotation") or int(conv["key_version"]) != version:
                        return err("کلید گفتگو نیازمند نوسازی است")
                    device = one(cur, """SELECT d.id FROM ChatDevices d
                        JOIN ChatConversationKeys k ON k.device_id=d.id
                          AND k.conversation_id=? AND k.key_version=?
                        WHERE d.id=? AND d.user_id=? AND d.is_active=1""",
                                 cid, version, device_id, g.user["id"])
                    if not device:
                        return err("این دستگاه کلید فعال گفتگو را ندارد", 403)

                storage = secrets.token_hex(24) + ".cipher"
                path = os.path.join(chat_dir, storage)
                with open(path, "wb") as handle:
                    handle.write(stored_raw)
                digest = hashlib.sha256(stored_raw).hexdigest()
                try:
                    cur.execute("""INSERT INTO ChatEncryptedFiles(conversation_id,
                        uploaded_by,storage_name,ciphertext_sha256,size_bytes,
                        encrypted_meta,key_version) OUTPUT INSERTED.id
                        VALUES(?,?,?,?,?,?,?)""",
                                cid, g.user["id"], storage, digest, len(stored_raw),
                                encrypted_meta, version)
                    fid = cur.fetchone()[0]; c.commit()
                except Exception:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                    raise
            return ok(id=fid, size_bytes=len(raw), sha256=digest,
                      chat_mode=CHAT_MODE)
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc))

    @app.route("/api/v8/chat/file_download/<int:file_id>", methods=["GET"])
    @require_auth
    def api_v8_chat_file_download(file_id):
        try:
            ensure_internal_chat_user(g.user)
            with db_lock:
                c = get_conn(); cur = c.cursor()
                row = one(cur, """SELECT f.* FROM ChatEncryptedFiles f
                    JOIN ChatMembers m ON m.conversation_id=f.conversation_id
                      AND m.user_id=? AND m.is_active=1
                    WHERE f.id=? AND f.is_active=1""", g.user["id"], file_id)
            if not row:
                return err("فایل یافت نشد یا دسترسی ندارید", 404)
            path = os.path.join(chat_dir, os.path.basename(row["storage_name"]))
            if not os.path.isfile(path):
                return err("فایل روی دیسک یافت نشد", 404)

            meta_text = str(row.get("encrypted_meta") or "")
            if server_chat_mode and meta_text.startswith(server_chat.marker + ":"):
                try:
                    with open(path, "rb") as handle:
                        plain = server_chat.decrypt_bytes(handle.read())
                    meta = server_chat.decrypt_json(
                        meta_text[len(server_chat.marker) + 1:]
                    )
                    return send_file(
                        io.BytesIO(plain), as_attachment=True,
                        download_name=str(meta.get("file_name") or ("file-%s" % file_id)),
                        mimetype=str(meta.get("file_type") or "application/octet-stream"),
                    )
                except ValueError:
                    return err("رمزگشایی فایل ممکن نشد", 500)

            return send_file(path, as_attachment=True,
                             download_name="encrypted-%s.bin" % file_id,
                             mimetype="application/octet-stream")
        except PermissionError as exc:
            return err(str(exc), 403)
        except Exception as exc:
            return err(str(exc), 500)

    @app.route("/api/v8/chat/message_delete", methods=["POST"])
    @require_auth
    def api_v8_chat_message_delete():
        """Delete ciphertext only; nobody, including admin, can inspect it."""
        try:
            mid = _int((request.get_json() or {}).get("id"))
            with db_lock:
                c = get_conn(); cur = c.cursor()
                row = one(cur, """SELECT m.id,m.sender_user_id,m.conversation_id,
                    c.created_by FROM ChatMessages m JOIN ChatConversations c
                    ON c.id=m.conversation_id WHERE m.id=? AND m.is_deleted=0""", mid)
                if not row:
                    return err("پیام یافت نشد")
                if int(row["sender_user_id"]) != int(g.user["id"]):
                    return err("فقط فرستنده می‌تواند محتوای رمز‌شده پیام خود را حذف کند", 403)
                cur.execute("""UPDATE ChatMessages SET is_deleted=1,
                    ciphertext=N'',iv=N'' WHERE id=?""", mid)
                c.commit()
            return ok()
        except Exception as exc:
            return err(str(exc))
