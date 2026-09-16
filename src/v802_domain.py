# -*- coding: utf-8 -*-
"""Pure business rules for TaskHub 8.0.2 financial attribution."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def _decimal(value, default=Decimal("0")):
    if value in (None, ""):
        return default
    try:
        return Decimal(str(value).replace(",", ""))
    except Exception:
        return default


def weighted_task_score(progress_weight, category_weight):
    """Return the non-monetary completed-task score used by the report."""
    progress = _decimal(progress_weight, Decimal("1"))
    category = _decimal(category_weight, Decimal("1"))
    score = progress * category
    return score if score > 0 else Decimal("0")


def split_person_task_score(score, time_seconds=None, assignee_ids=None):
    """Split one task score among people without inventing equal shares.

    Real positive timer seconds take precedence. If there is no timer data and
    exactly one distinct assignee, that person receives the full score. For no
    assignee or multiple assignees without time, the result is intentionally
    unresolved so the report can expose a data-quality warning.
    """
    score = _decimal(score)
    if score <= 0:
        return {}, False

    times = {
        int(user_id): max(0, int(seconds or 0))
        for user_id, seconds in (time_seconds or {}).items()
        if user_id is not None and int(seconds or 0) > 0
    }
    total_seconds = sum(times.values())
    if total_seconds:
        total = Decimal(total_seconds)
        return {
            user_id: score * Decimal(seconds) / total
            for user_id, seconds in times.items()
        }, False

    assignees = {int(x) for x in (assignee_ids or []) if x is not None}
    if len(assignees) == 1:
        return {next(iter(assignees)): score}, False
    return {}, True


def allocate_approved_amount(approved_amount, score, total_score):
    """Allocate approved revenue in proportion to a non-monetary score."""
    approved = _decimal(approved_amount)
    score = _decimal(score)
    total = _decimal(total_score)
    if approved <= 0 or score <= 0 or total <= 0:
        return Decimal("0")
    return approved * score / total


def percent(value, total):
    value = _decimal(value)
    total = _decimal(total)
    if not total:
        return Decimal("0.00")
    return (value * Decimal("100") / total).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
