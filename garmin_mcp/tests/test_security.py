"""Security-focused tests: secrets stay out of the MCP server, file paths are
confined, logins are throttled, texts can't break the page."""

import asyncio
import json
import os
import re
import stat

import pytest
from pathlib import Path

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

    monkeypatch.setattr(L, "mcp_identity", lambda user="garmin": (4242, 4243))
    monkeypatch.setattr(L.os, "chown", lambda *a, **k: None)

    monkeypatch.setattr(L.subprocess, "Popen", fake_popen)
    services = L.Services()
    services.primary.start_mcp()
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
    account = L.Services().primary
    account.pending_mfa.update({"garmin": object(), "state": None, "started": 0})
    account.expire_pending_mfa()
    assert not account.pending_mfa


# --- files with secrets ---------------------------------------------------------

def test_secret_files_are_private():
    L.get_secret(rotate=True)
    L.get_webhook_id(rotate=True)
    for path in (L.SECRET_FILE, L.WEBHOOK_ID_FILE):
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


# --- confirmation questions: any text (quotes too) stays a question ------------------

def test_confirm_texts_cannot_break_javascript():
    attrs = L._confirm("L'URL \"secrète\" </form><script>alert(1)</script>")
    assert attrs.endswith('onsubmit="return confirm(this.dataset.confirm)"')
    assert "<script>" not in attrs and "'" not in attrs.split("onsubmit")[0].replace("&#x27;", "")
    assert 'data-confirm="L&#x27;URL &quot;secrète&quot; &lt;/form&gt;' in attrs
    src = Path(L.__file__).read_text()
    assert "confirm(\\'" not in src  # no question built into script text any more
    for code in L.i18n.LANGUAGES:
        for key, value in L.i18n.ui(code).items():
            assert "<" not in value or key in ("tools_intro",), key


def test_sync_tools_are_guarded_too(run_mcp):
    def download_course_gpx(course_id: int, output_path: str = "") -> str:
        return "written"

    guarded = run_mcp.confine_paths(download_course_gpx)
    assert "blocked" in json.loads(guarded(1, output_path="/homeassistant/www/x.gpx"))["error"]
    assert guarded(1, output_path="x.gpx") == "written"


def test_translated_details_cannot_crash_the_page():
    t = {"detail_integration_state": "state {value} {n} {"}
    assert L.detail_text(t, "@integration_state|loaded") == "state loaded {n} {"
    assert L.detail_text(t, "<b>") == "&lt;b&gt;"


def test_discovery_tells_the_integration_everything_it_needs(monkeypatch):
    monkeypatch.setattr(L.socket, "gethostname", lambda: "abcd1234-garmin-mcp")
    monkeypatch.setattr(L, "_own_ip", lambda: "172.30.33.5")
    services = L.Services()
    second = services.add_account()
    remote = L.RemoteAccess(services)
    config = remote.discovery_config()
    first = services.primary
    assert config["app_slug"] == "abcd1234_garmin_mcp"
    assert config["report_url"] == f"http://172.30.33.5:8100/{services.report_secret}/ha"
    assert [a["id"] for a in config["accounts"]] == ["1", second.id]
    assert config["accounts"][1]["target_url"] == f"http://172.30.33.5:8100/{second.secret}/mcp"
    assert config["accounts"][1]["webhook_id"] == second.webhook_id != first.webhook_id
    # helper integrations before 0.5 read the first account from the top level
    assert config["target_url"] == f"http://172.30.33.5:8100/{first.secret}/mcp"
    assert config["webhook_id"] == first.webhook_id
    assert services.report_secret not in (first.secret, second.secret)
    import garmin_mcp_webhook.config_flow as flow

    data = flow.entry_data(config, "abcd1234_garmin_mcp")
    assert [a["id"] for a in data["accounts"]] == ["1", second.id]


def test_app_has_no_home_assistant_api():
    """The app must not be able to change anything in Home Assistant via its API."""
    cfg = (Path(L.__file__).resolve().parents[2] / "config.yaml").read_text()
    for key in ("homeassistant_api", "hassio_api", "auth_api", "docker_api", "full_access", "host_network", "privileged"):
        assert f"{key}:" not in cfg, key
    assert "garmin_mcp_webhook" in cfg.split("discovery:")[1].split("\n\n")[0]
    source = Path(L.__file__).read_text()
    assert "/core/api" not in source and "core/websocket" not in source
    assert re.findall(r'supervisor_api\("(?:POST|DELETE|GET)", f?"([^"{]+)', source) == ["/discovery", "/discovery/"]


def test_report_needs_the_key_from_nginx(monkeypatch):
    from starlette.testclient import TestClient

    services = L.Services()
    remote = L.RemoteAccess(services)
    monkeypatch.setattr(L, "SERVICES", services, raising=False)
    monkeypatch.setattr(L, "REMOTE", remote, raising=False)
    monkeypatch.setattr(services.primary, "login_status", lambda: "failed")
    with TestClient(L.app, client=("127.0.0.1", 50000)) as client:
        assert client.post("/report", json={}).status_code == 403
        assert client.post("/report", json={}, headers={"X-Report-Key": "wrong"}).status_code == 403
        # an account's secret path (it is in AI apps) is not the key
        assert client.post("/report", json={}, headers={"X-Report-Key": services.primary.secret}).status_code == 403
        too_big = {"external_url": "x" * 5000}
        assert client.post("/report", json=too_big, headers={"X-Report-Key": services.report_secret}).status_code == 413
        resp = client.post(
            "/report",
            json={"external_url": "https://home.example.com/lovelace", "language": "de", "integration_version": "1", "evil": "<script>"},
            headers={"X-Report-Key": services.report_secret},
        )
    assert resp.status_code == 200 and resp.json()["login"] == "failed"
    assert resp.json()["accounts"]["1"]["login"] == "failed"
    assert remote.report["external_url"] == "https://home.example.com" and remote.base_url() == "https://home.example.com"
    assert "evil" not in remote.report


def test_report_endpoint_only_in_webhook_mode_and_only_internal():
    services = L.Services()
    conf = services._report_location()
    assert f"/{services.report_secret}/ha" in conf and "allow 172.30.32.0/23;" in conf and "deny all;" in conf
    services.options = {**services.options, "remote_access": "direct"}
    assert services._report_location() == ""


def test_remote_state_follows_the_reports(monkeypatch):
    remote = L.RemoteAccess(L.Services())
    version = remote.bundled_version()
    remote.receive_report({"integration_version": version})
    assert remote.state == "active"
    remote.receive_report({"integration_version": "0.0.1"})
    assert remote.state == "restart_needed"
    remote.receive_report({"integration_version": version, "restart_needed": True})
    assert remote.state == "restart_needed"
    remote.report["time"] = 0  # no report for a long time
    remote.first_install = True
    remote._update_state()
    assert remote.state == "restart_needed"


def test_page_is_only_for_home_assistant(monkeypatch):
    """The MCP server shares the container (127.0.0.1): it may see the health
    check, but never the page with the CSRF token and the connector URL."""
    from starlette.testclient import TestClient

    monkeypatch.setattr(L, "ALLOW_ANY_UI_CLIENT", False)

    services = L.Services()
    monkeypatch.setattr(L, "SERVICES", services, raising=False)
    monkeypatch.setattr(L, "REMOTE", L.RemoteAccess(services), raising=False)
    for ip, page, status_json in (("127.0.0.1", 403, 200), ("172.30.32.2", None, 200), ("8.8.8.8", 403, 403)):
        with TestClient(L.app, client=(ip, 50000)) as client:
            assert client.get("/status.json").status_code == status_json, ip
            if page:
                assert client.get("/").status_code == page, ip
                for path in ("/rotate", "/tools", "/accounts/add", "/accounts/remove", "/accounts/rename",
                             "/accounts/settings", "/settings/shared", "/login", "/logout"):
                    assert client.post(path).status_code == page, (ip, path)


def test_landlock_limits_the_mcp_server_to_its_folders(tmp_path):
    """Runs in a child process: Landlock cannot be undone."""
    import subprocess
    import sys
    import textwrap

    import sandbox

    allowed, outside = tmp_path / "allowed", tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    (outside / "secrets.yaml").write_text("x")
    code = textwrap.dedent(f"""
        import os, sys
        sys.path.insert(0, {str(Path(sandbox.__file__).parent)!r})
        import sandbox
        prefix = os.path.realpath(sys.prefix)
        if not sandbox.restrict([{str(allowed)!r}], sandbox.READ_PATHS + (prefix, os.path.realpath(sys.base_prefix))):
            sys.exit(77)
        open({str(allowed / "ok")!r}, "w").write("ok")
        for action in (lambda: open({str(outside / "secrets.yaml")!r}).read(),
                       lambda: open({str(outside / "new")!r}, "w"),
                       lambda: os.listdir({str(tmp_path)!r})):
            try:
                action()
            except PermissionError:
                continue
            sys.exit("not blocked")
    """)
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    if result.returncode == 77:
        pytest.skip("Landlock not available on this machine")
    assert result.returncode == 0, result.stderr + result.stdout
    assert (allowed / "ok").read_text() == "ok"


def test_apparmor_profile_limits_the_home_assistant_folder():
    """The whole app may only touch its own helper integration in the HA folder."""
    profile = (Path(L.__file__).resolve().parents[2] / "apparmor.txt").read_text()
    assert re.search(r"^profile \S+ flags=\(attach_disconnected,mediate_deleted\) \{", profile, re.M)
    rules = [line.strip().rstrip(",") for line in profile.splitlines() if line.strip().startswith("/homeassistant")]
    assert sorted(rules) == sorted([
        "/homeassistant/ r",
        "/homeassistant/custom_components/ rw",
        "/homeassistant/custom_components/garmin_mcp_webhook/ rw",
        "/homeassistant/custom_components/garmin_mcp_webhook/** rwl",
        "/homeassistant/.garmin_mcp_webhook.json w",
    ])
    executables = re.findall(r"^\s*(\S+) [a-z]*x[a-z]*,", profile, re.M)
    assert sorted(executables) == ["/usr/local/bin/python3*", "/usr/sbin/nginx"]
    for capability in ("sys_admin", "net_admin", "sys_module", "sys_ptrace", "net_raw"):
        assert f"capability {capability}" not in profile


def test_rejected_login_during_a_call_is_reported(run_mcp, tmp_path, monkeypatch):
    """Garmin rejects the tokens while the server runs (e.g. password changed):
    the server leaves a marker, the app shows 'login failed' and HA a repair notice."""
    import garmin_mcp
    from garminconnect import GarminConnectAuthenticationError

    marker = tmp_path / "auth_failed"
    monkeypatch.setattr(run_mcp, "AUTH_FAILED_MARKER", str(marker))

    class Client:
        fail = True

        def get_activities(self):
            if self.fail:
                raise GarminConnectAuthenticationError("401")
            return []

    client = Client()
    proxy = garmin_mcp._GarminProxy(client)
    with pytest.raises(Exception) as err:
        proxy.get_activities()
    assert run_mcp.RELOGIN_HINT in str(err.value)
    assert marker.exists()
    client.fail = False
    assert proxy.get_activities() == []
    assert not marker.exists()


def test_app_shows_failed_login_from_the_marker(monkeypatch, tmp_path):
    account = L.Services().primary
    account.auth_failed_file = tmp_path / "auth_failed"
    monkeypatch.setattr(account, "has_tokens", lambda: True)
    monkeypatch.setattr(account, "mcp_state", lambda: "ready")
    assert account.login_status() == "ok" and account.shown_state() == "ready"
    (tmp_path / "auth_failed").write_text("x")
    assert account.login_status() == "failed" and account.shown_state() == "failed"


# --- switch "Garmin Connect MCP Server" in Home Assistant ----------------------------

def test_switch_in_home_assistant_stops_and_starts_the_server(monkeypatch):
    L.SWITCHED_OFF_FILE.unlink(missing_ok=True)
    services = L.Services()
    account = services.primary
    calls = []
    monkeypatch.setattr(account, "stop_mcp", lambda: calls.append("stop"))
    monkeypatch.setattr(account, "start_mcp", lambda: calls.append("start"))
    remote = L.RemoteAccess(services)
    version = remote.bundled_version()

    # helper integration 0.4: one switch at the top level = first account
    answer = remote.receive_report({"integration_version": version, "mcp_enabled": False})
    assert calls == ["stop"] and answer["mcp_enabled"] is False
    assert account.switched_off and L.SWITCHED_OFF_FILE.exists()
    assert account.login_status() == "off" and account.shown_state() == "off"

    remote.receive_report({"integration_version": version, "mcp_enabled": False})
    remote.receive_report({"integration_version": version})  # nothing about switches: no change
    assert calls == ["stop"]

    answer = remote.receive_report({"integration_version": version, "accounts": {"1": {"mcp_enabled": True}}})
    assert calls == ["stop", "start"] and answer["accounts"]["1"]["mcp_enabled"] is True
    assert not account.switched_off and not L.SWITCHED_OFF_FILE.exists()


def test_switched_off_server_is_not_started_and_survives_a_restart(monkeypatch):
    L.SWITCHED_OFF_FILE.touch()
    try:
        account = L.Services().primary
        assert account.switched_off
        monkeypatch.setattr(L.subprocess, "Popen", lambda *a, **k: pytest.fail("must not start"))
        account.start_mcp()
        assert account.mcp is None
    finally:
        L.SWITCHED_OFF_FILE.unlink(missing_ok=True)


def test_switch_only_counts_in_webhook_mode(monkeypatch):
    L.SWITCHED_OFF_FILE.touch()
    original = L.load_options
    monkeypatch.setattr(L, "load_options", lambda: {**original(), "remote_access": "direct"})
    account = L.Services().primary
    assert not account.switched_off and not L.SWITCHED_OFF_FILE.exists()


def test_stand_in_explains_the_switch():
    answer = L.not_ready_answer({"jsonrpc": "2.0", "id": 1, "method": "tools/call"}, "off")
    assert "switched off in Home Assistant" in answer["result"]["content"][0]["text"]


# --- root never follows the MCP user's symlinks -----------------------------------------

def test_connection_test_reads_tokens_without_following_links(tmp_path):
    folder = tmp_path / "tokens"
    folder.mkdir()
    target = tmp_path / "secret"
    target.write_text("x" * 600)
    (folder / "garmin_tokens.json").symlink_to(target)
    with pytest.raises(OSError):
        L.read_tokens(folder)  # planted link: refused, the target is never read
    (folder / "garmin_tokens.json").unlink()
    (folder / "garmin_tokens.json").write_text('{"di_token": "' + "t" * 600 + '"}')
    assert L.read_tokens(folder).startswith('{"di_token"')
    (folder / "garmin_tokens.json").write_text("{}")
    with pytest.raises(ValueError):
        L.read_tokens(folder)  # would be taken for a folder name by garminconnect


def test_chown_of_the_mcp_folders_does_not_follow_links(tmp_path, monkeypatch):
    services = L.Services()
    account = services.add_account()
    account.token_dir.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "root_only"
    outside.write_text("secret")
    os.chown(outside, 0, 0)
    (account.token_dir / "evil").symlink_to(outside)
    L.prepare_mcp_dirs((4321, 4321), account)
    assert os.stat(outside).st_uid == 0  # the target stays root's
    assert os.lstat(account.token_dir / "evil").st_uid == 4321
    assert os.stat(account.token_dir).st_uid == 4321


def test_removed_account_is_never_started_again(monkeypatch):
    services = L.Services()
    account = services.add_account()
    started = []
    monkeypatch.setattr(L.Account, "has_tokens", lambda self: True)
    monkeypatch.setattr(L.subprocess, "Popen", lambda *a, **k: started.append(a) or None)
    monkeypatch.setattr(L, "prepare_mcp_dirs", lambda *a, **k: None)
    services.remove_account(account)
    account.start_mcp()  # e.g. a restart timer or login check still running
    assert started == [] and account.id not in services.accounts
