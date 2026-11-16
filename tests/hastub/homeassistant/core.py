import asyncio


class _Config:
    language = "en"


class _ConfigEntries:
    def __init__(self, hass):
        self.hass = hass
        self.entries = []
        self.removed = []
        self.reloaded = []
        self.remove_hook = None  # like HA: removing an entry calls async_remove_entry

    def async_entries(self, domain=None):
        return list(self.entries)

    async def async_remove(self, entry_id):
        self.removed.append(entry_id)
        entry = next((e for e in self.entries if e.entry_id == entry_id), None)
        self.entries = [e for e in self.entries if e.entry_id != entry_id]
        if self.remove_hook and entry is not None:
            await self.remove_hook(self.hass, entry)
        return {"require_restart": False}


class HomeAssistant:
    def __init__(self):
        self.data = {}
        self.config = _Config()
        self.config_entries = _ConfigEntries(self)
        self.tasks = []

    async def async_add_executor_job(self, func, *args):
        return func(*args)

    def async_create_task(self, coro):
        task = asyncio.ensure_future(coro)
        self.tasks.append(task)
        return task

    def async_create_background_task(self, coro, name=None):
        return self.async_create_task(coro)
