from dataclasses import dataclass
from typing import Callable


class ToolFailure(str):
    """A tool result that is a failure, without changing what the model sees.

    Subclasses str deliberately. A failed tool call must still reach the model
    as its own text so it can correct itself, so everything downstream —
    add_message, json.dumps, the context — keeps treating this as the string it
    is. The type is the only thing that carries "this failed", and only the
    logger reads it.

    Exists because the flag it feeds used to lie. The agent logged ok=True
    unless a tool *raised*, but tools here do not raise: the local ones return
    "error: ..." from their `oops` helper, and MCP models a failed call as a
    successful JSON-RPC result carrying `isError`. Both were recorded as
    successes, so any error rate computed from the log undercounted exactly the
    failures that look like the agent getting stuck.
    """


def classify_result(result):
    """(ok, error) for a tool result, for the logger.

    Two signals, because there are two conventions in play and neither one can
    see the other's failures:

      ToolFailure   — set by tools/mcp.py from the MCP `isError` flag.
      "error: ..."  — the prefix tools/shell.py and tools/file_system.py return.

    The prefix check is stringly-typed and known to be so: a legitimate result
    that opens with "error: " is misread as a failure. That is the accepted cost
    of not refactoring every tool to a real result type this week; the wrapper
    above is the path out when one is wanted.
    """
    if isinstance(result, ToolFailure):
        return False, str(result)
    if isinstance(result, str) and result.startswith("error: "):
        return False, result

    return True, None


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    block: Callable

    def __str__(self):
        params = "[" + ", ".join(f":{key}" for key in self.parameters) + "]"
        return (
            f"#<Tool name={self.name} "
            f"description={str(self.description)[:41]} params={params}>"
        )

    __repr__ = __str__
