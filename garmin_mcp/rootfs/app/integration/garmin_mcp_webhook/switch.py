"""Switch "Garmin Connect MCP Server": turn the MCP server on and off.

Off means: the webhook answers every MCP request itself with "switched off"
(nothing reaches the app), and the app stops its Garmin server until the
switch is turned on again. The state survives restarts of Home Assistant and
of the app.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    async_add_entities([McpServerSwitch(hass, entry)])


class McpServerSwitch(SwitchEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "mcp_server"
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_mcp_server"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Garmin Connect MCP",
            manufacturer="mw-hbg",
            model="Home Assistant app",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _runtime(self) -> dict:
        return self.hass.data[DOMAIN][self._entry.entry_id]

    @property
    def is_on(self) -> bool:
        return bool(self._runtime["enabled"])

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        # On by default; only an explicit "off" is restored.
        self._runtime["enabled"] = not (last is not None and last.state == "off")

    async def _set(self, enabled: bool) -> None:
        self._runtime["enabled"] = enabled
        self.async_write_ha_state()
        # Tell the app right away (it stops or starts its Garmin server).
        await self._runtime["report"]()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
