"""Win32 window control for Home Panel (ctypes only, no extra packages).

WindowsBackend finds the browser app window that belongs to our dedicated profile and moves,
pins (HWND_TOPMOST), hides/shows and closes it. All coordinates are physical pixels; the Qt app
is per-monitor DPI aware, so GetWindowRect/SetWindowPos/monitor work areas agree.
"""
from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from panel_core import Rect, cmdline_uses_profile

if sys.platform == "win32":
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll")

    LONG_PTR = ctypes.c_ssize_t
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                                         ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    class UNICODE_STRING(ctypes.Structure):
        _fields_ = [("Length", wintypes.USHORT), ("MaximumLength", wintypes.USHORT),
                    ("Buffer", ctypes.c_void_p)]

    def _sig(fn, res, *args):
        fn.restype = res
        fn.argtypes = list(args)

    _sig(user32.EnumWindows, wintypes.BOOL, WNDENUMPROC, wintypes.LPARAM)
    _sig(user32.GetWindowThreadProcessId, wintypes.DWORD, wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    _sig(user32.GetClassNameW, ctypes.c_int, wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    _sig(user32.GetWindowTextW, ctypes.c_int, wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    _sig(user32.GetWindowTextLengthW, ctypes.c_int, wintypes.HWND)
    _sig(user32.IsWindow, wintypes.BOOL, wintypes.HWND)
    _sig(user32.IsWindowVisible, wintypes.BOOL, wintypes.HWND)
    _sig(user32.IsIconic, wintypes.BOOL, wintypes.HWND)
    _sig(user32.IsZoomed, wintypes.BOOL, wintypes.HWND)
    _sig(user32.GetWindowRect, wintypes.BOOL, wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    _sig(user32.SetWindowPos, wintypes.BOOL, wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
         ctypes.c_int, ctypes.c_int, wintypes.UINT)
    _sig(user32.ShowWindow, wintypes.BOOL, wintypes.HWND, ctypes.c_int)
    _sig(user32.SetForegroundWindow, wintypes.BOOL, wintypes.HWND)
    _sig(user32.BringWindowToTop, wintypes.BOOL, wintypes.HWND)
    _sig(user32.PostMessageW, wintypes.BOOL, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    _sig(user32.GetWindowLongPtrW, LONG_PTR, wintypes.HWND, ctypes.c_int)
    _sig(user32.SetWindowLongPtrW, LONG_PTR, wintypes.HWND, ctypes.c_int, LONG_PTR)
    _sig(user32.EnumDisplayMonitors, wintypes.BOOL, wintypes.HDC, ctypes.c_void_p, MONITORENUMPROC, wintypes.LPARAM)
    _sig(user32.GetMonitorInfoW, wintypes.BOOL, wintypes.HMONITOR, ctypes.POINTER(MONITORINFO))
    _sig(user32.GetDpiForWindow, wintypes.UINT, wintypes.HWND)
    _sig(user32.GetDpiForSystem, wintypes.UINT)
    _sig(user32.GetForegroundWindow, wintypes.HWND)
    _sig(user32.GetWindowThreadProcessId, wintypes.DWORD, wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    _sig(user32.AttachThreadInput, wintypes.BOOL, wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
    _sig(kernel32.GetCurrentThreadId, wintypes.DWORD)
    _sig(kernel32.CreateToolhelp32Snapshot, wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD)
    _sig(kernel32.Process32FirstW, wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    _sig(kernel32.Process32NextW, wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    _sig(kernel32.OpenProcess, wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _sig(kernel32.CloseHandle, wintypes.BOOL, wintypes.HANDLE)
    _sig(ntdll.NtQueryInformationProcess, ctypes.c_long, wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
         wintypes.ULONG, ctypes.POINTER(wintypes.ULONG))

GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_CAPTION, WS_THICKFRAME = 0x00C00000, 0x00040000
WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = 0x00000008, 0x00000080, 0x00040000
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x1, 0x2, 0x4, 0x10, 0x20
SW_HIDE, SW_SHOWNORMAL, SW_SHOW, SW_RESTORE = 0, 1, 5, 9
WM_CLOSE = 0x0010
TH32CS_SNAPPROCESS = 0x2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ProcessCommandLineInformation = 60
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
BROWSER_EXES = ("msedge.exe", "chrome.exe")
WINDOW_CLASS = "Chrome_WidgetWin_1"


def _rect(r) -> Rect:
    return Rect(r.left, r.top, r.right, r.bottom)


class WindowsBackend:
    supported = sys.platform == "win32"

    # ---- processes ---------------------------------------------------------
    def browser_pids(self) -> dict[int, str]:
        """pid -> exe name for every msedge.exe / chrome.exe process."""
        out: dict[int, str] = {}
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if not snap or snap == INVALID_HANDLE_VALUE:
            return out
        try:
            e = PROCESSENTRY32W()
            e.dwSize = ctypes.sizeof(e)
            ok = kernel32.Process32FirstW(snap, ctypes.byref(e))
            while ok:
                name = e.szExeFile.lower()
                if name in BROWSER_EXES:
                    out[e.th32ProcessID] = name
                ok = kernel32.Process32NextW(snap, ctypes.byref(e))
        finally:
            kernel32.CloseHandle(snap)
        return out

    @staticmethod
    def process_cmdline(pid: int) -> str | None:
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return None
        try:
            size = wintypes.ULONG(0)
            ntdll.NtQueryInformationProcess(h, ProcessCommandLineInformation, None, 0, ctypes.byref(size))
            if not size.value:
                return None
            buf = ctypes.create_string_buffer(size.value)
            if ntdll.NtQueryInformationProcess(h, ProcessCommandLineInformation, buf, size,
                                               ctypes.byref(size)) != 0:
                return None
            us = UNICODE_STRING.from_buffer(buf)
            return ctypes.wstring_at(us.Buffer, us.Length // 2) if us.Buffer else None
        finally:
            kernel32.CloseHandle(h)

    def profile_pids(self, profile: Path) -> set[int]:
        return {pid for pid in self.browser_pids()
                if cmdline_uses_profile(self.process_cmdline(pid) or "", profile)}

    # ---- windows -----------------------------------------------------------
    @staticmethod
    def title(hwnd) -> str:
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value

    def find_window(self, profile: Path, prefer_title: str = "Google Home") -> int:
        """The top-level app window of a browser process that uses our profile (0 if none).
        Prefers visible windows, then a title containing prefer_title, then the largest."""
        pids = self.profile_pids(profile)
        if not pids:
            return 0
        found: list[tuple] = []

        def cb(hwnd, _lp):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in pids:
                return True
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            if cls.value != WINDOW_CLASS:
                return True
            style = user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
            title = self.title(hwnd)
            if not title or not (style & WS_CAPTION or style & WS_THICKFRAME):
                return True
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            area = max(0, r.right - r.left) * max(0, r.bottom - r.top)
            if area < 150 * 150 and not user32.IsIconic(hwnd):
                return True
            found.append((bool(user32.IsWindowVisible(hwnd)), prefer_title.lower() in title.lower(),
                          area, int(hwnd or 0)))
            return True

        user32.EnumWindows(WNDENUMPROC(cb), 0)
        if not found:
            return 0
        found.sort(reverse=True)
        return found[0][3]

    def is_window(self, hwnd) -> bool:
        return bool(hwnd) and bool(user32.IsWindow(hwnd))

    def is_visible(self, hwnd) -> bool:
        return bool(user32.IsWindowVisible(hwnd))

    def is_minimized(self, hwnd) -> bool:
        return bool(user32.IsIconic(hwnd))

    def is_maximized(self, hwnd) -> bool:
        return bool(user32.IsZoomed(hwnd))

    def get_rect(self, hwnd) -> Rect:
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        return _rect(r)

    def set_rect(self, hwnd, rect: Rect) -> None:
        user32.SetWindowPos(hwnd, None, rect.left, rect.top, rect.width, rect.height,
                            SWP_NOZORDER | SWP_NOACTIVATE)

    def exstyle(self, hwnd) -> int:
        return int(user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE))

    def is_topmost(self, hwnd) -> bool:
        return bool(self.exstyle(hwnd) & WS_EX_TOPMOST)

    def set_topmost(self, hwnd, on: bool) -> bool:
        return bool(user32.SetWindowPos(hwnd, HWND_TOPMOST if on else HWND_NOTOPMOST, 0, 0, 0, 0,
                                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE))

    def is_toolwindow(self, hwnd) -> bool:
        return bool(self.exstyle(hwnd) & WS_EX_TOOLWINDOW)

    def set_toolwindow(self, hwnd, on: bool) -> None:
        """Hide from / show in the taskbar and Alt+Tab. The taskbar only notices while hidden."""
        ex = self.exstyle(hwnd)
        new = (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW if on else (ex & ~WS_EX_TOOLWINDOW)
        if new == ex:
            return
        visible = self.is_visible(hwnd)
        if visible:
            user32.ShowWindow(hwnd, SW_HIDE)
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, new)
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
        if visible:
            user32.ShowWindow(hwnd, SW_SHOW)

    def hide(self, hwnd) -> None:
        user32.ShowWindow(hwnd, SW_HIDE)

    def show(self, hwnd, activate: bool = True) -> None:
        user32.ShowWindow(hwnd, SW_RESTORE if self.is_minimized(hwnd) else SW_SHOW)
        if activate:
            self.bring_to_front(hwnd)

    def bring_to_front(self, hwnd) -> None:
        if user32.SetForegroundWindow(hwnd):
            return
        # Foreground lock: briefly attach to the foreground thread's input queue
        fg = user32.GetForegroundWindow()
        fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        me = kernel32.GetCurrentThreadId()
        if fg_thread and fg_thread != me:
            user32.AttachThreadInput(me, fg_thread, True)
            try:
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
            finally:
                user32.AttachThreadInput(me, fg_thread, False)

    def close(self, hwnd) -> None:
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)

    # ---- monitors ----------------------------------------------------------
    def work_areas(self) -> tuple[list[Rect], Rect]:
        """(all monitor work areas, primary work area)."""
        areas: list[Rect] = []
        primary: list[Rect] = []

        def cb(hmon, _hdc, _rc, _lp):
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(mi)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                areas.append(_rect(mi.rcWork))
                if mi.dwFlags & 1:  # MONITORINFOF_PRIMARY
                    primary.append(_rect(mi.rcWork))
            return True

        user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
        if not areas:
            areas = [Rect(0, 0, 1280, 720)]
        return areas, (primary[0] if primary else areas[0])

    def dpi_scale(self, hwnd=None) -> float:
        dpi = user32.GetDpiForWindow(hwnd) if hwnd else 0
        return (dpi or user32.GetDpiForSystem() or 96) / 96.0
