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

# The base directory tools will operate relative to — the step 7 folder makes
# a good playground since it already has source files to read.
base_dir = Path(__file__).resolve().parents[2] / "07_the_run_dsl"


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


boukensha.repl(tools=define_tools)
