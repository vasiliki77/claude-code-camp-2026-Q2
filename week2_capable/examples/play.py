"""Interactive session against the live MUD — the app, driven by hand.

    python examples/play.py              # Textual TUI
    python examples/play.py --no-tui     # plain terminal REPL

Then type goals at the prompt, one per turn:

    > look around and tell me where I am
    > go north and describe what you find
    > /compact
    > exit

Billable per turn, and history accumulates across turns — so a long session
costs more per turn than a short one, because every call re-sends the whole
conversation. `/compact` drops the oldest messages when it gets heavy.

**This is also the only path on which compaction can currently fire**, because
the check runs once per turn at turn start (see docs/plans/observability/layer1
§1.6.1). A one-shot run has exactly one turn boundary, at the beginning, when
there is nothing to compact.

Sister scripts, none of them interactive:

    demo.py         the whole pipeline, five acts, --offline to rehearse free
    mapping_run.py  one long unattended exploration (~$1 at 80 iterations)
    example.py      local file/shell tools, no MUD
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Default the config dir to this repo's .boukensha when the caller has not set
# one. Without this, forgetting `export BOUKENSHA_DIR=...` sends Config looking
# in ~/.boukensha, and the error names a path nobody chose. The week-1 launchers
# did the same with `: "${BOUKENSHA_DIR:=...}"`; week2_capable has no launcher,
# so the scripts carry it themselves.
os.environ.setdefault(
    "BOUKENSHA_DIR", str(Path(__file__).resolve().parents[2] / ".boukensha")
)

import boukensha  # noqa: E402

print("Connecting to the MUD over MCP — this spawns mud-manager as a subprocess.")
print("Type a goal, or 'exit' to quit. Ctrl-C ends the session cleanly.\n")

boukensha.repl(
    working_dir=False,  # MUD tools only — no filesystem or shell tools
    mcp=True,  # the mud: entry from settings.yaml, real credentials
    tui="--no-tui" not in sys.argv,
)
