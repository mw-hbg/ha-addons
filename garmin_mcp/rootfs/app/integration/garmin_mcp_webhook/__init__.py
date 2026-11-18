"""Remote access for the Garmin Connect MCP app via a Home Assistant webhook.

The app announces its settings (per Garmin account a random webhook id and
its internal MCP address) through the Supervisor's discovery service; Home
Assistant creates the config entry from it (see config_flow.py). This
integration registers one webhook per account, so MCP clients can reach the
app through Home Assistant's existing external address (Nabu Casa, Cloudflare
Tunnel, reverse proxy, …):

    https://<your-home-assistant>/api/webhook/<webhook id of the account>

Requests are forwarded unchanged to the app; responses (JSON or
Server-Sent Events) are streamed back. Nothing is stored and nothing is logged
except errors – the webhook id is never written to the log.

Every account is a device with a switch "Garmin Connect MCP <name> Server"
(switch.py): while it is off, the account's webhook answers MCP requests
itself and the app stops that account's Garmin server. The name is empty while
the app has a single account.

When the app announces new settings (account added, removed or renamed, secret
URL rotated), the entry is updated without a reload: webhooks, devices and
switches are added, changed or removed one by one, so the switches of the other
accounts are not touched.

The app itself has no access to the Home Assistant API. Everything the app
page needs to know (external address, language, loaded version) is reported
to the app by this integration, and the app answers with the Garmin login
state, which is shown here as a repair notice.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from pathlib import Path

import aiohttp
from aiohttp import web
from homeassistant.components.webhook import (
    async_register as webhook_register,
    async_unregister as webhook_unregister,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_interval

from .cleanup import async_app_gone, async_delete_files, async_watch_app
from .const import DOMAIN, ISSUE_LOGIN, ISSUE_RESTART, PLATFORMS, SIGNAL_NEW_ACCOUNTS, VERSION

_LOGGER = logging.getLogger(__name__)

# Request headers that must not be forwarded to the app.
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
REPORT_INTERVAL = timedelta(minutes=1)

_MANIFEST = Path(__file__).parent / "manifest.json"


def _manifest_version() -> str | None:
    try:
        return json.loads(_MANIFEST.read_text()).get("version")
    except (OSError, ValueError):
        return None


def _external_url(hass: HomeAssistant) -> str:
    """Public address of Home Assistant (external URL or Nabu Casa), if any."""
    try:
        from homeassistant.helpers.network import NoURLAvailableError, get_url
    except ImportError:  # pragma: no cover
        return ""
    try:
        return get_url(hass, allow_internal=False, allow_ip=True, prefer_external=True)
    except NoURLAvailableError:
        return ""
    except Exception:  # noqa: BLE001
        return ""


def entry_accounts(entry: ConfigEntry) -> list[dict]:
    """Accounts of the entry; entries made by app versions with a single
    account (before 0.6) have webhook_id/target_url at the top level."""
    accounts = entry.data.get("accounts")
    if isinstance(accounts, list):
        return [a for a in accounts if isinstance(a, dict) and a.get("webhook_id") and a.get("target_url")]
    if entry.data.get("webhook_id") and entry.data.get("target_url"):
        return [{"id": "1", "name": "", "webhook_id": entry.data["webhook_id"], "target_url": entry.data["target_url"]}]
    return []


def login_issue_id(account_id: str) -> str:
    return f"{ISSUE_LOGIN}_{account_id}"


def device_identifier(entry: ConfigEntry, account_id: str) -> tuple[str, str]:
    """Account 1 keeps the device of the versions with a single account."""
    return (DOMAIN, entry.entry_id if account_id == "1" else f"{entry.entry_id}_{account_id}")


def device_name(name: str) -> str:
    return f"Garmin Connect MCP {name or ''}".strip()


def _register_webhook(hass: HomeAssistant, runtime: dict, account: dict) -> None:
    acc = runtime["accounts"][account["id"]]

    async def handle(hass: HomeAssistant, wid: str, request: web.Request):
        if not acc["enabled"]:
            return await _switched_off(request)
        return await _forward(request, runtime["session"], acc["target_url"])

    webhook_register(
        hass,
        DOMAIN,
        device_name(account.get("name") or account["id"]),
        account["webhook_id"],
        handle,
        allowed_methods=["POST", "GET"],
    )


def _add_account(hass: HomeAssistant, runtime: dict, account: dict) -> None:
    runtime["accounts"][account["id"]] = {
        "id": account["id"],
        "name": account.get("name", ""),
        "webhook_id": account["webhook_id"],
        "target_url": account["target_url"],
        "enabled": True,
    }
    _register_webhook(hass, runtime, account)


async def _async_entry_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """New settings from the app – apply them without reloading the entry."""
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if runtime is None:
        return
    runtime["report_url"] = entry.data.get("report_url")
    wanted = {a["id"]: a for a in entry_accounts(entry)}
    current = runtime["accounts"]
    registry = dr.async_get(hass)

    for acc_id in [i for i in current if i not in wanted]:  # removed in the app
        webhook_unregister(hass, current.pop(acc_id)["webhook_id"])
        ir.async_delete_issue(hass, DOMAIN, login_issue_id(acc_id))

    added = []
    for acc_id, account in wanted.items():
        acc = current.get(acc_id)
        if acc is None:
            _add_account(hass, runtime, account)
            added.append(acc_id)
            continue
        name = account.get("name", "")
        if account["webhook_id"] != acc["webhook_id"] or name != acc["name"]:
            webhook_unregister(hass, acc["webhook_id"])
            acc["webhook_id"] = account["webhook_id"]
            acc["name"] = name
            _register_webhook(hass, runtime, account)
            device = registry.async_get_device(identifiers={device_identifier(entry, acc_id)})
            if device is not None and device.name != device_name(name):
                registry.async_update_device(device.id, name=device_name(name))
        acc["target_url"] = account["target_url"]

    if added:
        async_dispatcher_send(hass, f"{SIGNAL_NEW_ACCOUNTS}_{entry.entry_id}", added)
    _remove_stale_devices(hass, entry, set(current))
    hass.async_create_task(runtime["report"]())


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    accounts = entry_accounts(entry)
    report_url = entry.data.get("report_url")
    if not accounts and not report_url:
        raise ConfigEntryNotReady("Waiting for the Garmin Connect MCP app to announce its settings")

    session = aiohttp.ClientSession(
        # sock_read bounds a dead stream, not a slow Garmin request.
        timeout=aiohttp.ClientTimeout(connect=30, sock_connect=10, sock_read=300),
        auto_decompress=False,
    )
    runtime: dict = {"session": session, "accounts": {}, "report_url": report_url}

    for account in accounts:
        _add_account(hass, runtime, account)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    # notice of the versions with a single account
    ir.async_delete_issue(hass, DOMAIN, ISSUE_LOGIN)

    # The app replaces these files when it brings a newer version. Python
    # only loads the new code after a restart, so raise a fixable repair
    # issue (with a restart button) as soon as the files on disk change.
    # The version of the code that is RUNNING comes from const.py – the
    # manifest on disk may already be newer (e.g. after a reinstall while
    # Home Assistant still has the old module in memory).
    loaded_version = VERSION
    ir.async_delete_issue(hass, DOMAIN, ISSUE_RESTART)
    state = {"restart_needed": False}

    async def _check_update(_now=None) -> None:
        on_disk = await hass.async_add_executor_job(_manifest_version)
        if on_disk and on_disk != loaded_version:
            state["restart_needed"] = True
            ir.async_create_issue(
                hass,
                DOMAIN,
                ISSUE_RESTART,
                is_fixable=True,
                is_persistent=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_RESTART,
                translation_placeholders={"version": on_disk},
            )

    async def _report(_now=None) -> None:
        """Tell the app how Home Assistant sees it and the switch of every
        account; show the Garmin login state of every account."""
        report_url = runtime.get("report_url")
        if not report_url:
            return
        payload = {
            "external_url": _external_url(hass),
            "language": hass.config.language,
            "integration_version": loaded_version,
            "restart_needed": state["restart_needed"],
            "accounts": {acc_id: {"mcp_enabled": acc["enabled"]} for acc_id, acc in runtime["accounts"].items()},
        }
        try:
            async with session.post(report_url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return
                answer = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return  # app stopped or restarting – keep the current notices
        if not isinstance(answer, dict):
            return
        logins = answer.get("accounts")
        if not isinstance(logins, dict):  # app before 0.6: one account
            logins = {"1": {"login": answer.get("login")}}
        notify = answer.get("notify", True)
        for acc_id, acc in runtime["accounts"].items():
            info = logins.get(acc_id)
            if not isinstance(info, dict):
                continue
            name = str(info.get("name") or acc.get("name") or acc_id)[:60]
            if info.get("login") == "failed" and notify:
                ir.async_create_issue(
                    hass,
                    DOMAIN,
                    login_issue_id(acc_id),
                    is_fixable=False,
                    is_persistent=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key=ISSUE_LOGIN,
                    translation_placeholders={"name": name},
                )
            elif info.get("login") in ("ok", "failed", "logged_out"):
                ir.async_delete_issue(hass, DOMAIN, login_issue_id(acc_id))

    runtime["report"] = _report
    # The switches restore their state here – before the first report to the app.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _remove_stale_devices(hass, entry, set(runtime["accounts"]))

    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))
    entry.async_on_unload(async_track_time_interval(hass, _check_update, timedelta(minutes=1)))
    entry.async_on_unload(async_track_time_interval(hass, _report, REPORT_INTERVAL))
    await _check_update()  # before the first report, so the app learns it right away
    hass.async_create_task(_report())

    # Remove ourselves once the app has been uninstalled (see cleanup.py).
    async_watch_app(hass, entry, entry.data.get("app_slug"))

    _LOGGER.info("Garmin Connect MCP remote access enabled (%d account(s))", len(accounts))
    return True


def _remove_stale_devices(hass: HomeAssistant, entry: ConfigEntry, account_ids: set[str]) -> None:
    """Devices (and their switches) of accounts that were removed in the app."""
    registry = dr.async_get(hass)
    wanted = {device_identifier(entry, acc_id) for acc_id in account_ids}
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        if not device.identifiers & wanted:
            registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data:
        for account in data["accounts"].values():
            webhook_unregister(hass, account["webhook_id"])
        await data["session"].close()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Entry removed – by Home Assistant after the app was uninstalled, by the
    app in direct mode, or by hand. Delete our files if the app is gone.

    The Supervisor withdraws the announcement while it is still uninstalling,
    so check again a few times before giving up (the app removes the files
    itself in direct mode)."""
    ir.async_delete_issue(hass, DOMAIN, ISSUE_LOGIN)
    for account in entry_accounts(entry):
        ir.async_delete_issue(hass, DOMAIN, login_issue_id(account["id"]))
    app_slug = entry.data.get("app_slug")

    async def _check_later() -> None:
        for delay in (0, 30, 120, 600):
            await asyncio.sleep(delay)
            if hass.config_entries.async_entries(DOMAIN):
                return  # set up again (reinstalled) – keep everything
            if await async_app_gone(hass, app_slug):
                await async_delete_files(hass)
                return

    hass.async_create_background_task(_check_later(), f"{DOMAIN} cleanup")


SWITCHED_OFF_TEXT = (
    "The Garmin Connect MCP server of this Garmin account is switched off in Home Assistant. "
    "Ask the user to turn on its switch ('Garmin Connect MCP … Server') in Home Assistant, then "
    "try again."
)


def switched_off_answer(message) -> dict | None:
    """MCP answer for one JSON-RPC message while the switch is off (None = no answer)."""
    if not isinstance(message, dict) or "id" not in message:
        return None  # notification
    method = message.get("method")
    if method == "initialize":
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        result = {
            "protocolVersion": str(params.get("protocolVersion") or "2025-06-18"),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "Garmin Connect MCP (switched off)", "version": VERSION},
            "instructions": SWITCHED_OFF_TEXT,
        }
    elif method == "tools/list":
        result = {
            "tools": [
                {
                    "name": "garmin_connection_status",
                    "description": "Explains why the Garmin Connect tools are not available. " + SWITCHED_OFF_TEXT,
                    "inputSchema": {"type": "object", "properties": {}},
                }
            ]
        }
    elif method == "tools/call":
        result = {"content": [{"type": "text", "text": SWITCHED_OFF_TEXT}], "isError": True}
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": SWITCHED_OFF_TEXT}}
    return {"jsonrpc": "2.0", "id": message["id"], "result": result}


async def _switched_off(request: web.Request) -> web.Response:
    """Answer an MCP request ourselves – nothing is forwarded to the app."""
    if request.method != "POST":
        return web.Response(status=405, headers={"Allow": "POST"})
    try:
        data = json.loads(await request.read() or b"{}")
    except ValueError:
        return web.json_response({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
    if isinstance(data, list):
        answers = [a for a in (switched_off_answer(m) for m in data[:50]) if a is not None]
        return web.json_response(answers) if answers else web.Response(status=202)
    answer = switched_off_answer(data)
    return web.json_response(answer) if answer is not None else web.Response(status=202)


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
        _LOGGER.warning("Garmin Connect MCP app not reachable: %s", type(err).__name__)
        return web.json_response(
            {"error": "Garmin Connect MCP app is not reachable. Is it running?"},
            status=502,
        )
