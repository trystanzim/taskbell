"""Native GTK4 checklist, Done history and resident reminder scheduler."""

from __future__ import annotations

import time
from datetime import date, datetime

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from .history_layout import completed_counts_by_day, month_grid_days, shift_period
from .reminders import ReminderScheduler
from .store import TaskStore

APP_ID = "io.github.trystanzim.TaskBell"

STYLE = """
.task-title {font-size: 24px; font-weight: 700;}
.task-subtitle {font-size: 13px; opacity: 0.72;}
.task-row {padding: 12px 11px; border-bottom: 1px solid alpha(currentColor, 0.09);}
.task-name {font-weight: 600; font-size: 15px;}
.task-detail {font-size: 12px; opacity: 0.72;}
.task-warning {color: #d35400;}
.task-error {color: #d63031;}
.add-panel {padding: 12px;}
.done-heading {font-weight: 700; opacity: 0.85; padding: 9px 12px 4px;}
.done-calendar-day {min-height: 38px; font-size: 12px; padding: 3px 2px;}
.done-calendar-has-items {font-weight: 700;}
"""


def format_due(due_ts: int | None) -> str:
    if due_ts is None:
        return "No reminder set"
    due = datetime.fromtimestamp(due_ts)
    current = date.today()
    if due.date() == current:
        date_label = "Today"
    elif (due.date() - current).days == 1:
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
        self.pages = None
        self.list_box = None
        self.subtitle = None
        self.error_label = None
        self.title_entry = None
        self.due_entry = None
        self.notes_entry = None
        self.repeat_combo = None
        self.done_mode = "day"
        self.done_date = date.today()
        self.done_list_box = None
        self.done_subtitle = None
        self.done_period_label = None
        self.done_calendar_grid = None
        self.done_day_button = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(STYLE.encode("utf-8"))
        from gi.repository import Gdk
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        # Closing the window hides it. The one resident process keeps scanning.
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
            self._scan_reminders()  # Catch up immediately after login.
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
                # A reminder always opens To Do, even if Done was last viewed.
                self.pages.set_visible_child_name("todo")
        except Exception as exc:
            print(f"TaskBell scheduler error: {exc}", flush=True)
        return GLib.SOURCE_CONTINUE

    def _build_window(self):
        self.window = Adw.ApplicationWindow(application=self)
        self.window.connect("close-request", self._hide_on_close)
        self.window.set_title("TaskBell — Your tasks")
        self.window.set_default_size(680, 640)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        header = Adw.HeaderBar()
        root.append(header)

        self.pages = Gtk.Stack()
        self.pages.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.pages.set_vexpand(True)
        self.pages.add_titled(self._build_todo_page(), "todo", "To Do")
        self.pages.add_titled(self._build_done_page(), "done", "Done")
        tabs = Gtk.StackSwitcher()
        tabs.set_stack(self.pages)
        header.set_title_widget(tabs)
        root.append(self.pages)
        self.window.set_content(root)

    def _build_todo_page(self):
        content = self._page_box()
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
        close.connect("clicked", lambda _button: self.window.set_visible(False))
        footer.append(close)
        content.append(footer)
        return content

    def _build_done_page(self):
        content = self._page_box()
        heading = Gtk.Label(label="Completed tasks", xalign=0)
        heading.add_css_class("task-title")
        content.append(heading)
        self.done_subtitle = Gtk.Label(xalign=0)
        self.done_subtitle.add_css_class("task-subtitle")
        content.append(self.done_subtitle)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=7)
        toolbar.set_margin_top(6)
        day = Gtk.ToggleButton(label="Day")
        month = Gtk.ToggleButton(label="Month")
        month.set_group(day)
        day.set_active(True)
        day.connect("toggled", self._done_view_toggled, "day")
        month.connect("toggled", self._done_view_toggled, "month")
        self.done_day_button = day
        toolbar.append(day)
        toolbar.append(month)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        toolbar.append(spacer)
        prev = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        prev.set_tooltip_text("Previous day or month")
        prev.connect("clicked", self._move_done_period, -1)
        toolbar.append(prev)
        self.done_period_label = Gtk.Label()
        self.done_period_label.set_width_chars(17)
        self.done_period_label.set_xalign(0.5)
        toolbar.append(self.done_period_label)
        forward = Gtk.Button.new_from_icon_name("go-next-symbolic")
        forward.set_tooltip_text("Next day or month")
        forward.connect("clicked", self._move_done_period, 1)
        toolbar.append(forward)
        today = Gtk.Button(label="Today")
        today.connect("clicked", self._goto_today)
        toolbar.append(today)
        content.append(toolbar)

        self.done_calendar_grid = Gtk.Grid()
        self.done_calendar_grid.set_column_homogeneous(True)
        self.done_calendar_grid.set_column_spacing(3)
        self.done_calendar_grid.set_row_spacing(3)
        self.done_calendar_grid.set_margin_top(8)
        content.append(self.done_calendar_grid)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        self.done_list_box = Gtk.ListBox()
        self.done_list_box.add_css_class("boxed-list")
        self.done_list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll.set_child(self.done_list_box)
        content.append(scroll)
        return content

    @staticmethod
    def _page_box():
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_start(22)
        page.set_margin_end(22)
        page.set_margin_top(20)
        page.set_margin_bottom(16)
        return page

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
        check.set_tooltip_text("Mark completed and move to Done")
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

    @staticmethod
    def _done_row(completion):
        row = Gtk.ListBoxRow()
        row.set_activatable(False)
        line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=13)
        line.add_css_class("task-row")
        check = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
        check.set_valign(Gtk.Align.CENTER)
        line.append(check)
        details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        details.set_hexpand(True)
        title = Gtk.Label(label=completion.title, xalign=0)
        title.set_wrap(True)
        title.add_css_class("task-name")
        details.append(title)
        if completion.imported:
            information = "Previously completed · original completion date unknown"
        else:
            information = f"Completed at {datetime.fromtimestamp(completion.completed_ts).strftime('%-I:%M %p')}"
        if completion.recurrence == "daily":
            information += " · Daily task"
        elif completion.recurrence == "weekdays":
            information += " · Weekday task"
        if completion.notes:
            information += f" · {completion.notes}"
        description = Gtk.Label(label=information, xalign=0)
        description.set_wrap(True)
        description.add_css_class("task-detail")
        details.append(description)
        line.append(details)
        row.set_child(line)
        return row, line

    def _done_view_toggled(self, button, mode):
        if not button.get_active():
            return
        if mode == "day" and self.done_mode != "day":
            self.done_date = date.today()
        self.done_mode = mode
        self._refresh_done()

    def _move_done_period(self, _button, direction):
        self.done_date = shift_period(self.done_date, self.done_mode, direction)
        self._refresh_done()

    def _goto_today(self, _button):
        self.done_date = date.today()
        self._refresh_done()

    def _calendar_jump_to_day(self, _button, day):
        month = self.done_date
        selected = date(month.year, month.month, day)
        self.done_day_button.set_active(True)
        self.done_date = selected
        self._refresh_done()

    def _refresh_calendar(self, completions):
        grid = self.done_calendar_grid
        while child := grid.get_first_child():
            grid.remove(child)
        if self.done_mode != "month":
            grid.set_visible(False)
            return
        grid.set_visible(True)
        for column, weekday in enumerate(("M", "T", "W", "T", "F", "S", "S")):
            header = Gtk.Label(label=weekday)
            header.add_css_class("task-detail")
            grid.attach(header, column, 0, 1, 1)
        counts = completed_counts_by_day(completions)
        today = date.today()
        for row, week in enumerate(month_grid_days(self.done_date.year, self.done_date.month), start=1):
            for column, number in enumerate(week):
                if number == 0:
                    grid.attach(Gtk.Label(label=""), column, row, 1, 1)
                    continue
                count = counts.get(number, 0)
                label = f"{number} · {count} done" if count else str(number)
                button = Gtk.Button(label=label)
                button.add_css_class("flat")
                button.add_css_class("done-calendar-day")
                if count:
                    button.add_css_class("done-calendar-has-items")
                if date(self.done_date.year, self.done_date.month, number) == today:
                    button.add_css_class("suggested-action")
                button.set_tooltip_text(f"Show tasks completed on {self.done_date.strftime('%B')} {number}")
                button.connect("clicked", self._calendar_jump_to_day, number)
                grid.attach(button, column, row, 1, 1)

    def _refresh_done(self):
        if self.done_list_box is None:
            return
        while child := self.done_list_box.get_first_child():
            self.done_list_box.remove(child)
        chosen = self.done_date
        if self.done_mode == "day":
            completions = self.store.list_completions(day=chosen)
            self.done_period_label.set_text(chosen.strftime("%b %-d, %Y"))
        else:
            completions = self.store.list_completions(month=chosen)
            self.done_period_label.set_text(chosen.strftime("%B %Y"))
        self._refresh_calendar(completions)
        count = len(completions)
        period = "this day" if self.done_mode == "day" else "this month"
        self.done_subtitle.set_text(f"{count} completed task{'s' if count != 1 else ''} {period}")
        if not completions:
            label = Gtk.Label(label="No completed tasks for this period.")
            label.set_margin_top(40)
            label.set_margin_bottom(40)
            self.done_list_box.append(label)
            return
        last_day = None
        for item in completions:
            finished_day = datetime.fromtimestamp(item.completed_ts).date()
            if self.done_mode == "month" and finished_day != last_day:
                self.done_list_box.append(self._group_heading(finished_day.strftime("%A, %b %-d")))
                last_day = finished_day
            row, line = self._done_row(item)
            if item.can_restore:
                restore = Gtk.Button(label="Restore")
                restore.set_tooltip_text("Move this task back to To Do")
                restore.set_valign(Gtk.Align.CENTER)
                restore.connect("clicked", self._restore, item.id)
                line.append(restore)
            self.done_list_box.append(row)

    @staticmethod
    def _group_heading(title):
        heading = Gtk.ListBoxRow()
        heading.set_activatable(False)
        label = Gtk.Label(label=title, xalign=0)
        label.add_css_class("done-heading")
        heading.set_child(label)
        return heading

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
        due = sum(1 for task in tasks if task.due_ts is not None and task.due_ts <= int(time.time()))
        self.subtitle.set_text(f"{len(tasks)} open task{'s' if len(tasks) != 1 else ''} · {due} due now")
        self._refresh_done()

    def _complete(self, check, task_id):
        if check.get_active():
            self.store.complete_task(task_id)
            GLib.idle_add(self.refresh)

    def _restore(self, _button, completion_id):
        self.store.undo_completion(completion_id)
        self.refresh()

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
