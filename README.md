# TaskBell

A small, locally stored task checklist and scheduled popup reminder for GNOME-based Linux desktops such as **Zorin OS 18**.

## Features

- An actual checklist popup with clickable task completion checkboxes
- Desktop notification plus **a single consolidated checklist window** at reminder time
- Late startup catch-up: if the computer was off when a reminder was due, overdue tasks appear at the next login
- Uncompleted reminders are recovered after a reboot, even if the earlier notification was missed
- No stacks of windows: several overdue reminders (including missed recurring days) share one window and one notification
- One-time, daily, or weekday reminders, with snooze for 10 minutes
- Task creation, notes, and deletion from the app window
- Automatic background startup at graphical login (no terminal window)
- Local SQLite data in `~/.local/share/taskbell/tasks.db`; no account or cloud required
- Launch from the app grid or use `taskbell.py --show`

## Requirements

Python 3, PyGObject (GI), GTK4, libadwaita. Available by default on the verified Zorin OS 18.1 machine.

## Installation

From the extracted source folder, run `bash install.sh`. No root permission is required.

To verify after installation, run `python3 ~/.local/share/taskbell/app/taskbell.py seed-test` to import the two requested work items, then launch `python3 ~/.local/share/taskbell/app/taskbell.py --test-popup`.

The task service starts at your next graphical login, and normally runs without a visible terminal.

## Usage

```bash
python3 taskbell.py --show
python3 taskbell.py --background
python3 taskbell.py --test-popup
python3 taskbell.py add 'Follow up with customer' --at '2026-10-29 11:30'
python3 taskbell.py list
python3 taskbell.py seed-test
python3 -m unittest discover -s tests -v
```

The installer creates a startup entry in `~/.config/autostart/`, and the launcher lives in `~/.local/share/applications/`. Reminder popups require an active graphical login session. When the computer is off, due tasks are retained in SQLite and the **one** reminder window is shown after the next login. When the screen is locked, the desktop may delay showing notifications/windows until it is unlocked.

Closing the window hides it without losing tasks. On the next application startup, any still-overdue open tasks are shown again; during a running session, each reminder is alerted at most once until snoozed or advanced. Recurring tasks do not generate a backlog of one item per missed day.

## Source and license

Original Python source, licensed MIT (see LICENSE). Built with open-source Python 3, GTK4, libadwaita and SQLite. Open-source applications referenced as design/background examples, with **no code copied**: [Planify](https://github.com/alainm23/planify), [GNOME Reminders](https://github.com/remindersdevs/Reminders), and [KAlarm](https://invent.kde.org/pim/kalarm). The GitHub repository may be private while code remains locally licensed as MIT.

## Done history (v1.1)

Marking a one-time task complete moves it from **To Do** to **Done**; the
original task and a dated completion snapshot remain in local SQLite storage.
The Done tab offers **Day** and **Month** views, previous/next navigation,
Today, and a clickable month grid with counts per day. A completed one-time
task has a **Restore** button to return it to To Do.

For recurring tasks, each *actual* completion is recorded in Done, and the
next reminder stays in To Do. Missed days do not create fake completion
history, and deleting a recurring task leaves its completed work in Done.
Existing databases are upgraded without deleting any tasks; any tasks
completed before this feature existed are labeled as imported, since the
old database did not record the original completion date.
