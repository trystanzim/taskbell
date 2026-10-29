"""Missed-reminder recovery and consolidated reminder scheduling."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from taskbell.reminders import ReminderScheduler
from taskbell.store import TaskStore


class ReminderSchedulerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = TaskStore(Path(temp.name) / "tasks.db")

    def test_one_hour_late_login_displays_overdue_task(self):
        self.store.add_task("Odoo product search", due_ts=8 * 60 * 60)
        scheduler = ReminderScheduler(self.store)
        self.assertEqual([task.title for task in scheduler.scan(now=9 * 60 * 60)],
                         ["Odoo product search"])
        self.assertEqual(scheduler.scan(now=9 * 60 * 60 + 15), [])

    def test_login_recovers_uncompleted_reminder_claimed_before_shutdown(self):
        task = self.store.add_task("Finish call summaries", due_ts=100)
        self.assertEqual([t.id for t in self.store.claim_due(now=101)], [task.id])
        first_boot = ReminderScheduler(self.store)
        self.assertEqual([t.id for t in first_boot.scan(now=200)], [task.id])
        self.assertEqual(first_boot.scan(now=215), [])
        after_reboot = ReminderScheduler(TaskStore(self.store.path))
        self.assertEqual([t.id for t in after_reboot.scan(now=500)], [task.id])

    def test_three_days_offline_collapse_multiple_tasks_into_one_reminder_batch(self):
        start = int(datetime(2026, 10, 25, 8, 0).timestamp())
        boot = int(datetime(2026, 10, 29, 9, 0).timestamp())
        daily = self.store.add_task("Daily check-in", due_ts=start, recurrence="daily")
        onetime = self.store.add_task("Fix product search", due_ts=start + 60)
        scheduler = ReminderScheduler(self.store)
        batch = scheduler.scan(now=boot)
        self.assertEqual({t.id for t in batch}, {daily.id, onetime.id})
        self.assertEqual(len(batch), 2)  # One row per task, not once per missed day.
        self.assertEqual(scheduler.scan(now=boot + 15), [])
        self.store.complete_task(daily.id, now=boot)
        next_occurrence = self.store.list_tasks()[0]
        self.assertEqual(next_occurrence.id, onetime.id)  # Already-due task retained.
        repeating = [t for t in self.store.list_tasks() if t.id == daily.id][0]
        self.assertEqual(datetime.fromtimestamp(repeating.due_ts).date().isoformat(), "2026-10-30")
        self.assertEqual([t.id for t in ReminderScheduler(self.store).scan(now=boot + 30)],
                         [onetime.id])

    def test_snoozed_reminders_do_not_reopen_on_reboot_before_new_due_time(self):
        task = self.store.add_task("Phone work", due_ts=100)
        scheduler = ReminderScheduler(self.store)
        self.assertEqual([t.id for t in scheduler.scan(now=120)], [task.id])
        self.store.snooze_due(now=120, minutes=10)
        self.assertEqual(ReminderScheduler(self.store).scan(now=300), [])
        self.assertEqual([t.id for t in ReminderScheduler(self.store).scan(now=720)], [task.id])

    def test_newly_due_task_creates_one_new_batch_during_running_session(self):
        self.store.add_task("Early", due_ts=100)
        second = self.store.add_task("Later", due_ts=300)
        scheduler = ReminderScheduler(self.store)
        self.assertEqual(len(scheduler.scan(now=200)), 1)
        self.assertEqual([t.id for t in scheduler.scan(now=301)], [second.id])
        self.assertEqual(scheduler.scan(now=400), [])

    def test_completed_task_is_not_replayed_after_reboot(self):
        task = self.store.add_task("Done", due_ts=100)
        self.assertEqual(len(ReminderScheduler(self.store).scan(now=150)), 1)
        self.store.complete_task(task.id, now=151)
        self.assertEqual(ReminderScheduler(self.store).scan(now=400), [])


if __name__ == "__main__":
    unittest.main()
