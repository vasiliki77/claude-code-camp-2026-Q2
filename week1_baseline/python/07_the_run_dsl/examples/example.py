import os
import sys
from pathlib import Path

# Make the step package importable when run as `python examples/example.py`
# (the direct analogue of Ruby's `require_relative "../lib/boukensha"`).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boukensha  # noqa: E402

# Config is loaded automatically inside boukensha.run — system prompt, model,
# and API key all come from ~/.boukensha (or BOUKENSHA_DIR) by default.
# You can still override any of them as keyword arguments if you want.

print("=== BOUKENSHA Step 7: The Boukensha.run DSL ===")
print()
print(f"Config: {boukensha.config()}")
print()

base_dir = Path(__file__).resolve().parents[1]


# Ruby passes an instance_eval'd block here, so its tools read as a bare
# `tool "read_file"`. Python cannot rebind name resolution inside a function
# body, so the DSL object is an explicit parameter and the receiver stays
# visible as `dsl.`.
def define_tools(dsl):
    @dsl.tool(
        "read_file",
        description="Read the contents of a file from disk",
        parameters={"path": {"type": "string", "description": "The file path to read"}},
    )
    def read_file(path):
        return (base_dir / path).read_text()

    @dsl.tool(
        "list_directory",
        description="List the files in a directory",
        parameters={
            "path": {"type": "string", "description": "The directory path to list"}
        },
    )
    def list_directory(path):
        return ", ".join(
            f for f in os.listdir(base_dir / path) if not f.startswith(".")
        )


result = boukensha.run(
    task="Read the README.md file and summarise what this MUD player assistant framework can do.",
    tools=define_tools,
)

print()
print("=== FINAL RESPONSE ===")
print(result)
