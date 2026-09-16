# -*- coding: utf-8 -*-
"""Shared company/team visibility rules for TaskHub LAN R10.

Company-wide data visibility is intentionally tied to three global roles only.
Permissions decide *what* an account can do; team membership decides *where*
it can do it. This separation prevents a delegated button permission from
silently turning into access to the whole company.
"""
from __future__ import annotations

GLOBAL_COMPANY_ROLES = frozenset(("admin", "finance", "reporter"))
TEAM_REQUIRED_ROLES = frozenset(("manager", "planner", "support", "lead", "supervisor", "employer"))
# Employers and supervisors are the client's people, not staff (R14).
CHAT_CLIENT_ROLES = frozenset(("employer", "supervisor"))


def has_company_scope(user_or_role) -> bool:
    if isinstance(user_or_role, dict):
        role = user_or_role.get("role")
    else:
        role = user_or_role
    return role in GLOBAL_COMPANY_ROLES


def requires_team(role: str) -> bool:
    return role in TEAM_REQUIRED_ROLES


def default_team_role(role: str) -> str:
    if role == "manager":
        return "manager"
    if role == "planner":
        return "planner"
    return "member"


def chat_pair_allowed(a_id, a_role, b_id, b_role, contacts_of) -> bool:
    """Whether two people may share a messenger conversation.

    Staff talk to each other freely. A client account (employer or
    supervisor) talks only to the people ``contacts_of(client_id)`` returns:
    the other client accounts of its own project and the planners of the teams
    that run that project. The rule is checked from both ends, so a staff
    member cannot reach a client the client could not reach."""
    if a_role in CHAT_CLIENT_ROLES and int(b_id) not in contacts_of(int(a_id)):
        return False
    if b_role in CHAT_CLIENT_ROLES and int(a_id) not in contacts_of(int(b_id)):
        return False
    return True


def lead_group_ids(cur, lead_id) -> set:
    """The people a group lead (سرگروه) acts for: themselves and the active
    members of the group they lead (R16 WorkGroups; the R14/R15 sub-groups
    were migrated into them). A group is not a team; the caller still applies
    the team boundary on top of this."""
    cur.execute("""SELECT gm.user_id FROM WorkGroupMembers gm
        JOIN WorkGroups wg ON wg.id=gm.group_id AND wg.is_active=1
        JOIN Users u ON u.id=gm.user_id
        WHERE wg.lead_id=? AND u.is_active=1""", lead_id)
    return {int(row[0]) for row in cur.fetchall()} | {int(lead_id)}


def group_project_ids(cur, user_id) -> set:
    """Projects of the active group a person leads or belongs to (R16).

    An empty set means the person is in no group that has projects, so their
    team scope applies unchanged; otherwise their project lists and new tasks
    are limited to exactly these projects."""
    cur.execute("""SELECT DISTINCT gp.project_id FROM WorkGroupProjects gp
        JOIN WorkGroups wg ON wg.id=gp.group_id AND wg.is_active=1
        WHERE wg.lead_id=? OR EXISTS(SELECT 1 FROM WorkGroupMembers gm
          WHERE gm.group_id=wg.id AND gm.user_id=?)""", user_id, user_id)
    return {int(row[0]) for row in cur.fetchall()}
