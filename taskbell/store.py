"""SQLite task persistence, scheduling, and durable completion history."""

from __future__ import annotations

import os
from contextlib import contextmanager
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
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


@dataclass(frozen=True)
class CompletedTask:
    """A snapshot of one actual completion, including recurring occurrences."""

    id: int
    task_id: int
    title: str
    notes: str
    due_ts: int | None
    completed_ts: int
    recurrence: str
    imported: bool
    can_restore: bool


def next_due_after(previous_ts: int, recurrence: str, now: int) -> int:
    """Advance a daily/weekday task in the computer's local timezone."""
    if recurrence not in ("daily", "weekdays"):
        raise ValueError("Only recurring tasks have a next due time")
    day = datetime.fromtimestamp(previous_ts) + timedelta(days=1)
    # Skip elapsed occurrences; preserve the wall-clock hour across DST changes.
    while day.timestamp() <= now or (recurrence == "weekdays" and day.weekday() >= 5):
        day += timedelta(days=1)
    return int(day.timestamp())


def _day_range(day: date) -> tuple[int, int]:
    start = int(datetime(day.year, day.month, day.day).timestamp())
    tomorrow = day + timedelta(days=1)
    end = int(datetime(tomorrow.year, tomorrow.month, tomorrow.day).timestamp())
    return start, end


def _month_range(month: date) -> tuple[int, int]:
    start = int(datetime(month.year, month.month, 1).timestamp())
    next_month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    end = int(datetime(next_month.year, next_month.month, 1).timestamp())
    return start, end


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
            conn.execute("""CREATE TABLE IF NOT EXISTS task_completions (
                id INTEGER PRIMARY KEY,
                task_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                due_ts INTEGER,
                completed_ts INTEGER NOT NULL,
                recurrence TEXT NOT NULL,
                imported INTEGER NOT NULL DEFAULT 0
            )""")
            conn.execute("""CREATE INDEX IF NOT EXISTS task_completions_by_date
                ON task_completions (completed_ts DESC, id DESC)""")
            # Pre-upgrade completed tasks had no completion timestamps. Keep
            # them visible, explicitly marked as imported/undated, rather
            # than inventing their original completion date. Idempotent.
            conn.execute("""INSERT INTO task_completions
                (task_id, title, notes, due_ts, completed_ts, recurrence, imported)
                SELECT t.id, t.title, t.notes, t.due_ts, ?, t.recurrence, 1
                FROM tasks AS t WHERE t.completed = 1
                AND NOT EXISTS (SELECT 1 FROM task_completions AS c WHERE c.task_id = t.id)""",
                (int(time.time()),))

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _db(self):
        conn = self._connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _task(row):
        return Task(row["id"], row["title"], row["notes"], row["due_ts"],
                    row["recurrence"], bool(row["completed"]), row["notified_ts"])

    @staticmethod
    def _completion(row):
        return CompletedTask(row["id"], row["task_id"], row["title"], row["notes"],
                             row["due_ts"], row["completed_ts"], row["recurrence"],
                             bool(row["imported"]), bool(row["can_restore"]))

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

    def list_completions(self, *, day: date | None = None,
                         month: date | None = None) -> list[CompletedTask]:
        """Return saved work for the selected local day or calendar month."""
        if day is not None and month is not None:
            raise ValueError("Select either a day or a month")
        start_end = _day_range(day) if day is not None else (
            _month_range(month) if month is not None else None
        )
        condition = ""
        params: tuple[int, int] = ()
        if start_end:
            condition = "WHERE c.completed_ts >= ? AND c.completed_ts < ?"
            params = start_end
        with self._db() as conn:
            rows = conn.execute(f"""SELECT c.*, (t.completed = 1 AND t.recurrence = 'none') AS can_restore
                FROM task_completions AS c LEFT JOIN tasks AS t ON t.id = c.task_id
                {condition} ORDER BY c.completed_ts DESC, c.id DESC""", params).fetchall()
        return [self._completion(row) for row in rows]

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
        conn = self._connect()
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
        """Move a single completion to Done, preserving recurring history."""
        if now is None:
            now = int(time.time())
        with self._db() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                raise KeyError(task_id)
            if row["completed"]:
                return  # A one-time task already in Done; avoid duplicate events.
            conn.execute("""INSERT INTO task_completions
                (task_id, title, notes, due_ts, completed_ts, recurrence)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (task_id, row["title"], row["notes"], row["due_ts"], now, row["recurrence"]))
            if row["recurrence"] != "none" and row["due_ts"] is not None:
                next_ts = next_due_after(row["due_ts"], row["recurrence"], now)
                conn.execute("""UPDATE tasks SET completed = 0, due_ts = ?, notified_ts = NULL
                    WHERE id = ?""", (next_ts, task_id))
            else:
                conn.execute("UPDATE tasks SET completed = 1 WHERE id = ?", (task_id,))

    def undo_completion(self, completion_id: int):
        """Restore a one-time task to To Do and remove that completed entry."""
        with self._db() as conn:
            record = conn.execute("""SELECT c.task_id, c.recurrence, t.completed
                FROM task_completions c LEFT JOIN tasks t ON t.id = c.task_id
                WHERE c.id = ?""", (completion_id,)).fetchone()
            if record is None:
                raise KeyError(completion_id)
            if record["recurrence"] != "none" or record["completed"] != 1:
                raise ValueError("Only an existing one-time task can be restored")
            conn.execute("""UPDATE tasks SET completed = 0, notified_ts = NULL
                WHERE id = ?""", (record["task_id"],))
            conn.execute("DELETE FROM task_completions WHERE id = ?", (completion_id,))

    def reopen_task(self, task_id: int, due_ts: int | None = None):
        # Legacy API: clear existing one-time completion history on reopen.
        with self._db() as conn:
            conn.execute("""UPDATE tasks SET completed = 0, due_ts = ?, notified_ts = NULL
                WHERE id = ?""", (due_ts, task_id))
            conn.execute("""DELETE FROM task_completions WHERE task_id = ?
                AND recurrence = 'none'""", (task_id,))

    def delete_task(self, task_id: int):
        # Keep completion snapshots, including past recurring occurrences.
        with self._db() as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
