"""Layer 3: the world graph.

See docs/plans/observability/obs_plan.md §3. Rooms are nodes, movements are
edges, and the blocks a player hit are attached to the room they hit them from.
This is both the "map the world" deliverable and the substrate the blocked and
bored analyses run over.

Pure functions over journey events, like journey.py — nothing here reads a file
or a database, so the same builder runs over a live stream or over sessions.db.

## Room identity (obs_plan.md §4.2), settled by measurement

A room is identified by **(title, sorted exits)**, not by title alone. The
corpus is unambiguous about why: 72 room entries carry 32 distinct titles but
**36 distinct (title, exits) pairs**. Three titles cover more than one room —

    The Great Field Of Midgaard      exits ns   and ensw
    Wall Road                        exits ens  and ns
    A Shaded Path Through The Forest exits esw, sw and ns

— so keying on the title alone silently merges four rooms into three, and every
edge into or out of them becomes a lie. CircleMUD reuses titles across the
segments of a road or field; that is normal MUD authoring, not a quirk of this
world.

**The residual is real and worth stating**: two genuinely distinct rooms sharing
both a title and an exit set still merge. Distinguishing those needs the path
taken to reach them, which is a bigger change than this week's scope allows.
The corpus shows no such collision, but a larger map will have them.

## Dark rooms

`It is pitch black...` gives no title and no exits, so a dark room cannot be
identified by content at all. It is keyed by how it was entered — the room it
was entered *from*, plus the direction — which is unique per entrance and
therefore correct for the edge, if not necessarily for the node. Two entrances
to one dark room appear as two nodes. That is visible in the map as a labelled
guess rather than hidden as a silent merge.
"""


def room_id(room, exits):
    """Stable identity for a room. See the module docstring."""
    return f"{room}|{','.join(sorted(exits or []))}"


def dark_id(from_id, direction):
    return f"(dark) via {direction or '?'} from {from_id.split('|')[0]}"


def build(sessions):
    """Fold journey events into a graph.

    `sessions` is an iterable of iterables: one sequence of journey-event dicts
    per session, in the order they occurred. Sessions are kept separate because
    the "where am I" cursor cannot carry across a session boundary — the agent
    reconnects at the MUD's start room, not where it left off.

    Returns {"rooms": {...}, "edges": {...}, "blocked": [...]}.
    """
    rooms = {}
    edges = {}
    blocked = []

    for events in sessions:
        current = None

        for event in events:
            kind = event.get("event")

            if kind == "movement_blocked":
                # Attached to the room the player was standing in. A block with
                # no known origin is unattributable, so it is dropped rather
                # than guessed at.
                if current:
                    blocked.append(
                        {
                            "room": current,
                            "direction": event.get("direction"),
                            "reason": event.get("reason"),
                        }
                    )
                continue

            if kind != "room_entered":
                continue

            if event.get("dark"):
                node = dark_id(current, event.get("direction")) if current else "(dark)"
                exits = []
            else:
                node = room_id(event["room"], event.get("exits"))
                exits = event.get("exits") or []

            entry = rooms.setdefault(
                node,
                {
                    "title": event.get("room") or "(dark room)",
                    "exits": exits,
                    "visits": 0,
                    "dark": bool(event.get("dark")),
                },
            )
            entry["visits"] += 1

            direction = event.get("direction")
            # Only a move creates an edge. `look` re-describes the room the
            # player is already standing in, and treating that as a movement
            # would invent a self-loop for every glance around.
            if current and direction and event.get("command") == "move":
                edges.setdefault((current, node, direction), 0)
                edges[(current, node, direction)] += 1

            current = node

    return {"rooms": rooms, "edges": edges, "blocked": blocked}


def unexplored(graph):
    """Exits a room advertises that were never taken, per room.

    The gap between what the game offers and where the agent went — which is
    both a coverage measure for the map and the first place to look when asking
    whether a region is genuinely unreachable or merely unvisited.
    """
    taken = {}
    for (src, _dst, direction) in graph["edges"]:
        taken.setdefault(src, set()).add(direction[0].lower() if direction else "")

    for block in graph["blocked"]:
        if block["direction"]:
            taken.setdefault(block["room"], set()).add(block["direction"][0].lower())

    out = {}
    for node, room in graph["rooms"].items():
        missing = [e for e in room["exits"] if e not in taken.get(node, set())]
        if missing:
            out[node] = missing
    return out


def to_mermaid(graph, max_rooms=60):
    """A Mermaid flowchart. Renders natively on GitHub and in the artifacts
    viewer, so the map needs no toolchain to look at — which is why this is the
    primary output and Graphviz DOT is the alternate.
    """
    rooms = dict(sorted(graph["rooms"].items(), key=lambda kv: -kv[1]["visits"]))
    if len(rooms) > max_rooms:
        rooms = dict(list(rooms.items())[:max_rooms])

    ids = {node: f"R{i}" for i, node in enumerate(rooms)}
    lines = ["flowchart LR"]

    for node, room in rooms.items():
        label = room["title"].replace('"', "'")
        if room["visits"] > 1:
            label += f" ×{room['visits']}"
        shape = f'(["{label}"])' if room["dark"] else f'["{label}"]'
        lines.append(f"    {ids[node]}{shape}")

    for (src, dst, direction) in graph["edges"]:
        if src in ids and dst in ids:
            lines.append(f"    {ids[src]} -->|{direction}| {ids[dst]}")

    # One shared node per block reason rather than one per block: six dashed
    # edges into two labelled walls reads as a pattern, where six separate
    # nodes read as noise.
    reasons = {}
    for block in graph["blocked"]:
        if block["room"] not in ids:
            continue
        key = block["reason"] or "blocked"
        if key not in reasons:
            reasons[key] = f"B{len(reasons)}"
            lines.append(f'    {reasons[key]}{{{{"⛔ {key.replace("_", " ")}"}}}}')
        lines.append(
            f"    {ids[block['room']]} -.->|{block['direction'] or '?'}| {reasons[key]}"
        )

    return "\n".join(lines)


def to_dot(graph):
    """Graphviz DOT, for anyone who has `dot` installed. Not the primary output
    — see to_mermaid."""
    ids = {node: f"R{i}" for i, node in enumerate(graph["rooms"])}
    lines = ["digraph world {", "  rankdir=LR;", '  node [shape=box];']

    for node, room in graph["rooms"].items():
        label = room["title"].replace('"', "'")
        lines.append(f'  {ids[node]} [label="{label}\\n×{room["visits"]}"];')
    for (src, dst, direction) in graph["edges"]:
        lines.append(f'  {ids[src]} -> {ids[dst]} [label="{direction}"];')
    for block in graph["blocked"]:
        if block["room"] in ids:
            lines.append(
                f'  {ids[block["room"]]} -> blocked_{block["reason"]} '
                f'[style=dashed,label="{block["direction"] or "?"}"];'
            )

    lines.append("}")
    return "\n".join(lines)
