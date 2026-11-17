from enum import Enum


class DeviceEntryType(Enum):
    SERVICE = "service"


def DeviceInfo(**kwargs):  # noqa: N802 - TypedDict in Home Assistant
    return dict(kwargs)
