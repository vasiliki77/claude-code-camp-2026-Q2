import os

from .message import Message


class Context:
    def __init__(self, *, task, system=None, working_dir=None):
        self.task = task
        self.system = system
        self.messages = []
        self.tools = {}
        # Expanded eagerly so every consumer sees the same absolute path, and
        # left as None when unset — `working_dir=False` means "no filesystem
        # tools" at the run() layer and must not become the string "False" here.
        self.working_dir = (
            os.path.abspath(os.path.expanduser(str(working_dir))) if working_dir else None
        )

    def register_tool(self, tool):
        self.tools[tool.name] = tool

    def add_message(self, role, content, tool_use_id=None):
        self.messages.append(Message(role, content, tool_use_id))

    # Drop all conversation history, keeping tools and system prompt intact.
    # Used by the REPL's /clear command. Rebinds rather than mutating in place,
    # matching Ruby's `@messages = []`.
    def clear_messages(self):
        self.messages = []

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
