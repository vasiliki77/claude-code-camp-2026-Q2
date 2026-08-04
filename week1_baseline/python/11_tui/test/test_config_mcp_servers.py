import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boukensha  # noqa: E402


@contextmanager
def settings(hash_):
    """Point BOUKENSHA_DIR at a throwaway directory holding one settings.yaml."""
    with tempfile.TemporaryDirectory() as dir_:
        Path(dir_, "settings.yaml").write_text(yaml.dump(hash_))
        previous = os.environ.get("BOUKENSHA_DIR")
        os.environ["BOUKENSHA_DIR"] = dir_
        try:
            yield boukensha.Config()
        finally:
            if previous is None:
                os.environ.pop("BOUKENSHA_DIR", None)
            else:
                os.environ["BOUKENSHA_DIR"] = previous


class TestConfigMcpServers(unittest.TestCase):
    """mcp_servers — servers as data, not code."""

    def test_absent_block_is_empty_not_none(self):
        with settings({"tasks": {}}) as cfg:
            self.assertEqual({}, cfg.mcp_servers)

    def test_parses_a_full_entry(self):
        with settings(
            {
                "mcp_servers": {
                    "mud": {
                        "command": "mud-manager",
                        "args": ["--mcp"],
                        "prefix": "tbamud",
                        "env": {"MUD_HOST": "localhost", "MUD_PORT": 4000},
                    }
                }
            }
        ) as cfg:
            entry = cfg.mcp_servers["mud"]

            self.assertEqual("mud-manager", entry["command"])
            self.assertEqual(["--mcp"], entry["args"])
            self.assertEqual("tbamud", entry["prefix"])
            # Env values are stringified — a YAML integer port would otherwise
            # reach the subprocess environment as an int and raise on spawn.
            self.assertEqual({"MUD_HOST": "localhost", "MUD_PORT": "4000"}, entry["env"])

    def test_defaults(self):
        with settings({"mcp_servers": {"bare": {"command": "thing"}}}) as cfg:
            entry = cfg.mcp_servers["bare"]

            self.assertEqual([], entry["args"])
            self.assertEqual({}, entry["env"])
            self.assertIsNone(entry["prefix"])
            # A server you bothered to configure and which then fails is a
            # problem you want to hear about, so required defaults to True.
            self.assertTrue(entry["required"])

    def test_required_can_be_turned_off(self):
        with settings(
            {"mcp_servers": {"decor": {"command": "thing", "required": False}}}
        ) as cfg:
            self.assertFalse(cfg.mcp_servers["decor"]["required"])

    def test_malformed_entries_do_not_raise(self):
        # A half-written config should surface as "no command" at registration,
        # not as a parse crash before the agent even starts.
        with settings({"mcp_servers": {"broken": None, "alsobroken": "nonsense"}}) as cfg:
            self.assertIsNone(cfg.mcp_servers["broken"]["command"])
            self.assertIsNone(cfg.mcp_servers["alsobroken"]["command"])

    def test_multiple_servers(self):
        with settings(
            {
                "mcp_servers": {
                    "mud": {"command": "mud-manager", "args": ["--mcp"]},
                    "filesystem": {"command": "npx", "args": ["-y", "server-fs", "/tmp"]},
                }
            }
        ) as cfg:
            self.assertEqual(["filesystem", "mud"], sorted(cfg.mcp_servers))


class TestMcpOptionTriState(unittest.TestCase):
    """None, False and True are three different answers.

    Ruby distinguishes nil / false / Hash on this option; in Python None and
    False are both falsy, so a naive `if not mcp` would collapse the first two.
    That bug is invisible in normal use — it only shows for someone explicitly
    disabling the route, which is exactly the person least likely to be running
    the tests. Hence this test.
    """

    def test_none_and_false_both_register_nothing(self):
        from boukensha.run import _mcp_opts

        with settings({"mud": {"host": "h", "username": "u", "password": "p"}}) as cfg:
            self.assertIsNone(_mcp_opts(None, cfg))
            self.assertIsNone(_mcp_opts(False, cfg))

    def test_true_builds_the_mud_preset(self):
        from boukensha.run import _mcp_opts

        with settings({"mud": {"host": "h", "username": "u", "password": "p"}}) as cfg:
            opts = _mcp_opts(True, cfg)

            self.assertEqual(["--mcp"], opts["args"])
            self.assertEqual(boukensha.MUD_PREFIX, opts["prefix"])
            self.assertEqual("u", opts["env"]["MUD_NAME"])

    def test_config_entry_wins_over_the_preset(self):
        from boukensha.run import _mcp_opts

        with settings(
            {
                "mud": {"host": "h", "username": "u", "password": "p"},
                "mcp_servers": {"mud": {"command": "/custom/mud-manager", "prefix": "zzz"}},
            }
        ) as cfg:
            opts = _mcp_opts(True, cfg)

            self.assertEqual("/custom/mud-manager", opts["command"])
            self.assertEqual("zzz", opts["prefix"])
            # Credentials still layer in from the mud: block.
            self.assertEqual("u", opts["env"]["MUD_NAME"])

    def test_dict_overrides_parts_of_the_preset(self):
        from boukensha.run import _mcp_opts

        with settings({"mud": {"host": "h", "username": "u", "password": "p"}}) as cfg:
            opts = _mcp_opts({"prefix": "custom"}, cfg)

            self.assertEqual("custom", opts["prefix"])
            self.assertEqual(["--mcp"], opts["args"])


if __name__ == "__main__":
    unittest.main()
