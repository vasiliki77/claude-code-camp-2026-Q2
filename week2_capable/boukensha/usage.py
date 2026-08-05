"""Where each provider hides its token counts.

Every backend normalizes its *content*; none of them normalize their usage
accounting, and the differences are two-layered — the envelope the counts live
in, and the names of the counts themselves:

    Anthropic / OpenAI  response["usage"]["input_tokens" | "output_tokens"]
    OpenAI (chat)       response["usage"]["prompt_tokens" | "completion_tokens"]
    Gemini              response["usageMetadata"]["promptTokenCount" | "candidatesTokenCount"]
    Ollama              response["prompt_eval_count" | "eval_count"]   (top level)

Both readers of that data live one shim away from being Anthropic-only: Agent
needs the integers to drive the turn budget and the compaction trigger, Logger
needs them to price the call, and the TUI needs them for its live counters.
They read the same numbers, so the key lists live here once instead of in three
places.
"""

INPUT_KEYS = ("input_tokens", "prompt_tokens", "promptTokenCount", "prompt_eval_count")
OUTPUT_KEYS = (
    "output_tokens",
    "completion_tokens",
    "candidatesTokenCount",
    "eval_count",
)


def envelope(response):
    """The sub-dict a provider's counts live in, or None when the response
    carries none. Ollama has no envelope at all, so its top-level counters are
    lifted into one.

    Returning None rather than {} is deliberate: Logger._execution_metadata
    treats a falsy usage as "nothing to report", and an empty dict there would
    quietly change what a response event carries.
    """
    if not isinstance(response, dict):
        return None
    if response.get("usage") is not None:
        return response["usage"]
    if response.get("usageMetadata") is not None:
        return response["usageMetadata"]

    lifted = {k: response[k] for k in INPUT_KEYS + OUTPUT_KEYS if k in response}

    return lifted or None


def tokens(env):
    """{"input": int | None, "output": int | None} from an envelope."""
    env = env or {}

    return {
        "input": _first_integer(env, INPUT_KEYS),
        "output": _first_integer(env, OUTPUT_KEYS),
    }


def _first_integer(source, keys):
    for key in keys:
        value = source.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    return None
