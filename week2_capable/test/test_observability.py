"""Layer 1 observability fixes — see docs/plans/observability/layer1.

Three things the session stream used to get wrong, each of which made a
conclusion drawn from the log unsafe:

  - every tool call was recorded ok=True unless the tool *raised*, and the
    tools here return their failures rather than raising;
  - close() wrote nothing, so a clean exit and a crash were identical on disk;
  - every `prompt` event re-serialized the whole history, which grows
    quadratically in turn length.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boukensha  # noqa: E402
from boukensha.tool import ToolFailure, classify_result  # noqa: E402


def read_events(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


class TestToolResultOk(unittest.TestCase):
    """The flag has to distinguish a failure from a success on its own.

    Every one of these used to log ok=True. Only the raising case was ever
    reported truthfully, and raising is the one thing the tools do not do.
    """

    def test_a_returned_error_string_is_not_ok(self):
        ok, error = classify_result("error: command timed out after 30s: find /")

        self.assertFalse(ok)
        self.assertEqual("error: command timed out after 30s: find /", error)

    def test_an_mcp_failure_is_not_ok(self):
        ok, error = classify_result(ToolFailure("You can't go that way."))

        self.assertFalse(ok)
        self.assertEqual("You can't go that way.", error)

    def test_a_normal_result_is_ok(self):
        ok, error = classify_result("Market Square\n  You are standing...")

        self.assertTrue(ok)
        self.assertIsNone(error)

    def test_a_tool_failure_still_reaches_the_model_as_its_text(self):
        """The marker must not change what the model reads, only what the log
        records — the model needs the failure text to correct itself."""
        failure = ToolFailure("Nothing here by that name.")

        self.assertIsInstance(failure, str)
        self.assertEqual("Nothing here by that name.", str(failure))
        self.assertEqual("Nothing here by that name.", f"{failure}")

    def test_a_result_that_merely_mentions_an_error_is_still_ok(self):
        """The prefix check is stringly-typed and this is its known edge: only
        a leading "error: " counts, so ordinary prose is not misfiled."""
        ok, _error = classify_result("The scroll describes an error: read it.")

        self.assertTrue(ok)


class TestSessionEnd(unittest.TestCase):
    def logger_in(self, tmp):
        return boukensha.Logger(log=str(Path(tmp) / "session.jsonl"))

    def test_close_records_how_the_session_ended(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = self.logger_in(tmp)
            logger.turn(n=1)
            logger.close(reason="interrupted")

            last = read_events(logger.path)[-1]

        self.assertEqual("session_end", last["phase"])
        self.assertEqual("interrupted", last["reason"])
        self.assertEqual(1, last["turns"])
        self.assertIn("duration_s", last)

    def test_a_one_shot_run_counts_as_one_turn(self):
        """Only Repl calls turn(); run() does not. Counting those calls alone
        reported turns=0 for every non-REPL session — the 05-08 mapping run was
        80 iterations of one turn and said zero."""
        with tempfile.TemporaryDirectory() as tmp:
            logger = self.logger_in(tmp)
            logger.turn_end(reason="max_iterations", iterations=80, tokens=1040800)
            logger.close()

            self.assertEqual(1, read_events(logger.path)[-1]["turns"])

    def test_a_repl_session_counts_its_numbered_turns(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = self.logger_in(tmp)
            for n in (1, 2, 3):
                logger.turn(n=n)
                logger.turn_end(reason="completed", iterations=2)
            logger.close()

            self.assertEqual(3, read_events(logger.path)[-1]["turns"])

    def test_a_turn_interrupted_mid_flight_still_counts(self):
        """Counting endings alone would drop the turn that never finished."""
        with tempfile.TemporaryDirectory() as tmp:
            logger = self.logger_in(tmp)
            logger.turn(n=1)
            logger.turn_end(reason="completed", iterations=2)
            logger.turn(n=2)  # started, never ended
            logger.close(reason="interrupted")

            self.assertEqual(2, read_events(logger.path)[-1]["turns"])

    def test_default_reason_is_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = self.logger_in(tmp)
            logger.close()

            self.assertEqual("completed", read_events(logger.path)[-1]["reason"])

    def test_close_is_idempotent(self):
        """Both shutdown paths close in a finally block; a second close must not
        append a second ending."""
        with tempfile.TemporaryDirectory() as tmp:
            logger = self.logger_in(tmp)
            logger.close()
            logger.close()

            events = read_events(logger.path)

        self.assertEqual(1, len([e for e in events if e["phase"] == "session_end"]))

    def test_unpriced_session_reports_no_cost_rather_than_zero(self):
        """An unmeasured cost and a free run are different claims."""
        with tempfile.TemporaryDirectory() as tmp:
            logger = self.logger_in(tmp)
            logger.close()

            self.assertIsNone(read_events(logger.path)[-1]["total_cost_usd"])


class TestPromptPayload(unittest.TestCase):
    """`messages` is carried only when the last one is the user message that
    opened the turn — the only part log_viz reads."""

    def prompt_event(self, messages):
        with tempfile.TemporaryDirectory() as tmp:
            logger = boukensha.Logger(log=str(Path(tmp) / "session.jsonl"))
            logger.prompt(messages=messages, tools={}, context_window=200_000)
            logger.close()

            return next(e for e in read_events(logger.path) if e["phase"] == "prompt")

    def test_carried_when_the_last_message_is_from_the_user(self):
        messages = [boukensha.Message("user", "go north")]
        event = self.prompt_event(messages)

        self.assertIn("messages", event)
        self.assertEqual("go north", event["messages"][-1]["content"])

    def test_omitted_mid_turn(self):
        messages = [
            boukensha.Message("user", "go north"),
            boukensha.Message("assistant", "(tool use — 1 call)"),
            boukensha.Message("tool_result", "Market Square"),
        ]
        event = self.prompt_event(messages)

        self.assertNotIn("messages", event)

    def test_message_count_is_always_present(self):
        """The history's size stays visible even when its contents are not,
        so the growth this trim exists to stop is still measurable."""
        messages = [
            boukensha.Message("user", "go north"),
            boukensha.Message("assistant", "ok"),
        ]

        self.assertEqual(2, self.prompt_event(messages)["message_count"])


if __name__ == "__main__":
    unittest.main()
