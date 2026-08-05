import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boukensha  # noqa: E402
from boukensha import usage  # noqa: E402

ANTHROPIC = {"usage": {"input_tokens": 120, "output_tokens": 30}}
OPENAI_CHAT = {"usage": {"prompt_tokens": 120, "completion_tokens": 30}}
GEMINI = {"usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 30}}
OLLAMA = {"prompt_eval_count": 120, "eval_count": 30}

PROVIDERS = {
    "anthropic": ANTHROPIC,
    "openai_chat": OPENAI_CHAT,
    "gemini": GEMINI,
    "ollama": OLLAMA,
}


class FakeBackend:
    model = "fake-model"
    usage_unit = "tokens"


class FakeBuilder:
    def __init__(self):
        self.backend = FakeBackend()

    def parse_response(self, _response):
        return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "done"}]}


class FakeClient:
    def __init__(self, response):
        self._response = response

    def call(self, **_opts):
        return self._response


class TestUsageShim(unittest.TestCase):
    """Token accounting across providers.

    Every backend normalizes its *content*; none of them normalize their usage
    accounting. Reading response["usage"]["input_tokens"] — Anthropic's names —
    is why this file exists: on Gemini or Ollama both counters sit at zero, the
    turn budget never trips, the compaction trigger never fires, and the context
    gauge reads 0% all session. No error, no log line, nothing to notice.
    """

    def test_every_provider_shape_yields_the_same_counts(self):
        for name, response in PROVIDERS.items():
            with self.subTest(provider=name):
                counts = usage.tokens(usage.envelope(response))

                self.assertEqual(120, counts["input"])
                self.assertEqual(30, counts["output"])

    def test_a_response_with_no_usage_at_all(self):
        self.assertIsNone(usage.envelope({"content": []}))

        counts = usage.tokens(None)

        self.assertIsNone(counts["input"])
        self.assertIsNone(counts["output"])

    def test_unparseable_counts_do_not_raise(self):
        self.assertIsNone(usage.tokens({"input_tokens": "not a number"})["input"])

    def test_envelope_returns_none_not_empty_dict(self):
        """Logger._execution_metadata treats a falsy usage as "nothing to
        report", so {} and None are not interchangeable here."""
        self.assertIsNone(usage.envelope({}))


class TestAgentAccounting(unittest.TestCase):
    def run_one_turn(self, response):
        with tempfile.TemporaryDirectory() as tmp:
            context = boukensha.Context(
                task=boukensha.Player, system="s", context_window=1000
            )
            context.add_message("user", "hello")

            logger = boukensha.Logger(log=str(Path(tmp) / "session.jsonl"))
            agent = boukensha.Agent(
                context=context,
                registry=boukensha.Registry(context),
                builder=FakeBuilder(),
                client=FakeClient(response),
                logger=logger,
            )
            agent.run()
            logger.close()

            events = [
                json.loads(line) for line in Path(logger.path).read_text().splitlines()
            ]
            return context, events

    def test_turn_tokens_and_context_gauge_track_every_provider(self):
        for name, response in PROVIDERS.items():
            with self.subTest(provider=name):
                context, _events = self.run_one_turn(response)

                self.assertEqual(150, context.turn_tokens, "turn budget saw nothing")
                self.assertEqual(120, context.current_tokens, "gauge saw nothing")
                self.assertEqual(12, context.usage_pct())

    def test_response_events_carry_who_answered_and_what_it_cost(self):
        _context, events = self.run_one_turn(ANTHROPIC)
        response = next(e for e in events if e["phase"] == "response")

        self.assertEqual("fake_backend", response["provider"])
        self.assertEqual("fake-model", response["model"])
        self.assertEqual(120, response["input_tokens"])
        self.assertEqual(30, response["output_tokens"])


if __name__ == "__main__":
    unittest.main()
