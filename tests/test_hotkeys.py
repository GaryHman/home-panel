import pytest

import win_hotkeys as hk


def test_parse_default_toggle(qapp):
    mods, vk = hk.parse_hotkey("Ctrl+Alt+H")
    assert mods == hk.MOD_CONTROL | hk.MOD_ALT and vk == ord("H")


@pytest.mark.parametrize("text", ["H", "Ctrl+H", "", "Ctrl+Alt+Del"])
def test_parse_rejects(qapp, text):
    with pytest.raises(ValueError):
        hk.parse_hotkey(text)


def test_normalise_and_labels(qapp):
    assert hk.normalise("ctrl+alt+h") == "Ctrl+Alt+H"
    assert hk.label_of("toggle") == "Toggle panel (show / hide)"


def test_manager_duplicates_reported(qapp):
    m = hk.HotkeyManager()
    errs = m.apply({"toggle": "Ctrl+Alt+H", "show": "Ctrl+Alt+H", "hide": "Ctrl+H"})
    assert m.active == {"toggle": "Ctrl+Alt+H"}
    assert {e[0] for e in errs} == {"show", "hide"}
