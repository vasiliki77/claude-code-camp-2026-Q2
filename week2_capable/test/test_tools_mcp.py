import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boukensha  # noqa: E402
from boukensha.tools import mcp as tools_mcp  # noqa: E402

# week2_capable/test/ -> week2_capable -> repo root. Was parents[4] while this
# tree lived at week1_baseline/python/12_context/test/.
REPO_ROOT = Path(__file__).resolve().parents[2]
DAEMON = REPO_ROOT / "week0_explore" / "mud_manager" / "bin" / "mud-manager"
FAKE_MUD_LIB = REPO_ROOT / "week0_explore" / "mud_manager" / "lib"
CALCULATOR = Path(__file__).resolve().parent / "support" / "tiny_mcp_server.py"
PASSWORD = "swordfish"
PREFIX = boukensha.MUD_PREFIX


class FakeMudProcess:
    """The Ruby FakeMud, driven as a subprocess.

    Porting it to Python would mean maintaining two fake MUDs that must agree
    on the CircleMUD login dance — a second thing to keep in sync for no gain.
    It is a server on a socket; the language it is written in is invisible from
    here, which is the same argument that lets Python skip tools/mud.rb.
    """

    def __init__(self, password=PASSWORD):
        self.password = password
        self.port = None
        self._process = None

    def start(self):
        script = (
            "require 'mud_manager'; require 'mud_manager/fake_mud'; "
            f"m = MudManager::FakeMud.new(password: {self.password!r}).start; "
            "puts m.port; $stdout.flush; sleep"
        )
        self._process = subprocess.Popen(
            ["ruby", "-I", str(FAKE_MUD_LIB), "-e", script],
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.port = int(self._process.stdout.readline().strip())
        return self

    def stop(self):
        if not self._process:
            return

        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
        # Ruby closes the pipe when the process is reaped; Python holds the
        # TextIOWrapper open and warns. Not a leak that matters in a test, but a
        # ResourceWarning per test is noise that hides real ones.
        if self._process.stdout:
            self._process.stdout.close()
        self._process = None


@unittest.skipUnless(DAEMON.exists(), f"daemon not found at {DAEMON}")
class TestToolsMcp(unittest.TestCase):
    """Boukensha as an MCP host.

    These spawn real MCP servers as subprocesses, so they exercise the actual
    thing: an agent framework that knows nothing about MUDs acquiring tools at
    runtime. No API key, no billing, no real MUD.
    """

    def setUp(self):
        self.mud = FakeMudProcess().start()
        self.ctx = boukensha.Context(task=boukensha.Player, system="")
        self.registry = boukensha.Registry(self.ctx)
        self.clients = []

    def tearDown(self):
        for client in self.clients:
            try:
                client.close()
            except Exception:
                pass
        self.mud.stop()

    def register_mud(self, prefix=PREFIX):
        client = tools_mcp.register(
            self.registry,
            command="ruby",
            args=[str(DAEMON), "--mcp"],
            env={
                "MUD_HOST": "127.0.0.1",
                "MUD_PORT": str(self.mud.port),
                "MUD_NAME": "Gandalf",
                "MUD_PASSWORD": PASSWORD,
                "BOUKENSHA_DIR": "",
            },
            prefix=prefix,
            label="mud",
        )
        self.clients.append(client)
        return client

    def register_calculator(self, prefix="calc"):
        client = tools_mcp.register(
            self.registry,
            command=sys.executable,
            args=[str(CALCULATOR)],
            prefix=prefix,
            label="calc",
        )
        self.clients.append(client)
        return client

    # ---------- generic host behaviour ------------------------------------

    def test_registers_a_non_mud_server(self):
        # The point of the whole port: tools/mcp.py has no MUD knowledge. Proven
        # by demonstration rather than assertion — if MUD assumptions creep in,
        # this fails.
        self.register_calculator()

        self.assertEqual(sorted(self.ctx.tools), ["calc__add", "calc__shout"])
        self.assertEqual("42.0", self.registry.dispatch("calc__add", {"a": 2, "b": 40}))
        self.assertEqual("HELLO", self.registry.dispatch("calc__shout", {"text": "hello"}))

    def test_two_servers_coexist(self):
        self.register_mud()
        self.register_calculator()

        self.assertIn(f"{PREFIX}__look", self.ctx.tools)
        self.assertIn("calc__add", self.ctx.tools)
        self.assertEqual(28, len(self.ctx.tools))  # 26 MUD + 2 calculator

    def test_collision_raises_and_names_the_server(self):
        self.register_calculator(prefix="dup")

        with self.assertRaises(tools_mcp.ToolCollisionError) as caught:
            self.register_calculator(prefix="dup")

        self.assertIn("dup__add", str(caught.exception))
        self.assertIn("prefix", str(caught.exception))

    def test_bare_names_still_work(self):
        # Proves prefixing is a policy, not baked in.
        self.register_calculator(prefix=None)

        self.assertIn("add", self.ctx.tools)
        self.assertNotIn("calc__add", self.ctx.tools)

    def test_a_failing_server_raises(self):
        with self.assertRaises(Exception):
            tools_mcp.register(self.registry, command="/nonexistent/server")

        self.assertEqual({}, self.ctx.tools)

    # ---------- the MUD server over MCP -----------------------------------

    def test_registers_every_advertised_tool(self):
        self.register_mud()

        self.assertEqual(26, len(self.ctx.tools))
        self.assertIn(f"{PREFIX}__look", self.ctx.tools)
        self.assertIn(f"{PREFIX}__cast_spell", self.ctx.tools)

    def test_registered_tools_dispatch_through_the_registry(self):
        text = None
        self.register_mud()

        text = self.registry.dispatch(f"{PREFIX}__move", {"direction": "north"})

        self.assertIn("You north", text)

    def test_the_daemon_still_sees_bare_names(self):
        # The prefix is client-side. The wire is unchanged.
        client = self.register_mud()
        names = [t["name"] for t in client.tools]

        self.assertIn("look", names)
        self.assertNotIn(f"{PREFIX}__look", names)

    def test_schemas_carry_the_enums_from_the_server(self):
        self.register_mud()

        move = self.ctx.tools[f"{PREFIX}__move"]
        self.assertEqual(
            ["north", "east", "south", "west", "up", "down"],
            move.parameters["direction"]["enum"],
        )
        self.assertIn("one of: north", move.parameters["direction"]["description"])

    def test_tool_failure_returns_text_rather_than_raising(self):
        self.register_mud()

        text = self.registry.dispatch(f"{PREFIX}__move", {"direction": "widdershins"})

        self.assertIn("INVALID_ARGUMENTS", text)


if __name__ == "__main__":
    unittest.main()
