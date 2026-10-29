"""Date navigation and month-grid helpers for the Done history tab."""

import calendar
from collections import Counter
from datetime import date, datetime, timedelta


def month_grid_days(year: int, month: int) -> list[list[int]]:
    """Monday-first calendar weeks; 0 represents a day outside the month."""
    return calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)


def shift_period(selected: date, mode: str, direction: int) -> date:
    if mode == "day":
        return selected + timedelta(days=direction)
    if mode != "month":
        raise ValueError("Only day/month views are supported")
    number = selected.year * 12 + selected.month - 1 + direction
    return date(number // 12, number % 12 + 1, 1)


def completed_counts_by_day(entries) -> dict[int, int]:
    return dict(Counter(datetime.fromtimestamp(entry.completed_ts).day for entry in entries))
