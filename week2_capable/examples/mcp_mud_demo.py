#!/usr/bin/env python3
"""Step 10 — the MUD tools, over MCP.

Ruby's step 10 registers 26 MUD tools by hand: `tools/mud.rb` is 480 lines
driving a MudManager::Session in-process. **Python has no equivalent.** It
spawns `mud-manager --mcp` and asks what tools it has.

That is not a shortcut around the port — it is the reason the daemon exists.
Nothing in this file, or in boukensha, knows what a MUD is.

    python examples/mcp_mud_demo.py --dry    # no API calls, no billing
    python examples/mcp_mud_demo.py          # real agent run (billable)

By default it boots the Ruby FakeMud on a random port so the demo runs with no
MUD installed. Set MUD_HOST/MUD_PORT/MUD_NAME/MUD_PASSWORD to use a real one.
"""
import os
import subprocess
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
from boukensha.tools import mcp as tools_mcp  # noqa: E402

DRY = "--dry" in sys.argv

# week2_capable/examples/ -> week2_capable -> repo root. Was parents[4] while
# this tree lived at week1_baseline/python/12_context/examples/.
REPO_ROOT = Path(__file__).resolve().parents[2]
DAEMON = REPO_ROOT / "week0_explore" / "mud_manager" / "bin" / "mud-manager"
FAKE_MUD_LIB = REPO_ROOT / "week0_explore" / "mud_manager" / "lib"

if not DAEMON.exists():
    sys.exit(f"daemon not found at {DAEMON}")

# ── A MUD to talk to ────────────────────────────────────────────────────────
fake = None
if not os.environ.get("MUD_HOST"):
    fake = subprocess.Popen(
        [
            "ruby", "-I", str(FAKE_MUD_LIB), "-e",
            "require 'mud_manager'; require 'mud_manager/fake_mud'; "
            "m = MudManager::FakeMud.new(password: 'swordfish').start; "
            "puts m.port; $stdout.flush; sleep",
        ],
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    port = fake.stdout.readline().strip()
    os.environ.update(
        MUD_HOST="127.0.0.1", MUD_PORT=port, MUD_NAME="Gandalf", MUD_PASSWORD="swordfish"
    )
    print(f"Started FakeMud on 127.0.0.1:{port}")

mcp = {
    "command": "ruby",
    "args": [str(DAEMON), "--mcp"],
    # Named after the MUD engine, not the config key. Applied client-side —
    # the daemon still advertises bare `look` on the wire.
    "prefix": boukensha.MUD_PREFIX,
    "env": {k: os.environ[k] for k in ("MUD_HOST", "MUD_PORT", "MUD_NAME", "MUD_PASSWORD")},
}

try:
    if DRY:
        # Register into a throwaway context so the tool surface is visible
        # without touching a model. This is the part of the feature that does
        # not depend on the non-deterministic dependency, so it is the part
        # worth gating on.
        ctx = boukensha.Context(task=boukensha.Player, system="")
        registry = boukensha.Registry(ctx)

        client = tools_mcp.register(registry, **mcp)

        print(f"Daemon:  {client.server_info.get('name')} {client.server_info.get('version')}")
        print(f"Tools:   {len(ctx.tools)}")
        print()
        names = list(ctx.tools)
        for i in range(0, len(names), 6):
            print("  " + ", ".join(names[i:i + 6]))
        print()

        p = boukensha.MUD_PREFIX
        look = registry.dispatch(f"{p}__look", {}).splitlines()
        move = registry.dispatch(f"{p}__move", {"direction": "north"}).splitlines()
        bad = registry.dispatch(f"{p}__move", {"direction": "widdershins"}).strip()
        print(f"{p}__look -> {look[0].strip() if look else ''}")
        print(f"{p}__move -> {move[0].strip() if move else ''}")
        print(f"bad arg   -> {bad}")

        client.close()
        print()
        print(f"[dry run OK — {len(ctx.tools)} tools over MCP, no API calls made]")
    else:
        print(
            boukensha.run(
                task="Look at your surroundings, check your score, then tell me what you see.",
                working_dir=False,  # no filesystem tools
                mcp=mcp,
            )
        )
finally:
    if fake:
        fake.terminate()
        try:
            fake.wait(timeout=5)
        except subprocess.TimeoutExpired:
            fake.kill()
        if fake.stdout:
            fake.stdout.close()
