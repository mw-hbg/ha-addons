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
        assert result["type"] == "create_entry" and result["data"] == GOOD
        assert hass.config_entries.removed == ["old"]
        assert [e.unique_id for e in hass.config_entries.entries] == ["u1"]
        # same announcement with a new secret: entry updated and reloaded, no second entry
        new = {**GOOD, "target_url": GOOD["target_url"].replace(SECRET, "t" * 43)}
        result = await run_flow_step(_flow(hass), "async_step_hassio", _discovery(new))
        assert result == {"type": "abort", "reason": "already_configured"}
        assert hass.config_entries.entries[0].data == new and hass.config_entries.reloaded
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
            assert ("garmin_mcp_webhook", "garmin_login") in issue_registry.ISSUES
            await timers[1]()  # next report: login fine again
            assert ("garmin_mcp_webhook", "garmin_login") not in issue_registry.ISSUES
        finally:
            await integration.async_unload_entry(hass, entry)
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
