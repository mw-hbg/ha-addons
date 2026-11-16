"""Tests for the app launcher: tool protection, selection, texts, secrets, clean-up."""

import json

import pytest

import launcher as L


@pytest.fixture(autouse=True)
def _clean_selection():
    L.SELECTION_FILE.unlink(missing_ok=True)
    yield
    L.SELECTION_FILE.unlink(missing_ok=True)


def opts(**kwargs):
    return {**L.DEFAULT_OPTIONS, **kwargs}


# --- tool catalog and protection -------------------------------------------

def test_catalog_covers_every_registered_tool():
    names = {e["name"] for e in L.CATALOG}
    assert len(names) >= 150
    assert names == set(L.ALL_TOOLS)


def test_unknown_tools_count_as_change():
    assert L.kind_of("some_tool_a_future_update_adds") == "change"
    assert L.kind_of("get_activities") == "read"
    assert L.kind_of("schedule_workout") == "create"
    assert L.kind_of("delete_activity") == "change"


def test_read_only_allows_only_reading():
    _, active = L.tool_selection(opts(write_access="read_only"))
    assert active and all(L.kind_of(n) == "read" for n in active)


def test_create_only_never_allows_change():
    _, active = L.tool_selection(opts(write_access="create_only"))
    assert "schedule_workout" in active
    assert not any(L.kind_of(n) == "change" for n in active)


def test_full_allows_everything():
    _, active = L.tool_selection(opts(write_access="full"))
    assert active == set(L.ALL_TOOLS)


def test_unclassified_new_tool_is_blocked(monkeypatch):
    monkeypatch.setattr(L, "ALL_TOOLS", L.ALL_TOOLS | {"wipe_everything"})
    for level in ("read_only", "create_only"):
        env, active = L.tool_selection(opts(write_access=level))
        assert "wipe_everything" not in active
        assert "wipe_everything" in env["GARMIN_DISABLED_TOOLS"].split(",")


def test_disable_tools_always_wins():
    _, active = L.tool_selection(opts(write_access="full", disable_tools=["delete_activity"]))
    assert "delete_activity" not in active


def test_enable_tools_adds_single_tool():
    _, active = L.tool_selection(opts(write_access="create_only", enable_tools=["set_perceived_effort"]))
    assert "set_perceived_effort" in active
    assert "delete_activity" not in active


def test_area_profile_with_extra_tool():
    env, active = L.tool_selection(opts(tool_areas=["workouts"], enable_tools=["push_workout_to_device"]))
    assert env["GARMIN_TOOL_PROFILE"] == "workouts"
    assert "push_workout_to_device" in active
    assert "get_sleep_data" not in active


# --- saved selection ----------------------------------------------------------

def test_saved_selection_replaces_options():
    L.save_selection({"get_activities", "delete_activity"})
    env, active = L.tool_selection(opts(write_access="read_only"))
    assert active == {"get_activities", "delete_activity"}
    assert "get_sleep_data" in env["GARMIN_DISABLED_TOOLS"].split(",")


def test_selection_of_older_version_still_loads():
    L.SELECTION_FILE.write_text(json.dumps(["get_activities"]))
    _, active = L.tool_selection(opts())
    assert active == {"get_activities"}
    assert L.new_tools() == []


def test_new_tools_after_update_are_off_and_reported():
    known = sorted(set(L.ALL_TOOLS) - {"get_hill_score"})
    L.SELECTION_FILE.write_text(json.dumps({"enabled": ["get_activities"], "known": known}))
    assert L.new_tools() == ["get_hill_score"]
    _, active = L.tool_selection(opts())
    assert "get_hill_score" not in active


# --- secrets and nginx --------------------------------------------------------

def test_secret_path_is_long_random_and_stable():
    first = L.get_secret()
    assert len(first) >= 32
    assert L.get_secret() == first
    rotated = L.get_secret(rotate=True)
    assert rotated != first


def test_nginx_only_forwards_the_secret_path():
    conf = L.NGINX_TEMPLATE.format(public_port=8100, mcp_port=8000, secret="S3CRET")
    assert "location = /S3CRET/mcp" in conf
    assert "return 404" in conf
    assert "access_log off" in conf


# --- remote access clean-up (direct mode) ---------------------------------------

def test_direct_mode_removes_helper_integration(monkeypatch, tmp_path):
    component = tmp_path / "custom_components" / "garmin_mcp_webhook"
    component.mkdir(parents=True)
    (component / "manifest.json").write_text("{}")
    config_file = tmp_path / ".garmin_mcp_webhook.json"
    config_file.write_text("{}")
    monkeypatch.setattr(L, "COMPONENT_DST", component)
    monkeypatch.setattr(L, "WEBHOOK_CONFIG", config_file)

    calls = []

    def fake_api(method, path, data=None, quiet=False):
        calls.append((method, path))
        if method == "GET":
            return [{"domain": "garmin_mcp_webhook", "entry_id": "abc", "state": "loaded"}]
        return {}

    monkeypatch.setattr(L, "core_api", fake_api)
    L.OPTIONS_FILE.write_text(json.dumps({"remote_access": "direct"}))
    try:
        remote = L.RemoteAccess(L.Services())
        assert not remote.enabled
        remote.run()
    finally:
        L.OPTIONS_FILE.unlink()
    assert ("DELETE", "/config/config_entries/entry/abc") in calls
    assert not component.exists() and not config_file.exists()
    assert remote.cleaned_up
