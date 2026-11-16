"""Test setup: point the launcher at temporary folders and make the add-on
code and a minimal Home Assistant stub importable."""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "garmin_mcp" / "rootfs" / "app"

_tmp = Path(tempfile.mkdtemp(prefix="garmin-addon-test-"))
os.environ["ADDON_DATA_DIR"] = str(_tmp / "data")
os.environ["HA_CONFIG_DIR"] = str(_tmp / "homeassistant")
(_tmp / "data").mkdir()
(_tmp / "homeassistant").mkdir()

sys.path.insert(0, str(APP))
sys.path.insert(0, str(Path(__file__).resolve().parent / "hastub"))
sys.path.insert(0, str(APP / "integration"))
