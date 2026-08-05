# Claude Code Camp
This repo is created by a template of the Claude Code Camp repo operated by [ExamPro](https://www.exampro.co)

## Player Journey Agent

An agent that plays a MUD the way a new player would, maps the world, and
reports where players get **confused, blocked, bored or overpowered**. Built for
the Arcane Loop scenario, proven against CircleMUD.

![A recorded session: the agent's tool calls and the MUD's replies in log_viz, alongside the Metabase dashboard](arcaneLoop.gif)

*A recorded run, turn by turn — each tool call, the MUD's reply, and what it
cost.*

**→ [Operator's Guide](docs/user_guide.md)** — setup, running it, reading the
results, what it costs, and what it does not yet do.

Quick look, free and offline:

```sh
cd week2_capable
../.venv/bin/python examples/demo.py --offline
```

The agent is in [`week2_capable/`](week2_capable/README.md), the design in
[`docs/plans/observability/`](docs/plans/observability/), and the current map in
[`docs/maps/world.md`](docs/maps/world.md).

## Technical Journal

Bootcamp learning log under [`docs/technical_journal/`](docs/technical_journal/), one weekly summary (Technical Goal / Uncertainty / Hypotheses / Observations / Conclusions / Key Takeaway) backed by a detailed log per day.

- [Week 0 summary](docs/technical_journal/week0.md) — architecture comparison and key takeaway for the week.
  - [20-07-2026](docs/technical_journal/20-07-2026.md) — Repository setup, environment setup, Architecture 1 (Plain Agent File).
  - [21-07-2026](docs/technical_journal/21-07-2026.md) — Architecture 2 (Agent Skills), memory/goal tracking, the dungeon-trap and town-guard incidents, Architecture 3a (subagent port).
  - [22-07-2026](docs/technical_journal/22-07-2026.md) — Architecture 3b (programmatic `AgentDefinition`), Architecture 4 (n8n, blocked on API credits).
- [Week 1 summary](docs/technical_journal/week1.md) — the Baseline Agent (no SDK), steps 0–12 in Ruby and ported to Python: what an SDK hides turned out to be where every expensive bug lived, the MUD gem is reusable from Python as a *process* rather than a library, and porting is best understood as a code review of the original.
  - [24-07-2026](docs/technical_journal/24-07-2026.md) — Step 0 (Configuration): missing `dotenv` gem, `settings.yaml` filename/location fix.
  - [27-07-2026](docs/technical_journal/27-07-2026.md) — Step 1 (Struct Skeleton): Ruby → Python port of the `Tool`/`Message`/`Context` data containers.
  - [28-07-2026](docs/technical_journal/28-07-2026.md) — Step 2 (The Tool Registry): Ruby → Python port of `Registry`/`UnknownToolError`, block → decorator, stale Ruby README output.
  - [31-07-2026](docs/technical_journal/31-07-2026.md) — Steps 3–5 (Prompt Builder, API Client, Agent Loop): five backends, the stdout gate breaking on live API calls, two upstream Ruby bugs, and a port skill abandoned as too costly.
  - [01-08-2026](docs/technical_journal/01-08-2026.md) — Running `log_viz` (the session JSONL read as traces rather than logs), Steps 6–8 (The Logger, The Run DSL, The REPL Loop): the JSONL becomes the verification artifact, `instance_eval` has no Python equivalent, step 07 turns out to be branched from before step 06, step 08's real subject is persisting the assistant reply — and three counted-`..` path bugs in one day, ending with `BOUKENSHA_DIR` moving out of every example into the launchers. Then Step 9 (Global Executable): the installed gem is a fourth entry path the launcher fix cannot reach, `~/.boukensharc` gains a second key, and why Python needs no step 9 — plus what to keep when extracting both agents after the bootcamp.
  - [02-08-2026](docs/technical_journal/02-08-2026.md) — Running the steps rather than porting them: a launcher renamed on a misread of the step-vs-folder numbering, `bundle check || bundle install` added to all 12 launchers, `mud_manager` built but never installed (and bundler blaming its author), and the confusion worth recording — `boukensha` and `bin/ruby/<step>` are not two doors into the same room.
  - [04-08-2026](docs/technical_journal/04-08-2026.md) — Exposing the MUD over MCP, where almost every problem was a *signal* problem: a stdio server indistinguishable from a hang, a banner describing the route that was switched off, a timeout printing `after s`, and an env var ignored in silence. Plus a step-09 capability that never reached step 10 (a *floating artifact*), the installed-gem-versus-step-folder split for the third time, a login branch that only became reachable once there were two ways to connect, two Ruby constructs that bind to the wrong thing without complaining, and two plans that disagreed with themselves. Then porting step 10 to Python by **leaving out its largest file** — the daemon's premise tested by a second language for the first time — which came with the week's strongest verification gate and one more trap that recurred because it had been filed under where it was found. Then carrying step 10 into step 11 and porting step 11 (charm → Textual): a `cp` that fixed one floating artifact and **created another in the same command**, three more caches reporting anything but staleness, and a crash on quit that only the test harness's rhythm could expose. Finally Step 12 (Context Management), which was a **two-way merge rather than a carry-forward** — `log_viz` settled the conflict its two upstreams could not, merging surfaced three defects it did not introduce (token accounting inert on three of five backends, a "derived" model table that was neither derived nor correct, and compaction that orphans a `tool_result` into a 400), and the same delta ported to Python as a pure forward copy, proving the merge was a cost of the snapshot-per-step layout and not of the feature.
- [Week 2 summary](docs/technical_journal/week2.md) — Observability week: two telemetry streams for two audiences, and attribution — telling a game defect from an agent defect — as the constraint the week exists to satisfy. Four layers built (agent telemetry → journey telemetry → world graph → memory), a warehouse and dashboards over them, and the agent handed over with an [Operator's Guide](docs/user_guide.md). Code in [`week2_capable/`](week2_capable/README.md); design under [`docs/plans/observability/`](docs/plans/observability/): [`obs_plan.md`](docs/plans/observability/obs_plan.md), [`layer1`](docs/plans/observability/layer1), [`architecture.md`](docs/plans/observability/architecture.md). **Three findings**: [the world map](docs/maps/world.md) shows `The Dirt Path` refusing movement in all four directions; the newbie zone is safe *and* slow (33 exp a kill, one hit taken across three fights, 36 kills to level); and `map` tells players it is "disabled" when it is merely restricted to immortals by a default nobody chose.
  - [05-08-2026](docs/technical_journal/05-08-2026.md) — The whole of week 2 in one day. **Surveying before planning**: `tool_result.ok` reported success for tools that returned an error string, no session in 62 recorded how it ended, 85% of the largest file was re-serialized history, and `limit_reached`/`compaction` had fired zero times — while token accounting turned out *not* to be the defect it looked like. Technology settled away from cost (not OpenTelemetry: free, but renders no world map). Ruby dropped for Python, closing an open design decision for free; then a leaked REPL took the MUD down and argued for `session_end` better than the plan had. **Layer 2** parsed MUD replies into journey events — a first draft that would have matched 0 of 66 moves, because the exit line was written from memory. **Layer 3** folded those into a 61-room graph and produced the first finding; rendering the data then exposed a bug 130 tests had not. **Layer 4** fired compaction for the first time ever and found it cannot fire mid-turn at all. A scope cut reversed itself once the pipeline turned out to be legible only to its author, and Metabase went in over SQLite. Then auditing against the brief rather than the plan found the machinery complete and three of four report categories empty — two of which needed no new data, only reading telemetry collected weeks earlier for other reasons. Six components reported success while doing the wrong thing; **none of them failed, all of them lied.**
