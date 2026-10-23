import json
from pathlib import Path

import panel_core as pc
from panel_core import Rect


# ---- geometry ---------------------------------------------------------------
PRIMARY = Rect(0, 0, 1920, 1040)          # 1080p with a 40 px taskbar
LEFT = Rect(-2560, -200, 0, 1240)          # second monitor left of the primary, higher up


def test_default_rect_right_side_100pct():
    r = pc.default_rect(PRIMARY, 1.0)
    assert r.xywh() == [1920 - 16 - 420, 16, 420, 720]


def test_default_rect_scaled_150pct_and_small_screen():
    r = pc.default_rect(PRIMARY, 1.5)
    assert (r.width, r.height) == (630, 1040 - 48)   # height clamped to the work area
    assert r.right == 1920 - 24 and r.top == 24
    tiny = pc.default_rect(Rect(0, 0, 400, 500), 1.0)
    assert tiny.left >= 0 and tiny.right <= 400 and tiny.bottom <= 500


def test_fit_rect_none_and_garbage_give_default():
    d = pc.default_rect(PRIMARY)
    assert pc.fit_rect(None, [PRIMARY], PRIMARY) == d
    assert pc.fit_rect(["a", 1, 2, 3], [PRIMARY], PRIMARY) == d
    assert pc.fit_rect([0, 0, 0, 10], [PRIMARY], PRIMARY) == d


def test_fit_rect_keeps_valid_position():
    assert pc.fit_rect([100, 200, 420, 720], [PRIMARY], PRIMARY).xywh() == [100, 200, 420, 720]


def test_fit_rect_second_monitor_negative_coords():
    r = pc.fit_rect([-2000, -100, 500, 800], [PRIMARY, LEFT], PRIMARY)
    assert r.xywh() == [-2000, -100, 500, 800]


def test_fit_rect_unplugged_monitor_falls_back_to_default():
    assert pc.fit_rect([-2000, -100, 500, 800], [PRIMARY], PRIMARY) == pc.default_rect(PRIMARY)


def test_fit_rect_title_bar_offscreen_above_is_default():
    assert pc.fit_rect([100, -600, 420, 700], [PRIMARY], PRIMARY) == pc.default_rect(PRIMARY)


def test_fit_rect_partially_offscreen_is_pulled_in_and_shrunk():
    r = pc.fit_rect([1700, 900, 420, 720], [PRIMARY], PRIMARY)
    assert r.right <= 1920 and r.bottom <= 1040 and r.width == 420
    big = pc.fit_rect([10, 10, 4000, 3000], [PRIMARY], PRIMARY)
    assert (big.width, big.height) == (1920, 1040) and big.left == 0 and big.top == 0


# ---- settings ---------------------------------------------------------------
def test_settings_defaults_and_roundtrip(tmp_path):
    p = tmp_path / "settings.json"
    s = pc.SettingsStore(p)
    assert s["hotkeys"]["toggle"] == "Ctrl+Alt+H"
    assert s["url"] == "https://home.google.com/u/0/"
    assert s["always_on_top"] is True and s["hide_from_taskbar"] is False
    s["geometry"] = [1, 2, 420, 720]
    s.save()
    assert pc.SettingsStore(p)["geometry"] == [1, 2, 420, 720]
    assert not list(tmp_path.glob("*.tmp"))


def test_settings_damaged_file_and_bad_types(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{not json", encoding="utf-8")
    assert pc.SettingsStore(p).data == pc.DEFAULT_SETTINGS
    p.write_text(json.dumps({"url": "javascript:alert(1)", "always_on_top": "yes", "browser": "ie",
                             "geometry": [1, 2], "hotkeys": {"toggle": 5, "show": "Ctrl+Alt+S"}}))
    s = pc.SettingsStore(p)
    assert s["url"] == pc.DEFAULT_URL and s["always_on_top"] is True and s["browser"] == "auto"
    assert s["geometry"] is None
    assert s["hotkeys"] == {"toggle": "Ctrl+Alt+H", "show": "Ctrl+Alt+S", "hide": ""}


def test_default_hotkey_does_not_clash_with_sibling_apps():
    assert pc.hotkey_clash(pc.DEFAULT_SETTINGS["hotkeys"]["toggle"]) is None
    assert pc.hotkey_clash("Ctrl+Alt+K") == "KeepNotes Widgets"
    assert pc.hotkey_clash("Ctrl+Alt+T") == "Todoist Widgets"


# ---- browser ----------------------------------------------------------------
ENV = {"ProgramFiles(x86)": r"C:\Program Files (x86)", "ProgramFiles": r"C:\Program Files",
       "LOCALAPPDATA": r"C:\Users\Alex\AppData\Local"}
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def _norm(p):
    return str(p).replace("/", "\\")


def test_find_browser_prefers_edge_from_registry():
    kind, path = pc.find_browser("auto", ENV, registry=lambda exe: EDGE if exe == "msedge.exe" else CHROME,
                                 exists=lambda p: _norm(p) in (EDGE, CHROME))
    assert (kind, path) == ("edge", EDGE)


def test_find_browser_program_files_fallback_without_registry():
    kind, path = pc.find_browser("auto", ENV, registry=lambda exe: None,
                                 exists=lambda p: _norm(p) == EDGE)
    assert kind == "edge" and _norm(path) == EDGE


def test_find_browser_falls_back_to_chrome_and_none():
    kind, path = pc.find_browser("auto", ENV, registry=lambda exe: None, exists=lambda p: _norm(p) == CHROME)
    assert kind == "chrome" and _norm(path) == CHROME
    assert pc.find_browser("auto", ENV, registry=lambda e: None, exists=lambda p: False) == (None, None)
    kind, _ = pc.find_browser("chrome", ENV, registry=lambda e: None, exists=lambda p: True)
    assert kind == "chrome"


def test_app_mode_args_have_no_debug_port():
    args = pc.app_mode_args("https://home.google.com/u/0/", Path(r"C:\x\HomePanel\EdgeProfile"))
    assert args[0] == "--app=https://home.google.com/u/0/"
    assert any(a.startswith("--user-data-dir=") for a in args)
    assert not any("remote-debugging" in a for a in args)


def test_cmdline_uses_profile():
    prof = Path(r"C:\Users\Alex\AppData\Local\HomePanel\EdgeProfile")
    yes = [r'"C:\Edge\msedge.exe" --app=https://home.google.com/u/0/ "--user-data-dir=C:\Users\Alex\AppData\Local\HomePanel\EdgeProfile" --no-first-run',
           r'msedge.exe --user-data-dir=c:\users\alex\appdata\local\homepanel\edgeprofile',
           r'msedge.exe --type=renderer --user-data-dir="C:\Users\Alex\AppData\Local\HomePanel\EdgeProfile" --x']
    no = [r'msedge.exe --user-data-dir=C:\Users\Alex\AppData\Local\HomePanel\EdgeProfile2',
          r'msedge.exe --profile-directory=Default', "", None]
    for c in yes:
        assert pc.cmdline_uses_profile(c, prof), c
    for c in no:
        assert not pc.cmdline_uses_profile(c, prof), c


def test_profile_dir_locations(tmpenv):
    assert pc.profile_dir("edge").name == "EdgeProfile"
    assert pc.profile_dir("chrome").name == "ChromeProfile"
    assert pc.profile_dir("edge").parent.name == "HomePanel"
