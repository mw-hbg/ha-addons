"""Tests for the configuration options and their handling."""

import os
import re
import time
from pathlib import Path

import pytest

import launcher as L

ADDON = Path(__file__).resolve().parent.parent / "garmin_mcp"


def opts(**kwargs):
    return {**L.DEFAULT_OPTIONS, **kwargs}


@pytest.fixture(autouse=True)
def _clean_selection():
    L.SELECTION_FILE.unlink(missing_ok=True)
    yield
    L.SELECTION_FILE.unlink(missing_ok=True)


# --- config.yaml, defaults and translations stay in sync ---------------------------

def _top_keys(text: str, section: str) -> list[str]:
    block = re.search(rf"^{section}:\n((?:  .*\n|\n)+)", text, re.M).group(1)
    return re.findall(r"^  ([a-z_]+):", block, re.M)


def test_options_schema_defaults_and_translations_match():
    cfg = (ADDON / "config.yaml").read_text()
    options = _top_keys(cfg, "options")
    schema = _top_keys(cfg, "schema")
    assert options == schema
    assert set(options) == set(L.DEFAULT_OPTIONS)
    for lang in ("en", "de"):
        text = (ADDON / "translations" / f"{lang}.yaml").read_text()
        assert _top_keys(text, "configuration") == options, lang


def test_documentation_lists_every_option():
    docs = (ADDON / "DOCS.md").read_text()
    for key in L.DEFAULT_OPTIONS:
        assert f"| `{key}` |" in docs, key


def test_area_names_match_the_server_profiles():
    from garmin_mcp.tool_profiles import TOOL_PROFILES

    cfg = (ADDON / "config.yaml").read_text()
    areas = re.search(r'"list\((all\|minimal[^)]*)\)"', cfg).group(1).split("|")
    assert set(areas) == set(TOOL_PROFILES)
    for lang in ("en", "de"):
        text = (ADDON / "translations" / f"{lang}.yaml").read_text()
        for area in areas:
            assert re.search(rf"^\s+{area} = ", text, re.M), (lang, area)


# --- public address ------------------------------------------------------------------

@pytest.mark.parametrize(
    "value, expected",
    [
        ("", ("", "")),
        ("home.example.com", ("https://home.example.com", "")),
        ("https://home.example.com/", ("https://home.example.com", "")),
        ("https://home.example.com/lovelace/0?x=1", ("https://home.example.com", "")),
        ("  https://home.example.com:8443  ", ("https://home.example.com:8443", "")),
        ("http://192.168.1.2:8123", ("http://192.168.1.2:8123", "http")),
        ("ftp://home.example.com", ("", "invalid")),
        ("https://", ("", "invalid")),
        ("https://home.example.com:99999", ("", "invalid")),
        ("https://user:pw@home.example.com", ("", "invalid")),
        ("home example com", ("", "invalid")),
    ],
)
def test_public_url_is_normalized(value, expected):
    assert L.normalize_public_url(value) == expected


# --- tool options --------------------------------------------------------------------

def test_unknown_tool_names_are_reported():
    assert L.unknown_tool_names(opts(enable_tools=["push_workout_to_device", "pushworkout"], disable_tools=[" Delete_Activity "])) == ["pushworkout"]


def test_workouts_area_can_send_to_the_watch():
    env, active = L.tool_selection(opts(tool_areas=["workouts"]))
    assert "push_workout_to_device" in active
    assert "push_workout_to_device" in env["GARMIN_ENABLED_TOOLS"]
    # extras still obey the write access level
    assert "reschedule_workout" not in active
    env, active = L.tool_selection(opts(tool_areas=["workouts"], write_access="read_only"))
    assert "push_workout_to_device" not in active
    assert "push_workout_to_device" in env["GARMIN_DISABLED_TOOLS"].split(",")


def test_other_areas_get_no_extras():
    env, active = L.tool_selection(opts(tool_areas=["health"]))
    assert "GARMIN_ENABLED_TOOLS" not in env
    assert "push_workout_to_device" not in active


@pytest.mark.parametrize("value, days", [(7, 7), ("3", 3), (0, 0), (-5, 0), (9999, 365), ("x", 7), (None, 7)])
def test_keep_days_is_clamped(value, days):
    assert L.keep_days({"keep_downloads_days": value}) == days


# --- download clean-up ----------------------------------------------------------------

def test_old_downloads_are_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "DOWNLOAD_DIR", tmp_path)
    old = tmp_path / "runs" / "old.fit"
    new = tmp_path / "new.gpx"
    old.parent.mkdir()
    old.write_text("x")
    new.write_text("x")
    week_ago = time.time() - 8 * 86400
    os.utime(old, (week_ago, week_ago))
    assert L.prune_downloads(7) == 1
    assert not old.exists() and not old.parent.exists() and new.exists()
    assert L.prune_downloads(0, now=time.time() + 400 * 86400) == 0  # 0 = keep forever
    assert new.exists()


def test_cleanup_never_follows_symlinks(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    keep = outside / "keep.txt"
    keep.write_text("x")
    old = time.time() - 30 * 86400
    os.utime(keep, (old, old))
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "link").symlink_to(outside)
    monkeypatch.setattr(L, "DOWNLOAD_DIR", downloads)
    L.prune_downloads(1, now=time.time() + 30 * 86400)
    assert keep.exists()


# --- login notification can be switched off -------------------------------------------

def test_login_notification_option(monkeypatch):
    calls = []
    monkeypatch.setattr(L, "core_api", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(L, "has_tokens", lambda: True)
    services = L.Services()
    monkeypatch.setattr(services, "mcp_state", lambda: "failed")
    monkeypatch.setattr(services, "restart_mcp", lambda: None)
    services.options = opts(login_notification=False)
    services._login_failures = 5
    services._next_login_retry = time.time() + 999
    services._check_login()
    assert calls == []
    services.options = opts(login_notification=True)
    services._check_login()
    assert any("persistent_notification/create" in c[1] for c in calls)


# --- the page is never cached and only framed by Home Assistant -----------------------

def test_security_headers(monkeypatch):
    from starlette.testclient import TestClient

    monkeypatch.setattr(L, "ALLOW_ANY_UI_CLIENT", True)
    with TestClient(L.app) as client:
        resp = client.get("/does-not-exist")  # headers are added to every response
    assert resp.headers["cache-control"] == "no-store"
    assert resp.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'self'" in resp.headers["content-security-policy"]
