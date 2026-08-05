import io
import sys
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boukensha  # noqa: E402
from boukensha.agent import Agent  # noqa: E402
from boukensha.errors import ApiError, LoopError, TurnCancelled  # noqa: E402


def _repl_module():
    """The boukensha.repl *module*, not the re-exported repl() function.

    __init__.py does `from .run import repl`, which binds the function over the
    submodule of the same name, so `import boukensha.repl` hands back a
    function. Predates this step; sys.modules still has the real module.
    """
    return sys.modules["boukensha.repl"]


def make_repl(**overrides):
    ctx = boukensha.Context(task=boukensha.Player, system="")
    kwargs = dict(
        context=ctx,
        registry=boukensha.Registry(ctx),
        builder=Mock(),
        client=Mock(),
        logger=Mock(),
        version="0.11.0",
        model="test-model",
    )
    kwargs.update(overrides)
    return boukensha.Repl(**kwargs)


class TestHandleCommand(unittest.TestCase):
    """The slash-command chain, extracted from start() so a TUI can call it."""

    def setUp(self):
        self.repl = make_repl()
        self.written = []
        self.repl.on_output(self.written.append)

    def test_exit_and_quit_return_quit(self):
        self.assertEqual("quit", self.repl.handle_command("/exit"))
        self.assertEqual("quit", self.repl.handle_command("/quit"))
        self.assertIn("Goodbye.", self.written)

    def test_handled_commands_return_command(self):
        for cmd in ("/help", "/quiet", "/loud", "/clear"):
            self.assertEqual("command", self.repl.handle_command(cmd), cmd)

    def test_non_command_returns_none(self):
        self.assertIsNone(self.repl.handle_command("look around"))
        self.assertEqual([], self.written)

    def test_clear_resets_history_and_turn_count(self):
        self.repl.context.add_message("user", "hi")
        self.repl.turn = 7

        self.repl.handle_command("/clear")

        self.assertEqual([], self.repl.context.messages)
        self.assertEqual(0, self.repl.turn)

    def test_quiet_and_loud_toggle_runtime(self):
        self.repl.handle_command("/quiet")
        self.assertTrue(boukensha.is_quiet())
        self.repl.handle_command("/loud")
        self.assertFalse(boukensha.is_quiet())

    def test_nothing_reaches_stdout_when_a_callback_is_registered(self):
        # The whole point of on_output: a TUI owns the screen, and a stray print
        # would corrupt its frame.
        buf = io.StringIO()
        with redirect_stdout(buf):
            for cmd in ("/help", "/quiet", "/loud", "/clear", "/exit"):
                self.repl.handle_command(cmd)

        self.assertEqual("", buf.getvalue())
        self.assertTrue(self.written)


class TestOutputFallback(unittest.TestCase):
    def test_without_a_callback_output_goes_to_stdout(self):
        repl = make_repl()
        buf = io.StringIO()
        with redirect_stdout(buf):
            repl.handle_command("/loud")

        self.assertIn("(logging enabled)", buf.getvalue())

    def test_a_trailing_newline_is_not_doubled(self):
        # Ruby's puts leaves a string that already ends in a newline alone;
        # Python's print does not. The plain REPL's output is only a gate while
        # it stays byte-identical to step 10's.
        repl = make_repl()
        buf = io.StringIO()
        with redirect_stdout(buf):
            repl._output("already ends in a newline\n")

        self.assertEqual("already ends in a newline\n", buf.getvalue())


class TestRunTurnRouting(unittest.TestCase):
    """run_turn's results and errors go through the callback, never print."""

    def route(self, agent_behaviour):
        repl = make_repl()
        written = []
        repl.on_output(written.append)
        repl_mod = _repl_module()

        class FakeAgent:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def run(self):
                return agent_behaviour()

        repl_mod.Agent, saved = FakeAgent, repl_mod.Agent
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                repl.run_turn("do a thing")
            return written, buf.getvalue()
        finally:
            repl_mod.Agent = saved

    def test_result_is_routed(self):
        written, stdout = self.route(lambda: "the answer")

        self.assertIn("the answer", "".join(written))
        self.assertEqual("", stdout)

    def test_api_error_is_routed(self):
        def boom():
            raise ApiError("upstream exploded")

        written, stdout = self.route(boom)

        self.assertIn("API call failed", "".join(written))
        self.assertEqual("", stdout)

    def test_loop_error_is_routed(self):
        def boom():
            raise LoopError("runaway")

        written, _ = self.route(boom)
        self.assertIn("[error] runaway", "".join(written))

    def test_cancellation_is_routed(self):
        def boom():
            raise TurnCancelled("cancelled")

        written, _ = self.route(boom)
        self.assertIn("(interrupted)", "".join(written))


class TestAgentCancellation(unittest.TestCase):
    """Cooperative cancellation — the documented divergence from Ruby."""

    def test_raises_at_the_next_iteration_boundary(self):
        ctx = boukensha.Context(task=boukensha.Player, system="")
        event = threading.Event()
        event.set()

        # No backend call needed: the check sits at the top of the loop, so a
        # pre-set event short-circuits before the client is ever touched.
        agent = Agent(
            context=ctx,
            registry=boukensha.Registry(ctx),
            builder=Mock(),
            client=Mock(),
            logger=Mock(),
            cancel_event=event,
        )

        with self.assertRaises(TurnCancelled):
            agent.run()

        agent.client.call.assert_not_called()

    def test_absent_event_does_not_cancel(self):
        ctx = boukensha.Context(task=boukensha.Player, system="")
        agent = Agent(
            context=ctx,
            registry=boukensha.Registry(ctx),
            builder=Mock(),
            client=Mock(),
            logger=Mock(),
        )

        self.assertIsNone(agent.cancel_event)

    def test_run_turn_exposes_a_fresh_event_per_turn(self):
        repl_mod = _repl_module()
        repl = make_repl()
        repl.on_output(lambda _s: None)
        seen = []

        class FakeAgent:
            def __init__(self, **kwargs):
                seen.append(kwargs.get("cancel_event"))

            def run(self):
                return "ok"

        repl_mod.Agent, saved = FakeAgent, repl_mod.Agent
        try:
            repl.run_turn("one")
            repl.run_turn("two")
        finally:
            repl_mod.Agent = saved

        self.assertEqual(2, len(seen))
        self.assertIsNotNone(seen[0])
        # A cancel from the previous turn must not carry into the next.
        self.assertIsNot(seen[0], seen[1])


if __name__ == "__main__":
    unittest.main()
