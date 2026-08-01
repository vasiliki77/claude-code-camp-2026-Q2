from .errors import UnknownToolError
from .tool import Tool


class Registry:
    def __init__(self, context):
        self.context = context

    # Registers a tool on the context. Used as a decorator — the decorated
    # function is the tool's block (Ruby passes it as a `&block` instead).
    def tool(self, name, *, description, parameters=None):
        def register(block):
            self.context.register_tool(
                Tool(str(name), description, parameters or {}, block)
            )
            return block

        return register

    def dispatch(self, name, args=None):
        tool = self.context.tools.get(str(name))
        if not tool:
            raise UnknownToolError(f"No tool registered as '{name}'")
        return tool.block(**(args or {}))
