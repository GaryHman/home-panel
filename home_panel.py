#!/usr/bin/env python3
"""Home Panel - Google Home (home.google.com) as a small pinned desktop panel.

Starts real Microsoft Edge (or Chrome) in app mode with its own profile, then keeps that window
pinned on top, remembers its size/position, and shows/hides it from the tray or a global hotkey.
Run with pythonw (no console):  pythonw home_panel.py

Home Panel never sees your Google password or cookies: you sign in inside Edge itself, and the
login lives in the dedicated Edge profile (%LOCALAPPDATA%\\HomePanel\\EdgeProfile).
Not created by, affiliated with, or supported by Google or Microsoft.
"""
from __future__ import annotations

import sys

if sys.version_info < (3, 10):
    sys.stderr.write("Home Panel needs Python 3.10 or newer.\n")
    sys.exit(1)

import argparse
import getpass
import logging
import os
import subprocess
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))
_APP_NAME = "Home Panel"


def _startup_failure(exc: BaseException) -> None:
    """pythonw has no console: log the reason and show a message box instead of exiting silently."""
    import ctypes
    import datetime
    msg = (f"{_APP_NAME} could not start because a required Python package is missing or broken:\n\n"
           f"{exc}\n\nPython used: {sys.executable}\n\n"
           "Install it with:  py -m pip install PySide6-Essentials")
    try:
        d = Path(os.environ.get("HP_DATA_DIR") or Path(os.environ.get("APPDATA", str(Path.home()))) / "HomePanel")
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "homepanel.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} ERROR Startup failed: {exc!r} "
                    f"(python: {sys.executable})\n")
    except OSError:
        pass
    if sys.stderr is not None:
        sys.stderr.write(msg + "\n")
    if os.name == "nt":
        try:
            ctypes.windll.user32.MessageBoxW(None, msg, _APP_NAME, 0x10)
        except Exception:  # noqa: BLE001
            pass
    sys.exit(1)


try:
    from PySide6.QtCore import QLockFile, QObject, QPointF, QRectF, Qt, QTimer, Signal
    from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                                   QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMenu,
                                   QMessageBox, QPushButton, QSystemTrayIcon, QVBoxLayout)

    import panel_core as pc
    import win_hotkeys as hk
    from win_panel import WindowsBackend
except ImportError as _exc:  # pragma: no cover - only on a broken install
    _startup_failure(_exc)

log = logging.getLogger("homepanel")
APP_TITLE = pc.APP_TITLE
ACCENT = "#1A73E8"          # Google blue - KeepNotes is yellow, Todoist is red
ACCENT_DARK = "#1557B0"
LAUNCH_TIMEOUT_S = 25


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def setup_logging(directory: Path) -> None:
    handler = RotatingFileHandler(directory / "homepanel.log", maxBytes=512_000, backupCount=2,
                                  encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    if sys.stderr is not None:
        log.addHandler(logging.StreamHandler())


def draw_icon_pixmap(size: int, dimmed: bool = False) -> QPixmap:
    """Blue rounded square with a white house (distinct from Keep's note and Todoist's check)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 64.0
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 45))
    p.drawRoundedRect(QRectF(5 * s, 7 * s, 54 * s, 54 * s), 13 * s, 13 * s)
    p.setBrush(QColor("#9AA0A6" if dimmed else ACCENT))
    p.drawRoundedRect(QRectF(5 * s, 4 * s, 54 * s, 54 * s), 13 * s, 13 * s)
    house = QPainterPath()
    house.moveTo(32 * s, 14 * s)          # roof apex
    house.lineTo(50 * s, 30 * s)
    house.lineTo(45 * s, 30 * s)
    house.lineTo(45 * s, 47 * s)
    house.lineTo(19 * s, 47 * s)
    house.lineTo(19 * s, 30 * s)
    house.lineTo(14 * s, 30 * s)
    house.closeSubpath()
    p.setBrush(QColor("#FFFFFF"))
    p.drawPath(house)
    p.setBrush(QColor("#9AA0A6" if dimmed else ACCENT))   # door
    p.drawRoundedRect(QRectF(28 * s, 35 * s, 8 * s, 12 * s), 1.5 * s, 1.5 * s)
    p.end()
    return pm


def app_icon(dimmed: bool = False) -> QIcon:
    ico = APP_DIR / "icon.ico"
    if not dimmed and ico.exists():
        icon = QIcon(str(ico))
        if not icon.isNull():
            return icon
    icon = QIcon()
    for sz in (16, 20, 24, 32, 48, 64):
        icon.addPixmap(draw_icon_pixmap(sz, dimmed))
    return icon


def startup_shortcut_path() -> Path | None:
    if os.name != "nt":
        return None
    return (Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" /
            "Programs" / "Startup" / "Home Panel.lnk")


def pythonw_executable() -> str:
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if w.exists() else exe)


def create_shortcut(lnk: Path, target: str, args: str, workdir: str, icon: str) -> None:
    env = dict(os.environ, HP_LNK=str(lnk), HP_TARGET=target, HP_ARGS=args, HP_WD=workdir, HP_ICON=icon)
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:HP_LNK);"
          "$s.TargetPath=$env:HP_TARGET;$s.Arguments=$env:HP_ARGS;"
          "$s.WorkingDirectory=$env:HP_WD;$s.IconLocation=$env:HP_ICON;"
          "$s.Description='Home Panel - Google Home on your desktop';$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], env=env,
                   check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=30)


def default_launcher(cmd: list[str]):
    log.info("Launching: %s", subprocess.list2cmdline(cmd))
    return subprocess.Popen(cmd, close_fds=True, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
                            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))


# --------------------------------------------------------------------------
# Panel controller: the browser app window and what we do with it
# --------------------------------------------------------------------------
class PanelController(QObject):
    status_changed = Signal(str)        # "visible" | "hidden" | "closed" | "starting" | "no-browser"

    def __init__(self, settings: pc.SettingsStore, backend=None, launcher=default_launcher,
                 finder=pc.find_browser):
        super().__init__()
        self.settings = settings
        self.backend = backend or WindowsBackend()
        self.launcher = launcher
        self.finder = finder
        self.hwnd = 0
        self.launch_deadline = 0.0
        self.reload_pending = False
        self._last_rect = None
        self._unsaved_rect = None
        self._status = ""
        self.kind, self.browser_path = self.finder(self.settings["browser"])
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)

    # ---- state ---------------------------------------------------------------
    @property
    def profile(self) -> Path:
        return pc.profile_dir(self.kind or "edge")

    def window_alive(self) -> bool:
        return bool(self.hwnd) and self.backend.is_window(self.hwnd)

    def status(self) -> str:
        if not self.browser_path:
            return "no-browser"
        if self.window_alive():
            return "visible" if self.backend.is_visible(self.hwnd) else "hidden"
        if self.launch_deadline > time.monotonic():
            return "starting"
        return "closed"

    def _emit(self) -> None:
        s = self.status()
        if s != self._status:
            self._status = s
            log.info("Panel status: %s", s)
            self.status_changed.emit(s)

    def rediscover_browser(self) -> None:
        self.kind, self.browser_path = self.finder(self.settings["browser"])
        log.info("Browser: %s (%s)", self.browser_path or "not found", self.kind or "-")

    # ---- actions ---------------------------------------------------------------
    def adopt_existing(self) -> bool:
        """Pick up an app window that is still open from an earlier run."""
        if not self.browser_path:
            return False
        h = self.backend.find_window(self.profile)
        if h:
            log.info("Found an existing panel window (hwnd %s)", h)
            self._on_found(h, from_launch=False)
            return True
        return False

    def launch(self) -> bool:
        if not self.browser_path:
            self.rediscover_browser()
        if not self.browser_path:
            self._emit()
            return False
        self.profile.mkdir(parents=True, exist_ok=True)
        cmd = [self.browser_path] + pc.app_mode_args(self.settings["url"], self.profile)
        try:
            self.launcher(cmd)
        except OSError as exc:
            log.error("Could not start the browser: %s", exc)
            return False
        self.launch_deadline = time.monotonic() + LAUNCH_TIMEOUT_S
        self.timer.setInterval(200)
        self._emit()
        return True

    def _on_found(self, hwnd: int, from_launch: bool) -> None:
        self.hwnd = hwnd
        self.launch_deadline = 0.0
        self.timer.setInterval(1000)
        b = self.backend
        areas, primary = b.work_areas()
        target = pc.fit_rect(self.settings["geometry"], areas, primary, b.dpi_scale(hwnd))
        if not b.is_maximized(hwnd):
            b.set_rect(hwnd, target)
        if self.settings["hide_from_taskbar"]:
            b.set_toolwindow(hwnd, True)
        b.set_topmost(hwnd, self.settings["always_on_top"])
        if from_launch or not b.is_visible(hwnd):
            b.show(hwnd, activate=True)
        self._last_rect = b.get_rect(hwnd)
        log.info("Panel window ready: hwnd=%s rect=%s topmost=%s toolwindow=%s", hwnd,
                 self._last_rect.xywh(), b.is_topmost(hwnd), b.is_toolwindow(hwnd))
        self._emit()

    def show(self) -> None:
        if self.window_alive():
            self.backend.show(self.hwnd, activate=True)
            if self.settings["always_on_top"]:
                self.backend.set_topmost(self.hwnd, True)
        elif not self.adopt_existing() and self.status() != "starting":
            self.launch()
        self._emit()

    def hide(self) -> None:
        if self.window_alive():
            self._remember_rect()
            self.backend.hide(self.hwnd)
        self._emit()

    def toggle(self) -> None:
        if self.window_alive() and self.backend.is_visible(self.hwnd) and not self.backend.is_minimized(self.hwnd):
            self.hide()
        else:
            self.show()

    def reload(self) -> None:
        """Close the app window and open it again (a fresh load of the page)."""
        if self.window_alive():
            self._remember_rect()
            self.backend.close(self.hwnd)
            self.reload_pending = True
            self.timer.setInterval(200)
        else:
            self.launch()

    def open_in_browser(self) -> None:
        """The same page in the normal browser (normal profile, not the panel profile)."""
        if self.browser_path:
            try:
                self.launcher([self.browser_path, self.settings["url"]])
            except OSError as exc:
                log.error("Could not open the browser: %s", exc)

    def set_always_on_top(self, on: bool) -> None:
        self.settings["always_on_top"] = on
        self.settings.save()
        if self.window_alive():
            self.backend.set_topmost(self.hwnd, on)
        log.info("Always on top %s", "on" if on else "off")

    def set_hide_from_taskbar(self, on: bool) -> None:
        self.settings["hide_from_taskbar"] = on
        self.settings.save()
        if self.window_alive():
            self.backend.set_toolwindow(self.hwnd, on)
            if self.settings["always_on_top"]:
                self.backend.set_topmost(self.hwnd, True)

    def reset_geometry(self) -> None:
        self.settings["geometry"] = None
        self.settings.save()
        if self.window_alive():
            areas, primary = self.backend.work_areas()
            self.backend.set_rect(self.hwnd, pc.default_rect(primary, self.backend.dpi_scale(self.hwnd)))
            self._remember_rect()

    def shutdown(self) -> None:
        self.timer.stop()
        if self.window_alive():
            self._remember_rect()
            if self.settings["close_panel_on_quit"]:
                self.backend.close(self.hwnd)
            elif not self.backend.is_visible(self.hwnd):
                self.backend.show(self.hwnd, activate=False)   # never leave an invisible window behind
        self._flush_rect()

    # ---- periodic --------------------------------------------------------------
    def _remember_rect(self) -> None:
        b = self.backend
        if not self.window_alive() or not b.is_visible(self.hwnd) or b.is_minimized(self.hwnd) \
                or b.is_maximized(self.hwnd):
            return
        r = b.get_rect(self.hwnd)
        if r.width > 0 and r.height > 0 and r.xywh() != self.settings["geometry"]:
            self.settings["geometry"] = r.xywh()
            self.settings.save()
        self._last_rect = r
        self._unsaved_rect = None

    def _flush_rect(self) -> None:
        if self._unsaved_rect is not None:
            self.settings["geometry"] = self._unsaved_rect.xywh()
            self.settings.save()
            self._unsaved_rect = None

    def tick(self) -> None:
        b = self.backend
        if self.hwnd and not b.is_window(self.hwnd):
            log.info("Panel window was closed")
            self.hwnd = 0
            self._flush_rect()
            if self.reload_pending:
                self.reload_pending = False
                self.launch()
        if not self.hwnd and self.launch_deadline:
            h = b.find_window(self.profile)
            if h:
                self._on_found(h, from_launch=True)
            elif time.monotonic() > self.launch_deadline:
                log.warning("The panel window did not appear within %s s", LAUNCH_TIMEOUT_S)
                self.launch_deadline = 0.0
                self.timer.setInterval(1000)
        if self.window_alive() and b.is_visible(self.hwnd) and not b.is_minimized(self.hwnd) \
                and not b.is_maximized(self.hwnd):
            r = b.get_rect(self.hwnd)
            if r != self._last_rect:
                self._last_rect = r
                self._unsaved_rect = r           # still moving: save when it settles
            elif self._unsaved_rect is not None:
                self._flush_rect()
            if self.settings["always_on_top"] and not b.is_topmost(self.hwnd):
                b.set_topmost(self.hwnd, True)
        self._emit()


# --------------------------------------------------------------------------
# Settings dialog
# --------------------------------------------------------------------------
class SettingsDialog(QDialog):
    def __init__(self, app: "HomePanelApp"):
        super().__init__()
        self.app = app
        s = app.settings
        self.setWindowTitle(f"{APP_TITLE} – Settings")
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(470)
        lay = QVBoxLayout(self)

        title = QLabel(f"<b style='font-size:13pt; color:{ACCENT}'>Home Panel</b>"
                       "<br><span style='color:#5F6368'>Google Home in a small pinned window</span>")
        lay.addWidget(title)

        page = QGroupBox("Panel")
        f = QFormLayout(page)
        self.url = QLineEdit(s["url"])
        self.url.setToolTip("The page the panel opens. Default: " + pc.DEFAULT_URL)
        f.addRow("Page:", self.url)
        self.browser = QComboBox()
        for key, label in (("auto", "Automatic (Microsoft Edge, else Chrome)"), ("edge", "Microsoft Edge"),
                           ("chrome", "Google Chrome")):
            self.browser.addItem(label, key)
        self.browser.setCurrentIndex(max(0, self.browser.findData(s["browser"])))
        f.addRow("Browser:", self.browser)
        self.on_top = QCheckBox("Always on top")
        self.on_top.setChecked(s["always_on_top"])
        self.no_taskbar = QCheckBox("Hide the panel from the taskbar and Alt+Tab")
        self.no_taskbar.setChecked(s["hide_from_taskbar"])
        self.open_start = QCheckBox("Open the panel when Home Panel starts")
        self.open_start.setChecked(s["open_panel_on_start"])
        self.close_quit = QCheckBox("Close the panel window when quitting Home Panel")
        self.close_quit.setChecked(s["close_panel_on_quit"])
        for cb in (self.on_top, self.no_taskbar, self.open_start, self.close_quit):
            f.addRow(cb)
        reset = QPushButton("Reset size and position")
        reset.clicked.connect(self._reset)
        f.addRow(reset)
        lay.addWidget(page)

        self.hotkeys = hk.HotkeyGroup(s["hotkeys"], note="Click a field and press a combination such as "
                                      "Ctrl+Alt+H. Ctrl+Alt+K and Ctrl+Alt+T are used by KeepNotes and "
                                      "Todoist Widgets. Leave empty for no shortcut.")
        lay.addWidget(self.hotkeys)

        ctl = app.controller
        info = QLabel(f"<span style='color:#5F6368; font-size:8pt'>Browser: {ctl.browser_path or 'not found'}"
                      f"<br>Panel profile (your Google sign-in lives here): {ctl.profile}"
                      f"<br>Settings and log: {pc.data_dir()}</span>")
        info.setWordWrap(True)
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(info)

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _reset(self) -> None:
        self.app.controller.reset_geometry()

    def _save(self) -> None:
        url = self.url.text().strip()
        if not url.lower().startswith(("https://", "http://")):
            QMessageBox.warning(self, APP_TITLE, "The page must start with https://")
            return
        values = self.hotkeys.values()
        for action, text in values.items():
            other = pc.hotkey_clash(text)
            if other:
                QMessageBox.warning(self, APP_TITLE, f"{text} is already used by {other}. "
                                    "Please choose another shortcut.")
                return
        s = self.app.settings
        url_changed = url != s["url"]
        browser_changed = self.browser.currentData() != s["browser"]
        s["url"] = url
        s["browser"] = self.browser.currentData()
        s["open_panel_on_start"] = self.open_start.isChecked()
        s["close_panel_on_quit"] = self.close_quit.isChecked()
        s["hotkeys"] = values
        s.save()
        ctl = self.app.controller
        if self.on_top.isChecked() != s["always_on_top"]:
            ctl.set_always_on_top(self.on_top.isChecked())
        if self.no_taskbar.isChecked() != s["hide_from_taskbar"]:
            ctl.set_hide_from_taskbar(self.no_taskbar.isChecked())
        self.app.sync_menu()
        errors = self.app.apply_hotkeys(notify=False)
        if errors:
            QMessageBox.warning(self, APP_TITLE, "Some shortcuts could not be registered:\n" +
                                hk.describe_errors(errors))
        if browser_changed:
            ctl.rediscover_browser()
        if (url_changed or browser_changed) and ctl.window_alive():
            ctl.reload()
        self.accept()


# --------------------------------------------------------------------------
# App: tray, hotkeys, single instance
# --------------------------------------------------------------------------
class HomePanelApp(QObject):
    def __init__(self, qapp: QApplication, settings: pc.SettingsStore, controller: PanelController):
        super().__init__()
        self.qapp = qapp
        self.settings = settings
        self.controller = controller
        self.hotkeys = hk.HotkeyManager(self)
        self.hotkeys.triggered.connect(self.on_hotkey)
        self._settings_dlg = None
        self._build_tray()
        controller.status_changed.connect(self.update_status)
        self.update_status(controller.status())

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(app_icon(), self.qapp)
        m = QMenu()
        head = QAction(APP_TITLE, m)
        head.setEnabled(False)
        m.addAction(head)
        m.addSeparator()
        self.show_action = m.addAction("Show panel", self.controller.show)
        self.hide_action = m.addAction("Hide panel", self.controller.hide)
        m.addSeparator()
        self.top_action = m.addAction("Always on top")
        self.top_action.setCheckable(True)
        self.top_action.toggled.connect(self.controller.set_always_on_top)
        m.addAction("Reload", self.controller.reload)
        m.addAction("Open in normal browser", self.controller.open_in_browser)
        m.addSeparator()
        m.addAction("Settings…", self.show_settings)
        self.autostart_action = m.addAction("Start with Windows")
        self.autostart_action.setCheckable(True)
        lnk = startup_shortcut_path()
        self.autostart_action.setChecked(bool(lnk and lnk.exists()))
        self.autostart_action.setEnabled(lnk is not None)
        self.autostart_action.toggled.connect(self.set_autostart)
        m.addSeparator()
        m.addAction("Quit", self.quit)
        self.menu = m
        self.tray.setContextMenu(m)
        self.tray.activated.connect(self._tray_click)
        self.sync_menu()
        self.tray.show()

    def sync_menu(self) -> None:
        self.top_action.blockSignals(True)
        self.top_action.setChecked(self.settings["always_on_top"])
        self.top_action.blockSignals(False)

    def _tray_click(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.controller.toggle()

    def update_status(self, status: str) -> None:
        text = {"visible": "panel shown", "hidden": "panel hidden", "closed": "panel closed – click to open",
                "starting": "opening the panel…",
                "no-browser": "Microsoft Edge or Google Chrome was not found"}.get(status, status)
        keys = ", ".join(f"{hk.label_of(a)}: {k}" for a, k in self.hotkeys.active.items())
        self.tray.setToolTip(f"{APP_TITLE} – {text}" + (f"\n{keys}" if keys else ""))
        self.tray.setIcon(app_icon(dimmed=status in ("closed", "no-browser")))
        alive = status in ("visible", "hidden")
        self.hide_action.setEnabled(status == "visible")
        self.show_action.setText("Show panel" if alive else "Open panel")

    def apply_hotkeys(self, notify: bool = True) -> list:
        errors = self.hotkeys.apply(self.settings["hotkeys"])
        log.info("Hotkeys registered: %s", ", ".join(f"{a}={k}" for a, k in self.hotkeys.active.items()) or "none")
        for a, k, r in errors:
            log.warning("Hotkey %s (%s) not registered: %s", a, k, r)
        if errors and notify:
            self.tray.showMessage(APP_TITLE, "Some shortcuts could not be registered:\n" +
                                  hk.describe_errors(errors), QSystemTrayIcon.Warning, 8000)
        self.update_status(self.controller.status())
        return errors

    def on_hotkey(self, action: str) -> None:
        {"toggle": self.controller.toggle, "show": self.controller.show,
         "hide": self.controller.hide}.get(action, lambda: None)()

    def show_settings(self) -> None:
        if self._settings_dlg is not None and self._settings_dlg.isVisible():
            self._settings_dlg.raise_()
            self._settings_dlg.activateWindow()
            return
        self._settings_dlg = SettingsDialog(self)
        self._settings_dlg.show()
        self._settings_dlg.raise_()
        self._settings_dlg.activateWindow()

    def set_autostart(self, on: bool) -> None:
        lnk = startup_shortcut_path()
        if lnk is None:
            return
        try:
            if on:
                create_shortcut(lnk, pythonw_executable(), f'"{APP_DIR / "home_panel.py"}"',
                                str(APP_DIR), str(APP_DIR / "icon.ico"))
            elif lnk.exists():
                lnk.unlink()
            log.info("Start with Windows %s", "enabled" if on else "disabled")
        except Exception as exc:  # noqa: BLE001
            log.exception("Could not change startup shortcut")
            QMessageBox.warning(None, APP_TITLE, f"Could not change the startup shortcut:\n{exc}")
            self.autostart_action.blockSignals(True)
            self.autostart_action.setChecked(lnk.exists())
            self.autostart_action.blockSignals(False)

    def start(self) -> None:
        self.apply_hotkeys()
        if not self.controller.browser_path:
            self.tray.showMessage(APP_TITLE, "Microsoft Edge or Google Chrome is needed and was not found.",
                                  QSystemTrayIcon.Warning, 8000)
            return
        if not self.controller.adopt_existing() and self.settings["open_panel_on_start"]:
            self.controller.launch()

    def quit(self) -> None:
        log.info("Quitting")
        self.hotkeys.unregister_all()
        self.controller.shutdown()
        self.tray.hide()
        self.qapp.quit()


def server_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = "user"
    return f"HomePanel-{user}"


def notify_running_instance() -> bool:
    """Ask an already running Home Panel to show its panel. True if one answered."""
    sock = QLocalSocket()
    sock.connectToServer(server_name())
    if not sock.waitForConnected(500):
        return False
    sock.write(b"show\n")
    sock.flush()
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=APP_TITLE)
    ap.add_argument("--data-dir", help="override the settings folder (default %%APPDATA%%\\HomePanel)")
    args = ap.parse_args(argv)
    if args.data_dir:
        os.environ["HP_DATA_DIR"] = args.data_dir
    directory = pc.data_dir()
    setup_logging(directory)

    QApplication.setQuitOnLastWindowClosed(False)
    qapp = QApplication(sys.argv[:1])
    qapp.setApplicationName(APP_TITLE)
    qapp.setWindowIcon(app_icon())
    qapp.setFont(QFont("Segoe UI", 10))

    lock = QLockFile(str(directory / "app.lock"))
    if not lock.tryLock(200):
        if notify_running_instance():
            log.info("Already running - asked the running instance to show the panel")
            return 0
        lock.removeStaleLockFile()
        if not lock.tryLock(200):
            QMessageBox.information(None, APP_TITLE, "Home Panel is already running (see the tray icon).")
            return 0
    try:
        QLocalServer.removeServer(server_name())
        server = QLocalServer()
        server.listen(server_name())
        settings = pc.SettingsStore(directory / "settings.json")
        controller = PanelController(settings)
        app = HomePanelApp(qapp, settings, controller)

        def on_conn():
            while server.hasPendingConnections():
                c = server.nextPendingConnection()
                c.readyRead.connect(lambda c=c: (c.readAll(), controller.show()))
        server.newConnection.connect(on_conn)

        log.info("Home Panel started (python %s, data folder %s, browser %s)", sys.executable, directory,
                 controller.browser_path)
        app.start()
        rc = qapp.exec()
        server.close()
        log.info("Home Panel stopped")
        return rc
    finally:
        lock.unlock()


if __name__ == "__main__":
    sys.exit(main())
