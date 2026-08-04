import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boukensha  # noqa: E402
from boukensha.tools import file_system, shell  # noqa: E402


class LocalToolTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.ctx = boukensha.Context(task=boukensha.Player, system="", working_dir=self.root)
        self.registry = boukensha.Registry(self.ctx)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel, content):
        path = Path(self.root, rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path


class TestFileSystemTools(LocalToolTest):
    def setUp(self):
        super().setUp()
        file_system.register(self.registry, working_dir=self.root)

    def test_registers_the_expected_tools(self):
        self.assertEqual(
            ["delete_file", "list_directory", "pwd", "read_file", "search_files", "write_file"],
            sorted(self.ctx.tools),
        )

    def test_pwd_returns_the_root(self):
        self.assertEqual(os.path.abspath(self.root), self.registry.dispatch("pwd", {}))

    def test_write_read_roundtrip(self):
        out = self.registry.dispatch("write_file", {"path": "a/b.txt", "content": "héllo"})

        # Bytes, not characters — the accented character makes the two differ,
        # which is what Ruby's bytesize reports.
        self.assertIn("wrote 6 bytes", out)
        self.assertEqual("héllo", self.registry.dispatch("read_file", {"path": "a/b.txt"}))

    def test_list_directory_marks_directories(self):
        self.write("sub/file.txt", "x")
        self.write("top.txt", "y")

        self.assertEqual("sub/\ntop.txt", self.registry.dispatch("list_directory", {}))

    def test_empty_directory(self):
        os.makedirs(Path(self.root, "empty"))
        self.assertEqual("(empty)", self.registry.dispatch("list_directory", {"path": "empty"}))

    def test_delete_file(self):
        self.write("gone.txt", "x")

        self.assertEqual("ok: deleted gone.txt", self.registry.dispatch("delete_file", {"path": "gone.txt"}))
        self.assertFalse(Path(self.root, "gone.txt").exists())

    def test_search_files(self):
        self.write("one.txt", "alpha\nbeta\n")
        self.write("two.txt", "gamma\n")

        out = self.registry.dispatch("search_files", {"pattern": "beta"})

        self.assertEqual("one.txt:2:beta", out)

    def test_search_reports_no_matches(self):
        self.write("one.txt", "alpha\n")
        self.assertEqual("no matches", self.registry.dispatch("search_files", {"pattern": "zzz"}))

    def test_invalid_pattern_is_reported_not_raised(self):
        out = self.registry.dispatch("search_files", {"pattern": "["})
        self.assertTrue(out.startswith("error: invalid pattern"))

    def test_path_traversal_is_refused(self):
        # Deliberately not asserted against this file's own text: step 07's
        # escape check failed identically in both languages because the README
        # documenting it became the test data.
        for escape in ["../outside.txt", "a/../../outside.txt", "/etc/passwd"]:
            out = self.registry.dispatch("read_file", {"path": escape})
            self.assertIn("escapes the working directory", out, f"{escape} was not refused")

    def test_writing_outside_the_root_is_refused(self):
        out = self.registry.dispatch("write_file", {"path": "../evil.txt", "content": "x"})

        self.assertIn("escapes the working directory", out)
        self.assertFalse(Path(self.root).parent.joinpath("evil.txt").exists())

    def test_reading_a_directory_is_an_error_not_a_crash(self):
        os.makedirs(Path(self.root, "adir"))
        self.assertEqual("error: 'adir' is not a file", self.registry.dispatch("read_file", {"path": "adir"}))


class TestShellTools(LocalToolTest):
    def test_runs_a_command_in_the_root(self):
        shell.register(self.registry, working_dir=self.root)

        out = self.registry.dispatch("run_command", {"command": "pwd"})

        self.assertEqual(os.path.realpath(self.root), os.path.realpath(out))

    def test_reports_a_non_zero_exit(self):
        shell.register(self.registry, working_dir=self.root)

        out = self.registry.dispatch("run_command", {"command": "exit 3"})

        self.assertIn("[exit 3]", out)

    def test_timeout_is_reported(self):
        shell.register(self.registry, working_dir=self.root, timeout=1)

        out = self.registry.dispatch("run_command", {"command": "sleep 5"})

        self.assertIn("timed out after 1s", out)

    def test_allow_list_blocks_other_executables(self):
        shell.register(self.registry, working_dir=self.root, allowed_commands=["echo"])

        self.assertIn("hi", self.registry.dispatch("run_command", {"command": "echo hi"}))
        blocked = self.registry.dispatch("run_command", {"command": "cat /etc/passwd"})
        self.assertIn("not in the allowed-commands list", blocked)

    def test_empty_allow_list_permits_nothing(self):
        # [] is falsy in Python and truthy in Ruby. `if allowed_commands` would
        # silently permit everything here — the same truthiness divergence that
        # bit steps 03-06, in a new place.
        shell.register(self.registry, working_dir=self.root, allowed_commands=[])

        out = self.registry.dispatch("run_command", {"command": "echo hi"})

        self.assertIn("not in the allowed-commands list", out)

    def test_none_allow_list_permits_everything(self):
        shell.register(self.registry, working_dir=self.root, allowed_commands=None)

        self.assertIn("hi", self.registry.dispatch("run_command", {"command": "echo hi"}))


if __name__ == "__main__":
    unittest.main()
