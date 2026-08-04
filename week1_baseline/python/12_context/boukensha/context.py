import math
import os

from .message import Message


class Context:
    def __init__(
        self,
        *,
        task,
        system=None,
        working_dir=None,
        context_window=200_000,
        compaction_threshold=0.85,
    ):
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
        # Two counters, measuring different things. current_tokens is window
        # pressure — what the *next* call will send — and drives compaction.
        # turn_tokens is spend, cumulative across a turn, and drives the token
        # ceiling. Conflating them is what made the old display grow unbounded
        # past /clear.
        self.context_window = context_window
        self.compaction_threshold = compaction_threshold
        self.current_tokens = 0
        self.turn_tokens = 0

    def register_tool(self, tool):
        self.tools[tool.name] = tool

    def add_message(self, role, content, tool_use_id=None):
        self.messages.append(Message(role, content, tool_use_id))

    # Update the known context size from the last API response's input tokens.
    def update_tokens(self, n):
        self.current_tokens = int(n or 0)

    # Reset the cumulative per-turn spend counter. Called at the top of a turn.
    def reset_turn_tokens(self):
        self.turn_tokens = 0

    # Add one API call's input+output tokens to the cumulative per-turn total.
    def add_turn_tokens(self, input_tokens, output_tokens):
        self.turn_tokens += int(input_tokens or 0) + int(output_tokens or 0)

    # Fraction of the context window currently in use (0.0–1.0). The guard is
    # not decorative: a misconfigured window of 0 would otherwise be a
    # ZeroDivisionError raised mid-turn, from inside the render loop.
    def usage_fraction(self):
        if not self.context_window or self.context_window <= 0:
            return 0.0

        return self.current_tokens / self.context_window

    def usage_pct(self):
        return round(self.usage_fraction() * 100)

    # True when we should compact before the next API call.
    def needs_compaction(self, threshold=None):
        if threshold is None:
            threshold = self.compaction_threshold

        return self.usage_fraction() >= threshold

    # Drop the oldest messages to free space, keeping roughly target_fraction of
    # them and at least 2. Resets current_tokens to 0 (the next API response
    # reports the true new size). Returns the number of messages dropped.
    def compact_messages(self, target_fraction=0.60):
        if len(self.messages) <= 2:
            return 0

        drop = min(
            math.ceil(len(self.messages) * (1.0 - target_fraction)),
            len(self.messages) - 2,
        )
        drop = self._snap_to_user(max(drop, 0))

        # Rebound rather than mutated in place, matching clear_messages.
        self.messages = self.messages[drop:]
        self.current_tokens = 0

        return drop

    # Drop all conversation history, keeping tools and system prompt intact.
    # Used by the REPL's /clear command. Rebinds rather than mutating in place,
    # matching Ruby's `@messages = []`.
    def clear_messages(self):
        self.messages = []
        self.current_tokens = 0

    def tool_count(self):
        return len(self.tools)

    def turn_count(self):
        return len(self.messages)

    def __str__(self):
        task_name = self.task.task_name() if self.task else None
        return (
            f"#<Context task={task_name} "
            f"turns={self.turn_count()} tools={self.tool_count()} "
            f"window={self.context_window} current={self.current_tokens}>"
        )

    __repr__ = __str__

    # ---------- private ---------------------------------------------------

    # Advance a drop point until the first surviving message is a plain user
    # turn.
    #
    # Dropping purely by count orphans any tool_result whose tool_use was
    # dropped with it — Anthropic answers that with a 400, and separately
    # requires a conversation to open on a user turn. With the MUD tools
    # registered, tool pairs are most of the history, so an unsnapped drop lands
    # mid-pair more often than not.
    #
    # Snapping forward only ever drops *more*, never less, so the invariant
    # holds unconditionally. The newest message is always a user turn (both
    # run() and Repl.run_turn append the input before the agent runs), so the
    # scan always terminates on a real index.
    def _snap_to_user(self, index):
        while index < len(self.messages) and self.messages[index].role != "user":
            index += 1

        return index
