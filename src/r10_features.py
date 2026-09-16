# -*- coding: utf-8 -*-
"""R10 additive migration helpers.

The migration is safe to run at every startup. Existing users keep their
current primary team. Active team-scoped users without membership are attached
to their project team when possible, otherwise to the legacy default team.
"""
from __future__ import annotations

from team_scope import TEAM_REQUIRED_ROLES, default_team_role


def init_r10_tables(conn):
    cur = conn.cursor()
    cur.execute("""IF NOT EXISTS(SELECT 1 FROM Teams WHERE code=N'legacy-default')
        INSERT INTO Teams(code,name,description,is_active)
        VALUES(N'legacy-default',N'تیم پیش‌فرض',N'تیم انتقال داده‌های قدیمی',1)""")
    cur.execute("SELECT id FROM Teams WHERE code=N'legacy-default'")
    default_team_id = int(cur.fetchone()[0])

    marks = ",".join("?" for _ in TEAM_REQUIRED_ROLES)
    cur.execute("""SELECT u.id,u.role,u.project_id
        FROM Users u
        WHERE u.is_active=1 AND u.role IN (%s)
          AND NOT EXISTS(SELECT 1 FROM TeamMembers tm
              WHERE tm.user_id=u.id AND tm.is_active=1)
        ORDER BY u.id""" % marks, list(TEAM_REQUIRED_ROLES))
    missing = [(int(r[0]), str(r[1]), r[2]) for r in cur.fetchall()]
    for user_id, role, project_id in missing:
        team_id = default_team_id
        if project_id:
            cur.execute("""SELECT TOP 1 team_id FROM ProjectTeams
                WHERE project_id=? AND is_active=1
                ORDER BY is_primary DESC,id""", project_id)
            row = cur.fetchone()
            if row:
                team_id = int(row[0])
        team_role = default_team_role(role)
        cur.execute("""IF EXISTS(SELECT 1 FROM TeamMembers WHERE team_id=? AND user_id=?)
            UPDATE TeamMembers SET team_role=?,is_primary=1,is_active=1,left_at=NULL
              WHERE team_id=? AND user_id=?
            ELSE INSERT INTO TeamMembers(team_id,user_id,team_role,is_primary,is_active)
              VALUES(?,?,?,?,1)""",
            team_id, user_id, team_role, team_id, user_id,
            team_id, user_id, team_role, 1)

    # Keep exactly one active primary membership for every team-scoped user.
    cur.execute(""";WITH ranked AS(
        SELECT tm.team_id,tm.user_id,
          ROW_NUMBER() OVER(PARTITION BY tm.user_id
            ORDER BY tm.is_primary DESC,tm.team_id) AS rn
        FROM TeamMembers tm JOIN Users u ON u.id=tm.user_id
        WHERE tm.is_active=1 AND u.is_active=1
      )
      UPDATE tm SET is_primary=CASE WHEN r.rn=1 THEN 1 ELSE 0 END
      FROM TeamMembers tm JOIN ranked r
        ON r.team_id=tm.team_id AND r.user_id=tm.user_id""")
    cur.execute("""IF NOT EXISTS(SELECT 1 FROM sys.indexes
          WHERE name=N'UX_TeamMembers_ActivePrimaryUser'
            AND object_id=OBJECT_ID(N'TeamMembers'))
        CREATE UNIQUE INDEX UX_TeamMembers_ActivePrimaryUser
          ON TeamMembers(user_id) WHERE is_active=1 AND is_primary=1""")
    conn.commit()
