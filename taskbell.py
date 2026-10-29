#!/usr/bin/env python3
"""TaskBell launcher and command line management for Zorin/GNOME."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime


def cli(argv: list[str]) -> int:
    from taskbell.store import TaskStore

    store = TaskStore()
    parser = argparse.ArgumentParser(description="TaskBell task manager")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add", help="Add a task to the checklist")
    add.add_argument("title")
    add.add_argument("--at", help="Local date/time in YYYY-MM-DD HH:MM format")
    add.add_argument("--notes", default="")
    add.add_argument("--repeat", choices=("none", "daily", "weekdays"), default="none")
    sub.add_parser("list", help="List current tasks")
    sub.add_parser("seed-test", help="Import the two requested Odoo work items")
    args = parser.parse_args(argv)
    if args.command == "add":
        due = int(datetime.strptime(args.at, "%Y-%m-%d %H:%M").timestamp()) if args.at else None
        task = store.add_task(args.title, due_ts=due, recurrence=args.repeat, notes=args.notes)
        print(f"Added task #{task.id}: {task.title}")
    elif args.command == "list":
        for task in store.list_tasks():
            due = datetime.fromtimestamp(task.due_ts).strftime("%Y-%m-%d %I:%M %p") if task.due_ts else "unscheduled"
            print(f"#{task.id} | {due} | {task.title}")
    elif args.command == "seed-test":
        entries = [
            ("Investigate Odoo product search", "2026-10-29 08:00",
             "Verify starlight_product_search is installed; test Sales Orders, Purchase, Inventory and Invoicing. Check Catalog SKU and single-word search."),
            ("AI call summaries and ticket linking", "2026-10-29 09:00",
             "Research call summarization and link call logs to Odoo tickets created manually or automatically, including port-in tickets."),
        ]
        for title, at, notes in entries:
            due = int(datetime.strptime(at, "%Y-%m-%d %H:%M").timestamp())
            task = store.ensure_task(title, due_ts=due, notes=notes)
            print(f"Task #{task.id}: {task.title}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("add", "list", "seed-test"):
        sys.exit(cli(sys.argv[1:]))
    from taskbell.ui import run
    sys.exit(run(sys.argv))
