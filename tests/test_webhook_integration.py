"""Tests for the helper integration that forwards the HA webhook to the app."""

import asyncio
import json

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

    async def fake_addon(request):
        seen["headers"] = dict(request.headers)
        seen["body"] = await request.json()
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await resp.prepare(request)
        await resp.write(b'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{}}\n\n')
        await resp.write_eof()
        return resp

    addon = web.Application()
    addon.router.add_post("/secret/mcp", fake_addon)
    addon_runner = web.AppRunner(addon)
    await addon_runner.setup()
    await web.TCPSite(addon_runner, "127.0.0.1", 18100).start()

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
        await addon_runner.cleanup()


def test_addon_down_gives_502(tmp_path, monkeypatch):
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
