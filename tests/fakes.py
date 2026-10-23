"""Fake Win32 backend + launcher so the controller can be tested on any OS."""
from panel_core import Rect


class FakeBackend:
    def __init__(self, areas=None, primary=None, scale=1.0):
        self.areas = areas or [Rect(0, 0, 1920, 1040)]
        self.primary = primary or self.areas[0]
        self.scale = scale
        self.windows = {}          # hwnd -> dict(rect, visible, topmost, tool, min, max)
        self.next_hwnd = 100
        self.profile_window = 0    # what find_window returns
        self.calls = []

    def spawn(self, rect=Rect(100, 100, 900, 700)):
        h = self.next_hwnd
        self.next_hwnd += 1
        self.windows[h] = dict(rect=rect, visible=True, topmost=False, tool=False, min=False, max=False)
        self.profile_window = h
        return h

    def find_window(self, profile):
        self.calls.append(("find", str(profile)))
        return self.profile_window if self.profile_window in self.windows else 0

    def is_window(self, h): return h in self.windows
    def is_visible(self, h): return self.windows[h]["visible"]
    def is_minimized(self, h): return self.windows[h]["min"]
    def is_maximized(self, h): return self.windows[h]["max"]
    def get_rect(self, h): return self.windows[h]["rect"]

    def set_rect(self, h, r):
        self.calls.append(("set_rect", r.xywh()))
        self.windows[h]["rect"] = r

    def is_topmost(self, h): return self.windows[h]["topmost"]

    def set_topmost(self, h, on):
        self.calls.append(("topmost", on))
        self.windows[h]["topmost"] = on
        return True

    def is_toolwindow(self, h): return self.windows[h]["tool"]

    def set_toolwindow(self, h, on):
        self.calls.append(("tool", on))
        self.windows[h]["tool"] = on

    def hide(self, h):
        self.calls.append(("hide",))
        self.windows[h]["visible"] = False

    def show(self, h, activate=True):
        self.calls.append(("show", activate))
        self.windows[h]["visible"] = True
        self.windows[h]["min"] = False

    def close(self, h):
        self.calls.append(("close",))
        del self.windows[h]

    def work_areas(self): return self.areas, self.primary
    def dpi_scale(self, h=None): return self.scale


class FakeLauncher:
    """Records commands; app-mode launches make the backend 'open' a window."""
    def __init__(self, backend, opens_window=True):
        self.backend = backend
        self.opens_window = opens_window
        self.commands = []

    def __call__(self, cmd):
        self.commands.append(cmd)
        if self.opens_window and any(a.startswith("--app=") for a in cmd):
            self.backend.spawn()
        return None
