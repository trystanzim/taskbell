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
