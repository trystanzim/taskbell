"""Small native GTK4 reminder window and resident scheduler."""

from __future__ import annotations

import subprocess
import time
from datetime import datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from .reminders import ReminderScheduler
from .store import TaskStore

APP_ID = "io.github.trystanzim.TaskBell"

STYLE = """
.task-title {font-size: 26px; font-weight: 700;}
.task-subtitle {font-size: 13px; opacity: 0.72;}
.task-row {padding: 13px 12px; border-bottom: 1px solid alpha(currentColor, 0.09);}
.task-name {font-weight: 600; font-size: 15px;}
.task-detail {font-size: 12px; opacity: 0.72;}
.task-warning {color: #d35400;}
.task-list {background: transparent;}
.task-error {color: #d63031;}
.add-panel {padding: 12px;}
"""


def format_due(due_ts: int | None) -> str:
    if due_ts is None:
        return "No reminder set"
    due = datetime.fromtimestamp(due_ts)
    date = due.date()
    today = datetime.now().date()
    if date == today:
        date_label = "Today"
    elif (date - today).days == 1:
        date_label = "Tomorrow"
    else:
        date_label = due.strftime("%b %-d")
    return f"{date_label} · {due.strftime('%-I:%M %p')}"


class TaskBellApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.store = TaskStore()
        self.scheduler = ReminderScheduler(self.store)
        self.window = None
        self.list_box = None
        self.subtitle = None
        self.error_label = None
        self.title_entry = None
        self.due_entry = None
        self.notes_entry = None
        self.repeat_combo = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(STYLE.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_display(
            self.get_active_display() if hasattr(self, "get_active_display") else
            __import__("gi.repository", fromlist=["Gdk"]).Gdk.Display.get_default(),
            provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        # Keep one background process running when the window is closed.
        self.hold()
        GLib.timeout_add_seconds(15, self._scan_reminders)

    def do_command_line(self, command_line):
        args = [str(x) for x in command_line.get_arguments()]
        if "--test-popup" in args:
            self.activate()
            self._notify("TaskBell test", "Your task checklist is ready.")
        else:
            if "--background" not in args:
                self.activate()
            # Catch up immediately at login, not 15 seconds later.
            self._scan_reminders()
        return 0

    def do_activate(self):
        if self.window is None:
            self._build_window()
        self.refresh()
        self.window.present()

    def _notify(self, title: str, body: str):
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        notification.set_default_action("app.activate")
        self.send_notification("taskbell-due", notification)

    def _scan_reminders(self):
        try:
            due = self.scheduler.scan()
            if due:
                count = len(due)
                self._notify("TaskBell reminder", f"{count} task{'s' if count != 1 else ''} waiting in your checklist")
                self.activate()
        except Exception as exc:
            print(f"TaskBell scheduler error: {exc}", flush=True)
        return GLib.SOURCE_CONTINUE

    def _build_window(self):
        self.window = Adw.ApplicationWindow(application=self)
        # Hide instead of destroying, so every reminder reuses one window.
        self.window.connect("close-request", self._hide_on_close)
        self.window.set_title("TaskBell — Your tasks")
        self.window.set_default_size(630, 575)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label="TaskBell"))
        root.append(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_start(22)
        content.set_margin_end(22)
        content.set_margin_top(20)
        content.set_margin_bottom(16)

        heading = Gtk.Label(label="Your task checklist", xalign=0)
        heading.add_css_class("task-title")
        content.append(heading)
        self.subtitle = Gtk.Label(xalign=0)
        self.subtitle.add_css_class("task-subtitle")
        content.append(self.subtitle)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.list_box = Gtk.ListBox()
        self.list_box.add_css_class("boxed-list")
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll.set_child(self.list_box)
        content.append(scroll)

        expander = Gtk.Expander(label="Add a task")
        expander.set_expanded(False)
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        panel.add_css_class("add-panel")

        self.title_entry = Gtk.Entry(placeholder_text="Task name")
        self.title_entry.connect("activate", self._add_task)
        panel.append(self.title_entry)
        self.notes_entry = Gtk.Entry(placeholder_text="Notes (optional)")
        panel.append(self.notes_entry)
        self.due_entry = Gtk.Entry(placeholder_text="Reminder: YYYY-MM-DD HH:MM (optional)")
        panel.append(self.due_entry)

        form_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.repeat_combo = Gtk.ComboBoxText()
        for key, label in [("none", "One time"), ("daily", "Every day"), ("weekdays", "Weekdays")]:
            self.repeat_combo.append(key, label)
        self.repeat_combo.set_active_id("none")
        self.repeat_combo.set_hexpand(True)
        form_bottom.append(self.repeat_combo)
        add = Gtk.Button(label="Add task")
        add.add_css_class("suggested-action")
        add.connect("clicked", self._add_task)
        form_bottom.append(add)
        panel.append(form_bottom)
        self.error_label = Gtk.Label(xalign=0)
        self.error_label.add_css_class("task-error")
        self.error_label.set_wrap(True)
        panel.append(self.error_label)
        expander.set_child(panel)
        content.append(expander)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        snooze = Gtk.Button(label="Snooze due tasks 10 min")
        snooze.connect("clicked", self._snooze)
        footer.append(snooze)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        footer.append(spacer)
        close = Gtk.Button(label="Close")
        close.connect("clicked", lambda _b: self.window.set_visible(False))
        footer.append(close)
        content.append(footer)
        root.append(content)
        self.window.set_content(root)

    def _hide_on_close(self, _window):
        self.window.set_visible(False)
        return True

    def _task_row(self, task):
        row = Gtk.ListBoxRow()
        row.set_activatable(False)
        line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=13)
        line.add_css_class("task-row")
        check = Gtk.CheckButton()
        check.set_valign(Gtk.Align.CENTER)
        check.set_tooltip_text("Mark completed")
        check.connect("toggled", self._complete, task.id)
        line.append(check)

        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        details.set_hexpand(True)
        title = Gtk.Label(label=task.title, xalign=0)
        title.set_wrap(True)
        title.add_css_class("task-name")
        details.append(title)
        info = format_due(task.due_ts)
        if task.recurrence == "daily":
            info += " · Daily"
        elif task.recurrence == "weekdays":
            info += " · Weekdays"
        if task.notes:
            info += f" · {task.notes}"
        description = Gtk.Label(label=info, xalign=0)
        description.set_wrap(True)
        description.add_css_class("task-detail")
        if task.due_ts is not None and task.due_ts <= int(time.time()):
            description.add_css_class("task-warning")
        details.append(description)
        line.append(details)

        delete = Gtk.Button.new_from_icon_name("user-trash-symbolic")
        delete.add_css_class("flat")
        delete.set_tooltip_text("Delete task")
        delete.set_valign(Gtk.Align.CENTER)
        delete.connect("clicked", self._delete, task.id)
        line.append(delete)
        row.set_child(line)
        return row

    def refresh(self):
        if self.list_box is None:
            return
        while child := self.list_box.get_first_child():
            self.list_box.remove(child)
        tasks = self.store.list_tasks()
        for task in tasks:
            self.list_box.append(self._task_row(task))
        if not tasks:
            label = Gtk.Label(label="All clear. Add a task when you need one.")
            label.set_margin_top(45)
            label.set_margin_bottom(45)
            self.list_box.append(label)
        due = sum(1 for t in tasks if t.due_ts is not None and t.due_ts <= int(time.time()))
        self.subtitle.set_text(f"{len(tasks)} open task{'s' if len(tasks) != 1 else ''} · {due} due now")

    def _complete(self, check, task_id):
        if check.get_active():
            self.store.complete_task(task_id)
            GLib.idle_add(self.refresh)

    def _delete(self, _button, task_id):
        self.store.delete_task(task_id)
        GLib.idle_add(self.refresh)

    def _snooze(self, _button):
        self.store.snooze_due(minutes=10)
        self.refresh()
        self.window.set_visible(False)

    def _add_task(self, _widget):
        title = self.title_entry.get_text().strip()
        reminder = self.due_entry.get_text().strip()
        repeat = self.repeat_combo.get_active_id() or "none"
        self.error_label.set_text("")
        try:
            due_ts = None
            if reminder:
                due_ts = int(datetime.strptime(reminder, "%Y-%m-%d %H:%M").timestamp())
            self.store.add_task(title, due_ts=due_ts, recurrence=repeat,
                                notes=self.notes_entry.get_text())
        except ValueError as exc:
            self.error_label.set_text(f"Check the task name and reminder date: {exc}")
            return
        self.title_entry.set_text("")
        self.notes_entry.set_text("")
        self.due_entry.set_text("")
        self.repeat_combo.set_active_id("none")
        self.refresh()
        self._scan_reminders()


def run(argv: list[str]) -> int:
    return TaskBellApp().run(argv)
