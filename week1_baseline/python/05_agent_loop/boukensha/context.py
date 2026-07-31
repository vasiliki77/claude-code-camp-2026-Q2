from .message import Message


class Context:
    def __init__(self, *, task, system=None):
        self.task = task
        self.system = system
        self.messages = []
        self.tools = {}

    def register_tool(self, tool):
        self.tools[tool.name] = tool

    def add_message(self, role, content, tool_use_id=None):
        self.messages.append(Message(role, content, tool_use_id))

    def tool_count(self):
        return len(self.tools)

    def turn_count(self):
        return len(self.messages)

    def __str__(self):
        task_name = self.task.task_name() if self.task else None
        return (
            f"#<Context task={task_name} "
            f"turns={self.turn_count()} tools={self.tool_count()}>"
        )

    __repr__ = __str__
