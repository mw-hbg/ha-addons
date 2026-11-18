"""One switch per Garmin account: "Garmin Connect MCP <name> Server".

Off means: the account's webhook answers every MCP request itself with
"switched off" (nothing reaches the app), and the app stops that account's
Garmin server until the switch is turned on again. The state survives
restarts of Home Assistant and of the app.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from . import device_identifier
from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    accounts = hass.data[DOMAIN][entry.entry_id]["accounts"]
    async_add_entities([McpServerSwitch(hass, entry, account_id) for account_id in accounts])


class McpServerSwitch(SwitchEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "mcp_server"
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, account_id: str) -> None:
        self.hass = hass
        self._entry = entry
        self._account_id = account_id
        name = self._account.get("name") or ""
        # Account 1 keeps the unique id of the versions with a single account,
        # so its entity id (switch.garmin_connect_mcp_server) stays the same.
        suffix = "mcp_server" if account_id == "1" else f"{account_id}_mcp_server"
        self._attr_unique_id = f"{entry.entry_id}_{suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={device_identifier(entry, account_id)},
            name=f"Garmin Connect MCP {name}".strip(),
            manufacturer="mw-hbg",
            model="Garmin account",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _runtime(self) -> dict:
        return self.hass.data[DOMAIN][self._entry.entry_id]

    @property
    def _account(self) -> dict:
        return self._runtime["accounts"][self._account_id]

    @property
    def is_on(self) -> bool:
        return bool(self._account["enabled"])

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        # On by default; only an explicit "off" is restored.
        self._account["enabled"] = not (last is not None and last.state == "off")

    async def _set(self, enabled: bool) -> None:
        self._account["enabled"] = enabled
        self.async_write_ha_state()
        # Tell the app right away (it stops or starts this account's server).
        await self._runtime["report"]()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
