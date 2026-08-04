class UnknownToolError(Exception):
    """Raised when dispatch is called with a name that has no registered tool."""


class ApiError(Exception):
    """Raised when an API request fails after exhausting retries."""


class LoopError(Exception):
    """Declared for runaway agents, but never raised or rescued anywhere — Agent
    winds down via a final tools-disabled call instead. Present in step 05,
    deleted in step 06, restored here; mirrors Ruby, which does the same."""


class UnsupportedModelError(Exception):
    """Raised when a backend is constructed with a model outside its MODELS table."""


class TurnCancelled(Exception):
    """Raised when a turn is cancelled through Agent's cancel_event.

    Ruby's TUI cancels by calling Thread#raise(Interrupt) on the turn thread,
    which lands wherever that thread currently is — including inside a blocking
    read, because MRI checks for pending interrupts around blocking I/O.

    Python has no safe equivalent. PyThreadState_SetAsyncExc only fires the next
    time the target thread returns to Python bytecode, so it cannot cut short an
    HTTP call already in flight; it would take effect once that call returned
    anyway, which is exactly when it no longer matters. Rather than ship a
    ctypes hack that looks like Ruby's behaviour and silently fails in the one
    case worth cancelling, cancellation here is cooperative: the agent checks a
    threading.Event at the top of each iteration.

    Accepted gap: Esc does not interrupt a single in-flight backend call, only
    takes effect at the next iteration or tool-call boundary.
    """
