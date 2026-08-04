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
