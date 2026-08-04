from . import usage as usage_mod
from .errors import ApiError, TurnCancelled
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
        max_turn_tokens=None,
        max_output_tokens=None,
        cancel_event=None,
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
        # 0 = disabled, matching max_iterations.
        self.max_turn_tokens = self._resolve_max_turn_tokens(
            task_settings, max_turn_tokens
        )
        self.max_output_tokens = self._resolve_max_output_tokens(
            task_settings, max_output_tokens
        )
        # Optional threading.Event. When set, the loop raises TurnCancelled at
        # its next iteration boundary — cooperative, because Python cannot
        # safely interrupt a blocking call the way Ruby's Thread#raise can.
        self.cancel_event = cancel_event
        self.iteration = 0

    def run(self):
        self.context.reset_turn_tokens()
        self._compact_if_needed()

        while True:
            # Cancellation is checked before the ceilings, and before anything
            # is spent: a turn the user has already abandoned must not pay for
            # a wind-down call it will never show.
            if self.cancel_event is not None and self.cancel_event.is_set():
                raise TurnCancelled("turn cancelled")

            # Two independent ceilings; stop at whichever trips first. Limits
            # are *trigger thresholds*, not hard caps: once we reach one we stop
            # starting new work iterations and make exactly one terminal
            # wind-down call (counted in tokens, but not as another iteration)
            # instead of raising.
            if self._iteration_limit_reached():
                self.logger.limit_reached(
                    kind="max_iterations", n=self.iteration, max=self.max_iterations
                )
                return self._wrap_up("max_iterations")

            if self._token_limit_reached():
                self.logger.limit_reached(
                    kind="max_tokens",
                    n=self.context.turn_tokens,
                    max=self.max_turn_tokens,
                )
                return self._wrap_up("max_tokens")

            self.iteration += 1
            self.logger.iteration(n=self.iteration, max=self.max_iterations)
            self.logger.prompt(
                messages=self.context.messages,
                tools=self.context.tools,
                context_window=self.context.context_window,
            )

            response = self.client.call(**self._call_opts())
            self.logger.raw(data=response)
            parsed = self.builder.parse_response(response)
            self._record_usage(response)
            self._log_reasoning(parsed["content"])

            if parsed["stop_reason"] == "tool_use":
                self._handle_tool_calls(parsed["content"], response)
            else:
                text = self._extract_text(parsed["content"])
                self._log_response(
                    text=text, response=response, stop_reason=parsed["stop_reason"]
                )
                self.logger.turn_end(
                    reason="completed",
                    iterations=self.iteration,
                    tokens=self.context.turn_tokens,
                )
                # Persist the final reply. Up to step 07 this text was returned
                # and dropped, so a second turn over the same Context would see
                # the user's question and the tool results but not the answer.
                self.context.add_message("assistant", text)
                return text

    # ---------- private ---------------------------------------------------

    def _resolve_max_iterations(self, task_settings, explicit):
        if explicit is not None:
            return int(explicit)
        if task_settings and hasattr(self.context.task, "max_iterations"):
            return self.context.task.max_iterations(task_settings)

        return self.MAX_ITERATIONS

    def _resolve_max_turn_tokens(self, task_settings, explicit):
        if explicit is not None:
            return int(explicit)
        if task_settings and hasattr(self.context.task, "max_turn_tokens"):
            return int(self.context.task.max_turn_tokens(task_settings))

        return 0

    def _resolve_max_output_tokens(self, task_settings, explicit):
        if explicit is not None:
            return explicit
        if task_settings and hasattr(self.context.task, "max_output_tokens"):
            return self.context.task.max_output_tokens(task_settings)

        return None

    def _iteration_limit_reached(self):
        return self.max_iterations > 0 and self.iteration >= self.max_iterations

    def _token_limit_reached(self):
        return (
            self.max_turn_tokens > 0
            and self.context.turn_tokens >= self.max_turn_tokens
        )

    # Add this call's input+output to the cumulative turn total (the spend
    # budget) and refresh the known context size from input tokens (compaction
    # pressure). The trigger is evaluated on pre-wrap-up spend; the reported
    # total includes the wind-down call too.
    #
    # Goes through usage.py rather than reading response["usage"]["input_tokens"]
    # directly: those are Anthropic's key names, and on Gemini or Ollama both
    # counters would sit at zero forever — no error, just a token budget that
    # never trips and a compaction trigger that never fires.
    def _record_usage(self, response):
        counts = usage_mod.tokens(usage_mod.envelope(response))
        self.context.add_turn_tokens(counts["input"], counts["output"])
        self.context.update_tokens(counts["input"])

    def _compact_if_needed(self):
        if not self.context.needs_compaction():
            return

        before = self.context.current_tokens
        dropped = self.context.compact_messages()
        self.logger.compaction(
            before=before,
            dropped=dropped,
            context_window=self.context.context_window,
        )

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
            parsed_wrap = self.builder.parse_response(response)
            text = self._extract_text(parsed_wrap["content"])
        except ApiError:
            # No response to log, but the turn still ended — and it ended for
            # the limit reason, not "completed".
            msg = self._fallback_message(reason)
            self.logger.turn_end(
                reason=reason,
                iterations=self.iteration,
                tokens=self.context.turn_tokens,
            )
            self.context.add_message("assistant", msg)
            return msg

        if not text.strip():
            text = self._fallback_message(reason)

        # The wind-down call is not a counted iteration, but it is spent money:
        # its tokens belong in the turn total the log reports.
        self._record_usage(response)
        self._log_response(
            text=text, response=response, stop_reason=parsed_wrap["stop_reason"]
        )
        self.logger.turn_end(
            reason=reason, iterations=self.iteration, tokens=self.context.turn_tokens
        )
        self.context.add_message("assistant", text)
        return text

    def _fallback_message(self, reason):
        return (
            f"I reached my {self.max_iterations}-action limit for this turn before "
            f"finishing ({reason}). Ask me to continue and I'll pick up from here."
        )

    def _extract_text(self, content):
        return "\n".join(b["text"] for b in content if b.get("type") == "text")

    # Emit one `reasoning` event per reasoning block so the viewer can show the
    # model's thinking as a first-class step. Empty, non-redacted blocks are
    # skipped to avoid noise (a redacted/omitted block still renders, since it
    # tells the viewer "the model thought here").
    def _log_reasoning(self, content):
        for block in content:
            if block.get("type") != "reasoning":
                continue

            redacted = block.get("redacted") is True
            text = str(block.get("text") or "")
            if not text.strip() and not redacted:
                continue

            self.logger.reasoning(text=text, redacted=redacted)

    def _handle_tool_calls(self, content, response):
        tool_calls = [b for b in content if b.get("type") == "tool_use"]

        # A tool-use turn still costs tokens, so it is logged as a response.
        # Any prose the model sent alongside the calls is its plan for them, and
        # is logged separately — the placeholder below owns the turn's usage.
        preamble = self._extract_text(content)
        if preamble.strip():
            self.logger.plan(text=preamble)

        plural = "s" if len(tool_calls) != 1 else ""
        self._log_response(
            text=f"(tool use — {len(tool_calls)} call{plural})",
            response=response,
            stop_reason="tool_use",
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

    # stop_reason is the *normalized* one from the builder, not the provider's
    # raw string — the two agree on Anthropic and nowhere else.
    def _log_response(self, *, text, response, stop_reason):
        self.logger.response(
            text=text,
            usage=usage_mod.envelope(response),
            stop_reason=stop_reason,
            task=self.context.task,
            backend=self.builder.backend,
        )
