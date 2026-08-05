"""The whole pipeline in one command — built to be screen-recorded.

    python examples/demo.py --offline    # rehearse: no API calls, no billing
    python examples/demo.py              # the real thing, ~15c

Four acts, in the order the architecture runs:

    1. PLAY     the agent explores the live MUD, one command at a time
    2. CAPTURE  what the session file recorded
    3. ANALYSE  journey events, and where players get blocked
    4. MAP      the world graph

`--offline` skips act 1 and analyses the sessions already on disk. Use it to get
the pacing right before spending anything — the recording is one take, and the
paid run should not be the rehearsal.

Cost is bounded by --iterations (default 12), because that ceiling is what
decides the bill: every call re-sends the whole conversation, so cost grows
faster than the iteration count does.
"""

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]

sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import boukensha  # noqa: E402
from boukensha import world  # noqa: E402
from world_map import load_sessions  # noqa: E402

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
CYAN, GREEN, YELLOW, RED = "\033[36m", "\033[32m", "\033[33m", "\033[31m"

GOAL = (
    "Explore and map as much as you can reach from where you start. Prefer "
    "rooms you have not seen. Report anything that would confuse or block a "
    "new player."
)


_act_number = 0


def act(title, pause):
    """Numbered as they run, so --offline does not open on act 3."""
    global _act_number
    _act_number += 1
    print()
    print(f"{BOLD}{CYAN}{'─' * 66}{RESET}")
    print(f"{BOLD}{CYAN}  {_act_number}. {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * 66}{RESET}")
    time.sleep(pause)


def run_script(name, *args):
    """Child scripts rather than imported functions, so what the recording
    shows is exactly what a person would type."""
    return subprocess.run(
        [sys.executable, str(HERE / name), *args],
        cwd=HERE.parent,
        capture_output=True,
        text=True,
    ).stdout


def preflight():
    """Fail before the recording starts rather than during it.

    The MUD accepting a connection is not enough — on 05-08 it accepted
    connections for two hours while a leaked agent process hammered it, and
    never greeted anybody. The greeting is the real check.
    """
    print(f"{DIM}checking the MUD is up and greeting...{RESET}")
    try:
        sock = socket.create_connection(("localhost", 4000), timeout=10)
        sock.settimeout(10)
        greeting = sock.recv(4096)
        sock.close()
    except OSError as e:
        sys.exit(
            f"{RED}MUD not reachable on :4000 ({e}).{RESET}\n"
            f"  cd {REPO_ROOT}/week0_explore/infrastructure && docker compose up -d"
        )

    if not greeting:
        sys.exit(
            f"{RED}MUD accepted the connection but sent no greeting.{RESET}\n"
            "  Usually a leaked agent process flooding it — check: pgrep -af boukensha"
        )
    print(f"{GREEN}  MUD is up.{RESET}")


def play(iterations, pause):
    act("PLAY — the agent explores the live MUD", pause)
    spent = {"usd": 0.0, "moves": 0}

    def on_event(event):
        phase = event.get("phase")
        if phase == "tool_call":
            args = event.get("args") or {}
            detail = ", ".join(f"{k}={v}" for k, v in args.items())
            spent["moves"] += 1
            print(f"  {DIM}{spent['moves']:>3}{RESET} {event['name']}({detail})")
        elif phase == "response" and event.get("cost_usd"):
            spent["usd"] += event["cost_usd"]
        elif phase == "limit_reached":
            print(f"  {YELLOW}** {event['kind']} reached at {event['n']}{RESET}")
        elif phase == "compaction":
            print(f"  {YELLOW}** compaction: dropped {event['dropped']} messages{RESET}")
        elif phase == "session_end":
            print()
            print(
                f"  {GREEN}session ended: {event['reason']} · "
                f"{event['total_tokens']} tokens · "
                f"${event['total_cost_usd']} · {event['duration_s']}s{RESET}"
            )

    boukensha.run(
        task=GOAL,
        working_dir=False,  # MUD tools only
        mcp=True,
        on_event=on_event,
        max_iterations=iterations,
    )


def capture(pause):
    act("CAPTURE — what the session recorded", pause)
    sessions = sorted(
        (Path(os.environ.get("BOUKENSHA_DIR") or REPO_ROOT / ".boukensha") / "sessions")
        .glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
    )
    latest = sessions[-1]
    lines = latest.read_text(errors="replace").splitlines()
    print(f"  {latest.name}")
    print(f"  {len(lines)} events, {latest.stat().st_size:,} bytes")
    print()
    print(f"{DIM}  every tool call, its result, and what it cost — one JSON object per line{RESET}")
    for line in lines[:2]:
        print(f"{DIM}  {line[:100]}...{RESET}")
    time.sleep(pause)


def analyse(pause):
    act("ANALYSE — journey events and where players get blocked", pause)
    output = run_script("ingest_sessions.py")
    keep = False
    for line in output.splitlines():
        if line.startswith("ingested"):
            print(f"  {line}")
        if line.startswith("=== journey") or line.startswith("=== why players"):
            keep = True
            print(f"\n{BOLD}  {line.strip('= ')}{RESET}")
            continue
        if line.startswith("==="):
            keep = False
        if keep and line.strip():
            print(f"  {line}")
    time.sleep(pause)


def finding(pause):
    """The payoff: name the worst room, not just count the blocks.

    The ingest's own report groups blocks by reason and direction, which shows
    the *shape* of the problem. The room they happen in is what QnA can act on,
    and it only exists once the graph has attached each block to the room the
    player was standing in when they hit it.
    """
    act("FINDING — where the journey actually stops", pause)

    graph = world.build(load_sessions())
    by_room = {}
    for block in graph["blocked"]:
        entry = by_room.setdefault(
            block["room"], {"dirs": set(), "reasons": set(), "n": 0}
        )
        entry["n"] += 1
        entry["dirs"].add(block["direction"] or "?")
        entry["reasons"].add(block["reason"])

    if not by_room:
        print("  no blocks recorded yet")
        time.sleep(pause)
        return

    ranked = sorted(by_room.items(), key=lambda kv: -kv[1]["n"])
    for node, info in ranked:
        title = graph["rooms"].get(node, {}).get("title", node)
        exits = graph["rooms"].get(node, {}).get("exits", [])
        walled = len(info["dirs"]) >= max(1, len(exits))
        mark = f"{RED}{BOLD}" if walled else YELLOW
        print(
            f"  {mark}{title}{RESET} — {info['n']} block(s) "
            f"{DIM}[{', '.join(sorted(info['dirs']))}]{RESET} "
            f"{', '.join(sorted(info['reasons']))}"
        )
        if walled:
            print(
                f"    {RED}every advertised exit refused — a player who reaches "
                f"this room can only go back{RESET}"
            )
    time.sleep(pause)


def show_map(pause):
    act("MAP — the world graph", pause)
    for line in run_script("world_map.py").splitlines():
        print(f"  {line}")
    print()
    print(f"{DIM}  Mermaid — renders on GitHub with no toolchain{RESET}")
    time.sleep(pause)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="skip the live run")
    parser.add_argument("--iterations", type=int, default=12)
    parser.add_argument("--pause", type=float, default=1.2, help="seconds between acts")
    args = parser.parse_args()

    print()
    print(f"{BOLD}  Player Journey Agent — Arcane Loop{RESET}")
    print(f"{DIM}  plays a MUD, maps the world, reports where players get stuck{RESET}")

    if args.offline:
        print(f"\n{YELLOW}  [offline — analysing existing sessions, no API calls]{RESET}")
    else:
        preflight()
        play(args.iterations, args.pause)
        capture(args.pause)

    analyse(args.pause)
    finding(args.pause)
    show_map(args.pause)

    print()
    print(f"{GREEN}{BOLD}  done{RESET} — map: docs/maps/world.md")
    print()


if __name__ == "__main__":
    main()
