import asyncio


class _Config:
    language = "en"


class _ConfigEntries:
    def __init__(self, hass):
        self.hass = hass
        self.removed = []

    async def async_remove(self, entry_id):
        self.removed.append(entry_id)
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
