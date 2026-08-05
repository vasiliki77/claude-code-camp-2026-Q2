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
- **The substrate is sound and the gaps are specific.** Per-response usage and cost are complete (**85 of 85 events**), which corrected the day's opening assumption that token accounting was inert. What is missing is narrower and verifiable: `tool_result.ok` reports success for tools that returned an error string, **no** session records how it ended, API failures and retries emit nothing, there are no durations, and **85% of the largest session file** is `prompt` events re-serializing the whole history each iteration.
- **Week 1's parting uncertainty now has a number.** `limit_reached` and `compaction` have fired **0 times in 62 sessions**. Both are implemented and neither has ever executed, which converts "needs a real session driven past the threshold" from a worry into a gate scheduled before any long mapping run.
- **The technology question resolved away from cost.** OpenTelemetry is free, and so is every backend worth considering; the decision turned instead on the deliverable (no tracing backend renders a world map) and on operational weight. JSONL stays the source of truth, SQLite becomes the aggregation layer at zero installs, Graphviz/Mermaid draw the graph.
- **The week's first real incident argued for the work better than the plan did.** CircleMUD accepted connections and never greeted anyone; the cause was a `boukensha` REPL left running in a terminal, hammering it several times a second for 21 minutes. **Nothing on disk recorded that session existed** — no ending, no owner, no trace. That is the exact gap `session_end` closes, found by walking into it rather than by reasoning about it.

## Technical Conclusions

*Pending — the week has one day of work in it. Settled so far:*

- **"The existing JSONL is closer to sufficient than it looks." — Holding.** Nothing found on day 1 argues for replacing it, and two things argue against: `log_viz` already reads it as traces, and the 62 archived sessions stay queryable by tools not yet written. Retention is `git`.
- **"Cost will not be the deciding factor." — Confirmed, and more strongly than expected.** Every candidate is free to self-host, so the constraint eliminated nothing and the decision had to be made on other grounds entirely.
- **"The agent stream has to be trustworthy first." — Vindicated on day 1, by accident.** The leaked REPL was a session with no ending, no owner and no record, and it took the MUD down for everyone. Had the mapping run happened first, the resulting silence would have read as a blocked player journey. **The control stream is not scaffolding for the findings; it is what makes a finding falsifiable.**
- **§4.1 is closed** — journey events emit from the MCP wrapper, because after dropping Ruby that is the only path a MUD call can take.
- **Open:** whether the two streams should share one file (`obs_plan.md` §4.3), and what a room's identity is (§4.2) — the latter being the highest-leverage modelling choice in the project, since the whole graph's shape follows from it.

## Key Takeaway

*Provisional.* Week 1 ended on the observation that building an agent without an
SDK teaches you how to make a system say something true about itself. Week 2
opened by finding that the system's most confident statement — `"ok": true` on
every tool call — was the false one, and that the two paths meant to report
exhaustion had never once run. **The instrumentation that has never fired and the
flag that cannot say "no" are the same defect: telemetry nobody has yet had a
reason to disbelieve.**
