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
    conf = L.NGINX_TEMPLATE.format(public_port=8100, mcp_port=8000, secret="S3CRET", report_location="")
    assert "location = /S3CRET/mcp" in conf
    assert "return 404" in conf
    assert "access_log off" in conf


# --- remote access clean-up (direct mode) ---------------------------------------

def test_direct_mode_removes_helper_integration(monkeypatch, tmp_path):
    component = tmp_path / "custom_components" / "garmin_mcp_webhook"
    component.mkdir(parents=True)
    (component / "manifest.json").write_text("{}")
    legacy = tmp_path / ".garmin_mcp_webhook.json"
    legacy.write_text("{}")
    monkeypatch.setattr(L, "COMPONENT_DST", component)
    monkeypatch.setattr(L, "LEGACY_WEBHOOK_CONFIG", legacy)
    monkeypatch.setattr(L, "DISCOVERY_FILE", tmp_path / "discovery_uuid")
    (tmp_path / "discovery_uuid").write_text("1234abcd")

    calls = []
    monkeypatch.setattr(L, "supervisor_api", lambda method, path, data=None: calls.append((method, path)) or {})
    L.OPTIONS_FILE.write_text(json.dumps({"remote_access": "direct"}))
    try:
        remote = L.RemoteAccess(L.Services())
        assert not remote.enabled
        remote.run()
    finally:
        L.OPTIONS_FILE.unlink()
    # Home Assistant removes the config entry itself when the discovery is withdrawn
    assert calls == [("DELETE", "/discovery/1234abcd")]
    assert not component.exists() and not legacy.exists()
    assert not (tmp_path / "discovery_uuid").exists()
    assert remote.cleaned_up


# --- connection test: blocks by Cloudflare are a note, not an error --------------

def _http_error(code, headers=None, body=b""):
    import io
    import urllib.error
    from email.message import Message

    msg = Message()
    for k, v in (headers or {}).items():
        msg[k] = v
    return urllib.error.HTTPError("https://example.com", code, "x", msg, io.BytesIO(body))


def test_cloudflare_block_is_recognised():
    assert L.blocked_by_proxy(_http_error(403, {"Server": "cloudflare", "CF-RAY": "abc"}))
    assert L.blocked_by_proxy(_http_error(403, body=b"<title>Attention Required! | Cloudflare</title>"))
    assert not L.blocked_by_proxy(_http_error(403, {"Server": "nginx"}))
    assert not L.blocked_by_proxy(_http_error(404, {"Server": "cloudflare"}))


def test_connection_test_sends_a_real_client_name(monkeypatch):
    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"result": {}}'

    def fake_urlopen(req, timeout=0):
        seen.update({k.lower(): v for k, v in req.header_items()})
        return Resp()

    monkeypatch.setattr(L.urllib.request, "urlopen", fake_urlopen)
    L._mcp_request("https://example.com/x", {})
    assert "python-urllib" not in seen["user-agent"].lower()
    assert "GarminConnectMCP" in seen["user-agent"]
