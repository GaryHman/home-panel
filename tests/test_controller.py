import time

import panel_core as pc
from panel_core import Rect
from fakes import FakeBackend, FakeLauncher
import home_panel as hp

EDGE = r"C:\Edge\msedge.exe"


def make(tmpenv, qapp, **settings):
    s = pc.SettingsStore(pc.data_dir() / "settings.json")
    for k, v in settings.items():
        s[k] = v
    b = FakeBackend()
    launcher = FakeLauncher(b)
    c = hp.PanelController(s, backend=b, launcher=launcher, finder=lambda pref: ("edge", EDGE))
    c.timer.stop()
    return c, b, launcher, s


def test_launch_places_default_and_pins(tmpenv, qapp):
    c, b, l, s = make(tmpenv, qapp)
    assert c.launch()
    cmd = l.commands[0]
    assert cmd[0] == EDGE and cmd[1] == "--app=https://home.google.com/u/0/"
    assert c.status() == "starting"
    c.tick()
    assert c.hwnd and c.status() == "visible"
    w = b.windows[c.hwnd]
    assert w["rect"] == pc.default_rect(b.primary) and w["topmost"] and not w["tool"]


def test_saved_geometry_restored_and_moves_saved_when_settled(tmpenv, qapp):
    c, b, l, s = make(tmpenv, qapp, geometry=[50, 60, 500, 600])
    c.launch(); c.tick()
    assert b.windows[c.hwnd]["rect"].xywh() == [50, 60, 500, 600]
    b.windows[c.hwnd]["rect"] = Rect.from_xywh(300, 300, 450, 650)    # user drags
    c.tick()                                     # change seen, not yet saved
    assert s["geometry"] == [50, 60, 500, 600]
    c.tick()                                     # settled -> saved
    assert pc.SettingsStore(s.path)["geometry"] == [300, 300, 450, 650]


def test_offscreen_saved_geometry_uses_default(tmpenv, qapp):
    c, b, l, s = make(tmpenv, qapp, geometry=[-3000, 100, 420, 720])
    c.launch(); c.tick()
    assert b.windows[c.hwnd]["rect"] == pc.default_rect(b.primary)


def test_toggle_hide_show_and_relaunch_after_close(tmpenv, qapp):
    c, b, l, s = make(tmpenv, qapp)
    c.launch(); c.tick()
    h = c.hwnd
    c.toggle()
    assert not b.windows[h]["visible"] and c.status() == "hidden"
    c.toggle()
    assert b.windows[h]["visible"] and c.status() == "visible"
    b.close(h)                                   # user closes the Edge window
    c.tick()
    assert c.hwnd == 0 and c.status() == "closed"
    c.show()                                     # Show relaunches
    assert len([x for x in l.commands if "--app=" in x[1]]) == 2
    c.tick()
    assert c.hwnd and c.hwnd != h and c.status() == "visible"


def test_topmost_toggle_and_reapply(tmpenv, qapp):
    c, b, l, s = make(tmpenv, qapp)
    c.launch(); c.tick()
    c.set_always_on_top(False)
    assert not b.windows[c.hwnd]["topmost"] and pc.SettingsStore(s.path)["always_on_top"] is False
    c.set_always_on_top(True)
    b.windows[c.hwnd]["topmost"] = False         # something dropped it
    c.tick()
    assert b.windows[c.hwnd]["topmost"]


def test_hide_from_taskbar(tmpenv, qapp):
    c, b, l, s = make(tmpenv, qapp, hide_from_taskbar=True)
    c.launch(); c.tick()
    assert b.windows[c.hwnd]["tool"]
    c.set_hide_from_taskbar(False)
    assert not b.windows[c.hwnd]["tool"]


def test_adopt_existing_window_without_launch(tmpenv, qapp):
    c, b, l, s = make(tmpenv, qapp)
    h = b.spawn()
    b.windows[h]["visible"] = False              # left hidden by a crashed earlier run
    assert c.adopt_existing() and c.hwnd == h
    assert b.windows[h]["visible"] and not l.commands


def test_reload_closes_and_relaunches(tmpenv, qapp):
    c, b, l, s = make(tmpenv, qapp)
    c.launch(); c.tick()
    h = c.hwnd
    c.reload()
    assert h not in b.windows
    c.tick()          # notices close -> relaunch
    c.tick()          # finds new window
    assert c.hwnd and c.hwnd != h and len(l.commands) == 2


def test_open_in_normal_browser_uses_no_profile(tmpenv, qapp):
    c, b, l, s = make(tmpenv, qapp)
    c.open_in_browser()
    assert l.commands == [[EDGE, "https://home.google.com/u/0/"]]


def test_shutdown_shows_hidden_window_or_closes(tmpenv, qapp):
    c, b, l, s = make(tmpenv, qapp)
    c.launch(); c.tick(); c.hide()
    c.shutdown()
    assert b.windows[c.hwnd]["visible"]
    c2, b2, l2, s2 = make(tmpenv, qapp, close_panel_on_quit=True)
    c2.launch(); c2.tick()
    h = c2.hwnd
    c2.shutdown()
    assert h not in b2.windows


def test_launch_timeout_and_no_browser(tmpenv, qapp, monkeypatch):
    c, b, l, s = make(tmpenv, qapp)
    l.opens_window = False
    c.launch()
    c.launch_deadline = time.monotonic() - 1
    c.tick()
    assert c.status() == "closed"
    s2 = pc.SettingsStore(pc.data_dir() / "s2.json")
    c2 = hp.PanelController(s2, backend=FakeBackend(), launcher=FakeLauncher(None),
                            finder=lambda pref: (None, None))
    c2.timer.stop()
    assert c2.status() == "no-browser" and c2.launch() is False
