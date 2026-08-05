"""Layer 2: turning MUD replies into player-journey events.

See docs/plans/observability/obs_plan.md §3. Layer 1 answers "is the agent
working"; this answers the question Arcane Loop is actually paying for — where
a player gets confused, blocked, bored or overpowered.

Pure functions over text. Nothing here does I/O, spawns anything, or knows what
a session is, so the same parser runs live from tools/mcp.py and offline over
archived .jsonl. That is deliberate: the parsers were developed against the
05-08 mapping corpus (81 tool calls, 34 rooms) rather than against guesses, and
they stay re-runnable over it.

## What the MUD actually sends

A successful move:

    Behind The Temple Altar\r\n
       You are on a dirt path leading away from the Temple Altar which is south\r\n
    of here.  To the north, the path continues ...\r\n
    [ Exits: n s ]\r\n
    \r\n
    22H 100M 81V (news) (motd) >

A refused one:

    The door seems to be closed.\r\n\r\n22H 100M 76V (news) (motd) >

Three things follow, and each was checked against the corpus rather than
assumed:

  - **The exit line is what identifies a room**, not the shape of the first
    line. Guessing from punctuation misfiles `You are 18 years old.` (a score
    readout) and anything whose title happens to end in a full stop.
  - **The direction of a blocked move is not in the reply.** "The door seems to
    be closed." never says which door. It has to come from the tool call's
    arguments, which is why parse() takes them.
  - **The prompt line carries vitals** — `22H 100M 83V` is hit/mana/movement.
    Free progression and combat-risk signal on every single reply.
"""

import re

# Colour codes wrap room titles; every pattern below assumes they are gone.
ANSI = re.compile(r"\x1b\[[0-9;]*m")

# The trailing status prompt, e.g. "22H 100M 83V (news) (motd) > ".
PROMPT = re.compile(r"(?P<hp>\d+)H (?P<mana>\d+)M (?P<mv>\d+)V[^>]*>\s*$")

# "[ Exits: n e s w d ]" — 19 distinct variants across the corpus, all this
# shape. Its presence is the room discriminator.
EXITS = re.compile(r"^\[ Exits:(?P<exits>[^\]]*)\]\s*$", re.MULTILINE)

# A move the game refused. `reason` is what makes these useful to QnA: a closed
# door is a puzzle, a level gate is a progression wall, and they are different
# findings.
BLOCKED = [
    (re.compile(r"^The door seems to be closed\.", re.I), "closed_door"),
    (re.compile(r"^Alas, you cannot go that way\.", re.I), "no_exit"),
    (re.compile(r"^This zone is above your recommended level\.", re.I), "level_gated"),
    (re.compile(r"^You (?:are too exhausted|do not have enough movement)", re.I), "exhausted"),
]

# An unlit room. The move *succeeded* — the player is somewhere new — but the
# game says only "It is pitch black...": no name, no exits, nothing to map.
#
# Worth its own pattern rather than falling through as unparsed, because
# dropping it loses the node *and* the edge that reached it, leaving a hole in
# the graph that looks like the agent never moved. It is also a journey signal
# in its own right: a new player with no light source, in a room that will not
# describe itself, is exactly the "confused and stuck" moment the brief asks
# about.
DARK = re.compile(r"^It is pitch black\.\.\.", re.I)

# A command the game did not understand or could not apply. These are the
# confusion signal — a real player types something reasonable and gets nothing
# back that tells them what to do instead.
REJECTED = [
    re.compile(r"^Huh\?!\?", re.I),
    re.compile(r"^You do not see that here\.", re.I),
    re.compile(r"^Nothing here by that name\.", re.I),
    re.compile(r"^They aren't here\.", re.I),
]


def strip_ansi(text):
    return ANSI.sub("", text or "")


def split_prompt(text):
    """(body, vitals) — the reply without its trailing status prompt.

    vitals is {"hp":…, "mana":…, "movement":…} or None. Every reply ends with
    the prompt, so this is the cheapest progression signal available and it
    costs nothing extra to collect.
    """
    text = strip_ansi(text).replace("\r\n", "\n").strip()
    match = PROMPT.search(text)
    if not match:
        return text, None

    vitals = {
        "hp": int(match.group("hp")),
        "mana": int(match.group("mana")),
        "movement": int(match.group("mv")),
    }
    return text[: match.start()].strip(), vitals


def parse_room(body):
    """(name, exits, doors) for a room description, or (None, None, None).

    A room is a reply carrying an exit line; its name is the first line. Rooms
    with no exits at all do not occur in the corpus, and would be unmappable
    anyway — a node with no edges is not a place a journey passes through.

    **Exits are normalized and doors reported separately.** CircleMUD wraps a
    closed-door exit in parentheses — `[ Exits: n (e) s ]` — and the corpus has
    9 of them. Carrying the parentheses through was wrong twice over: the
    coverage check compared `(e)` against `e` and so reported every door as an
    exit never taken, and room identity keys on the exit set, so a door that is
    shut on one visit and open on the next would split one room into two nodes.
    No collision in this corpus, but only by luck.

    The door itself is worth keeping — a closed door is where a player is about
    to be blocked — so it comes back as its own list rather than being discarded.
    """
    match = EXITS.search(body)
    if not match:
        return None, None, None

    lines = [line for line in body.split("\n") if line.strip()]
    if not lines:
        return None, None, None

    raw = [d for d in match.group("exits").split() if d]
    exits = [d.strip("()") for d in raw]
    doors = [d.strip("()") for d in raw if d.startswith("(")]
    return lines[0].strip(), exits, doors


def parse(name, args, result):
    """Journey events for one tool call. A list, because one reply can carry
    more than one signal, and empty when it carries none.

    `name` may be prefixed (tbamud__move) or bare (move); both are accepted, so
    the parser does not care how the MCP server was registered.

    Events carry no session_id/turn/iteration — the caller owns correlation.
    Keeping that out of here is what lets the same function run offline over an
    archived session, where those values come from the file rather than from a
    live logger.
    """
    args = args or {}
    command = str(name or "").split("__")[-1]
    body, vitals = split_prompt(result)
    if not body:
        return []

    events = []

    for pattern, reason in BLOCKED:
        if pattern.search(body):
            events.append(
                {
                    "event": "movement_blocked" if command == "move" else "command_rejected",
                    "command": command,
                    # The reply never names the direction; the call does.
                    "direction": args.get("direction"),
                    "reason": reason,
                    "text": body.split("\n")[0].strip(),
                    "vitals": vitals,
                }
            )
            return events

    for pattern in REJECTED:
        if pattern.search(body):
            events.append(
                {
                    "event": "command_rejected",
                    "command": command,
                    "target": args.get("target"),
                    "text": body.split("\n")[0].strip(),
                    "vitals": vitals,
                }
            )
            return events

    # Checked before parse_room, which needs an exit line a dark room never has.
    # room is None rather than a placeholder: every dark room would otherwise
    # collapse into one node and invent edges between unrelated places. Identity
    # here waits on obs_plan.md §4.2 like every other room's does.
    if DARK.search(body):
        events.append(
            {
                "event": "room_entered",
                "command": command,
                "room": None,
                "exits": [],
                "dark": True,
                "direction": args.get("direction"),
                "vitals": vitals,
            }
        )
        return events

    room, exits, doors = parse_room(body)
    if room:
        events.append(
            {
                "event": "room_entered",
                "command": command,
                "room": room,
                "exits": exits,
                # Closed doors, as a subset of exits. Where a player is about to
                # be blocked, visible before they try it.
                "doors": doors,
                # How the player got here. The graph needs the edge, not just
                # the node, and only the call knows which way we came.
                "direction": args.get("direction"),
                "vitals": vitals,
            }
        )

    return events
