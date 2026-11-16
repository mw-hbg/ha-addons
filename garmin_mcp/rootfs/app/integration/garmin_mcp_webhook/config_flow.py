"""Config flow for the Garmin Connect MCP remote-access webhook.

The entry is normally created automatically by the Garmin Connect MCP app.
Adding it by hand via Settings → Devices & services works too; it has no
options – everything comes from the app.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN, TITLE


class GarminMcpWebhookConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create the single config entry without asking anything."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=TITLE, data={})

    async def async_step_import(
        self, import_data: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self.async_step_user()
