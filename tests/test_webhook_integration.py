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


def test_manifest_and_translations_are_consistent():
    manifest = json.loads((integration._MANIFEST).read_text())
    assert manifest["domain"] == "garmin_mcp_webhook"
    assert "webhook" in manifest["dependencies"]
    base = integration._MANIFEST.parent
    for name in ("strings.json", "translations/en.json", "translations/de.json"):
        data = json.loads((base / name).read_text())
        assert "restart_required" in data["issues"]


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

    config = tmp_path / "webhook.json"
    config.write_text(json.dumps({"webhook_id": "wh123", "target_url": "http://127.0.0.1:18100/secret/mcp"}))
    monkeypatch.setattr(integration, "CONFIG_FILE", config)

    hass, entry = HomeAssistant(), ConfigEntry()
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
        config = tmp_path / "webhook.json"
        config.write_text(json.dumps({"webhook_id": "wh502", "target_url": "http://127.0.0.1:1/x"}))
        monkeypatch.setattr(integration, "CONFIG_FILE", config)
        hass, entry = HomeAssistant(), ConfigEntry("e2")
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
    monkeypatch.setattr(cleanup, "CONFIG_FILE", config)
    hass, entry = HomeAssistant(), ConfigEntry("cleanup")
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
    monkeypatch.setattr(cleanup, "CONFIG_FILE", tmp_path / "x.json")
    cleanup._delete_files()
    assert other.exists()
