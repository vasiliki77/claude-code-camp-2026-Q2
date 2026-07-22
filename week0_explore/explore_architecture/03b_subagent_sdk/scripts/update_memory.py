#!/usr/bin/env python3
"""
update_memory.py - Parse recent game output and update player.md with current state.

Usage: python3 update_memory.py [--state-dir DIR]

Reads the most recent lines from transcript.log, extracts key facts (HP, mana, moves,
location, level), and updates data/player.md with current state. This keeps the
memory file in sync with the actual character state, so future sessions can reference
it for decision-making.

This is a simple educational example showing how agents can maintain persistent state
by parsing output and updating markdown files.
"""

import argparse
import os
import re
import sys
from pathlib import Path

# MUD-specific patterns
PROMPT_RE = re.compile(r"(\d+)H\s+(\d+)M\s+(\d+)V")  # 22H 100M 83V
# The prompt line carries the room name after the final ">": "22H 100M 83V > The Dump"
PROMPT_ROOM_RE = re.compile(r"\d+H\s+\d+M\s+\d+V\b.*>\s*(\S.*?)\s*$")
LEVEL_RE = re.compile(r"This ranks you as .+ \(level (\d+)\)")
EXP_RE = re.compile(r"You have (\d+) exp")
NEXT_LEVEL_RE = re.compile(r"You need (\d+) exp to reach your next level")


def read_transcript(transcript_path, lines=100):
    """Read the last N lines of the transcript."""
    if not os.path.exists(transcript_path):
        return ""
    with open(transcript_path) as f:
        all_lines = f.readlines()
    return "".join(all_lines[-lines:])


def extract_vitals(text):
    """Extract HP, mana, moves from the most recent prompt."""
    matches = PROMPT_RE.findall(text)
    if matches:
        hp, mana, moves = matches[-1]
        return {"hp": int(hp), "mana": int(mana), "moves": int(moves)}
    return None


def extract_level(text):
    """Extract character level from score output."""
    m = LEVEL_RE.search(text)
    return int(m.group(1)) if m else None


def extract_exp(text):
    """Extract current and next-level experience."""
    exp_m = EXP_RE.search(text)
    next_m = NEXT_LEVEL_RE.search(text)
    current = int(exp_m.group(1)) if exp_m else None
    needed = int(next_m.group(1)) if next_m else None
    return current, needed


def extract_location(text):
    """Extract the most recent room name.

    With autoexits on, a room block ends at the `[ Exits: ... ]` line, and the
    name sits on the prompt line that opened the block. So find the last exits
    line and walk back to the prompt above it — anything in between is room
    description, which is why matching on line shape alone picks up prose.
    """
    lines = text.strip().split("\n")
    exits = [i for i, l in enumerate(lines) if l.strip().startswith("[ Exits:")]
    if not exits:
        return None
    for i in range(exits[-1] - 1, -1, -1):
        if lines[i].strip().startswith("[ Exits:"):
            break  # ran into the previous block without finding a prompt
        m = PROMPT_ROOM_RE.search(lines[i])
        if m:
            return m.group(1)
    return None


def update_player_md(player_md_path, vitals=None, level=None, exp=None, location=None):
    """Update player.md with current state."""
    if not os.path.exists(player_md_path):
        print(f"player.md not found at {player_md_path}", file=sys.stderr)
        return False

    with open(player_md_path) as f:
        content = f.read()

    # Update vitals if found. The prompt only reports current values, so the
    # maximum already in the file is kept — a level-up raises it, and only
    # `score` (edited in by hand) knows the new number.
    if vitals:
        for field, current in (
            ("HP", vitals["hp"]),
            ("Mana", vitals["mana"]),
            ("Moves", vitals["moves"]),
        ):
            pattern = r"- \*\*%s\*\*: (\d+) / (\d+)" % field

            def replace(m, current=current, field=field):
                maximum = max(int(m.group(2)), current)
                return f"- **{field}**: {current} / {maximum}"

            content = re.sub(pattern, replace, content)

    # Update level if found
    if level:
        content = re.sub(
            r"- \*\*Level\*\*: \d+",
            f"- **Level**: {level}",
            content
        )

    # Update experience if found
    if exp and exp[0] is not None:
        needed = exp[1] if exp[1] else "???"
        content = re.sub(
            r"- \*\*Experience\*\*: \d+ / \d+",
            f"- **Experience**: {exp[0]} / {needed}",
            content
        )

    # Update location if found
    if location:
        content = re.sub(
            r"- \*\*Current Room\*\*: [^\n]+",
            f"- **Current Room**: {location}",
            content
        )

    with open(player_md_path, "w") as f:
        f.write(content)

    return True


def main():
    ap = argparse.ArgumentParser(
        description="Update player.md memory from recent game output"
    )
    ap.add_argument(
        "--state-dir",
        default=os.path.expanduser("~/.mud-player/localhost-4000"),
        help="MUD session state directory (default: ~/.mud-player/localhost-4000)"
    )
    args = ap.parse_args()

    transcript_path = os.path.join(args.state_dir, "transcript.log")
    player_md_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "data",
        "player.md"
    )

    # Read recent transcript
    text = read_transcript(transcript_path, lines=200)
    if not text:
        print("no transcript found", file=sys.stderr)
        return 1

    # Extract facts
    vitals = extract_vitals(text)
    level = extract_level(text)
    exp = extract_exp(text)
    location = extract_location(text)

    # Report what was found
    print("Extracted from transcript:")
    if vitals:
        print(f"  vitals: {vitals['hp']}H {vitals['mana']}M {vitals['moves']}V")
    if level:
        print(f"  level: {level}")
    if exp[0] is not None:
        print(f"  experience: {exp[0]} / {exp[1]}")
    if location:
        print(f"  location: {location}")

    # Update player.md
    if update_player_md(player_md_path, vitals, level, exp, location):
        print(f"updated {player_md_path}")
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
