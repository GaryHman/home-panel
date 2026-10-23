"""Headless smoke test: tray menu + settings dialog with a fake window backend; saves screenshots."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
tmp = Path(tempfile.mkdtemp())
os.environ["HP_DATA_DIR"] = str(tmp / "data")
os.environ["HP_PROFILE_BASE"] = str(tmp / "local")

from PySide6.QtWidgets import QApplication  # noqa: E402

qapp = QApplication([])
import home_panel as hp  # noqa: E402
import panel_core as pc  # noqa: E402
from fakes import FakeBackend, FakeLauncher  # noqa: E402

out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT
s = pc.SettingsStore(pc.data_dir() / "settings.json")
b = FakeBackend()
c = hp.PanelController(s, backend=b, launcher=FakeLauncher(b),
                       finder=lambda p: ("edge", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"))
app = hp.HomePanelApp(qapp, s, c)
app.start(); c.tick()
print("status after start:", c.status(), "| topmost:", b.windows[c.hwnd]["topmost"])
print("tray menu:", [a.text() for a in app.menu.actions() if a.text()])
app.on_hotkey("toggle"); print("after toggle hotkey:", c.status())
app.on_hotkey("toggle"); print("after toggle again:", c.status())
print("tooltip:", app.tray.toolTip().replace("\n", " | "))

dlg = hp.SettingsDialog(app)
dlg.show(); qapp.processEvents()
dlg.adjustSize(); qapp.processEvents()
dlg.grab().save(str(out / "screenshot-settings.png"))
dlg.hotkeys.edits["show"].setKeySequence("Ctrl+Alt+K")
from PySide6.QtWidgets import QMessageBox  # noqa: E402
QMessageBox.warning = staticmethod(lambda *a, **k: print("warning shown:", a[2]))
dlg._save()
print("dialog still open after clash:", dlg.isVisible())
dlg.hotkeys.edits["show"].setKeySequence("Ctrl+Alt+Shift+H")
dlg.on_top.setChecked(False)
dlg._save()
print("saved hotkeys:", pc.SettingsStore(s.path)["hotkeys"], "| on top:", pc.SettingsStore(s.path)["always_on_top"])

menu = app.menu
menu.popup(menu.pos()); qapp.processEvents()
menu.grab().save(str(out / "screenshot-tray-menu.png"))
menu.hide()
icon = hp.draw_icon_pixmap(64)
print("icon ok:", not icon.isNull())
app.quit()
print("SMOKE OK")
