import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boukensha  # noqa: E402
from boukensha.tui import Tui  # noqa: E402


class FakeRepl:
    """A Repl-shaped stub.

    The TUI is supposed to own no session logic, so a stub with the five members
    it reads plus the three methods it calls should be enough to drive the whole
    interface. If this class ever needs to grow, logic has leaked out of Repl.
    """

    def __init__(self, mcp_status="(not configured)"):
        ctx = boukensha.Context(task=boukensha.Player, system="")
        self.context = ctx
        self.logger = Mock()
        self.version = "0.11.0"
        self.model = "test-model"
        self.turn = 0
        self._mcp_status = mcp_status
        self._cancel_event = None
        self.output_cb = None
        self.commands = []
        self.turns = []

    def banner(self):
        return "BANNER LINE\n"

    def mud_status(self):
        return self._mcp_status

    def on_output(self, cb):
        self.output_cb = cb

    def handle_command(self, line):
        self.commands.append(line)
        if line in ("/exit", "/quit"):
            return "quit"
        if line.startswith("/"):
            return "command"
        return None

    def run_turn(self, line):
        self.turns.append(line)


class TestTui(unittest.IsolatedAsyncioTestCase):
    """Driven through Textual's headless harness — no real terminal.

    Ruby ships no automated coverage for its own Tui; this is a net gain the
    harness makes possible, not scope creep.
    """

    async def test_banner_is_rendered_and_output_is_wired(self):
        repl = FakeRepl()
        app = Tui(repl)

        async with app.run_test():
            self.assertIsNotNone(repl.output_cb, "on_output must be registered at mount")
            repl.logger.subscribe.assert_called_once()

    async def test_submitting_text_launches_a_turn(self):
        repl = FakeRepl()
        app = Tui(repl)

        async with app.run_test() as pilot:
            await pilot.press("l", "o", "o", "k")
            await pilot.press("enter")
            await pilot.pause(0.2)

        self.assertEqual(["look"], repl.turns)

    async def test_slash_command_is_dispatched_not_run_as_a_turn(self):
        repl = FakeRepl()
        app = Tui(repl)

        async with app.run_test() as pilot:
            for ch in "/help":
                await pilot.press(ch if ch != "/" else "slash")
            await pilot.press("enter")
            await pilot.pause(0.1)

        self.assertIn("/help", repl.commands)
        self.assertEqual([], repl.turns)

    async def test_ctrl_l_clears(self):
        repl = FakeRepl()
        app = Tui(repl)

        async with app.run_test() as pilot:
            await pilot.press("ctrl+l")
            await pilot.pause(0.1)

        self.assertIn("/clear", repl.commands)

    async def test_escape_sets_the_cancel_event_when_a_turn_is_running(self):
        import threading

        repl = FakeRepl()
        started, release = threading.Event(), threading.Event()

        def slow_turn(_line):
            started.set()
            release.wait(5)

        repl.run_turn = slow_turn
        app = Tui(repl)

        async with app.run_test() as pilot:
            await pilot.press("h", "i")
            await pilot.press("enter")
            self.assertTrue(started.wait(3), "turn thread never started")

            # The Repl owns the event; the TUI only sets it.
            repl._cancel_event = threading.Event()
            await pilot.press("escape")
            await pilot.pause(0.1)

            self.assertTrue(repl._cancel_event.is_set())
            release.set()

    async def test_escape_is_harmless_when_idle(self):
        repl = FakeRepl()
        app = Tui(repl)

        async with app.run_test() as pilot:
            await pilot.press("escape")
            await pilot.pause(0.05)  # must not raise

    async def test_status_bar_names_the_mud_route(self):
        for status, expected in [
            ("(not configured)", ""),
            ("via mud-manager 0.2.0 (26 tools over MCP)", "mud:mcp"),
            ("localhost:4000  (Reachable)", "mud:direct"),
        ]:
            repl = FakeRepl(mcp_status=status)
            app = Tui(repl)
            async with app.run_test():
                route = app._mud_route()
            if expected:
                self.assertIn(expected, route)
            else:
                self.assertEqual("", route)

    async def test_turn_error_clears_the_progress_line(self):
        repl = FakeRepl()

        def boom(_line):
            raise RuntimeError("kaboom")

        repl.run_turn = boom
        app = Tui(repl)

        async with app.run_test() as pilot:
            await pilot.press("h", "i")
            await pilot.press("enter")
            await pilot.pause(0.4)

            # The finally: in the turn thread must always enqueue turn_complete,
            # or the spinner runs forever after an unexpected failure.
            self.assertFalse(app._live["active"])


if __name__ == "__main__":
    unittest.main()
