"""Remote access for the Garmin Connect MCP add-on via a Home Assistant webhook.

The add-on writes /config/.garmin_mcp_webhook.json with a random webhook id
and the add-on's internal MCP address. This integration registers that
webhook, so MCP clients can reach the add-on through Home Assistant's existing
external address (Nabu Casa, Cloudflare Tunnel, reverse proxy, …):

    https://<your-home-assistant>/api/webhook/<webhook id>

Requests are forwarded unchanged to the add-on; responses (JSON or
Server-Sent Events) are streamed back. Nothing is stored and nothing is logged
except errors – the webhook id is never written to the log.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web
from homeassistant.components.webhook import (
    async_register as webhook_register,
    async_unregister as webhook_unregister,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_interval

from .const import CONFIG_FILE, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Request headers that must not be forwarded to the add-on.
_DROP_REQUEST_HEADERS = {
    "host",
    "content-length",
    "transfer-encoding",
    "connection",
    "cookie",
    "authorization",
    "origin",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "x-real-ip",
}
_ALLOWED_CONTENT_TYPES = ("application/json", "text/event-stream")


_MANIFEST = Path(__file__).parent / "manifest.json"
_RESTART_ISSUE = "restart_required"


def _manifest_version() -> str | None:
    try:
        return json.loads(_MANIFEST.read_text()).get("version")
    except (OSError, ValueError):
        return None


def _read_config() -> dict[str, Any] | None:
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (OSError, ValueError):
        return None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    config = await hass.async_add_executor_job(_read_config)
    if not config or not config.get("webhook_id") or not config.get("target_url"):
        raise ConfigEntryNotReady(
            "Garmin Connect MCP add-on has not written its configuration yet – "
            "start the add-on"
        )

    webhook_id: str = config["webhook_id"]
    target_url: str = config["target_url"]
    session = aiohttp.ClientSession(
        # sock_read bounds a dead stream, not a slow Garmin request.
        timeout=aiohttp.ClientTimeout(connect=30, sock_connect=10, sock_read=300),
        auto_decompress=False,
    )

    async def handle(hass: HomeAssistant, wid: str, request: web.Request):
        return await _forward(request, session, target_url)

    webhook_register(
        hass,
        DOMAIN,
        "Garmin Connect MCP",
        webhook_id,
        handle,
        allowed_methods=["POST", "GET"],
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "webhook_id": webhook_id,
        "session": session,
    }
    # The add-on replaces these files when it brings a newer version. Python
    # only loads the new code after a restart, so raise a fixable repair
    # issue (with a restart button) as soon as the files on disk change.
    loaded_version = await hass.async_add_executor_job(_manifest_version)
    ir.async_delete_issue(hass, DOMAIN, _RESTART_ISSUE)

    async def _check_update(_now=None) -> None:
        on_disk = await hass.async_add_executor_job(_manifest_version)
        if on_disk and on_disk != loaded_version:
            ir.async_create_issue(
                hass,
                DOMAIN,
                _RESTART_ISSUE,
                is_fixable=True,
                is_persistent=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=_RESTART_ISSUE,
                translation_placeholders={"version": on_disk},
            )

    entry.async_on_unload(
        async_track_time_interval(hass, _check_update, timedelta(minutes=1))
    )

    _LOGGER.info("Garmin Connect MCP remote access enabled")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data:
        webhook_unregister(hass, data["webhook_id"])
        await data["session"].close()
    return True


async def _forward(
    request: web.Request, session: aiohttp.ClientSession, target_url: str
) -> web.StreamResponse:
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _DROP_REQUEST_HEADERS
    }
    body = await request.read()
    try:
        async with session.request(
            request.method, target_url, headers=headers, data=body or None
        ) as upstream:
            content_type = upstream.headers.get("Content-Type", "")
            resp_headers = {
                "Cache-Control": "no-cache, no-transform",
                "Content-Encoding": "identity",
            }
            if session_id := upstream.headers.get("Mcp-Session-Id"):
                resp_headers["Mcp-Session-Id"] = session_id

            if "text/event-stream" in content_type:
                resp_headers["Content-Type"] = "text/event-stream"
                resp_headers["X-Accel-Buffering"] = "no"
                response = web.StreamResponse(status=upstream.status, headers=resp_headers)
                await response.prepare(request)
                async for chunk in upstream.content.iter_any():
                    await response.write(chunk)
                await response.write_eof()
                return response

            if not any(ct in content_type for ct in _ALLOWED_CONTENT_TYPES):
                content_type = "application/json"
            resp_headers["Content-Type"] = content_type
            return web.Response(
                status=upstream.status, body=await upstream.read(), headers=resp_headers
            )
    except aiohttp.ClientError as err:
        _LOGGER.warning("Garmin Connect MCP add-on not reachable: %s", type(err).__name__)
        return web.json_response(
            {"error": "Garmin Connect MCP add-on is not reachable. Is it running?"},
            status=502,
        )
