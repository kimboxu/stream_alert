from base import (initVar, userDataVar, discordBotDataVars)
class StateManager:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
            cls._instance.init_var = None
        return cls._instance

    async def initialize(self):
        if self.init_var is None:
            self.init_var = initVar()
            await discordBotDataVars(self.init_var)
            await userDataVar(self.init_var)
        return self.init_var

    def get_init(self):
        return self.init_var
