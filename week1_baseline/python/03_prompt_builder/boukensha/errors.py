class UnknownToolError(Exception):
    """Raised when dispatch is called with a name that has no registered tool."""


class UnsupportedModelError(Exception):
    """Raised when a backend is constructed with a model outside its MODELS table."""
