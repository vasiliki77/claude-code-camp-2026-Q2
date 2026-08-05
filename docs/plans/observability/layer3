# Layer 3 Plan — The world graph

Child of [`obs_plan.md`](obs_plan.md) §3; consumes [`layer2`](layer2)'s events.
Scope: fold journey events into **rooms as nodes and movements as edges**, and
attach to each room what happened there.

This is simultaneously the brief's "map the world", the substrate the *blocked*
and *bored* analyses run over, and the most legible artifact to put in front of
someone who did not build it.

---

## 1. Why a graph rather than a room list

Two things a list cannot do, and both turned out to matter:

- **A block belongs to the room it was hit from, and the journey event does not
  know that room.** `movement_blocked` carries the direction and the refusal;
  the origin exists only once movements are folded into a path. The week's first
  finding — a room refusing all four of its exits — is invisible without this
  step.
- **A map has to be able to say what it has not seen.** Advertised exits never
  taken are the difference between "this region is unreachable" and "nobody went
  there", and reporting the first when the second is true is the worst error
  this layer could make.

---

## 2. Room identity

**The highest-leverage modelling decision in the project** — the whole graph's
shape follows from it. `obs_plan.md` §4.2 listed three candidates: description
hash, description hash + exit set, or path-from-origin.

**DECIDED 05-08 — `(title, sorted exits)`, settled by counting rather than
arguing.** The corpus holds 72 room entries with **32 distinct titles but 36
distinct (title, exits) pairs**. Three titles cover more than one room:

```
The Great Field Of Midgaard        exits ns   and ensw
Wall Road                          exits ens  and ns
A Shaded Path Through The Forest   exits esw, sw and ns
```

Keying on title alone merges four rooms into three and **makes every edge
through them a lie**. CircleMUD reuses titles across the segments of a road or
field; that is ordinary MUD authoring, not a quirk of this world.

**The residual is stated rather than hidden.** Two genuinely distinct rooms
sharing both a title *and* an exit set still merge. Separating those needs
path-from-origin, which is a larger change than this week allows. No collision
exists in the current corpus; a larger map will produce them.

**Dark rooms have no content to key on**, so they are keyed by their entrance —
the room entered *from*, plus the direction. Unique per entrance, therefore
right for the edge even when wrong for the node. Two entrances to one dark room
appear as two nodes: **a visible guess rather than a silent merge.**

Exits are normalized before they reach the key, so a door opening between visits
does not split a room ([`layer2`](layer2) §2.1).

---

## 3. Building the graph

- **Only a `move` creates an edge.** `look` re-describes the room the player is
  already standing in; treating it as movement invents a self-loop for every
  glance around.
- **Sessions never chain.** The "where am I" cursor resets at each session
  boundary, because a reconnect starts at the MUD's start room and not where the
  last session stopped. An edge across that boundary would be fabricated.
- **A block with no known origin is dropped, not guessed at.** If the cursor
  does not know where the player was standing, the block is unattributable.

## 4. Coverage and tedium

Two derived measures, both computed from data already recorded — neither needs
anything new collected.

**`unexplored()`** — advertised exits never taken, per room. The map's own
coverage measure, and the guard against §1's worst error.

**`tedium()`** — the *bored* signal, three measures because boring is not one
thing:

| Measure | What it catches |
| --- | --- |
| `discovery_rate` | new rooms per move; a run that stops finding anything |
| `revisit_ratio` | moves ÷ distinct rooms; 3.0 means walking the same ground three times |
| `longest_barren` | most consecutive moves discovering nothing — **the one that matches what a player actually feels**, which is not "few rooms" but "a long stretch where nothing was new" |

**Reported per session, never averaged.** A 61-move run and a 1-move run are not
comparable and a mean of the two describes neither.

---

## 5. Output

**Mermaid is primary, Graphviz DOT the alternate.** Not because `dot` is
missing — Mermaid renders natively on GitHub, so the map drops into a README
with no toolchain and no image file to keep in sync with the data.

Rendering is not decoration here: laying the coverage table out for a human is
what exposed the parenthesised-exit bug that 130 passing tests had not.
**A test asserts what you thought to ask; a rendering shows you what you did
not.**

---

## 6. Gates

1. **A mapping run reproduces the zone's real topology.** ⚠️ **Partly met.** The
   graph is self-consistent — 61 rooms, 91 passages — but has **never been
   compared against CircleMUD's own zone files**, and
   `week0_explore/circlemud-world-parser` already converts those to JSON. Until
   that comparison runs, **the map is what the agent believes rather than what
   the world is**, which is the week's own attribution question one level up.
2. **Every block resolves to a room.** *Met.*
3. **The map reports its own coverage.** *Met — 22 rooms with untaken exits.*

## 7. Known limits

- **Coverage is 61 rooms of 12,733** — 0.5% of the world. The machinery maps
  correctly; it has not been pointed at much. "We mapped Midgaard centre and the
  newbie zone completely" would be a defensible claim; a scattering of rooms is
  not yet one.
- **Identity collisions are possible and undetected** (§2's residual).
- **`check kind=exits` is unused.** It returns a full adjacency list —
  `north - By The Temple Altar` — direction and destination in one command, the
  richest map signal available. Roughly 15 lines whenever the graph wants it.
