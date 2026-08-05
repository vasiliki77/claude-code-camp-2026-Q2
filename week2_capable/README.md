# Week 2 · Capable — the observability agent

Branched from [`week1_baseline/python/12_context`](../week1_baseline/python/12_context/README.md)
on 05-08-2026. That tree stays frozen as week 1's artifact; this one is the live
line. **Python only** — Ruby survives as a *runtime* rather than a codebase:
`mud-manager --mcp` is still the MCP daemon, and
[`log_viz`](../week1_baseline/ruby/log_viz) is still the session viewer. Neither
is edited here.

Plans: [`docs/plans/observability/`](../docs/plans/observability/) —
[`obs_plan.md`](../docs/plans/observability/obs_plan.md) for the four layers and
the technology decisions, [`layer1`](../docs/plans/observability/layer1) for the
agent-telemetry detail, [`architecture.md`](../docs/plans/observability/architecture.md)
for how the pieces fit together.

## What week 2 added

| | |
| --- | --- |
| `boukensha/tool.py` | `ToolFailure` and `classify_result` — the `ok` flag stops reporting failures as successes |
| `boukensha/tools/mcp.py` | reads the MCP `isError` flag instead of discarding it |
| `boukensha/logger.py` | `session_end` with reason and totals; `prompt` no longer re-serializes the whole history every iteration |
| `boukensha/run.py` | `on_event=` so a run is not silent for its whole duration |
| `boukensha/journey.py` | **Layer 2** — MUD replies parsed into player-journey events |

## Running it

All commands assume the repo root's virtualenv and config directory:

```sh
cd week2_capable
export BOUKENSHA_DIR="$(cd .. && pwd)/.boukensha"
PY=../.venv/bin/python
```

| Command | What it does | Cost |
| --- | --- | --- |
| `$PY -m unittest discover -s test` | 127 tests | free |
| `$PY examples/ingest_sessions.py` | rebuild `sessions.db`, print the report | free |
| `$PY examples/ingest_sessions.py --report` | report only, no rebuild | free |
| `$PY examples/compaction_gate.py` | force compaction deliberately | ~4c |
| `$PY examples/mapping_run.py` | explore and map the live MUD | **~$1** |
| `$PY examples/example.py` | local-tools REPL, no MUD | billable |

`mapping_run.py` needs CircleMUD up — `docker compose up -d` in
[`week0_explore/infrastructure`](../week0_explore/infrastructure/README.md), then
`nc localhost 4000` should greet you within a second or two. If it connects and
stays silent, check for a leaked `boukensha` process before blaming the MUD.

**Check the ceilings in `.boukensha/settings.yaml` before any run.** They are set
conservatively (`max_iterations: 25`, `max_turn_tokens: 60000`). The 05-08
mapping run raised them to 80 with the token ceiling disabled and cost $1.07 in
166 seconds — cost is not linear in iterations, because every call re-sends the
whole conversation, so the last ones cost several times the first.

## The data

`.boukensha/sessions/*.jsonl` is the source of truth and stays tracked in git —
the journal's measurements are only reproducible because those files are there.
`.boukensha/sessions.db` is a derived cache: gitignored, and rebuilt from
scratch on every ingest rather than appended to.

Journey events are **derived at ingest** rather than emitted live
(`obs_plan.md` §4.1, option C). `tool_result` already carries the MUD's full
reply, so nothing is lost by parsing after the fact, and two things are gained:
no agent change is needed, and the parsers apply retroactively to every session
recorded before Layer 2 existed.

## Known gaps, deliberately not fixed

- **Compaction cannot fire mid-turn** (`layer1` §1.6.1). The check sits outside
  the agent loop, so a mapping run — which is one long turn — grows without ever
  compacting. This sits directly under the project's core use case.
- **`wrap_up` deflates the context reading** (`layer1` §1.6.2), because the
  wind-down call runs with tools disabled and so excludes every tool definition
  from `input_tokens`.
- **No durations, no `api_retry`/`error` phases** (`layer1` §1.3–1.4), cut as
  agent-health polish the report does not depend on.
- **Nothing cleans up MCP subprocesses** when the parent is killed rather than
  exiting. A leaked REPL took the MUD down on 05-08.
