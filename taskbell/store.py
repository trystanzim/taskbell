"""SQLite task persistence and occurrence scheduling (no GUI dependencies)."""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

VALID_RECURRENCES = frozenset(("none", "daily", "weekdays"))


def data_directory() -> Path:
    return Path(os.getenv("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "taskbell"


@dataclass(frozen=True)
class Task:
    id: int
    title: str
    notes: str
    due_ts: int | None
    recurrence: str
    completed: bool
    notified_ts: int | None


def next_due_after(previous_ts: int, recurrence: str, now: int) -> int:
    """Advance a daily/weekday task in the computer's local timezone."""
    if recurrence not in ("daily", "weekdays"):
        raise ValueError("Only recurring tasks have a next due time")
    date = datetime.fromtimestamp(previous_ts)
    date += timedelta(days=1)
    # Skip elapsed occurrences; preserve the wall-clock hour across DST changes.
    while date.timestamp() <= now or (recurrence == "weekdays" and date.weekday() >= 5):
        date += timedelta(days=1)
    return int(date.timestamp())


class TaskStore:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path is not None else data_directory() / "tasks.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                due_ts INTEGER,
                recurrence TEXT NOT NULL DEFAULT 'none',
                completed INTEGER NOT NULL DEFAULT 0,
                notified_ts INTEGER,
                created_ts INTEGER NOT NULL
            )""")

    def _db(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _task(row):
        return Task(row["id"], row["title"], row["notes"], row["due_ts"],
                    row["recurrence"], bool(row["completed"]), row["notified_ts"])

    def add_task(self, title: str, due_ts: int | None = None,
                 recurrence: str = "none", notes: str = "") -> Task:
        title = title.strip()
        if not title:
            raise ValueError("Task title is required")
        if recurrence not in VALID_RECURRENCES:
            raise ValueError("Invalid recurrence")
        if recurrence != "none" and due_ts is None:
            raise ValueError("Repeating tasks require a reminder time")
        with self._db() as conn:
            cursor = conn.execute("""INSERT INTO tasks
                (title, notes, due_ts, recurrence, created_ts)
                VALUES (?, ?, ?, ?, ?)""",
                (title, notes.strip(), due_ts, recurrence, int(time.time())))
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return self._task(row)

    def ensure_task(self, title: str, due_ts: int | None = None,
                    recurrence: str = "none", notes: str = "") -> Task:
        with self._db() as conn:
            row = conn.execute("""SELECT * FROM tasks
                WHERE title = ? AND due_ts IS ? AND recurrence = ? LIMIT 1""",
                (title.strip(), due_ts, recurrence)).fetchone()
        return self._task(row) if row else self.add_task(title, due_ts, recurrence, notes)

    def list_tasks(self, include_completed: bool = False) -> list[Task]:
        condition = "" if include_completed else "WHERE completed = 0"
        with self._db() as conn:
            rows = conn.execute(f"""SELECT * FROM tasks {condition}
                ORDER BY due_ts IS NULL, due_ts, id""").fetchall()
        return [self._task(row) for row in rows]

    def overdue_tasks(self, now: int | None = None) -> list[Task]:
        """All incomplete overdue tasks, even ones alerted before shutdown.

        Results contain each task once, regardless of how many scheduled
        occurrences were missed while the machine was powered off.
        """
        if now is None:
            now = int(time.time())
        with self._db() as conn:
            rows = conn.execute("""SELECT * FROM tasks
                WHERE completed = 0 AND due_ts IS NOT NULL AND due_ts <= ?
                ORDER BY due_ts, id""", (now,)).fetchall()
        return [self._task(row) for row in rows]

    def claim_due(self, now: int | None = None) -> list[Task]:
        """Atomically claim reminders so they are not repeatedly displayed."""
        if now is None:
            now = int(time.time())
        conn = self._db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("""SELECT * FROM tasks
                WHERE completed = 0 AND due_ts IS NOT NULL AND due_ts <= ?
                AND (notified_ts IS NULL OR notified_ts < due_ts)
                ORDER BY due_ts, id""", (now,)).fetchall()
            if rows:
                conn.executemany("UPDATE tasks SET notified_ts = ? WHERE id = ?",
                                 [(now, row["id"]) for row in rows])
            conn.commit()
            return [self._task(row) for row in rows]
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def snooze_due(self, now: int | None = None, minutes: int = 10) -> int:
        if now is None:
            now = int(time.time())
        if minutes < 1:
            raise ValueError("Snooze must be at least one minute")
        with self._db() as conn:
            result = conn.execute("""UPDATE tasks SET due_ts = ?, notified_ts = NULL
                WHERE completed = 0 AND due_ts IS NOT NULL AND due_ts <= ?""",
                (now + minutes * 60, now))
            return result.rowcount

    def complete_task(self, task_id: int, now: int | None = None):
        if now is None:
            now = int(time.time())
        with self._db() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                raise KeyError(task_id)
            if row["recurrence"] != "none" and row["due_ts"] is not None:
                next_ts = next_due_after(row["due_ts"], row["recurrence"], now)
                conn.execute("""UPDATE tasks SET completed = 0, due_ts = ?, notified_ts = NULL
                    WHERE id = ?""", (next_ts, task_id))
            else:
                conn.execute("UPDATE tasks SET completed = 1 WHERE id = ?", (task_id,))

    def reopen_task(self, task_id: int, due_ts: int | None = None):
        with self._db() as conn:
            conn.execute("""UPDATE tasks SET completed = 0, due_ts = ?, notified_ts = NULL
                WHERE id = ?""", (due_ts, task_id))

    def delete_task(self, task_id: int):
        with self._db() as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
