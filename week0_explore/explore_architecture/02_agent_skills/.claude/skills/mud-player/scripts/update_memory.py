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
LOCATION_RE = re.compile(r"^([A-Z][^\n]*?)(?:\n|$)")  # Room name (first line of look)
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
    """Extract HP, mana, moves from prompt."""
    m = PROMPT_RE.search(text)
    if m:
        return {"hp": int(m.group(1)), "mana": int(m.group(2)), "moves": int(m.group(3))}
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
    """Extract current room name from look output."""
    lines = text.strip().split("\n")
    # Room name is usually first non-empty line after "look" that's not a description
    for i, line in enumerate(lines):
        line = line.strip()
        if line and len(line) > 5 and not line.startswith("["):
            # Skip status lines and prompts
            if not any(x in line for x in ["H ", "M ", "V ", ">"]):
                return line
    return None


def update_player_md(player_md_path, vitals=None, level=None, exp=None, location=None):
    """Update player.md with current state."""
    if not os.path.exists(player_md_path):
        print(f"player.md not found at {player_md_path}", file=sys.stderr)
        return False

    with open(player_md_path) as f:
        content = f.read()

    # Update vitals if found
    if vitals:
        content = re.sub(
            r"- \*\*HP\*\*: \d+ / \d+",
            f"- **HP**: {vitals['hp']} / 22",
            content
        )
        content = re.sub(
            r"- \*\*Mana\*\*: \d+ / \d+",
            f"- **Mana**: {vitals['mana']} / 100",
            content
        )
        content = re.sub(
            r"- \*\*Moves\*\*: \d+ / \d+",
            f"- **Moves**: {vitals['moves']} / 83",
            content
        )

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
