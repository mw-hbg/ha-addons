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

    def fake_popen(cmd, env=None, cwd=None):
        captured.update(cmd=cmd, env=env, cwd=cwd)
        return FakeProc()

    monkeypatch.setattr(L.subprocess, "Popen", fake_popen)
    services = L.Services()
    services.start_mcp()
    env = captured["env"]
    assert "SUPERVISOR_TOKEN" not in env and "HASSIO_TOKEN" not in env
    assert "GARMIN_PASSWORD" not in env
    assert env["GARMINTOKENS"] == str(L.TOKEN_DIR)
    assert captured["cmd"][-1].endswith("run_mcp.py")
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
    for lang in L.TEXT.values():
        for key, value in lang.items():
            if key.endswith("_confirm"):
                assert "'" not in value and "\\\\" not in value, (key, value)
    for lang in L.TEXT.values():
        for key, value in lang.items():
            assert "<" not in value or key in ("tools_intro",), key
