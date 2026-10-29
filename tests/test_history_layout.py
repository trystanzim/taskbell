"""Calendar navigation and grouping without GUI dependencies."""

import unittest
from datetime import date
from types import SimpleNamespace

from taskbell.history_layout import month_grid_days, shift_period, completed_counts_by_day


class DoneCalendarTests(unittest.TestCase):
    def test_calendar_grid_is_monday_first_and_ends_correctly(self):
        weeks = month_grid_days(2026, 10)
        self.assertEqual(weeks[0], [0, 0, 0, 1, 2, 3, 4])
        self.assertEqual(weeks[-1], [26, 27, 28, 29, 30, 31, 0])

    def test_day_arrows_cross_month(self):
        self.assertEqual(shift_period(date(2026, 10, 31), 'day', 1), date(2026, 11, 1))
        self.assertEqual(shift_period(date(2026, 11, 1), 'day', -1), date(2026, 10, 31))

    def test_month_arrows_cross_year(self):
        self.assertEqual(shift_period(date(2026, 12, 20), 'month', 1), date(2027, 1, 1))
        self.assertEqual(shift_period(date(2027, 1, 20), 'month', -1), date(2026, 12, 1))

    def test_day_counts_show_only_actual_completion_dates(self):
        from datetime import datetime
        one = int(datetime(2026, 10, 29, 8).timestamp())
        two = int(datetime(2026, 10, 31, 9).timestamp())
        entries = [SimpleNamespace(completed_ts=one), SimpleNamespace(completed_ts=one + 60),
                   SimpleNamespace(completed_ts=two)]
        self.assertEqual(completed_counts_by_day(entries), {29: 2, 31: 1})


if __name__ == '__main__':
    unittest.main()
