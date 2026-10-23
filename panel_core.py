"""Home Panel - platform-neutral logic (no Qt, no Win32): settings, geometry, browser discovery.

Everything here is unit-tested on any OS.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

APP_TITLE = "Home Panel"
DEFAULT_URL = "https://home.google.com/u/0/"
DEFAULT_W, DEFAULT_H = 420, 720          # at 100 % scaling (96 dpi); scaled by the monitor DPI
EDGE_MARGIN = 16                         # gap to the screen edge for the default position
TITLE_STRIP = 40                         # the top strip that must stay reachable to drag the window
MIN_VISIBLE_W = 120
MIN_W, MIN_H = 280, 300

DEFAULT_SETTINGS: dict = {
    "url": DEFAULT_URL,
    "browser": "auto",                   # auto | edge | chrome
    "always_on_top": True,
    "hide_from_taskbar": False,
    "close_panel_on_quit": False,
    "open_panel_on_start": True,
    "geometry": None,                    # [x, y, w, h] in physical pixels, or None = default
    "hotkeys": {"toggle": "Ctrl+Alt+H", "show": "", "hide": ""},
}
# Defaults of the sibling apps - Home Panel must never use them
OTHER_APP_HOTKEYS = {"Ctrl+Alt+K": "KeepNotes Widgets", "Ctrl+Alt+T": "Todoist Widgets"}


# --------------------------------------------------------------------------
# Folders
# --------------------------------------------------------------------------
def data_dir() -> Path:
    """%APPDATA%\\HomePanel (settings + log). HP_DATA_DIR overrides (tests)."""
    d = os.environ.get("HP_DATA_DIR")
    if d:
        p = Path(d)
    else:
        p = Path(os.environ.get("APPDATA") or Path.home() / ".config") / "HomePanel"
    p.mkdir(parents=True, exist_ok=True)
    return p


def profile_dir(browser_kind: str) -> Path:
    """Dedicated browser profile: %LOCALAPPDATA%\\HomePanel\\EdgeProfile (or ChromeProfile)."""
    base = os.environ.get("HP_PROFILE_BASE") or os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    name = "ChromeProfile" if browser_kind == "chrome" else "EdgeProfile"
    return Path(base) / "HomePanel" / name


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------
def merge_settings(raw) -> dict:
    """Defaults + known keys from raw with type checks (a damaged file never crashes the app)."""
    out = copy.deepcopy(DEFAULT_SETTINGS)
    if not isinstance(raw, dict):
        return out
    for key in ("url",):
        v = raw.get(key)
        if isinstance(v, str) and v.strip().lower().startswith(("https://", "http://")):
            out[key] = v.strip()
    if raw.get("browser") in ("auto", "edge", "chrome"):
        out["browser"] = raw["browser"]
    for key in ("always_on_top", "hide_from_taskbar", "close_panel_on_quit", "open_panel_on_start"):
        if isinstance(raw.get(key), bool):
            out[key] = raw[key]
    g = raw.get("geometry")
    if (isinstance(g, (list, tuple)) and len(g) == 4 and all(isinstance(n, (int, float)) for n in g)
            and g[2] >= MIN_W // 2 and g[3] >= MIN_H // 2):
        out["geometry"] = [int(n) for n in g]
    hk = raw.get("hotkeys")
    if isinstance(hk, dict):
        for a in ("toggle", "show", "hide"):
            if isinstance(hk.get(a), str):
                out["hotkeys"][a] = hk[a]
    return out


class SettingsStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = merge_settings(self._read())

    def _read(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def save(self) -> None:
        """Atomic write (temp file + replace) so a crash never leaves a half-written file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="settings-", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def __getitem__(self, k):
        return self.data[k]

    def __setitem__(self, k, v):
        self.data[k] = v


# --------------------------------------------------------------------------
# Geometry (physical pixels, Win32 RECT style: left, top, right, bottom)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @classmethod
    def from_xywh(cls, x, y, w, h) -> "Rect":
        return cls(int(x), int(y), int(x + w), int(y + h))

    def xywh(self) -> list[int]:
        return [self.left, self.top, self.width, self.height]

    def intersect(self, o: "Rect") -> Optional["Rect"]:
        l, t, r, b = max(self.left, o.left), max(self.top, o.top), min(self.right, o.right), min(self.bottom, o.bottom)
        return Rect(l, t, r, b) if r > l and b > t else None


def default_rect(primary_work: Rect, scale: float = 1.0) -> Rect:
    """Compact panel at the right side of the primary screen's work area."""
    m = round(EDGE_MARGIN * scale)
    w = min(round(DEFAULT_W * scale), primary_work.width - 2 * m)
    h = min(round(DEFAULT_H * scale), primary_work.height - 2 * m)
    x = primary_work.right - m - w
    y = primary_work.top + m
    return Rect.from_xywh(x, y, w, h)


def fit_rect(saved: Optional[Iterable[int]], work_areas: list[Rect], primary_work: Rect,
             scale: float = 1.0) -> Rect:
    """Return the saved rect if it is still reachable on some monitor (its title strip overlaps a
    work area by at least MIN_VISIBLE_W x 20 px), shrunk to fit that monitor; else the default.
    Handles unplugged monitors, resolution changes and negative multi-monitor coordinates."""
    if not saved:
        return default_rect(primary_work, scale)
    try:
        x, y, w, h = (int(n) for n in saved)
    except (TypeError, ValueError):
        return default_rect(primary_work, scale)
    if w <= 0 or h <= 0:
        return default_rect(primary_work, scale)
    r = Rect.from_xywh(x, y, w, h)
    strip = Rect(r.left, r.top, r.right, r.top + TITLE_STRIP)
    best, best_area = None, 0
    for wa in work_areas:
        hit = strip.intersect(wa)
        if hit and hit.width >= MIN_VISIBLE_W and hit.height >= 20:
            area = hit.width * hit.height
            if area > best_area:
                best, best_area = wa, area
    if best is None:
        return default_rect(primary_work, scale)
    # shrink to the monitor and pull fully inside it
    w = max(min(w, best.width), min(MIN_W, best.width))
    h = max(min(h, best.height), min(MIN_H, best.height))
    x = min(max(x, best.left), best.right - w)
    y = min(max(y, best.top), best.bottom - h)
    return Rect.from_xywh(x, y, w, h)


# --------------------------------------------------------------------------
# Browser discovery + command line
# --------------------------------------------------------------------------
EDGE_REL = Path("Microsoft") / "Edge" / "Application" / "msedge.exe"
CHROME_REL = Path("Google") / "Chrome" / "Application" / "chrome.exe"


def _registry_app_path(exe_name: str) -> Optional[str]:
    if os.name != "nt":
        return None
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (0, winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}",
                                    0, winreg.KEY_READ | view) as k:
                    v, _ = winreg.QueryValueEx(k, "")
                    if v:
                        return str(v).strip('"')
            except OSError:
                continue
    return None


def candidate_paths(kind: str, env: Optional[dict] = None,
                    registry: Callable[[str], Optional[str]] = _registry_app_path) -> list[str]:
    env = os.environ if env is None else env
    exe, rel = ("msedge.exe", EDGE_REL) if kind == "edge" else ("chrome.exe", CHROME_REL)
    out = []
    reg = registry(exe)
    if reg:
        out.append(reg)
    for var in ("ProgramFiles(x86)", "ProgramFiles", "ProgramW6432", "LOCALAPPDATA"):
        base = env.get(var)
        if base:
            out.append(str(Path(base) / rel))
    seen, uniq = set(), []
    for p in out:
        k = p.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq


def find_browser(preference: str = "auto", env: Optional[dict] = None,
                 registry: Callable[[str], Optional[str]] = _registry_app_path,
                 exists: Callable[[str], bool] = os.path.isfile) -> tuple[Optional[str], Optional[str]]:
    """(kind, path) of Edge (preferred) or Chrome; (None, None) if neither is installed."""
    order = {"auto": ("edge", "chrome"), "edge": ("edge", "chrome"), "chrome": ("chrome", "edge")}.get(preference, ("edge", "chrome"))
    for kind in order:
        for p in candidate_paths(kind, env, registry):
            if exists(p):
                return kind, p
    return None, None


def app_mode_args(url: str, profile: Path) -> list[str]:
    """Flags for a chromeless app window with its own profile. No remote-debugging port."""
    return [f"--app={url}", f"--user-data-dir={profile}", "--no-first-run",
            "--no-default-browser-check"]


def cmdline_uses_profile(cmdline: str, profile: Path) -> bool:
    """True if a browser process command line was started with exactly our --user-data-dir
    (quoted or not; 'EdgeProfile2' does not match 'EdgeProfile')."""
    if not cmdline:
        return False
    c = cmdline.replace('"', "").replace("/", "\\").lower()
    needle = "--user-data-dir=" + str(profile).replace("/", "\\").rstrip("\\").lower()
    i = c.find(needle)
    while i >= 0:
        j = i + len(needle)
        if j == len(c) or c[j] in " \t\\":
            if j == len(c) or c[j] != "\\" or j + 1 == len(c) or c[j + 1] in " \t":
                return True
        i = c.find(needle, i + 1)
    return False


def hotkey_clash(text: str) -> Optional[str]:
    """Name of a sibling app that uses this shortcut by default, else None."""
    return OTHER_APP_HOTKEYS.get((text or "").strip())
