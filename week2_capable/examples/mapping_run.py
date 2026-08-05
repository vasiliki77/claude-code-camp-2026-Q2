"""A real mapping run against the live MUD — the Layer 2 corpus.

Unlike examples/mcp_mud_demo.py this spawns no fake MUD and hardcodes no task:
it connects to whatever `mud:` in settings.yaml points at, which is the live
CircleMUD on :4000.

    python examples/mapping_run.py                 # default mapping goal
    python examples/mapping_run.py "your goal"     # something else

Billable. The ceilings that bound it live in settings.yaml under tasks.player —
max_iterations is the one that decides how long (and how expensive) this gets.

What the run is for, in order of importance:

  1. The corpus. Raw MUD text lands in `tool_result` events whether or not
     journey-event emission exists yet, so the parsers for Layer 2 can be
     written and tested against this file offline, without paying for a
     second run.
  2. Layer 1 in anger. session_end, the truthful ok flag and the trimmed
     prompt payload have been unit-tested and gated against the daemon, but no
     real session has been through them.
  3. Room identity (obs_plan.md §4.2) — the open modelling decision, best made
     by looking at real room names and exit lists rather than reasoning about
     hypothetical duplicate corridors.
  4. Compaction. With compaction_threshold lowered it should fire for the first
     time in any recorded session.

working_dir=False registers no filesystem tools: the agent gets the 26 MUD
tools and nothing else, so every tool call in the log is a MUD command. That
keeps the corpus clean and stops the agent from wandering off to read files
when the MUD frustrates it.
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

DEFAULT_GOAL = (
    "Explore and map as much of the world as you can reach from where you "
    "start. Visit new rooms in preference to ones you have already seen, and "
    "keep going until you run out of moves. As you go, report anything that "
    "would confuse, block, bore or overpower a new player."
)

goal = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GOAL


def progress(event):
    """One line per tool call, plus a running cost.

    Without this the run prints nothing between launch and its final answer.
    The 05-08 run was 166 silent seconds spending a dollar, which is
    indistinguishable from a wedged daemon while it is happening.
    """
    phase = event.get("phase")
    if phase == "tool_call":
        args = ", ".join(f"{k}={v!r}" for k, v in (event.get("args") or {}).items())
        print(f"  -> {event['name']}({args})", flush=True)
    elif phase == "response" and event.get("cost_usd"):
        progress.spent += event["cost_usd"]
        print(f"     [${progress.spent:.3f}]", flush=True)
    elif phase in ("limit_reached", "compaction"):
        print(f"  ** {phase}: {event}", flush=True)
    elif phase == "session_end":
        print(
            f"\n[{event['reason']}] {event['turns']} turn(s), "
            f"{event['total_tokens']} tokens, ${event['total_cost_usd']}, "
            f"{event['duration_s']}s",
            flush=True,
        )


progress.spent = 0.0

print(f"goal: {goal}\n")
print(
    boukensha.run(
        task=goal,
        working_dir=False,  # MUD tools only — no filesystem tools
        mcp=True,  # the mud: entry from settings.yaml, real credentials
        on_event=progress,  # otherwise this runs silently for minutes
    )
)
