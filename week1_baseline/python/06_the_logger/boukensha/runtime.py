"""Process-wide runtime state: the memoized Config plus the quiet/debug flags.

Mirrors the `module Boukensha` block `lib/boukensha.rb` gained in this step.
It lives in its own module rather than in `__init__.py` because `logger.py`
needs it at import time, and importing the package from inside one of its own
submodules is a circular import. Ruby has no equivalent problem: there,
`Boukensha.config` is resolved at call time.

Everything here is re-exported from `boukensha/__init__.py`, so callers reach it
as `boukensha.config()` exactly as Ruby reaches `Boukensha.config`.
"""

from .config import Config

_config = None
_quiet = False
_debug = False


# Memoized, mirroring Ruby's `@config ||= Config.new`. Constructing a Config
# reads settings.yaml, so it is deliberately deferred until something asks.
def config():
    global _config
    if _config is None:
        _config = Config()

    return _config


# quiet/loud are declared but unread in this step — nothing consults is_quiet()
# yet. Ruby declares them here too; kept for surface parity with later steps.
def set_quiet():
    global _quiet
    _quiet = True


def set_loud():
    global _quiet
    _quiet = False


def is_quiet():
    return _quiet


# debug *is* live: Logger.raw() writes nothing unless this is on.
def set_debug():
    global _debug
    _debug = True


def is_debug():
    return _debug
