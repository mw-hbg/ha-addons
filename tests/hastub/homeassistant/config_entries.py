class ConfigEntry:
    def __init__(self, entry_id="test"):
        self.entry_id = entry_id
        self.unloads = []

    def async_on_unload(self, func):
        self.unloads.append(func)


class ConfigFlow:
    def __init_subclass__(cls, **kwargs):
        pass


ConfigFlowResult = dict
