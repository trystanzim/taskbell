import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from taskbell.store import TaskStore, next_due_after


class TaskStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = TaskStore(Path(self.temp.name) / "tasks.db")

    def test_add_and_list_orders_by_due(self):
        second = self.store.add_task("Second", due_ts=200)
        first = self.store.add_task("First", due_ts=100)
        self.assertEqual([t.id for t in self.store.list_tasks()], [first.id, second.id])
        self.assertEqual(self.store.list_tasks()[0].title, "First")

    def test_due_tasks_are_only_notified_once(self):
        self.store.add_task("Due", due_ts=100)
        self.store.add_task("Later", due_ts=500)
        self.assertEqual([t.title for t in self.store.claim_due(now=120)], ["Due"])
        self.assertEqual(self.store.claim_due(now=121), [])
        self.assertEqual(self.store.claim_due(now=501)[0].title, "Later")

    def test_snooze_reschedules_and_alerts_again(self):
        t = self.store.add_task("Due", due_ts=100)
        self.store.claim_due(now=120)
        self.store.snooze_due(now=120, minutes=10)
        self.assertEqual(self.store.claim_due(now=719), [])
        self.assertEqual([x.id for x in self.store.claim_due(now=720)], [t.id])

    def test_mark_complete_hides_one_time_task(self):
        task = self.store.add_task("Task", due_ts=100)
        self.store.complete_task(task.id, now=120)
        self.assertEqual(self.store.list_tasks(), [])
        self.assertEqual(len(self.store.list_tasks(include_completed=True)), 1)

    def test_repeating_daily_task_moves_to_future_on_completion(self):
        start = int(datetime(2026, 10, 29, 8, 0).timestamp())
        now = int(datetime(2026, 10, 29, 8, 30).timestamp())
        t = self.store.add_task("Daily", due_ts=start, recurrence="daily")
        self.store.claim_due(now=now)
        self.store.complete_task(t.id, now=now)
        task = self.store.list_tasks()[0]
        self.assertFalse(task.completed)
        self.assertEqual(datetime.fromtimestamp(task.due_ts).hour, 8)
        self.assertEqual(datetime.fromtimestamp(task.due_ts).day, 30)
        self.assertEqual(self.store.claim_due(now=now), [])

    def test_weekday_recurring_skips_weekend(self):
        fri = int(datetime(2026, 10, 30, 9, 0).timestamp())
        monday = datetime.fromtimestamp(next_due_after(fri, "weekdays", fri)).date()
        self.assertEqual(monday.isoformat(), "2026-11-02")

    def test_prevent_duplicate_seeded_tasks(self):
        one = self.store.ensure_task("First", due_ts=100)
        two = self.store.ensure_task("First", due_ts=100)
        self.assertEqual(one.id, two.id)
        self.assertEqual(len(self.store.list_tasks()), 1)

    def test_invalid_reminder_and_repeat_are_rejected(self):
        with self.assertRaises(ValueError):
            self.store.add_task("", due_ts=50)
        with self.assertRaises(ValueError):
            self.store.add_task("Ok", recurrence="unknown", due_ts=50)
        with self.assertRaises(ValueError):
            self.store.add_task("Ok", recurrence="daily")

    def test_delete_and_undo_complete(self):
        task = self.store.add_task("One", due_ts=100)
        self.store.complete_task(task.id, now=120)
        self.store.reopen_task(task.id, due_ts=150)
        self.assertEqual(self.store.list_tasks()[0].due_ts, 150)
        self.store.delete_task(task.id)
        self.assertEqual(self.store.list_tasks(include_completed=True), [])


if __name__ == "__main__":
    unittest.main()
