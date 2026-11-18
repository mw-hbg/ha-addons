"""Tests for the helper integration that forwards the HA webhook to the app."""

import asyncio
import json

import pytest

from aiohttp import ClientSession, web

import garmin_mcp_webhook as integration
from homeassistant.components.webhook import REGISTERED
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry

_REAL_SLEEP = asyncio.sleep


def test_manifest_and_translations_are_consistent():
    manifest = json.loads((integration._MANIFEST).read_text())
    assert manifest["domain"] == "garmin_mcp_webhook"
    assert "webhook" in manifest["dependencies"]
    base = integration._MANIFEST.parent
    for name in ("strings.json", "translations/en.json", "translations/de.json"):
        data = json.loads((base / name).read_text())
        assert "restart_required" in data["issues"] and "garmin_login" in data["issues"]
        assert {"invalid_discovery", "set_up_by_app"} <= set(data["config"]["abort"])
    # several entries must be possible for a moment while one replaces the other
    assert "single_config_entry" not in manifest


def test_forwards_requests_and_streams_answers(tmp_path, monkeypatch):
    asyncio.run(_forward_round_trip(tmp_path, monkeypatch))


async def _forward_round_trip(tmp_path, monkeypatch):
    seen = {}

    async def fake_app(request):
        seen["headers"] = dict(request.headers)
        seen["body"] = await request.json()
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await resp.prepare(request)
        await resp.write(b'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\n\n')
        await resp.write_eof()
        return resp

    app_server = web.Application()
    app_server.router.add_post("/secret/mcp", fake_app)
    app_runner = web.AppRunner(app_server)
    await app_runner.setup()
    await web.TCPSite(app_runner, "127.0.0.1", 18100).start()

    hass = HomeAssistant()
    entry = ConfigEntry(data={"webhook_id": "wh123", "target_url": "http://127.0.0.1:18100/secret/mcp"})
    assert await integration.async_setup_entry(hass, entry)
    assert "wh123" in REGISTERED
    assert ("garmin_mcp_webhook", "restart_required") not in issue_registry.ISSUES

    async def ha_route(request):
        return await REGISTERED[request.match_info["wid"]](hass, request.match_info["wid"], request)

    ha = web.Application()
    ha.router.add_route("*", "/api/webhook/{wid}", ha_route)
    ha_runner = web.AppRunner(ha)
    await ha_runner.setup()
    await web.TCPSite(ha_runner, "127.0.0.1", 18123).start()

    try:
        async with ClientSession() as session:
            async with session.post(
                "http://127.0.0.1:18123/api/webhook/wh123",
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
                headers={
                    "Authorization": "Bearer from-ha-mcp-oauth",
                    "Origin": "https://claude.ai",
                    "Cookie": "session=x",
                },
            ) as resp:
                text = await resp.text()
                assert resp.status == 200
                assert resp.headers["Content-Type"].startswith("text/event-stream")
                assert '"result"' in text
        assert seen["body"]["method"] == "initialize"
        lower = {k.lower() for k in seen["headers"]}
        assert "authorization" not in lower
        assert "origin" not in lower
        assert "cookie" not in lower
    finally:
        assert await integration.async_unload_entry(hass, entry)
        assert "wh123" not in REGISTERED
        await ha_runner.cleanup()
        await app_runner.cleanup()


def test_app_down_gives_502(tmp_path, monkeypatch):
    async def run():
        hass = HomeAssistant()
        entry = ConfigEntry("e2", {"webhook_id": "wh502", "target_url": "http://127.0.0.1:1/x"})
        await integration.async_setup_entry(hass, entry)

        async def ha_route(request):
            return await REGISTERED["wh502"](hass, "wh502", request)

        ha = web.Application()
        ha.router.add_post("/hook", ha_route)
        runner = web.AppRunner(ha)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", 18124).start()
        try:
            async with ClientSession() as session:
                async with session.post("http://127.0.0.1:18124/hook", json={}) as resp:
                    assert resp.status == 502
        finally:
            await integration.async_unload_entry(hass, entry)
            await runner.cleanup()

    asyncio.run(run())


# --- set up by the app through discovery ------------------------------------------------

SECRET = "s" * 43
GOOD = {
    "webhook_id": "garmin_mcp_" + "w" * 43,
    "target_url": f"http://172.30.33.5:8100/{SECRET}/mcp",
    "report_url": f"http://172.30.33.5:8100/{SECRET}/ha",
    "app_slug": "abcd1234_garmin_mcp",
}


MULTI = {
    "accounts": [
        {"id": "1", "name": "Moritz", "webhook_id": GOOD["webhook_id"], "target_url": GOOD["target_url"]},
        {"id": "2", "name": "Belinda", "webhook_id": "garmin_mcp_" + "v" * 43, "target_url": f"http://172.30.33.5:8100/{'b' * 43}/mcp"},
    ],
    "report_url": GOOD["report_url"],
    "app_slug": GOOD["app_slug"],
}


@pytest.mark.parametrize(
    "accounts",
    [
        [{**MULTI["accounts"][0], "id": "x"}],                      # odd id
        [MULTI["accounts"][0], MULTI["accounts"][0]],                # same account twice
        [{**MULTI["accounts"][1], "target_url": "http://evil/x"}],   # not an internal address
        [{**MULTI["accounts"][1], "webhook_id": "short"}],
        ["not a dict"],
        [MULTI["accounts"][0]] * 11,                                 # more than 10
    ],
)
def test_invalid_account_lists_are_refused(accounts):
    from garmin_mcp_webhook.config_flow import entry_data

    assert entry_data(MULTI, "abcd1234_garmin_mcp") is not None
    assert entry_data({**MULTI, "accounts": accounts}, "abcd1234_garmin_mcp") is None


def test_account_names_are_cleaned():
    from garmin_mcp_webhook.config_flow import entry_data

    raw = {**MULTI, "accounts": [{**MULTI["accounts"][0], "name": "  Bel\ninda\x00 " + "x" * 100}]}
    name = entry_data(raw, "abcd1234_garmin_mcp")["accounts"][0]["name"]
    assert name.startswith("Belinda x") and "\x00" not in name and len(name) <= 60


def _flow(hass):
    from garmin_mcp_webhook.config_flow import GarminMcpWebhookConfigFlow

    flow = GarminMcpWebhookConfigFlow()
    flow.hass = hass
    return flow


def _discovery(config, uuid="u1"):
    from homeassistant.helpers.service_info.hassio import HassioServiceInfo

    return HassioServiceInfo(config=config, name="Garmin Connect MCP", slug="abcd1234_garmin_mcp", uuid=uuid)


@pytest.mark.parametrize(
    "change",
    [
        {"target_url": "http://evil.example.com/x"},
        {"target_url": "https://172.30.33.5:8100/" + SECRET + "/mcp"},
        {"report_url": "http://172.30.33.5:8100/short/ha"},
        {"webhook_id": "other"},
        {"app_slug": "../x"},
    ],
)
def test_invalid_announcements_are_refused(change):
    from garmin_mcp_webhook.config_flow import entry_data

    assert entry_data(GOOD, "abcd1234_garmin_mcp") is not None
    assert entry_data({**GOOD, **change}, "abcd1234_garmin_mcp") is None


def test_discovery_creates_updates_and_replaces_the_entry():
    from homeassistant.config_entries import run_flow_step

    async def run():
        hass = HomeAssistant()
        # an entry of an older app version (set up by hand / API)
        hass.config_entries.entries.append(ConfigEntry("old", {}, source="user", unique_id="garmin_mcp_webhook"))
        result = await run_flow_step(_flow(hass), "async_step_hassio", _discovery(GOOD))
        # an announcement of an app with a single account becomes account 1
        assert result["type"] == "create_entry"
        assert result["data"] == {
            "accounts": [{"id": "1", "name": "", "webhook_id": GOOD["webhook_id"], "target_url": GOOD["target_url"]}],
            "report_url": GOOD["report_url"],
            "app_slug": GOOD["app_slug"],
        }
        assert hass.config_entries.removed == ["old"]
        assert [e.unique_id for e in hass.config_entries.entries] == ["u1"]
        # same announcement with a second account: entry updated and reloaded, no second entry
        result = await run_flow_step(_flow(hass), "async_step_hassio", _discovery(MULTI))
        assert result == {"type": "abort", "reason": "already_configured"}
        data = hass.config_entries.entries[0].data
        assert [a["name"] for a in data["accounts"]] == ["Moritz", "Belinda"] and hass.config_entries.reloaded
        # junk is refused
        result = await run_flow_step(_flow(hass), "async_step_hassio", _discovery({"target_url": "x"}, "u2"))
        assert result["reason"] == "invalid_discovery"
        # never by hand
        result = await run_flow_step(_flow(hass), "async_step_user")
        assert result["reason"] == "set_up_by_app"

    asyncio.run(run())


def test_reports_to_the_app_and_shows_login_problems(monkeypatch):
    from homeassistant.helpers import network

    monkeypatch.setattr(network, "EXTERNAL", "https://home.example.com")

    async def run():
        answers = [{"login": "failed", "notify": True}, {"login": "ok", "notify": True}]
        seen = []

        async def fake_report(request):
            seen.append(await request.json())
            return web.json_response(answers.pop(0))

        app_server = web.Application()
        app_server.router.add_post("/key/ha", fake_report)
        runner = web.AppRunner(app_server)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", 18125).start()
        timers = []
        monkeypatch.setattr(integration, "async_track_time_interval", lambda h, action, i: timers.append(action) or (lambda: None))
        hass = HomeAssistant()
        hass.config.language = "de"
        entry = ConfigEntry("r", {"webhook_id": "whr", "target_url": "http://127.0.0.1:1/x", "report_url": "http://127.0.0.1:18125/key/ha"})
        try:
            await integration.async_setup_entry(hass, entry)
            await asyncio.gather(*hass.tasks)
            assert seen[0]["external_url"] == "https://home.example.com" and seen[0]["language"] == "de"
            # an app with a single account answers without "accounts" -> account 1
            assert ("garmin_mcp_webhook", "garmin_login_1") in issue_registry.ISSUES
            await timers[1]()  # next report: login fine again
            assert ("garmin_mcp_webhook", "garmin_login_1") not in issue_registry.ISSUES
        finally:
            await integration.async_unload_entry(hass, entry)
            await runner.cleanup()

    asyncio.run(run())


def test_several_accounts_get_webhooks_switches_and_notices(monkeypatch):
    from homeassistant.helpers import device_registry

    async def run():
        seen = []

        async def fake_report(request):
            seen.append(await request.json())
            return web.json_response({
                "accounts": {
                    "1": {"name": "Moritz", "login": "ok"},
                    "2": {"name": "Belinda", "login": "failed"},
                },
                "notify": True,
            })

        app_server = web.Application()
        app_server.router.add_post("/key/ha", fake_report)
        runner = web.AppRunner(app_server)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", 18129).start()
        monkeypatch.setattr(integration, "async_track_time_interval", lambda h, action, i: lambda: None)
        hass = HomeAssistant()
        data = {
            "accounts": [
                {"id": "1", "name": "Moritz", "webhook_id": "wh_m", "target_url": "http://127.0.0.1:1/a/mcp"},
                {"id": "2", "name": "Belinda", "webhook_id": "wh_b", "target_url": "http://127.0.0.1:1/b/mcp"},
            ],
            "report_url": "http://127.0.0.1:18129/key/ha",
            "app_slug": "abcd1234_garmin_mcp",
        }
        entry = ConfigEntry("multi", data)
        # a device of an account that was removed in the app meanwhile
        stale = device_registry.REGISTRY.add("multi", {("garmin_mcp_webhook", "multi_7")})
        kept = device_registry.REGISTRY.add("multi", {("garmin_mcp_webhook", "multi")})
        try:
            await integration.async_setup_entry(hass, entry)
            await asyncio.gather(*hass.tasks)
            assert {"wh_m", "wh_b"} <= set(REGISTERED)
            switches = hass.config_entries.entities
            assert [s._attr_unique_id for s in switches] == ["multi_mcp_server", "multi_2_mcp_server"]
            assert [s._attr_device_info["name"] for s in switches] == ["Garmin Connect MCP Moritz", "Garmin Connect MCP Belinda"]
            assert seen[-1]["accounts"] == {"1": {"mcp_enabled": True}, "2": {"mcp_enabled": True}}
            assert ("garmin_mcp_webhook", "garmin_login_2") in issue_registry.ISSUES
            assert issue_registry.ISSUES[("garmin_mcp_webhook", "garmin_login_2")]["translation_placeholders"] == {"name": "Belinda"}
            assert ("garmin_mcp_webhook", "garmin_login_1") not in issue_registry.ISSUES
            assert stale.id in device_registry.REGISTRY.removed and kept.id not in device_registry.REGISTRY.removed
            # switching off account 2 only affects account 2
            await switches[1].async_turn_off()
            assert seen[-1]["accounts"] == {"1": {"mcp_enabled": True}, "2": {"mcp_enabled": False}}
        finally:
            await integration.async_unload_entry(hass, entry)
            assert not {"wh_m", "wh_b"} & set(REGISTERED)
            issue_registry.ISSUES.clear()
            await runner.cleanup()

    asyncio.run(run())


# --- removes itself when the app was uninstalled ----------------------------------------

def _cleanup_setup(tmp_path, monkeypatch, installed):
    from homeassistant.components import hassio, persistent_notification

    from garmin_mcp_webhook import cleanup

    hassio.INSTALLED = installed
    persistent_notification.CREATED.clear()
    folder = tmp_path / "custom_components" / "garmin_mcp_webhook"
    (folder / "translations").mkdir(parents=True)
    for lang in ("en", "de"):
        src = integration._MANIFEST.parent / "translations" / f"{lang}.json"
        (folder / "translations" / f"{lang}.json").write_text(src.read_text())
    config = tmp_path / ".garmin_mcp_webhook.json"
    config.write_text("{}")
    monkeypatch.setattr(cleanup, "_INTEGRATION_DIR", folder)
    monkeypatch.setattr(cleanup, "LEGACY_CONFIG_FILE", config)
    monkeypatch.setattr(integration.asyncio, "sleep", lambda s: _REAL_SLEEP(0))
    hass = HomeAssistant()
    entry = ConfigEntry("cleanup", {"app_slug": "abcd1234_garmin_mcp"})
    hass.config_entries.entries.append(entry)
    hass.config_entries.remove_hook = integration.async_remove_entry
    hass.config.language = "de"
    return cleanup, hass, entry, folder, config, persistent_notification


def test_removes_itself_after_the_app_is_gone(tmp_path, monkeypatch):
    async def run():
        cleanup, hass, entry, folder, config, notes = _cleanup_setup(tmp_path, monkeypatch, ["core_ssh"])
        checks = []
        monkeypatch.setattr(cleanup, "async_track_time_interval", lambda h, action, i: checks.append(action) or (lambda: None))
        cleanup.async_watch_app(hass, entry, "abcd1234_garmin_mcp")
        await asyncio.gather(*hass.tasks)
        # one missing answer is not enough
        assert folder.exists() and not hass.config_entries.removed
        await checks[0]()
        assert hass.config_entries.removed == ["cleanup"]
        await asyncio.gather(*hass.tasks)
        assert not folder.exists() and not config.exists()
        assert "deinstalliert" in notes.CREATED[0]["message"]

    asyncio.run(run())


@pytest.mark.parametrize("installed", [["abcd1234_garmin_mcp"], RuntimeError("supervisor down"), None])
def test_keeps_itself_while_installed_or_unsure(tmp_path, monkeypatch, installed):
    async def run():
        cleanup, hass, entry, folder, config, notes = _cleanup_setup(tmp_path, monkeypatch, installed)
        checks = []
        monkeypatch.setattr(cleanup, "async_track_time_interval", lambda h, action, i: checks.append(action) or (lambda: None))
        cleanup.async_watch_app(hass, entry, "abcd1234_garmin_mcp")
        await asyncio.gather(*hass.tasks)
        for _ in range(3):
            await checks[0]()
        assert folder.exists() and config.exists() and not hass.config_entries.removed

    asyncio.run(run())


def test_no_check_without_app_slug(tmp_path, monkeypatch):
    cleanup, hass, entry, folder, config, notes = _cleanup_setup(tmp_path, monkeypatch, [])
    cleanup.async_watch_app(hass, entry, None)
    assert not hass.tasks and not entry.unloads


def test_only_its_own_folder_is_ever_deleted(tmp_path, monkeypatch):
    from garmin_mcp_webhook import cleanup

    other = tmp_path / "custom_components" / "something_else"
    other.mkdir(parents=True)
    monkeypatch.setattr(cleanup, "_INTEGRATION_DIR", other)
    monkeypatch.setattr(cleanup, "LEGACY_CONFIG_FILE", tmp_path / "x.json")
    cleanup._delete_files()
    assert other.exists()


def test_entry_removed_by_home_assistant_after_uninstall(tmp_path, monkeypatch):
    """Uninstall: the Supervisor withdraws the discovery, HA removes the entry;
    the integration then deletes its files once the app is really gone."""
    async def run():
        cleanup, hass, entry, folder, config, notes = _cleanup_setup(tmp_path, monkeypatch, ["abcd1234_garmin_mcp"])
        from homeassistant.components import hassio

        async def uninstall_finishes_later(seconds):
            hassio.INSTALLED = []  # the Supervisor is done uninstalling

        monkeypatch.setattr(integration.asyncio, "sleep", uninstall_finishes_later)
        await hass.config_entries.async_remove("cleanup")
        await asyncio.gather(*hass.tasks)
        assert not folder.exists()
        assert notes.CREATED

    asyncio.run(run())


def test_entry_removed_while_app_installed_keeps_files(tmp_path, monkeypatch):
    """Direct mode or removed by hand: the app is still there – keep the files."""
    async def run():
        cleanup, hass, entry, folder, config, notes = _cleanup_setup(tmp_path, monkeypatch, ["abcd1234_garmin_mcp"])
        await hass.config_entries.async_remove("cleanup")
        await asyncio.gather(*hass.tasks)
        assert folder.exists() and not notes.CREATED

    asyncio.run(run())


# --- switch "Garmin Connect MCP Server" -------------------------------------------------

def test_switch_has_names_and_icons_in_every_language():
    base = integration._MANIFEST.parent
    for name in ("strings.json", "translations/en.json", "translations/de.json"):
        data = json.loads((base / name).read_text())
        assert data["entity"]["switch"]["mcp_server"]["name"]
    icons = json.loads((base / "icons.json").read_text())
    assert icons["entity"]["switch"]["mcp_server"]["default"].startswith("mdi:")


def test_switched_off_answers_without_the_app():
    answer = integration.switched_off_answer({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert "switched off" in answer["result"]["instructions"]
    call = integration.switched_off_answer({"jsonrpc": "2.0", "id": 2, "method": "tools/call"})
    assert call["result"]["isError"] and "turn on" in call["result"]["content"][0]["text"]
    assert integration.switched_off_answer({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert "error" in integration.switched_off_answer({"jsonrpc": "2.0", "id": 3, "method": "other"})


def test_switch_blocks_the_webhook_and_tells_the_app(monkeypatch):
    from homeassistant.helpers import restore_state

    restore_state.LAST_STATE["value"] = None

    async def run():
        reports, forwarded = [], []

        async def fake_report(request):
            reports.append(await request.json())
            return web.json_response({"login": "ok"})

        async def fake_mcp(request):
            forwarded.append(await request.json())
            return web.json_response({"jsonrpc": "2.0", "id": 1, "result": {"from": "app"}})

        app_server = web.Application()
        app_server.router.add_post("/key/ha", fake_report)
        app_server.router.add_post("/key/mcp", fake_mcp)
        runner = web.AppRunner(app_server)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", 18126).start()
        monkeypatch.setattr(integration, "async_track_time_interval", lambda h, action, i: lambda: None)
        hass = HomeAssistant()
        entry = ConfigEntry("sw", {"webhook_id": "whs", "target_url": "http://127.0.0.1:18126/key/mcp", "report_url": "http://127.0.0.1:18126/key/ha"})

        ha = web.Application()
        async def ha_route(request):
            return await REGISTERED[request.match_info["wid"]](hass, "whs", request)

        ha.router.add_route("*", "/api/webhook/{wid}", ha_route)
        ha_runner = web.AppRunner(ha)
        await ha_runner.setup()
        await web.TCPSite(ha_runner, "127.0.0.1", 18127).start()

        async def call():
            async with ClientSession() as s:
                async with s.post("http://127.0.0.1:18127/api/webhook/whs", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call"}) as r:
                    return await r.json()

        try:
            await integration.async_setup_entry(hass, entry)
            await asyncio.gather(*hass.tasks)
            switch = hass.config_entries.entities[0]
            assert switch.is_on and switch._attr_unique_id == "sw_mcp_server"
            assert reports[-1]["accounts"]["1"]["mcp_enabled"] is True
            assert (await call())["result"] == {"from": "app"}

            await switch.async_turn_off()
            assert not switch.is_on and switch.written_states[-1] == "off"
            assert reports[-1]["accounts"]["1"]["mcp_enabled"] is False  # app told right away
            answer = await call()
            assert answer["result"]["isError"] and len(forwarded) == 1  # nothing reached the app

            await switch.async_turn_on()
            assert reports[-1]["accounts"]["1"]["mcp_enabled"] is True
            assert (await call())["result"] == {"from": "app"} and len(forwarded) == 2
        finally:
            await integration.async_unload_entry(hass, entry)
            await runner.cleanup()
            await ha_runner.cleanup()

    asyncio.run(run())


@pytest.mark.parametrize("last, expected", [(None, True), ("on", True), ("off", False), ("unavailable", True)])
def test_switch_restores_its_state(monkeypatch, last, expected):
    from homeassistant.helpers import restore_state

    restore_state.LAST_STATE["value"] = last
    monkeypatch.setattr(integration, "async_track_time_interval", lambda h, action, i: lambda: None)

    async def run():
        hass = HomeAssistant()
        entry = ConfigEntry("rs", {"webhook_id": "whx", "target_url": "http://127.0.0.1:1/x"})
        try:
            await integration.async_setup_entry(hass, entry)
            assert hass.config_entries.entities[0].is_on is expected
            assert hass.data["garmin_mcp_webhook"]["rs"]["accounts"]["1"]["enabled"] is expected
        finally:
            await integration.async_unload_entry(hass, entry)
            restore_state.LAST_STATE["value"] = None

    asyncio.run(run())


# --- restart notice: the RUNNING code's version counts, not the files on disk ----------

def test_code_version_matches_the_manifest():
    from garmin_mcp_webhook.const import VERSION

    assert json.loads(integration._MANIFEST.read_text())["version"] == VERSION


def test_old_code_in_memory_with_newer_files_asks_for_a_restart(monkeypatch):
    """Reinstall without restart: Home Assistant still runs the old module while
    the app already copied newer files – the notice must appear right away and
    the app must be told the old version."""
    monkeypatch.setattr(integration, "VERSION", "0.0.1")
    monkeypatch.setattr(integration, "async_track_time_interval", lambda h, action, i: lambda: None)

    async def run():
        reports = []

        async def fake_report(request):
            reports.append(await request.json())
            return web.json_response({"login": "ok"})

        app_server = web.Application()
        app_server.router.add_post("/key/ha", fake_report)
        runner = web.AppRunner(app_server)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", 18128).start()
        hass = HomeAssistant()
        entry = ConfigEntry("old", {"webhook_id": "who", "target_url": "http://127.0.0.1:1/x", "report_url": "http://127.0.0.1:18128/key/ha"})
        try:
            await integration.async_setup_entry(hass, entry)
            await asyncio.gather(*hass.tasks)
            assert ("garmin_mcp_webhook", "restart_required") in issue_registry.ISSUES
            assert reports[-1]["integration_version"] == "0.0.1"
            assert reports[-1]["restart_needed"] is True
        finally:
            await integration.async_unload_entry(hass, entry)
            issue_registry.ISSUES.pop(("garmin_mcp_webhook", "restart_required"), None)
            await runner.cleanup()

    asyncio.run(run())
