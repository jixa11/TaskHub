# -*- coding: utf-8 -*-
"""Pure, dependency-free business rules for TaskHub v7."""
from __future__ import annotations

import datetime
import decimal


ZERO = decimal.Decimal('0')


def money(value):
    return ZERO if value in (None, '') else decimal.Decimal(str(value))


def effective_contract_price(base_price, approved_extension_deltas):
    return money(base_price) + sum((money(x) for x in approved_extension_deltas), ZERO)


def statement_amount_without_vat(row):
    """The first defined amount in the approved business priority order."""
    for key in ('confirmed_without_vat', 'confirmed_price',
                'requested_without_vat', 'requested_price'):
        if row.get(key) is not None:
            return money(row[key])
    return ZERO


def contract_remaining(effective_price, employer_approved_statements):
    """Do not clamp negative values; an overrun must stay visible as an error."""
    return money(effective_price) - sum((statement_amount_without_vat(x)
                                         for x in employer_approved_statements), ZERO)


def validate_monthly_allocation(annual_target, monthly_amounts):
    values = [money(x) for x in monthly_amounts]
    if len(values) != 12:
        return False, 'هر ۱۲ ماه باید مقدار داشته باشند', None
    if any(x < ZERO for x in values):
        return False, 'هدف ماهانه نمی‌تواند منفی باشد', None
    unallocated = money(annual_target) - sum(values, ZERO)
    if unallocated < ZERO:
        return False, 'جمع اهداف ماهانه از هدف سالانه بیشتر است', unallocated
    return True, None, unallocated


def expiry_level(end_date, today=None, red_days=15, yellow_days=45):
    if not end_date:
        return 'normal', None
    if isinstance(end_date, str):
        end_date = datetime.date.fromisoformat(end_date[:10])
    if isinstance(end_date, datetime.datetime):
        end_date = end_date.date()
    today = today or datetime.date.today()
    days = (end_date - today).days
    return ('red' if days <= red_days else ('yellow' if days <= yellow_days else 'normal')), days

