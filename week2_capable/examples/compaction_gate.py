"""Fire compaction for the first time, deliberately and cheaply.

`limit_reached` and `compaction` are both implemented and, across 63 recorded
sessions, `compaction` has never once executed (layer1 §1.6). This closes that
gate.

    python examples/compaction_gate.py

Costs a few cents: two short turns, three iterations each.

## Why the 05-08 mapping run did not fire it

Two independent reasons, and the second is the one that matters:

  1. Context peaked at 20,568 tokens — 0.103 of the 200k window — against a
     0.15 trigger. It did not reach the threshold.
  2. `Agent.run` calls `_compact_if_needed()` at agent.py:63, *before* the
     `while True` loop. Compaction is evaluated **once per turn, at turn
     start**, when a one-shot run's context is still empty. A single-turn run
     therefore cannot compact no matter how large it grows or how low the
     threshold is set.

That second point is a live limitation rather than a quirk: a mapping run is
one long turn, so its context only grows. A long enough one reaches the context
window and fails instead of compacting.

## How this fires it

Two turns on one context. Turn 1 leaves ~4-5k tokens behind (the system prompt
and 26 MUD tool definitions alone are ~4.1k), and turn 2's start-of-turn check
sees them.

The threshold is overridden on the context object rather than in settings.yaml,
so there is no config left in a dangerous state if this script is interrupted.
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

from boukensha.agent import Agent  # noqa: E402
from boukensha.run import _build_session, _close_mcp_clients  # noqa: E402

# 0.003 of a 200k window = 600 tokens.
#
# The first attempt used 0.02 (4,000 tokens) on the reasoning that the system
# prompt plus 26 tool definitions is ~4.1k. It did not fire, for a reason worth
# keeping: a turn that hits max_iterations ends with `wrap_up`, which calls the
# model with **tools disabled**. That last call's input_tokens therefore
# excludes every tool definition, and record_usage writes it straight into
# current_tokens — so the context-pressure reading *collapses* immediately
# after a turn that hit its ceiling. Turn 1 reported 928 tokens rather than the
# ~4.5k actually in play, and turn 2's start-of-turn check saw 928.
#
# The effect is perverse: compaction is least likely to fire right after the
# turns that worked hardest.
THRESHOLD = 0.003
TURNS = [
    "Look at your surroundings.",
    "Check your score, then say how you feel.",
    "Look again and tell me one thing you notice.",
]

session = None
fired = False
try:
    session = _build_session(
        system=None,
        model=None,
        backend=None,
        api_key=None,
        ollama_host=None,
        log=None,
        context_window=None,
        max_output_tokens=None,
        tools=None,
        working_dir=False,  # MUD tools only
        allowed_commands=None,
        shell_timeout=30,
        mcp=True,
    )

    def watch(event):
        global fired
        phase = event.get("phase")
        if phase == "compaction":
            fired = True
            print(f"  ** COMPACTION: {event}", flush=True)
        elif phase == "tool_call":
            print(f"  -> {event['name']}", flush=True)

    session.logger.subscribe(watch)
    session.context.compaction_threshold = THRESHOLD

    for n, task in enumerate(TURNS, start=1):
        print(f"\n--- turn {n}: {task}")
        session.logger.turn(n=n)
        session.context.add_message("user", task)
        agent = Agent(
            context=session.context,
            registry=session.registry,
            builder=session.builder,
            client=session.client,
            logger=session.logger,
            task_settings=session.task_settings,
            max_iterations=3,  # keep each turn short and cheap
            max_turn_tokens=session.max_turn_tokens,
            max_output_tokens=session.max_output_tokens,
        )
        agent.run()
        frac = session.context.usage_fraction()
        print(f"    context now {session.context.current_tokens} tokens ({frac:.3f})")

finally:
    if session:
        session.logger.close(reason="completed")
        _close_mcp_clients(session.mcp_clients)

print()
print(f"GATE: compaction fired = {fired} (want True)")
print(f"session: {session.logger.path if session else 'not built'}")
