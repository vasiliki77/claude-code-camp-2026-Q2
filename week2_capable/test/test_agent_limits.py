import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boukensha  # noqa: E402


class FakeBackend:
    model = "fake-model"


class ScriptedBuilder:
    """Answers "tool_use" until told otherwise, so the loop keeps going."""

    def __init__(self, stop_reason="tool_use"):
        self.backend = FakeBackend()
        self._stop_reason = stop_reason

    def parse_response(self, _response):
        if self._stop_reason == "tool_use":
            return {
                "stop_reason": "tool_use",
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "noop", "input": {}}
                ],
            }
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "done"}]}

    # The wind-down call is tools-disabled, so it must not loop forever.
    def wind_down(self):
        self._stop_reason = "end_turn"


class ScriptedClient:
    def __init__(self, builder, input_tokens, output_tokens):
        self._builder = builder
        self._usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}
        self.calls = 0

    def call(self, **opts):
        self.calls += 1
        # tools=[] marks the wind-down call — answer it as a normal reply.
        if opts.get("tools") == []:
            self._builder.wind_down()
        return {"usage": self._usage, "content": []}


class TestAgentLimits(unittest.TestCase):
    """The agent's two circuit breakers and the compaction trigger.

    All three fire only deep into a long or expensive turn, which is exactly
    where they are most awkward to observe. A scripted client reaches them in
    milliseconds and without an API key.
    """

    def run_agent(
        self,
        *,
        input_tokens=100,
        output_tokens=10,
        context_window=1000,
        current_tokens=0,
        pairs=0,
        stop_reason="tool_use",
        **agent_opts,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            context = boukensha.Context(
                task=boukensha.Player, system="s", context_window=context_window
            )
            for i in range(pairs):
                context.add_message("user", f"turn {i}")
                context.add_message(
                    "assistant",
                    [{"type": "tool_use", "id": f"t{i}", "name": "noop", "input": {}}],
                )
                context.add_message("tool_result", "ok", tool_use_id=f"t{i}")
            context.add_message("user", "go")
            context.update_tokens(current_tokens)

            registry = boukensha.Registry(context)
            registry.tool("noop", description="does nothing")(lambda: "ok")

            builder = ScriptedBuilder(stop_reason=stop_reason)
            client = ScriptedClient(builder, input_tokens, output_tokens)
            logger = boukensha.Logger(log=str(Path(tmp) / "session.jsonl"))

            before = len(context.messages)
            boukensha.Agent(
                context=context,
                registry=registry,
                builder=builder,
                client=client,
                logger=logger,
                **agent_opts,
            ).run()
            logger.close()

            events = [
                json.loads(line) for line in Path(logger.path).read_text().splitlines()
            ]
            return context, events, before

    def test_iteration_ceiling_stops_the_turn_and_winds_down(self):
        _ctx, events, _before = self.run_agent(max_iterations=3)
        limit = next(e for e in events if e["phase"] == "limit_reached")

        turn_end = next(e for e in events if e["phase"] == "turn_end")

        self.assertEqual("max_iterations", limit["kind"])
        self.assertEqual(3, limit["max"])
        self.assertEqual("max_iterations", turn_end["reason"])

    def test_token_ceiling_stops_a_turn_the_iteration_ceiling_would_not(self):
        """A turn can be cheap in tool calls and expensive in tokens, which is
        the gap this second ceiling exists to close."""
        ctx, events, _before = self.run_agent(
            input_tokens=400,
            output_tokens=100,
            max_iterations=100,
            max_turn_tokens=1200,
        )
        limit = next(e for e in events if e["phase"] == "limit_reached")

        turn_end = next(e for e in events if e["phase"] == "turn_end")

        self.assertEqual("max_tokens", limit["kind"])
        self.assertGreaterEqual(ctx.turn_tokens, 1200)
        self.assertEqual("max_tokens", turn_end["reason"])

    def test_zero_disables_a_ceiling(self):
        _ctx, events, _before = self.run_agent(max_iterations=2, max_turn_tokens=0)
        limit = next(e for e in events if e["phase"] == "limit_reached")

        self.assertEqual("max_iterations", limit["kind"])

    def test_compaction_fires_when_the_window_is_nearly_full(self):
        ctx, events, before = self.run_agent(
            pairs=15, current_tokens=900, stop_reason="end_turn"
        )
        compaction = next((e for e in events if e["phase"] == "compaction"), None)

        self.assertIsNotNone(compaction, "compaction never fired at 90% of the window")
        self.assertEqual(900, compaction["before"])
        self.assertEqual(1000, compaction["context_window"])
        self.assertGreater(compaction["dropped"], 0)
        self.assertLess(len(ctx.messages), before)

    def test_no_compaction_below_the_threshold(self):
        _ctx, events, _before = self.run_agent(
            pairs=15, current_tokens=100, stop_reason="end_turn"
        )

        self.assertIsNone(next((e for e in events if e["phase"] == "compaction"), None))


if __name__ == "__main__":
    unittest.main()
