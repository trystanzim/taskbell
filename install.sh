#!/usr/bin/env bash
# Install TaskBell to the current user's GNOME desktop (no sudo needed).
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/taskbell/app"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"

command -v python3 >/dev/null || { echo 'Python 3 is required.' >&2; exit 1; }
python3 - <<'PY'
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw
print('GTK4 and libadwaita: available')
PY
mkdir -p "$APP_DIR/taskbell" "$DESKTOP_DIR" "$AUTOSTART_DIR"
install -m 644 "$SOURCE_DIR/taskbell/__init__.py" "$APP_DIR/taskbell/__init__.py"
install -m 644 "$SOURCE_DIR/taskbell/store.py" "$APP_DIR/taskbell/store.py"
install -m 644 "$SOURCE_DIR/taskbell/reminders.py" "$APP_DIR/taskbell/reminders.py"
install -m 644 "$SOURCE_DIR/taskbell/ui.py" "$APP_DIR/taskbell/ui.py"
install -m 644 "$SOURCE_DIR/icon.svg" "$APP_DIR/icon.svg"
install -m 755 "$SOURCE_DIR/taskbell.py" "$APP_DIR/taskbell.py"
cat > "$DESKTOP_DIR/io.github.trystanzim.TaskBell.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=TaskBell
Comment=Local checklist and scheduled reminder popups
Exec=/usr/bin/python3 $APP_DIR/taskbell.py
Icon=$APP_DIR/icon.svg
Terminal=false
Categories=Utility;Office;
StartupNotify=true
EOF
cat > "$AUTOSTART_DIR/io.github.trystanzim.TaskBell.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=TaskBell reminder service
Comment=Show scheduled and missed task reminders after login
Exec=/usr/bin/python3 $APP_DIR/taskbell.py --background
Icon=$APP_DIR/icon.svg
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
chmod 644 "$DESKTOP_DIR/io.github.trystanzim.TaskBell.desktop" "$AUTOSTART_DIR/io.github.trystanzim.TaskBell.desktop"
echo "Installed TaskBell in $APP_DIR"
echo 'To test it, run: python3 ~/.local/share/taskbell/app/taskbell.py --test-popup'
echo 'Reminder service will start automatically at your next graphical login.'
