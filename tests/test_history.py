"""Completed work stays accessible; each recurrence leaves an audit entry."""

import sqlite3
from contextlib import closing
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from taskbell.store import TaskStore


class CompletedHistoryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'tasks.db'
        self.store = TaskStore(self.path)

    def test_completed_one_time_task_is_in_done_day_and_month(self):
        when = int(datetime(2026, 10, 29, 14, 12).timestamp())
        item = self.store.add_task('Fix Odoo search', notes='Search by SKU', due_ts=when - 3600)
        self.store.complete_task(item.id, now=when)
        self.assertEqual(self.store.list_tasks(), [])
        today = self.store.list_completions(day=date(2026, 10, 29))
        self.assertEqual(len(today), 1)
        self.assertEqual(today[0].title, 'Fix Odoo search')
        self.assertEqual(today[0].notes, 'Search by SKU')
        self.assertEqual(today[0].completed_ts, when)
        self.assertEqual(today[0].task_id, item.id)
        self.assertEqual(len(self.store.list_completions(month=date(2026, 10, 1))), 1)
        self.assertEqual(self.store.list_completions(day=date(2026, 10, 30)), [])

    def test_repeated_complete_on_one_time_task_does_not_duplicate_history(self):
        item = self.store.add_task('Once', due_ts=100)
        self.store.complete_task(item.id, now=120)
        self.store.complete_task(item.id, now=121)
        self.assertEqual(len(self.store.list_completions()), 1)
        self.assertEqual(self.store.list_completions()[0].completed_ts, 120)

    def test_recurring_task_records_every_real_completion(self):
        morning = int(datetime(2026, 10, 29, 8).timestamp())
        item = self.store.add_task('Daily report', due_ts=morning, recurrence='daily')
        first = int(datetime(2026, 10, 29, 9).timestamp())
        second = int(datetime(2026, 10, 30, 9).timestamp())
        self.store.complete_task(item.id, now=first)
        self.store.complete_task(item.id, now=second)
        entries = self.store.list_completions(month=date(2026, 10, 1))
        self.assertEqual([entry.completed_ts for entry in entries], [second, first])
        self.assertTrue(all(entry.task_id == item.id for entry in entries))
        self.assertEqual([t.title for t in self.store.list_tasks()], ['Daily report'])
        self.assertEqual(len(self.store.list_completions(day=date(2026, 10, 29))), 1)
        self.assertEqual(len(self.store.list_completions(day=date(2026, 10, 30))), 1)

    def test_offline_days_do_not_create_fake_completion_history(self):
        due = int(datetime(2026, 10, 25, 8).timestamp())
        done = int(datetime(2026, 10, 29, 9).timestamp())
        item = self.store.add_task('Catch up', due_ts=due, recurrence='daily')
        self.store.complete_task(item.id, now=done)
        self.assertEqual(len(self.store.list_completions(month=date(2026, 10, 1))), 1)
        self.assertEqual(len(self.store.list_completions(day=date(2026, 10, 25))), 0)

    def test_month_and_day_queries_respect_midnight_boundaries(self):
        october = int(datetime(2026, 10, 31, 23, 59).timestamp())
        november = int(datetime(2026, 11, 1, 0, 0).timestamp())
        first = self.store.add_task('October')
        second = self.store.add_task('November')
        self.store.complete_task(first.id, now=october)
        self.store.complete_task(second.id, now=november)
        self.assertEqual([x.title for x in self.store.list_completions(month=date(2026, 10, 1))], ['October'])
        self.assertEqual([x.title for x in self.store.list_completions(month=date(2026, 11, 1))], ['November'])
        self.assertEqual([x.title for x in self.store.list_completions(day=date(2026, 11, 1))], ['November'])

    def test_restore_one_time_task_from_done_returns_it_to_todo(self):
        item = self.store.add_task('Bring back', due_ts=123)
        self.store.complete_task(item.id, now=200)
        event = self.store.list_completions()[0]
        self.store.undo_completion(event.id)
        self.assertEqual([t.id for t in self.store.list_tasks()], [item.id])
        self.assertEqual(self.store.list_tasks()[0].due_ts, 123)
        self.assertEqual(self.store.list_completions(), [])

    def test_only_one_time_completion_can_be_restored(self):
        due = int(datetime(2026, 10, 29, 8).timestamp())
        item = self.store.add_task('Repeat', recurrence='daily', due_ts=due)
        self.store.complete_task(item.id, now=due + 60)
        with self.assertRaises(ValueError):
            self.store.undo_completion(self.store.list_completions()[0].id)
        self.assertEqual(len(self.store.list_completions()), 1)

    def test_deleting_recurring_task_does_not_erase_its_done_history(self):
        due = int(datetime(2026, 10, 29, 8).timestamp())
        item = self.store.add_task('Track repeat', recurrence='daily', due_ts=due)
        self.store.complete_task(item.id, now=due + 60)
        self.store.delete_task(item.id)
        self.assertEqual(self.store.list_tasks(), [])
        self.assertEqual(self.store.list_completions()[0].title, 'Track repeat')

    def test_existing_reopen_method_removes_one_time_done_entry(self):
        item = self.store.add_task('Restore legacy')
        self.store.complete_task(item.id, now=200)
        self.store.reopen_task(item.id, due_ts=300)
        self.assertEqual(self.store.list_completions(), [])
        self.assertEqual(self.store.list_tasks()[0].due_ts, 300)

    def test_existing_database_migration_preserves_completed_tasks_without_fake_date(self):
        old_file = self.path.parent / 'legacy.db'
        with closing(sqlite3.connect(old_file)) as db:
            db.execute('''CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '', due_ts INTEGER,
                recurrence TEXT NOT NULL DEFAULT 'none', completed INTEGER NOT NULL DEFAULT 0,
                notified_ts INTEGER, created_ts INTEGER NOT NULL)''')
            db.execute("""INSERT INTO tasks VALUES
                (41, 'Finished before upgrade', '', 100, 'none', 1, 120, 120),
                (42, 'Still open', '', 200, 'none', 0, NULL, 120)""")
            db.commit()
        upgraded = TaskStore(old_file)
        done = upgraded.list_completions()
        self.assertEqual([x.title for x in done], ['Finished before upgrade'])
        self.assertTrue(done[0].imported)
        self.assertEqual([t.title for t in upgraded.list_tasks()], ['Still open'])
        self.assertEqual(len(TaskStore(old_file).list_completions()), 1)


if __name__ == '__main__':
    unittest.main()
