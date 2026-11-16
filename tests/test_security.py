"""Security-focused tests: secrets stay out of the MCP server, file paths are
confined, logins are throttled, texts can't break the page."""

import asyncio
import json
import os
import stat

import pytest

import launcher as L


# --- the internet-facing server never gets the Supervisor token ----------------

def test_mcp_server_gets_no_supervisor_token(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "super-secret")
    monkeypatch.setenv("HASSIO_TOKEN", "super-secret")
    monkeypatch.setenv("GARMIN_PASSWORD", "pw")
    L.TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    (L.TOKEN_DIR / "garmin_tokens.json").write_text("{}")
    captured = {}

    class FakeProc:
        def poll(self):
            return None

    def fake_popen(cmd, env=None, cwd=None, **kwargs):
        captured.update(cmd=cmd, env=env, cwd=cwd, kwargs=kwargs)
        return FakeProc()

    monkeypatch.setattr(L, "mcp_identity", lambda: (4242, 4243))
    monkeypatch.setattr(L.os, "lchown", lambda *a: None)
    monkeypatch.setattr(L.os, "chown", lambda *a: None)

    monkeypatch.setattr(L.subprocess, "Popen", fake_popen)
    services = L.Services()
    services.start_mcp()
    env = captured["env"]
    assert "SUPERVISOR_TOKEN" not in env and "HASSIO_TOKEN" not in env
    assert "GARMIN_PASSWORD" not in env
    assert env["GARMINTOKENS"] == str(L.TOKEN_DIR)
    assert captured["cmd"][-1].endswith("run_mcp.py")
    # runs as the unprivileged user, without extra groups, private files
    assert captured["kwargs"] == {"user": 4242, "group": 4243, "extra_groups": [], "umask": 0o077}
    assert env["HOME"] == str(L.MCP_HOME)
    assert env["GARMINTOKENS_BASE64"].startswith(str(L.TOKEN_DIR))
    (L.TOKEN_DIR / "garmin_tokens.json").unlink()


# --- tools can only touch files inside the download folder ---------------------

@pytest.fixture()
def run_mcp(tmp_path, monkeypatch):
    monkeypatch.setenv("GARMIN_FIT_DOWNLOAD_DIR", str(tmp_path / "downloads"))
    (tmp_path / "downloads").mkdir()
    import importlib
    import run_mcp as module
    return importlib.reload(module)


@pytest.mark.parametrize(
    "value",
    ["/homeassistant/www", "/data/garmin_tokens", "../../etc", "/homeassistant/secrets.yaml", "~", ""],
)
def test_paths_outside_download_folder_are_blocked(run_mcp, value):
    assert not run_mcp.path_allowed(value)


def test_paths_inside_download_folder_are_allowed(run_mcp):
    assert run_mcp.path_allowed(run_mcp.SANDBOX)
    assert run_mcp.path_allowed(os.path.join(run_mcp.SANDBOX, "runs"))
    assert run_mcp.path_allowed("course.gpx")  # relative = inside the folder


def test_symlink_escape_is_blocked(run_mcp, tmp_path):
    link = os.path.join(run_mcp.SANDBOX, "escape")
    os.symlink(str(tmp_path), link)
    assert not run_mcp.path_allowed(os.path.join(link, "x.gpx"))


def test_guarded_tool_refuses_outside_paths(run_mcp):
    calls = []

    async def upload_course(gpx_path: str, name: str = "x") -> str:
        calls.append(gpx_path)
        return "ok"

    guarded = run_mcp.confine_paths(upload_course)
    assert guarded.__name__ == "upload_course"
    blocked = asyncio.run(guarded(gpx_path="/homeassistant/secrets.yaml"))
    assert "blocked" in json.loads(blocked)["error"]
    assert calls == []
    assert asyncio.run(guarded(gpx_path="ok.gpx")) == "ok"


def test_every_path_parameter_of_the_server_is_covered(run_mcp):
    """If the server adds a new file path parameter, this test fails so it gets reviewed."""
    import importlib
    import inspect
    import pkgutil

    import garmin_mcp

    found = set()

    class Collect:
        def tool(self, *a, **k):
            def wrap(fn):
                for p in inspect.signature(fn).parameters:
                    if any(w in p.lower() for w in ("path", "dir", "file", "folder")):
                        found.add(p)
                return fn
            return wrap

        def __getattr__(self, _):
            return lambda *a, **k: (lambda fn: fn)

    for m in pkgutil.iter_modules(garmin_mcp.__path__):
        if m.name.startswith("_") or m.name == "auth_cli":
            continue
        mod = importlib.import_module(f"garmin_mcp.{m.name}")
        if hasattr(mod, "register_tools"):
            mod.register_tools(Collect())
    assert found <= run_mcp.PATH_PARAMETERS, f"unguarded path parameters: {found - run_mcp.PATH_PARAMETERS}"


# --- logins -------------------------------------------------------------------

def test_login_attempts_are_throttled(monkeypatch):
    L.LOGIN_ATTEMPTS.clear()
    for _ in range(L.MAX_LOGINS):
        L._throttle_login()
    with pytest.raises(L.LoginError) as err:
        L._throttle_login()
    assert err.value.key == "err_too_many_attempts"
    L.LOGIN_ATTEMPTS.clear()


def test_half_finished_mfa_login_expires():
    L.PENDING_MFA.update({"garmin": object(), "state": None, "started": 0})
    L.expire_pending_mfa()
    assert not L.PENDING_MFA


# --- files with secrets ---------------------------------------------------------

def test_secret_files_are_private():
    L.get_secret(rotate=True)
    L.get_webhook_id(rotate=True)
    for path in (L.SECRET_FILE, L.WEBHOOK_ID_FILE):
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


# --- texts used inside JavaScript confirm('...') must not contain quotes -------------

def test_confirm_texts_cannot_break_javascript():
    for code in L.i18n.LANGUAGES:
        for key, value in L.i18n.ui(code).items():
            if key.endswith("_confirm"):
                assert "'" not in value and "\\\\" not in value, (key, value)
    for code in L.i18n.LANGUAGES:
        for key, value in L.i18n.ui(code).items():
            assert "<" not in value or key in ("tools_intro",), key


def test_sync_tools_are_guarded_too(run_mcp):
    def download_course_gpx(course_id: int, output_path: str = "") -> str:
        return "written"

    guarded = run_mcp.confine_paths(download_course_gpx)
    assert "blocked" in json.loads(guarded(1, output_path="/homeassistant/www/x.gpx"))["error"]
    assert guarded(1, output_path="x.gpx") == "written"


def test_page_requests_never_wait_for_home_assistant(monkeypatch):
    calls = []
    monkeypatch.setattr(L, "core_api", lambda *a, **k: calls.append(a) or {"language": "de"})
    L.ha_language()
    assert calls == []
    assert L.refresh_ha_language() == "de" and L.ha_language() == "de"
    monkeypatch.setattr(L, "core_api", lambda *a, **k: None)  # HA unreachable: keep last value
    assert L.refresh_ha_language() == "de"
    monkeypatch.setattr(L, "_ha_language_cache", (0.0, ""))


def test_translated_details_cannot_crash_the_page():
    t = {"detail_integration_state": "state {value} {n} {"}
    assert L.detail_text(t, "@integration_state|loaded") == "state loaded {n} {"
    assert L.detail_text(t, "<b>") == "&lt;b&gt;"


def test_webhook_config_tells_the_integration_its_app(monkeypatch, tmp_path):
    monkeypatch.setattr(L, "WEBHOOK_CONFIG", tmp_path / "hook.json")
    monkeypatch.setattr(L.socket, "gethostname", lambda: "abcd1234-garmin-mcp")
    remote = L.RemoteAccess(L.Services())
    remote.webhook_id = "garmin_mcp_x"
    remote._write_config()
    data = json.loads((tmp_path / "hook.json").read_text())
    assert data["app_slug"] == "abcd1234_garmin_mcp"
    assert stat.S_IMODE(os.stat(tmp_path / "hook.json").st_mode) == 0o600


def test_page_is_only_for_home_assistant(monkeypatch):
    """The MCP server shares the container (127.0.0.1): it may see the health
    check, but never the page with the CSRF token and the connector URL."""
    from starlette.testclient import TestClient

    monkeypatch.setattr(L, "ALLOW_ANY_UI_CLIENT", False)

    class FakeServices:
        active_tools = set()
        options = {}

        def mcp_state(self):
            return "stopped"

    monkeypatch.setattr(L, "SERVICES", FakeServices(), raising=False)
    for ip, page, status_json in (("127.0.0.1", 403, 200), ("172.30.32.2", None, 200), ("8.8.8.8", 403, 403)):
        with TestClient(L.app, client=(ip, 50000)) as client:
            assert client.get("/status.json").status_code == status_json, ip
            if page:
                assert client.get("/").status_code == page, ip
                assert client.post("/restart-ha").status_code == page, ip
                assert client.post("/tools").status_code == page, ip
