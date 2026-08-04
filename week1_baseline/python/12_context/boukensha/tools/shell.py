import os
import subprocess


def register(registry, *, working_dir, timeout=30, allowed_commands=None):
    """Register command-execution tools.

    Tools registered:
      run_command  — run a shell command inside the working directory

    Options:
      working_dir:      (required) all commands run with this as their cwd
      timeout:          seconds before a command is killed (default 30)
      allowed_commands: optional list of allowed executable names. None (the
                        default) permits everything; an empty list permits
                        nothing.
    """
    root = os.path.abspath(os.path.expanduser(working_dir))

    def oops(msg):
        return f"error: {msg}"

    allow_note = ""
    if allowed_commands is not None:
        allow_note = f"Allowed executables: {', '.join(str(c) for c in allowed_commands)}."

    @registry.tool(
        "run_command",
        description=(
            "Run a shell command inside the working directory and return its combined "
            f"stdout+stderr output. Commands run with a {timeout}-second timeout. {allow_note}"
        ),
        parameters={
            "command": {
                "type": "string",
                "description": "The shell command to execute (e.g. 'python script.py', 'ls -la', 'git status')",
            }
        },
    )
    def run_command(command):
        # `is not None`, not truthiness: an empty allow-list means "permit
        # nothing", which is a meaningful configuration and is falsy in Python.
        # Ruby's `if allowed_commands` gets this right for free because [] is
        # truthy there — the same trap as steps 03-06, in a new place.
        if allowed_commands is not None:
            executable = (str(command).strip().split() or [""])[0]
            if executable not in [str(c) for c in allowed_commands]:
                allowed = ", ".join(str(c) for c in allowed_commands)
                return oops(f"'{executable}' is not in the allowed-commands list ({allowed})")

        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=timeout,
                # Ruby's Timeout.timeout kills the block; subprocess.run's timeout
                # raises but only kills the direct child. shell=True means that
                # child is the shell, so a grandchild can survive — accepted,
                # because matching Ruby exactly would mean process groups and a
                # platform-specific kill, which this step is not about.
            )
        except subprocess.TimeoutExpired:
            return oops(f"command timed out after {timeout}s: {command}")
        except FileNotFoundError as e:
            return oops(f"command not found: {e}")
        except OSError as e:
            return oops(str(e))

        # capture2e in Ruby merges the streams; capture_output keeps them apart,
        # so join them in the same order a terminal would have shown them.
        combined = (completed.stdout or "") + (completed.stderr or "")
        exit_note = "" if completed.returncode == 0 else f"\n[exit {completed.returncode}]"
        output = combined.strip()
        return f"(no output){exit_note}" if not output else f"{output}{exit_note}"
