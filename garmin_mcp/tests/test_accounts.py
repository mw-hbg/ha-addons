"""Several Garmin accounts in one app: update path, limits, separation, rights, page."""

import json
import re

import pytest

import launcher as L


@pytest.fixture()
def page(monkeypatch):
    """Services + remote access as the page sees them, page open to the test client."""
    from starlette.testclient import TestClient

    services = L.Services()
    remote = L.RemoteAccess(services)
    remote.state = "active"
    monkeypatch.setattr(L, "SERVICES", services, raising=False)
    monkeypatch.setattr(L, "REMOTE", remote, raising=False)
    monkeypatch.setattr(L, "ALLOW_ANY_UI_CLIENT", True)
    for name in ("start_mcp", "stop_mcp"):
        monkeypatch.setattr(L.Account, name, lambda self: None)
    with TestClient(L.app) as client:
        yield services, client


def _form(**fields):
    return {"csrf": L.CSRF_TOKEN, **fields}


# --- update from a version with a single account ------------------------------------

def test_existing_install_becomes_account_1_unchanged():
    secret = L.get_secret(rotate=True)
    webhook = L.get_webhook_id(rotate=True)
    L.ACCOUNT_FILE.write_text(json.dumps({"name": "Moritz"}))
    try:
        services = L.Services()
        account = services.primary
        assert list(services.accounts) == ["1"]
        assert account.secret == secret and account.webhook_id == webhook  # same connector URL
        assert account.token_dir == L.TOKEN_DIR and account.home == L.MCP_HOME  # files stay where they are
        assert account.user == "garmin" and account.port == L.MCP_PORT
        assert account.display_name() == "Moritz"
        assert services.same_settings  # settings keep applying to everything
        assert json.loads(L.ACCOUNTS_FILE.read_text())["accounts"] == [{"id": "1", "slot": 1, "custom_name": ""}]
    finally:
        L.ACCOUNT_FILE.unlink(missing_ok=True)


# --- adding and removing ------------------------------------------------------------

def test_up_to_ten_accounts_each_with_own_files_user_and_port():
    services = L.Services()
    for _ in range(L.MAX_ACCOUNTS - 1):
        services.add_account()
    with pytest.raises(L.AccountError) as err:
        services.add_account()
    assert err.value.key == "err_max_accounts"
    accounts = list(services.accounts.values())
    assert len(accounts) == 10
    for attr in ("secret", "webhook_id", "port", "user", "token_dir", "home", "download_dir"):
        values = [getattr(a, attr) for a in accounts]
        assert len(set(values)) == 10, attr
    assert sorted(a.user for a in accounts) == sorted(["garmin"] + [f"garmin{n}" for n in range(2, 11)])
    assert all(a.base == L.ACCOUNTS_DIR / a.id for a in accounts[1:])
    # other users may pass through, but never list the folders
    import os
    import stat

    for folder in (L.ACCOUNTS_DIR, accounts[1].base):
        assert stat.S_IMODE(os.stat(folder).st_mode) == 0o711
    assert stat.S_IMODE(os.stat(accounts[1].secret_file).st_mode) == 0o600


def test_ids_are_never_reused_but_slots_are(tmp_path):
    services = L.Services()
    second = services.add_account()
    (second.token_dir).mkdir(parents=True, exist_ok=True)
    (second.token_dir / "garmin_tokens.json").write_text("{}")
    services.remove_account(second)
    assert not second.base.exists()  # tokens, URL, settings gone
    third = services.add_account()
    assert third.id != second.id and third.slot == second.slot  # entity ids in HA stay unique
    reloaded = L.Services()
    assert list(reloaded.accounts) == ["1", third.id]


def test_removing_account_1_deletes_only_its_files():
    services = L.Services()
    second = services.add_account()
    first = services.primary
    L.TOKEN_DIR.mkdir(exist_ok=True)
    (L.TOKEN_DIR / "garmin_tokens.json").write_text("{}")
    L.OPTIONS_FILE.write_text("{}")
    try:
        services.remove_account(first)
        assert not L.TOKEN_DIR.exists() and not L.SECRET_FILE.exists()
        assert L.OPTIONS_FILE.exists() and second.secret_file.exists()  # app and other accounts untouched
        assert list(L.Services().accounts) == [second.id]
    finally:
        L.OPTIONS_FILE.unlink(missing_ok=True)


def test_names_profile_or_own():
    services = L.Services()
    account = services.add_account()
    assert account.display_name() == account.id
    account.info_file.parent.mkdir(parents=True, exist_ok=True)
    account.info_file.write_text(json.dumps({"name": "Belinda Muster"}))
    assert account.display_name() == "Belinda Muster"
    services.rename_account(account, "  Beli\n   " + "x" * 60)
    assert account.display_name().startswith("Beli x") and len(account.display_name()) == 40
    services.rename_account(account, "")
    assert account.display_name() == "Belinda Muster"
    services.rename_account(account, "Belinda")
    assert L.Services().accounts[account.id].display_name() == "Belinda"  # kept


# --- separation -------------------------------------------------------------------

def test_each_server_gets_only_its_own_account(monkeypatch):
    captured = []

    class FakeProc:
        def poll(self):
            return None

    monkeypatch.setattr(L.subprocess, "Popen", lambda cmd, env=None, cwd=None, **kw: captured.append((env, kw)) or FakeProc())
    monkeypatch.setattr(L, "mcp_identity", lambda user="garmin": (5000 + int(user[6:] or 1), 6000))
    monkeypatch.setattr(L.os, "lchown", lambda *a: None)
    monkeypatch.setattr(L.os, "chown", lambda *a: None)
    services = L.Services()
    second = services.add_account()
    second.token_dir.mkdir(parents=True, exist_ok=True)
    (second.token_dir / "garmin_tokens.json").write_text("{}")
    second.start_mcp()
    env, kwargs = captured[-1]
    assert env["GARMINTOKENS"] == str(second.token_dir) and env["HOME"] == str(second.home)
    assert env["GARMIN_FIT_DOWNLOAD_DIR"] == str(second.download_dir)
    assert env["GARMIN_MCP_PORT"] == str(second.port) != str(L.MCP_PORT)
    assert kwargs["user"] == 5000 + second.slot  # its own user, not "garmin"
    assert str(L.TOKEN_DIR) not in json.dumps(env)


def test_switches_only_affect_their_own_account(monkeypatch):
    services = L.Services()
    second = services.add_account()
    calls = []
    for account in services.accounts.values():
        monkeypatch.setattr(account, "stop_mcp", lambda a=account: calls.append(("stop", a.id)))
        monkeypatch.setattr(account, "start_mcp", lambda a=account: calls.append(("start", a.id)))
    remote = L.RemoteAccess(services)
    answer = remote.receive_report({"accounts": {"1": {"mcp_enabled": True}, second.id: {"mcp_enabled": False}, "77": {"mcp_enabled": False}}})
    assert calls == [("stop", second.id)]
    assert second.switched_off and not services.primary.switched_off
    assert answer["accounts"][second.id] == {"name": second.display_name(), "login": "off", "mcp_enabled": False}
    assert set(answer["accounts"]) == {"1", second.id}


# --- rights: shared or per account ----------------------------------------------------

def test_shared_or_own_rights():
    services = L.Services()
    second = services.add_account()
    second.save_own_settings("read_only", ["health"])
    second.reload_settings()
    shared_count = len(second.active_tools)
    assert second.options()["write_access"] == "create_only"  # shared: own settings ignored
    services.set_same_settings(False)
    assert second.options()["write_access"] == "read_only"
    assert all(L.kind_of(n) == "read" for n in second.active_tools)
    assert len(second.active_tools) < shared_count
    assert services.primary.options()["write_access"] == "create_only"  # the other account keeps its own
    assert second.selection_file() == second.own_selection_file != L.SELECTION_FILE
    services.set_same_settings(True)
    assert second.options()["write_access"] == "create_only"


def test_own_settings_reject_junk():
    services = L.Services()
    account = services.primary
    account.save_own_settings("root", ["health", "../etc", "all"])
    assert account.own_settings() == {"write_access": "create_only", "tool_areas": ["health", "all"]}


# --- page -----------------------------------------------------------------------------

def test_page_shows_every_account_with_its_own_url(page):
    services, client = page
    second = services.add_account()
    services.rename_account(second, "Belinda")
    html = client.get("/", headers={"Accept-Language": "de"}).text
    assert "Konto 1" in html and "Belinda" in html and "✏️" in html
    assert services.primary.webhook_id in html and second.webhook_id in html
    assert html.count('name="account" value="1"') >= 3 and f'name="account" value="{second.id}"' in html
    assert "Garmin-Konto hinzufügen" in html and "Gleiche Einstellungen für alle Konten" in html
    assert "Administrator" in html  # admins see every account
    assert "Mehr als 3 Konten" not in html


def test_load_warning_from_the_fourth_account(page):
    services, client = page
    services.add_account()
    services.add_account()
    html = client.get("/", headers={"Accept-Language": "en"}).text
    assert html.count("More than 3 accounts") == 1  # only next to "add" (the 4th)
    services.add_account()
    html = client.get("/", headers={"Accept-Language": "en"}).text
    assert html.count("More than 3 accounts") == 2  # banner + next to "add"
    for _ in range(6):
        services.add_account()
    html = client.get("/", headers={"Accept-Language": "en"}).text
    assert "maximum of 10 accounts" in html and 'action="accounts/add"' not in html


def test_add_rename_settings_remove_through_the_page(page):
    services, client = page
    assert client.post("/accounts/add", data={"csrf": "wrong"}, follow_redirects=False).status_code == 303
    assert len(services.accounts) == 1  # no CSRF token, nothing happens
    client.post("/accounts/add", data=_form(), follow_redirects=False)
    second = list(services.accounts.values())[1]
    client.post("/accounts/rename", data=_form(account=second.id, name="Belinda"), follow_redirects=False)
    assert second.display_name() == "Belinda"
    client.post("/settings/shared", data=_form(), follow_redirects=False)  # box unticked
    assert not services.same_settings
    html = client.get("/", headers={"Accept-Language": "en"}).text
    assert "Rights of this account" in html and f"tools?account={second.id}" in html
    client.post("/accounts/settings", data=_form(account=second.id, write_access="full", area=["health", "training"]), follow_redirects=False)
    assert second.own_settings() == {"write_access": "full", "tool_areas": ["health", "training"]}
    client.post("/tools", data=_form(account=second.id, tool=["get_activities"]), follow_redirects=False)
    assert second.active_tools == {"get_activities"} and services.primary.active_tools != {"get_activities"}
    client.post("/accounts/remove", data=_form(account=second.id), follow_redirects=False)
    assert list(services.accounts) == ["1"]
    resp = client.post("/accounts/rename", data=_form(account=second.id, name="x"), follow_redirects=False)
    assert resp.status_code == 303  # gone: no error page, just a message


def test_mfa_waits_per_account(page):
    services, client = page
    second = services.add_account()
    second.pending_mfa.update({"garmin": object(), "state": None, "started": 9e12})
    html = client.get("/", headers={"Accept-Language": "en"}).text
    # code form only in the card of the account that waits for it
    card = html.split('name="account" value="' + second.id + '"')[0]
    assert html.count('name="code"') == 1 and 'name="code"' not in card.split('<div class="card">')[-1]


def test_account_ids_in_forms_are_checked(page):
    services, client = page
    for bad in ("../1", "1 OR 1", "", "99"):
        resp = client.post("/logout", data=_form(account=bad), follow_redirects=False)
        assert resp.status_code == 303
    assert list(services.accounts) == ["1"]


def test_status_json_lists_every_account(page):
    services, client = page
    second = services.add_account()
    data = client.get("/status.json").json()
    assert [a["id"] for a in data["accounts"]] == ["1", second.id]
    assert re.fullmatch(r"1:\w+:[01]\|\d+:\w+:[01]\|\w+", data["state"])


def test_names_only_from_the_second_account_on(page):
    services, client = page
    L.write_private(services.primary.info_file, json.dumps({"name": "Moritz Weidelener", "profile": "p1"}))
    remote = L.REMOTE
    html = client.get("/", headers={"Accept-Language": "de"}).text
    assert "✏️" not in html and "<h2>Garmin-Konto</h2>" in html
    assert remote.discovery_config()["accounts"][0]["name"] == ""  # Home Assistant: no name
    assert "Konto entfernen?" in html or "Dieses Konto entfernen?" in html
    second = services.add_account()
    html = client.get("/", headers={"Accept-Language": "de"}).text
    assert html.count("✏️") == 2 and "Moritz Weidelener" in html
    assert [a["name"] for a in remote.discovery_config()["accounts"]] == ["Moritz Weidelener", second.id]
    services.rename_account(services.primary, "Mo")
    services.remove_account(second)
    html = client.get("/", headers={"Accept-Language": "de"}).text
    assert "✏️" not in html and remote.discovery_config()["accounts"][0]["name"] == ""
    assert services.primary.custom_name == "Mo"  # kept for when a second account comes back


def test_remove_question_names_the_account_safely(page):
    services, client = page
    second = services.add_account()
    services.rename_account(second, "Te'st</form><script>")
    html = client.get("/", headers={"Accept-Language": "de"}).text
    assert "Konto „Te&#x27;st&lt;/form&gt;&lt;script&gt;“ entfernen?" in html
    assert "<script>" not in html.split("</style>")[-1].split("<script")[0]  # never as markup
    assert 'onsubmit="return confirm(this.dataset.confirm)"' in html


def test_same_garmin_account_twice_is_pointed_out(page):
    services, client = page
    second, third = services.add_account(), services.add_account()
    for account, profile in ((services.primary, "p1"), (second, "p1"), (third, "p2")):
        account.token_dir.mkdir(parents=True, exist_ok=True)
        (account.token_dir / "garmin_tokens.json").write_text("{}")
        L.write_private(account.info_file, json.dumps({"name": "Moritz Weidelener", "profile": profile}))
    services.rename_account(second, "Test")
    assert services.same_garmin_account(services.primary) == [second]
    assert services.same_garmin_account(third) == []  # same name, other Garmin profile
    html = client.get("/", headers={"Accept-Language": "de"}).text
    assert html.count("Dieses Garmin-Konto ist auch als") == 2 and "„Test“" in html
    # logged in before 0.6.1 (no profile id): the name decides
    L.write_private(third.info_file, json.dumps({"name": "Moritz Weidelener"}))
    assert third in services.same_garmin_account(services.primary)


def test_upload_hint_only_once(page):
    services, client = page
    for account in (services.primary, services.add_account()):
        account.token_dir.mkdir(parents=True, exist_ok=True)
        (account.token_dir / "garmin_tokens.json").write_text("{}")
    html = client.get("/", headers={"Accept-Language": "en"}).text
    assert html.count("Upload device data") == 1
