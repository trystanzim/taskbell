"""Consolidate missed reminders without replaying missed days."""

from __future__ import annotations

import time

from .store import Task, TaskStore


class ReminderScheduler:
    """One reminder batch per scan; initial scan recovers incomplete alerts.

    The resident process polls for newly due tasks. Its first scan after
    launch additionally recovers all overdue tasks, even if a previous run
    marked them notified before a crash or shutdown. Each task is returned
    at most once per scan, not once for every missed recurring occurrence.
    """

    def __init__(self, store: TaskStore):
        self.store = store
        self._startup_scanned = False

    def scan(self, now: int | None = None) -> list[Task]:
        if now is None:
            now = int(time.time())
        if not self._startup_scanned:
            overdue = self.store.overdue_tasks(now)
            self.store.claim_due(now)
            self._startup_scanned = True
            return overdue
        return self.store.claim_due(now)
