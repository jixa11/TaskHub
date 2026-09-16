# -*- coding: utf-8 -*-
"""Pure business rules for TaskHub 8.

The functions in this module deliberately have no Flask or database
dependency.  Keeping contribution and allocation rules here makes them
testable and prevents dashboard code from inventing a second definition.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


GLOBAL_TEAM_VIEW_ROLES = frozenset(("admin", "manager", "planner", "finance", "reporter"))
GLOBAL_TEAM_WRITE_ROLES = frozenset(("admin",))
FINANCE_WRITE_ROLES = frozenset(("admin", "manager", "planner", "finance"))
REPORT_ROLES = frozenset(
    ("admin", "manager", "planner", "finance", "reporter", "support")
)


def decimal_value(value, default=Decimal("0")):
    if value in (None, ""):
        return default
    return Decimal(str(value))


def percent(part, whole):
    part, whole = decimal_value(part), decimal_value(whole)
    if whole == 0:
        return Decimal("0")
    return (part * Decimal("100") / whole).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def validate_team_allocations(contract_price, allocations):
    """Validate optional team envelopes without forcing an allocation.

    A shared contract may intentionally have no team allocations.  Once
    allocations are entered, their total may not exceed the effective
    contract price.  A lower total is allowed and is reported as unallocated.
    """
    price = decimal_value(contract_price)
    values = [decimal_value(x) for x in (allocations or [])]
    if price < 0 or any(x < 0 for x in values):
        return False, "مبلغ قرارداد و سهم تیم‌ها نمی‌تواند منفی باشد", price
    allocated = sum(values, Decimal("0"))
    remaining = price - allocated
    if remaining < 0:
        return False, "جمع سهم تیم‌ها از مبلغ مؤثر قرارداد بیشتر است", remaining
    return True, None, remaining


def project_progress(tasks):
    """Weighted project completion percentage.

    Archived/cancelled rows are expected to be removed by the caller.
    Weight is operational effort, never a monetary value.
    """
    rows = list(tasks or [])
    total = sum((decimal_value(x.get("progress_weight"), Decimal("1"))
                 for x in rows), Decimal("0"))
    done = sum((decimal_value(x.get("progress_weight"), Decimal("1"))
                for x in rows if x.get("status") == "done"), Decimal("0"))
    return {
        "total_weight": total,
        "completed_weight": done,
        "progress_percent": percent(done, total),
    }


def team_completion_shares(tasks):
    """Return each team's share of completed weighted output."""
    completed = [x for x in (tasks or []) if x.get("status") == "done"]
    total = sum((decimal_value(x.get("progress_weight"), Decimal("1"))
                 for x in completed), Decimal("0"))
    by_team = {}
    for row in completed:
        team_id = row.get("team_id")
        weight = decimal_value(row.get("progress_weight"), Decimal("1"))
        by_team[team_id] = by_team.get(team_id, Decimal("0")) + weight
    return {
        team_id: {
            "completed_weight": weight,
            "share_percent": percent(weight, total),
        }
        for team_id, weight in by_team.items()
    }


def person_output_shares(tasks, time_rows):
    """Attribute completed task weight to people using actual logged time.

    Rules agreed with the user:
    * one assignee and no time -> that assignee receives the task weight;
    * several assignees and no time -> do not guess an equal split; flag it;
    * with time -> prorate the task weight by each person's logged seconds.
    """
    time_by_task = {}
    for row in time_rows or []:
        task_id = row.get("task_id")
        user_id = row.get("user_id")
        seconds = max(0, int(row.get("seconds") or 0))
        time_by_task.setdefault(task_id, {})
        time_by_task[task_id][user_id] = (
            time_by_task[task_id].get(user_id, 0) + seconds
        )

    totals = {}
    incomplete = []
    total_weight = Decimal("0")
    for task in tasks or []:
        if task.get("status") != "done":
            continue
        task_id = task.get("id")
        weight = decimal_value(task.get("progress_weight"), Decimal("1"))
        total_weight += weight
        logged = time_by_task.get(task_id, {})
        logged_total = sum(logged.values())
        if logged_total:
            for user_id, seconds in logged.items():
                share = weight * Decimal(seconds) / Decimal(logged_total)
                totals[user_id] = totals.get(user_id, Decimal("0")) + share
            continue

        assignees = []
        primary = task.get("staff_id")
        if primary is not None:
            assignees.append(primary)
        for helper in task.get("helper_ids") or []:
            if helper is not None and helper not in assignees:
                assignees.append(helper)
        if len(assignees) == 1:
            totals[assignees[0]] = totals.get(assignees[0], Decimal("0")) + weight
        else:
            incomplete.append(task_id)

    return {
        "rows": {
            user_id: {
                "output_weight": weight.quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                ),
                "share_percent": percent(weight, total_weight),
            }
            for user_id, weight in totals.items()
        },
        "total_completed_weight": total_weight,
        "incomplete_task_ids": incomplete,
    }

