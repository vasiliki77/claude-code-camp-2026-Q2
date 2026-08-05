# Week 2

*In progress — day 1 of the week. Conclusions are provisional and marked as such.*

## Technical Goal

Week 2 is **observability week**, and it is deliberately open — the theme is
fixed, the implementation is each participant's own choice. Memory and
compaction are in scope alongside it.

Goal as worked to: make the Player Journey Agent able to say something true
about what it did — both as an engineering artifact (is it working, what does a
run cost) and as the product Arcane Loop is actually buying (where players get
confused, blocked, bored or overpowered on CircleMUD).

Gameplan, as planned on day 1 and recorded in
[`docs/plans/observability/obs_plan.md`](../plans/observability/obs_plan.md):

- **Layer 1 — agent telemetry.** Repair the existing session stream so it can serve as evidence. Detail in [`layer1`](../plans/observability/layer1).
- **Layer 2 — journey telemetry.** Domain events from the MUD tool calls, correlated to Layer 1 by `session_id` + `turn` + `iteration`.
- **Layer 3 — the world graph.** Rooms as nodes, exits as edges, annotated with what happened at each.
- **Layer 4 — memory and compaction.** `compact_messages!` drops the oldest 40% with no summarization and has never once run; this week forces it and observes what it destroys.

The work lives in [`week2_capable/`](../../week2_capable/README.md), branched
from `week1_baseline/python/12_context` on 05-08; that tree stays frozen as week
1's artifact.

Scoped on day 1 to the **minimum effective path** (`obs_plan.md` §5.3): the
shortest route that still produces the deliverable, cutting anything that serves
neither the report nor the map. The course reference implementation uses
OpenTelemetry with Docker; this project diverges deliberately, because a
collector reproduces the emission half of a pipeline while the work here is in
the half that lands telemetry somewhere queryable and turns it into a report.

Architecture and the reasoning behind its shape:
[`architecture.md`](../plans/observability/architecture.md).

## Technical Uncertainty

Written before the work, as of the morning of 05-08.

- Whether the existing `Logger`/JSONL substrate is good enough to build on, or whether observability week means replacing it with a real tracing stack.
- Whether OpenTelemetry is the expected answer, and if so what it costs to run — the constraint stated up front was that nothing may be paid for.
- Whether "observability" for this project means the agent's own health, the player's journey, or both — and if both, whether they share a pipeline.
- Whether one agent's telemetry can support a claim about *players* at all, given the agent is a single synthetic user rather than a population.
- Whether the compaction path flagged at the end of [week 1](week1.md) as never having fired would turn out to matter here.

## Technical Hypotheses

- The existing JSONL is closer to sufficient than it looks, and the week's work is mostly completion rather than replacement — `log_viz` already reads it as traces, which is evidence the shape is right.
- Agent telemetry and journey telemetry are different products for different readers, and conflating them is the trap the week is designed to expose.
- Free-to-run rules out hosted platforms but not much else, so cost will not be the deciding factor in the technology choice.
- Findings about the game will only be credible if the same run can prove the agent itself was healthy — so the agent stream has to be trustworthy *first*.

## Technical Observations

Day-by-day detail in [05-08-2026](05-08-2026.md). Summary so far:

- **Day 1 surveyed first, then built.** The 62 session files already on disk and the step-12 sources were measured before anything was planned — three planning pages, a scope cut, then Layer 1 implemented in the afternoon.
- **Layer 1 shipped, Python only.** `ToolFailure` gives the `ok` flag a type rather than a guess; `session_end` records how a session ended; `prompt` carries the full history only when the last message is the user's. 108 tests pass, 12 of them new. The distinction the design rests on is confirmed against the live MUD: a game refusal logs `ok=True` and a daemon error logs `ok=False` — **the tool worked, the player was blocked**, which the old code called the same thing.
- **Dropping Ruby settled an open design decision for free.** `obs_plan.md` §4.1 asked where journey events should be emitted. Python has no in-process MUD tool module, so the MCP wrapper covers every MUD call there is; the question existed only because Ruby had two routes to the same tools.
- **Layer 2 parses real MUD output, and the corpus was what made it correct.** The first draft looked for `Obvious exits:` — read off an older session — where real move replies end `[ Exits: n s ]`; **0 of 66 moves would have matched.** Three further corrections came from the data rather than from reasoning: a room is identified by its exit line and not by its first line's shape, a blocked move's direction exists only in the tool call and never in the reply, and `It is pitch black...` is a *successful* move whose node and edge were being silently dropped. **74 of 88 calls parse** — 61 `room_entered` across 30 rooms, 7 `command_rejected`, 6 `movement_blocked`.
- **The first real player-journey finding was not one that had been predicted.** **5 of 6 blocks are `level_gated`** — *"This zone is above your recommended level."* A progression wall rather than a puzzle, visible only because the event carries a `reason`; a single "blocked" count would have buried it inside the closed door.
- **Journey events are derived at ingest, not emitted live.** `obs_plan.md` §4.1 had chosen live emission; option C turned out strictly better here — no agent change, no re-run, and the parsers apply **retroactively to all 66 archived sessions**, including the 62 predating Layer 2. 1,164 rows in one SQLite table, and **all 90 journey rows carry `turn` and `iteration`**, meeting §7's Layer 2 gate.
- **Layer 3 produced the week's first real finding, and it was not one anybody predicted.** `The Dirt Path` refuses movement in **all four advertised directions** with *"This zone is above your recommended level."* — five of the corpus's six blocks in one room, where a low-level player can enter and then only leave the way they came. It exists only because the graph attaches each block to the room the player was standing in: the journey event carries the direction and the refusal but never the origin, and the origin appears only once movements are folded into a path.
- **Room identity (§4.2) was settled by counting.** 72 room entries, 32 distinct titles, **36 distinct (title, exits) pairs** — three titles cover more than one room, so keying on title alone merges four rooms and makes every edge through them a lie. The map is 37 rooms, 62 passages, and reports its own coverage: 24 rooms have advertised exits never taken, which is the guard against calling a region unreachable when it was merely unvisited.
- **Rendering the data found a bug 130 tests had not.** The coverage table showed `(n), (e)` — CircleMUD parenthesises closed-door exits, and the parser was carrying the parentheses through, so every door read as an exit never taken and a door opening between visits would have split one room into two nodes. **A test asserts what you thought to ask; a rendering shows you what you did not.**
- **Week 2's code had been written into week 1's folder.** `week2_capable/` existed and sat empty while the Layer 1 commit modified `week1_baseline/python/12_context`. Moving it broke three paths expressed as counts of parent directories — **the fourth instance of that family in two weeks** — and surfaced a step-11 README that had been shipping inside the step-12 folder unnoticed.
- **The substrate is sound and the gaps are specific.** Per-response usage and cost are complete (**85 of 85 events**), which corrected the day's opening assumption that token accounting was inert. What is missing is narrower and verifiable: `tool_result.ok` reports success for tools that returned an error string, **no** session records how it ended, API failures and retries emit nothing, there are no durations, and **85% of the largest session file** is `prompt` events re-serializing the whole history each iteration.
- **Week 1's parting uncertainty had a number, and is now closed.** `limit_reached` and `compaction` had fired **0 times in 62 sessions**. Both fired on 05-08 — `limit_reached` during the mapping run, `compaction` twice in a 4.1-cent gate — and no 400 appeared.
- **Closing that gate found the defect underneath it.** `_compact_if_needed()` sits outside the agent loop, so compaction is evaluated once per turn at turn start. **A mapping run is one long turn**, which means the agent cannot compact during the one activity the project exists to perform; the 05-08 run grew 4,117 → 20,568 tokens with no opportunity to compact at any point. A second defect compounds it: `wrap_up` runs with tools disabled, so a ceiling-terminated turn writes a context reading that excludes all 26 tool definitions — 917 tokens reported against ~4.5k in play. **Compaction is therefore least likely to fire right after the turns that worked hardest.** Both deferred as out of scope, both recorded.
- **The technology question resolved away from cost.** OpenTelemetry is free, and so is every backend worth considering; the decision turned instead on the deliverable (no tracing backend renders a world map) and on operational weight. JSONL stays the source of truth, SQLite becomes the aggregation layer at zero installs, Graphviz/Mermaid draw the graph.
- **The week's first real incident argued for the work better than the plan did.** CircleMUD accepted connections and never greeted anyone; the cause was a `boukensha` REPL left running in a terminal, hammering it several times a second for 21 minutes. **Nothing on disk recorded that session existed** — no ending, no owner, no trace. That is the exact gap `session_end` closes, found by walking into it rather than by reasoning about it.

## Technical Conclusions

*Pending — the week has one day of work in it. Settled so far:*

- **"The existing JSONL is closer to sufficient than it looks." — Holding.** Nothing found on day 1 argues for replacing it, and two things argue against: `log_viz` already reads it as traces, and the 62 archived sessions stay queryable by tools not yet written. Retention is `git`.
- **"Cost will not be the deciding factor." — Confirmed, and more strongly than expected.** Every candidate is free to self-host, so the constraint eliminated nothing and the decision had to be made on other grounds entirely.
- **"The agent stream has to be trustworthy first." — Vindicated on day 1, by accident.** The leaked REPL was a session with no ending, no owner and no record, and it took the MUD down for everyone. Had the mapping run happened first, the resulting silence would have read as a blocked player journey. **The control stream is not scaffolding for the findings; it is what makes a finding falsifiable.**
- **"Findings will only be credible if the run can prove the agent was healthy." — Extended by the parsers, not just confirmed.** The same principle turned out to apply *inside* Layer 2: a game refusal must log `ok=True`, because the tool worked and the player was blocked. Collapsing those two would have made every blocked-journey finding unfalsifiable at the point of measurement rather than at the point of analysis.
- **§4.1 is closed twice over** — first by dropping Ruby, which left the MCP wrapper as the only path a MUD call can take, then by deriving at ingest instead, which made the emission point moot for now.
- **§4.3 is closed:** one file, one table, `journey.*` phases beside the agent phases. The correlation is positional and the ingest forward-fills it.
- **§4.2 is closed: `(title, sorted exits)`.** All three of §4's decisions are now settled, and every one of them was settled by measuring the corpus rather than by choosing between plausible designs in advance.
- **The deliverable exists, and it is not verified.** The map's topology has never been compared against CircleMUD's own zone files, though `week0_explore/circlemud-world-parser` already converts them to JSON. **Until that comparison is made, the map is what the agent believes rather than what the world is** — which is the same distinction, one level up, that the whole week has been about.
- **The week's method is holding.** Every correction of consequence so far came from measuring rather than reasoning: the token accounting that was not broken, the exit line that was not `Obvious exits:`, the compaction that could not fire, the MUD that was not down. **Reasoning produced the plan; the data produced the plan's corrections.**

## Key Takeaway

*Provisional.* Week 1 ended on the observation that building an agent without an
SDK teaches you how to make a system say something true about itself. Week 2
opened by finding that the system's most confident statement — `"ok": true` on
every tool call — was the false one, and that the two paths meant to report
exhaustion had never once run. **The instrumentation that has never fired and the
flag that cannot say "no" are the same defect: telemetry nobody has yet had a
reason to disbelieve.**
