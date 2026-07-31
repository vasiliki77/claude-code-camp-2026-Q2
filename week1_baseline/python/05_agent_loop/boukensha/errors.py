class UnknownToolError(Exception):
    """Raised when dispatch is called with a name that has no registered tool."""


class ApiError(Exception):
    """Raised when an API request fails after exhausting retries."""


class LoopError(Exception):
    """Declared for runaway agents, but currently unused — Agent winds down via
    a final tools-disabled call rather than raising. Mirrors Ruby, which also
    declares it without a raise site."""


class UnsupportedModelError(Exception):
    """Raised when a backend is constructed with a model outside its MODELS table."""
