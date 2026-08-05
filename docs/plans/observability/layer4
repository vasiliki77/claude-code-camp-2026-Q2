# Layer 4 Plan — Memory and compaction

Child of [`obs_plan.md`](obs_plan.md) §3. Scope: what the agent keeps when a
session outgrows its context window — and, this week, **whether the existing
behaviour is even reachable.**

Memory and observability are the same question approached from opposite ends.
You cannot judge a compaction strategy without telemetry showing *what was
dropped* and *whether the agent re-discovered it*; and the world graph
([`layer3`](layer3)) is the obvious thing to compact *into*, since a map is a
summary of exploration that survives the messages being deleted.

---

## 1. What exists

`Context.compact_messages!` drops the oldest 40% of messages and snaps to a user
boundary. **Pure deletion: no summarization, nothing persisted.** It throws away
precisely the world knowledge the agent has accumulated, which is the problem
this layer eventually exists to solve.

It had also **never once executed** — 0 occurrences across 62 recorded sessions
— exactly as [week 1](../../technical_journal/week1.md) predicted. The behaviour
most likely to first appear mid-play was the one with the least evidence behind
it.

---

## 2. Scope this week: observe, do not redesign

`obs_plan.md` §5.3 trims the week to the minimum effective path. Redesigning
compaction is out; **making it run and watching what it does** is in.

The reasoning is not only budget. A redesign built against a behaviour nobody
has observed would be built against an assumption — and §4 shows the assumption
would have been wrong in a way no amount of design could have anticipated.

---

## 3. Gate: force it deliberately

**CLOSED 05-08** via `examples/compaction_gate.py`: three short turns on one
context, threshold overridden **on the context object rather than in
`settings.yaml`**, so an interrupted run leaves no dangerous configuration
behind.

Result: `limit_reached` ×2, `compaction` ×2 (dropping 7 messages then 6), 4.1
cents, and **no 400** — the failure week 1 warned about, where compaction
orphans a `tool_result`, did not occur. §4.1 explains why, and it is not
reassuring.

**The first attempt failed, and the failure was the finding.** A 4,000-token
threshold should have fired at turn 2 and did not; turn 1 reported **917 tokens**
when ~4.5k was in play. See §4.2.

---

## 4. What the gate uncovered

Both defects are **real, out of scope this week, and recorded because the first
will bite as soon as a mapping run gets long.**

### 4.1 Compaction cannot fire mid-turn

`Agent.run` calls `_compact_if_needed()` at `agent.py:63`, **outside and before**
the `while True` loop. Compaction is therefore evaluated **once per turn, at
turn start** — when a one-shot run's context is still empty.

**A mapping run is one long turn.** The 05-08 run grew from 4,117 to 20,568
tokens across 80 iterations with no opportunity to compact at any point. A long
enough run reaches the context window and fails rather than compacting, and
**that is the project's core use case rather than an edge of it.**

It also explains the 400 that did not happen: a *mid-turn* compaction is exactly
the one that could orphan a `tool_result`, and mid-turn compaction cannot
currently occur. **The two findings are one fact seen from opposite sides** —
fixing the first makes the second reachable, so they have to be fixed together.

### 4.2 `wrap_up` deflates the reading compaction depends on

A turn ending on `max_iterations` makes one final model call with **tools
disabled**. That call's `input_tokens` therefore excludes all 26 tool
definitions, and `record_usage` writes it straight into `current_tokens`.

Turn 1 of the gate reported 917 tokens with ~4.5k in play; turn 3 reported 948
after genuinely spending 13,946.

Compounded with §4.1 the effect is perverse: **compaction is least likely to
fire right after the turns that worked hardest**, because those are the turns
that end on a ceiling and so end with a deflated reading.

---

## 5. What a redesign would have to do

Deferred, but the shape is now known rather than guessed:

- **Move the check inside the loop**, so a long single turn can compact — and
  handle the orphaned `tool_result` that becomes reachable the moment it can.
- **Measure context pressure from something `wrap_up` cannot deflate**, since
  the wind-down call is structurally unrepresentative of the turn.
- **Summarize into the world graph rather than deleting.** The map already holds
  what exploration established; compaction that writes there first would drop
  messages without dropping knowledge.
- **Verify with the telemetry that already exists**: `unexplored()` and the
  visit counts can answer *did the agent re-walk ground it had already mapped* —
  which is the only real test of whether a memory strategy works.

## 6. Known limits

- **The re-walk question has not been asked**, though the data to answer it is
  in `sessions.db` today.
- **The gate is synthetic.** Compaction has fired under a deliberately lowered
  threshold, never under natural pressure in a long session — because §4.1 makes
  that impossible.
