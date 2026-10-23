import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tmpenv(tmp_path, monkeypatch):
    monkeypatch.setenv("HP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HP_PROFILE_BASE", str(tmp_path / "local"))
    return tmp_path
