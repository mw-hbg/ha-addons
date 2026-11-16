"""Config flow for the Garmin Connect MCP remote-access webhook.

The entry is created automatically: the app announces its settings through
the Supervisor's discovery service, Home Assistant starts this flow with them
(source "hassio") and the entry is created without questions. When the app
announces new settings (new secret URL), the entry is updated and reloaded.
When the app is uninstalled, the Supervisor withdraws the announcement and
Home Assistant removes the entry by itself.
"""

from __future__ import annotations

import re
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN, TITLE

try:  # Home Assistant 2025.1+
    from homeassistant.helpers.service_info.hassio import HassioServiceInfo
except ImportError:  # pragma: no cover
    HassioServiceInfo = Any  # type: ignore[misc,assignment]

_INTERNAL_URL = re.compile(r"^http://[0-9a-zA-Z.\-]+:\d{1,5}/[A-Za-z0-9_\-]{20,}/(mcp|ha)$")
_WEBHOOK_ID = re.compile(r"^garmin_mcp_[A-Za-z0-9_\-]{20,}$")
_SLUG = re.compile(r"^[a-z0-9_]{1,64}$")


def entry_data(config: dict[str, Any], slug: str) -> dict[str, str] | None:
    """Validate what the app announced; None if anything looks wrong."""
    data = {
        "webhook_id": str(config.get("webhook_id", "")),
        "target_url": str(config.get("target_url", "")),
        "report_url": str(config.get("report_url", "")),
        "app_slug": str(config.get("app_slug", "") or slug),
    }
    if not _WEBHOOK_ID.match(data["webhook_id"]):
        return None
    if not _INTERNAL_URL.match(data["target_url"]) or not _INTERNAL_URL.match(data["report_url"]):
        return None
    if not _SLUG.match(data["app_slug"]):
        return None
    return data


class GarminMcpWebhookConfigFlow(ConfigFlow, domain=DOMAIN):
    """Only ever set up by the app (discovery), never by hand."""

    VERSION = 1

    async def async_step_hassio(self, discovery_info: HassioServiceInfo) -> ConfigFlowResult:
        data = entry_data(discovery_info.config, discovery_info.slug)
        if data is None:
            return self.async_abort(reason="invalid_discovery")
        await self.async_set_unique_id(discovery_info.uuid)
        # Same announcement with new settings (secret URL rotated, new IP):
        # update the entry and reload it.
        self._abort_if_unique_id_configured(updates=data)
        # Only one entry: replace one from an older app version or install.
        for entry in self._async_current_entries(include_ignore=False):
            await self.hass.config_entries.async_remove(entry.entry_id)
        return self.async_create_entry(title=TITLE, data=data)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_abort(reason="set_up_by_app")
