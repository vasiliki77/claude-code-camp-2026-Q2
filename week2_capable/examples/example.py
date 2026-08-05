import os
import sys
from pathlib import Path

# Make the step package importable when run as `python examples/example.py`
# (the direct analogue of Ruby's `require_relative "../lib/boukensha"`).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boukensha  # noqa: E402

# Config is loaded automatically inside boukensha.repl — system prompt, model,
# and API key all come from ~/.boukensha (or BOUKENSHA_DIR) by default.

print(f"Config: {boukensha.config()}")
print()

# The base directory tools will operate relative to. This pointed at the step-7
# folder while this tree lived under week1_baseline/python/; that was only ever
# "somewhere with source files to read", and the sibling step folders are not
# here any more. The week2_capable tree itself does the same job.
base_dir = Path(__file__).resolve().parents[1]


def define_tools(dsl):
    @dsl.tool(
        "read_file",
        description="Read the contents of a file from disk",
        parameters={
            "path": {
                "type": "string",
                "description": "File path (relative to the working directory)",
            }
        },
    )
    def read_file(path):
        return (base_dir / path).read_text()

    @dsl.tool(
        "list_directory",
        description="List the files in a directory",
        parameters={
            "path": {
                "type": "string",
                "description": (
                    "Directory path (relative to the working directory, "
                    "or '.' for root)"
                ),
            }
        },
    )
    def list_directory(path):
        return ", ".join(
            sorted(f for f in os.listdir(base_dir / path) if not f.startswith("."))
        )


# --no-tui falls back to the plain terminal REPL. Parsed here rather than in a
# loader: Ruby reaches its TUI through the installed gem's bin/boukensha, a
# packaging concept this port has excluded since step 10, while every Python
# step's launcher runs this file directly.
boukensha.repl(tools=define_tools, tui="--no-tui" not in sys.argv)
