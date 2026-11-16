class HomeAssistant:
    def __init__(self):
        self.data = {}

    async def async_add_executor_job(self, func, *args):
        return func(*args)
