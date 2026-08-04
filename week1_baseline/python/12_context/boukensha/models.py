"""Model → capability table, folded from every backend's own MODELS dict.

``context_window`` is a known *model* fact — the physical input ceiling — not a
value the user sets. The agent looks it up from its configured model id; the
user never configures it in settings.yaml.

Derived rather than hand-written because the lookup has to happen *before* a
backend is constructed (run() sizes the Context first), which is the only reason
this module exists at all. A second hand-maintained copy of the same numbers
drifts: Ruby's static version claimed claude-sonnet-4-6 was 200k while the
Anthropic backend said 1M, and gave every non-Anthropic model the fallback
below — the configured gemma4:e4b (128k) would have compacted at a fifth of its
real window.

Imports the backends, so nothing under backends/ may import this module.
"""

from .backends.anthropic import Anthropic
from .backends.gemini import Gemini
from .backends.ollama import Ollama
from .backends.ollama_cloud import OllamaCloud
from .backends.openai import OpenAI

BACKENDS = (Anthropic, OpenAI, Gemini, Ollama, OllamaCloud)

TABLE = {
    model: spec for backend in BACKENDS for model, spec in backend.MODELS.items()
}

# Conservative floor for a model no backend declares. Deliberately small: an
# unrecognised id compacting early is recoverable, one assuming a window it does
# not have is a 400 mid-turn.
DEFAULT_CONTEXT_WINDOW = 32_000


def context_window(model):
    return TABLE.get(str(model), {}).get("context_window") or DEFAULT_CONTEXT_WINDOW


def known(model):
    return str(model) in TABLE
