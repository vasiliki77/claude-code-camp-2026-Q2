from .errors import ApiError
from .logger import Logger


class Agent:
    """The agent loop: send, dispatch any tool calls, repeat until the model
    signals it is done. The agent never decides on its own to stop — it watches
    for stop_reason == "end_turn"."""

    # Default iteration ceiling. The *enforced* value comes from the
    # max_iterations constructor arg (sourced from Config at the run/repl path),
    # which falls back to this constant. 0 (or None) disables the ceiling.
    MAX_ITERATIONS = 25

    # The wind-down call is deliberately short and cheap.
    WRAP_UP_OUTPUT_TOKENS = 400
    WRAP_UP_DIRECTIVE = (
        "You have reached your action limit for this turn. Do not call any more tools.\n"
        "Briefly summarize what you accomplished, what is still unfinished, and the\n"
        "single next action you would take."
    )

    def __init__(
        self,
        *,
        context,
        registry,
        builder,
        client,
        logger=None,
        task_settings=None,
        max_iterations=None,
        max_output_tokens=None,
    ):
        self.context = context
        self.registry = registry
        self.builder = builder
        self.client = client
        # Ruby defaults this to Logger.new in the signature. Python evaluates
        # defaults once at def-time, which would share a single open file handle
        # across every Agent ever constructed — so it is built here instead.
        self.logger = logger or Logger()
        self.max_iterations = self._resolve_max_iterations(task_settings, max_iterations)
        self.max_output_tokens = self._resolve_max_output_tokens(
            task_settings, max_output_tokens
        )
        self.iteration = 0

    def run(self):
        while True:
            # Limits are *trigger thresholds*, not hard caps: once we reach one
            # we stop starting new work iterations and make exactly one terminal
            # wind-down call instead of raising.
            if self._iteration_limit_reached():
                self.logger.limit_reached(
                    kind="max_iterations", n=self.iteration, max=self.max_iterations
                )
                return self._wrap_up("max_iterations")

            self.iteration += 1
            self.logger.iteration(n=self.iteration, max=self.max_iterations)
            self.logger.prompt(messages=self.context.messages, tools=self.context.tools)

            response = self.client.call(**self._call_opts())
            self.logger.raw(data=response)
            parsed = self.builder.parse_response(response)

            if parsed["stop_reason"] == "tool_use":
                self._handle_tool_calls(parsed["content"], response)
            else:
                text = self._extract_text(parsed["content"])
                self._log_response(text=text, response=response)
                self.logger.turn_end(reason="completed", iterations=self.iteration)
                return text

    # ---------- private ---------------------------------------------------

    def _resolve_max_iterations(self, task_settings, explicit):
        if explicit is not None:
            return int(explicit)
        if task_settings and hasattr(self.context.task, "max_iterations"):
            return self.context.task.max_iterations(task_settings)

        return self.MAX_ITERATIONS

    def _resolve_max_output_tokens(self, task_settings, explicit):
        if explicit is not None:
            return explicit
        if task_settings and hasattr(self.context.task, "max_output_tokens"):
            return self.context.task.max_output_tokens(task_settings)

        return None

    def _iteration_limit_reached(self):
        return self.max_iterations > 0 and self.iteration >= self.max_iterations

    # Per-call options shared by every model round-trip of the turn.
    # `is not None`, not truthiness: an explicit max_output_tokens of 0 is
    # meaningful and Ruby forwards it (0 is truthy there).
    def _call_opts(self):
        if self.max_output_tokens is None:
            return {}

        return {"max_output_tokens": self.max_output_tokens}

    # One final, tools-disabled model call so the agent ends the turn in
    # character rather than aborting. Runs *outside* the counted loop: it never
    # re-checks the limits (so it cannot re-trigger) and does not increment
    # self.iteration — which is why the logged `iterations` counts work
    # iterations only. Falls back to a deterministic message if the call fails.
    def _wrap_up(self, reason):
        self.context.add_message("user", self.WRAP_UP_DIRECTIVE)

        try:
            response = self.client.call(
                tools=[], max_output_tokens=self.WRAP_UP_OUTPUT_TOKENS
            )
            text = self._extract_text(self.builder.parse_response(response)["content"])
        except ApiError:
            # No response to log, but the turn still ended — and it ended for
            # the limit reason, not "completed".
            msg = self._fallback_message(reason)
            self.logger.turn_end(reason=reason, iterations=self.iteration)
            return msg

        if not text.strip():
            text = self._fallback_message(reason)

        self._log_response(text=text, response=response)
        self.logger.turn_end(reason=reason, iterations=self.iteration)
        return text

    def _fallback_message(self, reason):
        return (
            f"I reached my {self.max_iterations}-action limit for this turn before "
            f"finishing ({reason}). Ask me to continue and I'll pick up from here."
        )

    def _extract_text(self, content):
        return "".join(b["text"] for b in content if b.get("type") == "text")

    def _handle_tool_calls(self, content, response):
        tool_calls = [b for b in content if b.get("type") == "tool_use"]

        # A tool-use turn still costs tokens, so it is logged as a response.
        # When the model sent no prose alongside the calls, stand in a summary
        # so the transcript is not a blank assistant turn.
        reasoning = self._extract_text(content)
        plural = "s" if len(tool_calls) != 1 else ""
        self._log_response(
            text=reasoning
            if reasoning.strip()
            else f"(tool use — {len(tool_calls)} call{plural})",
            response=response,
        )

        # The assistant message must be stored before its tool results — the
        # Anthropic API rejects a tool_result whose tool_use block is not
        # already in the history.
        self.context.add_message("assistant", content)

        for block in tool_calls:
            name = block["name"]
            args = block["input"]
            use_id = block["id"]

            self.logger.tool_call(name=name, args=args)
            # A failing tool is data, not a crash: the error goes back to the
            # model as the tool result so it can recover on the next iteration.
            try:
                result = self.registry.dispatch(name, args)
                self.logger.tool_result(name=name, result=result, ok=True)
            except Exception as e:
                result = f"ERROR: {type(e).__name__}: {e}"
                self.logger.tool_result(
                    name=name, result=result, ok=False, error=str(e)
                )

            self.context.add_message("tool_result", str(result), tool_use_id=use_id)

    def _log_response(self, *, text, response):
        self.logger.response(
            text=text,
            usage=self._normalized_usage(response),
            stop_reason=response.get("stop_reason"),
            task=self.context.task,
            backend=self.builder.backend,
        )

    # Anthropic and OpenAI put usage under "usage", Gemini under
    # "usageMetadata", Ollama at the top level as two loose counters.
    def _normalized_usage(self, response):
        if response.get("usage") is not None:
            return response["usage"]
        if response.get("usageMetadata") is not None:
            return response["usageMetadata"]

        usage = {}
        for key in ("prompt_eval_count", "eval_count"):
            if key in response:
                usage[key] = response[key]

        return usage or None
