"""Billing period arithmetic.

Periods are anchored to the subscription's start_date, never to the calendar
month. A subscription starting on the 15th bills 15th -> 14th.

Every downstream money bug traces back to this module, so it is pure, has no
Django dependency, and is the first thing built.
"""

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

# Payment terms. A constant rather than a setting: the brief does not ask for
# configurable terms, and a constant is honest about that.
NET_DAYS = timedelta(days=14)

MONTHLY = "monthly"
ANNUAL = "annual"


def _step(cycle, n):
    """The offset from start_date to the n-th period boundary."""
    if cycle == ANNUAL:
        return relativedelta(years=n)
    return relativedelta(months=n)


def period_for_index(start_date, cycle, n):
    """The n-th billing period (0-based) as an inclusive (start, end) pair.

    relativedelta clamps month ends correctly: 2025-01-31 + 1 month is
    2025-02-28. Periods therefore stay contiguous and never overlap, which is
    the property that matters. Alignment drift after a clamp is accepted; the
    alternative — re-anchoring to the 31st — opens gaps.
    """
    if n < 0:
        raise ValueError("period index cannot be negative")
    period_start = start_date + _step(cycle, n)
    period_end = start_date + _step(cycle, n + 1) - timedelta(days=1)
    return period_start, period_end


def current_period(start_date, cycle, as_of=None):
    """The period containing as_of, or None if the subscription has not started.

    Returns an inclusive (start, end) pair.
    """
    as_of = as_of or date.today()
    if as_of < start_date:
        return None  # ruling A-13 — reported as skipped, not failed

    # Estimate the index, then correct it. The estimate can be off by one
    # around month-end clamping, so the answer is always verified rather than
    # trusted.
    delta = relativedelta(as_of, start_date)
    if cycle == ANNUAL:
        guess = delta.years
    else:
        guess = delta.years * 12 + delta.months

    for candidate in (guess, guess - 1, guess + 1, guess - 2, guess + 2):
        if candidate < 0:
            continue
        period_start, period_end = period_for_index(start_date, cycle, candidate)
        if period_start <= as_of <= period_end:
            return period_start, period_end

    return None


def due_date_for(period_start):
    """Payment is due NET_DAYS after the period opens."""
    return period_start + NET_DAYS
