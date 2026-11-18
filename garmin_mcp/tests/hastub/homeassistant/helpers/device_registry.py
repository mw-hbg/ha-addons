from enum import Enum


class DeviceEntryType(Enum):
    SERVICE = "service"


def DeviceInfo(**kwargs):  # noqa: N802 - TypedDict / dataclass in Home Assistant
    return dict(kwargs)


class _Device:
    def __init__(self, device_id, identifiers, config_entry_id):
        self.id = device_id
        self.identifiers = set(identifiers)
        self.config_entries = {config_entry_id}


class _Registry:
    """Devices by config entry; tests add devices and check removals."""

    def __init__(self):
        self.devices = {}
        self.removed = []

    def add(self, config_entry_id, identifiers):
        device = _Device(f"d{len(self.devices) + 1}", identifiers, config_entry_id)
        self.devices[device.id] = device
        return device

    def async_update_device(self, device_id, *, remove_config_entry_id=None, **_kwargs):
        device = self.devices[device_id]
        if remove_config_entry_id:
            device.config_entries.discard(remove_config_entry_id)
            self.removed.append(device_id)
            if not device.config_entries:
                self.devices.pop(device_id)
        return device


REGISTRY = _Registry()


def async_get(hass):
    return REGISTRY


def async_entries_for_config_entry(registry, config_entry_id):
    return [d for d in registry.devices.values() if config_entry_id in d.config_entries]
