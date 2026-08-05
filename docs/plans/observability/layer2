# Layer 2 Plan — Journey telemetry

Child of [`obs_plan.md`](obs_plan.md) §3; drawn in
[`architecture.md`](architecture.md). Scope: turn what the MUD says back to the
agent into events about the **player's** experience — where someone would be
confused, blocked, bored or overpowered.

Layer 1 answers *is the agent working*. This layer answers the question Arcane
Loop is actually paying for. It depends on Layer 1 being trustworthy first:
**a finding about the game is only credible if the same run can show the agent
was healthy**, which is why this is second and not first.

---

## 1. Where the events come from

`obs_plan.md` §4.1 weighed three emission points. Restating them against what
this layer needs:

| Option | Where | Verdict |
| --- | --- | --- |
| A — in `mud_manager` | the Ruby gem, at primitive level | **No.** Sees raw output first, but runs as an MCP subprocess with no idea of `session_id` or `turn`; correlation would have to be threaded over the wire. |
| B — in `boukensha` | the MCP tool wrapper | Viable. Correlation is free. Requires an agent change and only affects runs made *after* it lands. |
| C — at ingest | a reader over the recorded JSONL | **Taken.** |

**DECIDED 05-08 — option C.** `tool_result` already records the MUD's complete
reply, so nothing is lost by parsing after the fact, and two things are gained:
no agent change is needed, and **the parsers apply retroactively to every
session already on disk**, including the 62 recorded before this layer existed.

The trade is that nothing can *react* to a journey event during a run. Nothing
needs to yet. Option B stays a small change if something ever does.

A consequence worth recording: because journey events are derived rather than
emitted, `obs_plan.md` §4.3 — *does the journey stream share the session file?* —
answers itself. The JSONL keeps only what the agent observed; the derived layer
lives in `sessions.db`.

---

## 2. Parsing rules

These are properties of tbaMUD's output, and every one must be established from
**recorded replies rather than from memory of CircleMUD**. That is not a style
preference — see §6.

### 2.1 A room is identified by its exit line

A successful move looks like:

```
Behind The Temple Altar
   You are on a dirt path leading away from the Temple Altar which is south
of here.  To the north, the path continues ...
[ Exits: n s ]

22H 100M 81V (news) (motd) >
```

**The presence of `[ Exits: … ]` is what marks a reply as a room description**,
and the room's name is the first line. Inferring it from the shape of the first
line instead misfiles `You are 18 years old.` — the opening line of a score
readout — as a room.

Closed-door exits arrive parenthesised: `[ Exits: n (e) s ]`. **Exits are
normalized and the doors reported separately.** Carrying the parentheses through
breaks two things at once: a coverage check comparing `(e)` against `e` reports
every door as an exit never taken, and since room identity keys on the exit set
(see [`layer3`](layer3) §2), a door shut on one visit and open on the next
splits one room into two nodes.

### 2.2 The direction of a refusal is not in the refusal

*"The door seems to be closed."* never says which door. The direction exists
only in the tool call's arguments, so `parse()` takes the call and the reply
together rather than the reply alone.

### 2.3 An unlit room is still a room

`It is pitch black...` is a **successful** move. Discarding it loses the node
*and* the edge that reached it, leaving a hole in the graph that looks like the
agent never moved. It is emitted with `room: None` and `dark: True` — never a
placeholder name, which would collapse every unlit room into one node and invent
edges between unrelated places.

### 2.4 Every reply carries vitals for free

The trailing prompt — `22H 100M 83V` — is hit points, mana and movement, on
every single reply. Collected on every event at no extra cost; it is the raw
material for the *overpowered* category.

---

## 3. The events

Four types. Each carries a `reason` where the same event has materially
different causes, because **a single count hides exactly the distinction that
makes a finding actionable** — a locked door is a puzzle, a level gate is a
progression wall, and they need different fixes.

| Event | Fields | Category served |
| --- | --- | --- |
| `room_entered` | `room`, `exits`, `doors`, `direction`, `dark`, `vitals` | mapping, bored |
| `movement_blocked` | `direction`, `reason`, `text`, `vitals` | **blocked** |
| `command_rejected` | `command`, `target`, `reason`, `text`, `vitals` | **confused** |
| `progression` | `exp`, `exp_to_next`, `level`, `rank`, `gold`, `hp`/`max_hp`, … | **progression, overpowered** |

**Reasons.** `movement_blocked`: `closed_door`, `no_exit`, `level_gated`,
`exhausted`. `command_rejected`: `not_present`, `unknown_command`,
`cannot_take`, `disabled_command`.

**Absent stays absent.** A character with no gold and a reply that did not
mention gold are different facts; the score parser omits what it did not see
rather than defaulting to zero. Same rule the ingest follows for NULLs.

---

## 4. Correlation

Every journey row must resolve to the model call that produced it. **A finding
that cannot be audited is not a finding.**

The ingest inserts each journey row immediately after the `tool_result` it came
from, inheriting that row's `turn` and `iteration`. Those two are forward-filled
at ingest because only the `turn` and `iteration` events carry them — `log_viz`
re-derives the same thing while scanning, and so would every future reader.

Journey rows live in the same `events` table under `journey.*` phases, using the
existing `raw` column for type-specific fields. No schema migration; see
[`layer1`](layer1) §2.1 for why `raw` exists.

---

## 5. Gates

1. **Every journey event resolves back to a `session_id` + `turn` + `iteration`
   present in the agent stream.** *Met — 90 of 90 rows.*
2. **The parsers run over sessions recorded before they existed.** *Met — 14
   progression readings recovered from the archive.*
3. **A game refusal is not recorded as a tool failure.** *Met, verified against
   the live MUD: `look` at an absent target logs `ok=True` and emits
   `command_rejected`; a daemon error logs `ok=False`.* **The tool worked; the
   player was blocked** — collapsing those two would make every blocked-journey
   finding unfalsifiable at the point of measurement.
4. **Each category carries more than one distinct cause.** *Met for blocked (3
   reasons) and confused (4). See §6.*

---

## 6. Known limits

- **Patterns written from memory fail silently, and did so twice.** The first
  draft looked for `Obvious exits:` where tbaMUD emits `[ Exits: n s ]` — it
  would have matched **0 of 66 moves**. The rejection pattern read `Huh?!?`
  where the game says `Huh!?!`, and matched nothing for as long as it existed.
  Both were syntactically valid, both passed review, neither failed loudly.
  **Every pattern in `journey.py` is now copied from a recorded reply**, and the
  tests quote real corpus strings rather than invented ones.
- **The confusion corpus is monotone.** 24 events, 19 of them one message. The
  signal is proven; characterising it needs *interaction* — examining, taking,
  buying, talking — not more walking.
- **`combat_resolved` is not implemented.** Kills are visible in the raw replies
  and the exp deltas are recovered from `progression`, but a per-fight event
  (target, damage taken, outcome) would make the overpowered analysis direct
  rather than inferred.
