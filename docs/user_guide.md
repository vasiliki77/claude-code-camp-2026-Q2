# Player Journey Agent — Operator's Guide

For the Arcane Loop team. This is everything needed to run the agent against a
MUD, read what it found, and judge how far to trust it.

The agent plays a text adventure the way a new player would, records everything
it did, and reports where a player would get **confused, blocked, bored or
overpowered**. It currently runs against CircleMUD as the proving ground, per
the brief — it has no access to Arcane Loop's live world, player data, or
proprietary systems.

---

## 1. What you get

Four things, in the order they are produced:

| Artifact | Where | What it answers |
| --- | --- | --- |
| **Session log** | `.boukensha/sessions/*.jsonl` | exactly what the agent did, one JSON object per event |
| **Session trace** | log_viz, `:4567` | one run, turn by turn, with cost |
| **Dashboard** | Metabase, `:3000` | patterns across every run |
| **World map** | `docs/maps/world.md` | the rooms, the passages, the walls |

They share one identifier — the **session id** — so any number on a dashboard
can be traced back to the exact model call that produced it. That traceability
is the point: a finding you cannot audit is not a finding.

---

## 2. Prerequisites

| | Why | Check |
| --- | --- | --- |
| Docker | runs CircleMUD and Metabase | `docker --version` |
| Python 3.12+ | the agent | `python3 --version` |
| Ruby 3.4+ | the MUD driver and the trace viewer | `ruby -v` |
| Anthropic API key | the agent's model | see §3 |

Ruby is needed as a *runtime*, not for development — the agent is Python and
talks to the MUD through a Ruby daemon over MCP.

---

## 3. First-time setup

```sh
git clone <repo> && cd claude-code-camp-2026-Q2

# Python
python3 -m venv .venv
.venv/bin/pip install -r week2_capable/requirements.txt

# The MUD driver (Ruby gem, provides `mud-manager`)
cd week0_explore/mud_manager
gem build mud_manager.gemspec && gem install ./mud_manager-0.2.0.gem
cd ../..

# The API key
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .boukensha/.env
```

Then start the MUD:

```sh
cd week0_explore/infrastructure
docker compose up -d
nc localhost 4000        # should greet you within a second or two
```

> **If it connects but stays silent**, something is flooding it — usually an
> agent process left running from an earlier session. Check with
> `pgrep -af boukensha` and kill it. A MUD that accepts connections and never
> greets looks broken but is merely busy.

Settings live in `.boukensha/settings.yaml` — model, MUD credentials, and the
per-run ceilings covered in §6.

---

## 4. Running the agent

Set this once per shell:

```sh
cd week2_capable
export BOUKENSHA_DIR="$(cd .. && pwd)/.boukensha"
PY=../.venv/bin/python
```

| Command | What it does | Typical cost |
| --- | --- | --- |
| `$PY examples/demo.py --offline` | the whole pipeline over existing data | **free** |
| `$PY examples/demo.py` | same, with a short live run first | ~$0.15 |
| `$PY examples/play.py` | interactive session — you type the goals | per turn |
| `$PY examples/mapping_run.py` | one long unattended exploration | ~$1.00 |

**Start with `--offline`.** It runs every stage except the live MUD and costs
nothing, so you can see the shape of the output before spending anything.

`play.py` is the one to use when you want to steer. Type goals at the prompt:

```
> look around and tell me where you are
> go north and describe what you find
> /compact          # free up context on a long session
> exit
```

---

## 5. Reading the results

### The dashboard — patterns across runs

```sh
$PY examples/ingest_sessions.py          # rebuild the warehouse from the logs
cd observability && docker compose up -d && python3 provision.py
```

Open the printed URL, sign in with the printed credentials. Full detail in
[`week2_capable/observability/README.md`](../week2_capable/observability/README.md).

> **Re-run `ingest_sessions.py` after every agent run.** Metabase reads a
> database built from the logs, not the logs themselves. Skip this and the
> dashboard will quietly show you yesterday's world.

### The trace — one run in detail

```sh
cd week1_baseline/ruby/log_viz
bundle install && bundle exec ruby bin/log_viz
```

Then <http://localhost:4567>. Clicking a session in the dashboard's index opens
it here; pasting an id from here into the dashboard's **Session** filter narrows
every chart to that run.

### The map

```sh
$PY examples/world_map.py
```

Writes [`docs/maps/world.md`](maps/world.md) — rooms, passages, blocks, and
which advertised exits were never taken. Renders as a diagram on GitHub.

### Ad-hoc questions

```sh
sqlite3 "$BOUKENSHA_DIR/sessions.db"
```

One table, `events`, holding both what the agent did and what the player
experienced:

```sql
-- every place a player was refused, traceable to the exact model call
SELECT session_id, turn, iteration, direction, reason
FROM events WHERE phase = 'journey.movement_blocked';
```

---

## 6. What a run costs, and how to cap it

**Cost is not linear in run length.** Every model call re-sends the whole
conversation, so the last iterations of a long run cost several times the first.
An 80-iteration mapping run cost **$1.07** in 166 seconds; a 12-iteration demo
costs about 15 cents.

Two ceilings in `.boukensha/settings.yaml` bound it:

```yaml
max_iterations: 25        # MUD commands per turn — the main cost lever
max_turn_tokens: 60000    # token budget per turn; 0 disables
```

Both ship set conservatively. Raise them deliberately for one run, then put them
back. `examples/mapping_run.py` and `examples/demo.py` accept the ceiling
directly so you need not edit the file at all.

---

## 7. Reading a finding

The report categories map onto recorded events:

| Category | What the agent records |
| --- | --- |
| **Blocked** | `journey.movement_blocked` with a reason — `level_gated`, `closed_door` |
| **Confused** | `journey.command_rejected` — a reasonable command the game refused |
| **Bored** | rooms revisited, turns per newly discovered room |
| **Overpowered** | health and progression from the status line on every reply |

A worked example, and the first real finding this produced:

> **The Dirt Path** refuses movement in *all four* advertised directions with
> *"This zone is above your recommended level."* Five of the corpus's six blocks
> are in that one room. A low-level player who walks in can only leave the way
> they came.

To audit that yourself: filter the dashboard to the session, open the same
session in log_viz, and read the turn where it happened. Every claim decomposes
to a model call and the MUD's exact reply.

---

## 8. What this does not yet do

Stated plainly, because a tool that oversells itself is worse than one that
under-delivers.

- **The map is self-consistent, not verified.** Its topology has never been
  compared against CircleMUD's own world files, so it reflects what the agent
  believes rather than what the world provably is. The comparison is available
  — `week0_explore/circlemud-world-parser` converts the world data to JSON — and
  simply has not been run.
- **The confusion corpus is thin.** 13 rejections across ~90 tool calls, nearly
  all one message. Enough to prove the signal works, not to characterise it.
  More runs would fix this.
- **Two rooms sharing a title *and* an exit set merge into one node.** No
  collision exists in the current data; a larger map will produce them.
  Separating them needs the path taken to reach them.
- **Compaction cannot fire mid-turn**, so a single very long run grows its
  context until it hits the model's window. Bounded in practice by
  `max_iterations`.
- **log_viz predates the journey layer** and shows only agent telemetry — no
  rooms or blocks. Metabase and the map cover those.
- **Boredom and overpoweredness are recorded but not yet scored.** The
  underlying data (visit counts, health, progression) is captured on every
  reply; no threshold has been set for when either becomes a finding.

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| MUD connects but never greets | a leaked agent process flooding it | `pgrep -af boukensha`, kill it |
| `mud-manager: command not found` | gem not installed | §3 |
| Dashboard shows stale data | `sessions.db` not rebuilt | re-run `ingest_sessions.py` |
| Metabase won't start | port 3000 taken | `docker compose down` then up, or change the port mapping |
| A run seems frozen | it prints nothing by default | `demo.py` and `play.py` show live progress; plain `run()` does not |
| Agent stops early | hit `max_iterations` | §6; check for `limit_reached` in the log |

---

## 10. How it is built

Four layers, each depending on the one before:

1. **Agent telemetry** — every turn, tool call, cost and session outcome.
2. **Journey telemetry** — MUD replies parsed into player-experience events.
3. **The world graph** — those events folded into rooms and passages.
4. **Memory** — what the agent keeps when a session outgrows its context.

The design and its trade-offs are in
[`docs/plans/observability/`](plans/observability/); the day-by-day record,
including what went wrong, is in
[`docs/technical_journal/`](technical_journal/).

The constraint the whole design serves: **when the agent stops making progress,
that is either a game defect or an agent defect, and a report is worthless if
the two cannot be told apart.** That is why agent health is measured as
carefully as player experience.
