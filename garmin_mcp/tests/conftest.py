"""Test setup: point the launcher at temporary folders and make the app
code and a minimal Home Assistant stub importable."""

import os
import sys
import tempfile
from pathlib import Path

# Tests live in the app folder: garmin_mcp/tests
ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "rootfs" / "app"

_tmp = Path(tempfile.mkdtemp(prefix="garmin-app-test-"))
os.environ["APP_DATA_DIR"] = str(_tmp / "data")
os.environ["HA_CONFIG_DIR"] = str(_tmp / "homeassistant")
(_tmp / "data").mkdir()
(_tmp / "homeassistant").mkdir()

sys.path.insert(0, str(APP))
sys.path.insert(0, str(Path(__file__).resolve().parent / "hastub"))
sys.path.insert(0, str(APP / "integration"))
