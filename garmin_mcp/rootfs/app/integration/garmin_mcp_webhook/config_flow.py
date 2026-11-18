"""Config flow for the Garmin Connect MCP remote-access webhook.

The entry is created automatically: the app announces its settings through
the Supervisor's discovery service, Home Assistant starts this flow with them
(source "hassio") and the entry is created without questions. When the app
announces new settings (account added or removed, new secret URL, new name),
the entry is updated without a reload (see __init__.py). When the app is
uninstalled, the Supervisor withdraws the announcement and Home Assistant removes the entry by
itself.
"""

from __future__ import annotations

import re
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN, MAX_ACCOUNTS, TITLE

try:  # Home Assistant 2025.1+
    from homeassistant.helpers.service_info.hassio import HassioServiceInfo
except ImportError:  # pragma: no cover
    HassioServiceInfo = Any  # type: ignore[misc,assignment]

_INTERNAL_URL = re.compile(r"^http://[0-9a-zA-Z.\-]+:\d{1,5}/[A-Za-z0-9_\-]{20,}/(mcp|ha)$")
_WEBHOOK_ID = re.compile(r"^garmin_mcp_[A-Za-z0-9_\-]{20,}$")
_SLUG = re.compile(r"^[a-z0-9_]{1,64}$")
_ACCOUNT_ID = re.compile(r"^[0-9]{1,6}$")


def _clean_name(value: Any) -> str:
    """A display name: printable, single line, at most 60 characters."""
    text = "".join(ch for ch in str(value or "") if ch.isprintable())
    return " ".join(text.split())[:60]


def entry_data(config: dict[str, Any], slug: str) -> dict[str, Any] | None:
    """Validate what the app announced; None if anything looks wrong."""
    report_url = str(config.get("report_url", ""))
    app_slug = str(config.get("app_slug", "") or slug)
    if not _INTERNAL_URL.match(report_url) or not report_url.endswith("/ha") or not _SLUG.match(app_slug):
        return None
    raw = config.get("accounts")
    if raw is None:  # app versions with a single account
        raw = [{"id": "1", "name": "", "webhook_id": config.get("webhook_id"), "target_url": config.get("target_url")}]
    if not isinstance(raw, list) or len(raw) > MAX_ACCOUNTS:
        return None
    accounts = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        account = {
            "id": str(item.get("id", "")),
            "name": _clean_name(item.get("name")),
            "webhook_id": str(item.get("webhook_id", "")),
            "target_url": str(item.get("target_url", "")),
        }
        if not _ACCOUNT_ID.match(account["id"]) or not _WEBHOOK_ID.match(account["webhook_id"]):
            return None
        if not _INTERNAL_URL.match(account["target_url"]) or not account["target_url"].endswith("/mcp"):
            return None
        accounts.append(account)
    if len({a["id"] for a in accounts}) != len(accounts) or len({a["webhook_id"] for a in accounts}) != len(accounts):
        return None
    return {"accounts": accounts, "report_url": report_url, "app_slug": app_slug}


class GarminMcpWebhookConfigFlow(ConfigFlow, domain=DOMAIN):
    """Only ever set up by the app (discovery), never by hand."""

    VERSION = 1

    async def async_step_hassio(self, discovery_info: HassioServiceInfo) -> ConfigFlowResult:
        data = entry_data(discovery_info.config, discovery_info.slug)
        if data is None:
            return self.async_abort(reason="invalid_discovery")
        await self.async_set_unique_id(discovery_info.uuid)
        # Same announcement with new settings (account added/removed/renamed,
        # secret URL rotated, new IP): update the entry. No reload – the
        # update listener applies the change, so the switches of the other
        # accounts stay as they are.
        self._abort_if_unique_id_configured(updates=data, reload_on_update=False)
        # Only one entry: replace one from an older app version or install.
        for entry in self._async_current_entries(include_ignore=False):
            await self.hass.config_entries.async_remove(entry.entry_id)
        return self.async_create_entry(title=TITLE, data=data)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_abort(reason="set_up_by_app")
