# Layer 1 Plan — Agent telemetry

Child of [`obs_plan.md`](obs_plan.md) §3; drawn in
[`architecture.md`](architecture.md). Scope: make the existing session
stream honest and complete, so it can serve as the **control** the journey
stream (Layer 2) is read against. No new architecture — the JSONL-per-session
shape stays, `log_viz` stays the reader, and every change lands in
`week2_capable/` — branched from `week1_baseline/python/12_context` on 05-08,
which stays frozen as week 1's artifact.

The premise of the layer: *a finding about the game is only credible if the same
run can prove the agent itself was healthy.* Every item below is either a place
where the stream lies, or a place where it is silent about something that
distinguishes an agent failure from a game failure.

---

> **Scope note (05-08).** `obs_plan.md` §5.3 trims this week to the minimum
> effective path. Of the six defects below, **§1.1 (cheap variant), §1.2 and
> §1.5 are in scope**; §1.3 and §1.4 are deferred as agent-health polish the
> report does not depend on, and §1.6 becomes a gate rather than a fix. The full
> analysis stays here because the deferred items are real and will be wanted the
> first time a run fails in a way the current stream cannot explain.

## 1. Six defects

Ordered by how badly each one corrupts a conclusion, not by effort.

### 1.1 `tool_result.ok` is wrong

`agent.rb:195–208` (Ruby) / `agent.py:288–296` (Python):

```ruby
begin
  result = @registry.dispatch(name, args)
  @logger.tool_result(name: name, result: result, ok: true)
rescue StandardError => e
  @logger.tool_result(name: name, result: result, ok: false, error: e.message)
end
```

`ok: false` is reached only when the tool **raises**. But the standard-library
tools do not raise — they return an error *string*, via the `oops` lambda in
`tools/shell.rb:31` and `tools/file_system.rb:43`:

```ruby
oops = ->(msg) { "error: #{msg}" }
```

So a `run_command` that times out after 30s is logged `"ok": true` with
`"result": "error: command timed out after 30s: …"` — an observed event in
`.boukensha/sessions/20260804T171943Z-6e8a2f67.jsonl`. Any error rate derived
from `ok` undercounts, silently, and undercounts *exactly* the failures that
look like the agent getting stuck.

Only `Registry#dispatch`'s `UnknownToolError` (`registry.rb:21`) and genuine
exceptions inside a tool body reach the `false` branch today.

**Fix — two options.**

| | Change | Cost | Risk |
| --- | --- | --- | --- |
| **A — sniff the prefix** | logger treats a result matching `/\Aerror: /` as `ok: false` | ~3 lines | stringly-typed; a legitimate tool result beginning "error: " is misclassified; the convention is undocumented and MCP tools do not follow it |
| **B — real result type** | `oops` returns a `Tool::Failure` (or a `{ok:, value:, error:}` struct); `dispatch` and the logger read the flag | touches both tool files, `registry.rb`, `agent.rb`, and every `next target if target.start_with?("error:")` guard (`file_system.rb:78, 93, 109`) | wider blast radius, but removes a convention that is *already* being pattern-matched by string prefix in five places |

**Taking A this week**, per `obs_plan.md` §5.3 — extended to read the MCP
`isError` flag for MCP tools, which is where every MUD command arrives from in
Layer 2. That covers every tool the work actually calls, in a handful of lines.
B stays the right long-term answer and the analysis below stands.

**Why B is the better fix.** The `start_with?("error:")` guards already scattered through
`file_system.rb` are the same defect showing up in the tools themselves — the
codebase has invented an error type and is checking it by prefix. Making it real
fixes the telemetry and those guards in one move. Prefix-sniffing alone also
cannot see MCP failures, which is where every MUD command arrives from in
Layer 2 — hence the `isError` extension above, which is the part of A that is
not optional.

Either way, `tools/mcp.rb` is where the MCP `isError` flag has to be read rather
than flattened into text. Under A it sets the log flag directly; under B it maps
onto the same result type as everything else.

### 1.2 No `session_end`

`Logger#close` (`logger.rb`) closes the IO and writes nothing. **0 of 62**
session files record how the session ended. A clean exit, a `SIGINT`, and a
crash inside the agent loop are indistinguishable on disk — and "the session
just stops" is precisely the shape a blocked player journey also has.

**Fix.** `Logger#close(reason:)` writes a final
`{"phase":"session_end","reason":…,"turns":…,"total_tokens":…,"total_cost_usd":…,"duration_s":…}`.
Reasons: `completed`, `interrupted`, `error`. Wire it from the REPL/TUI exit
paths and from an `ensure` so an exception still produces the event. Session
totals belong here rather than being re-summed by every reader.

Note the crash-on-quit bug recorded in the 04-08 journal entry — the TUI's exit
path is already known to be fragile, so this fix needs testing against quit,
`Ctrl-C`, and an exception raised mid-turn.

### 1.3 API failures emit nothing

`agent.rb:143–152`: `wrap_up` rescues `ApiError` and logs `turn_end`, but there
is no event saying the call failed. `Client#call` (`client.rb:25`) retries
internally (`retryable_response?`, `retry_delay`) and those retries are invisible
too — a turn that succeeded after three 529s looks identical to one that
succeeded first time, except for wall-clock.

**Fix.** Two new phases:

- `api_retry` — `{attempt, delay_s, status, model}`, written from `client.rb`'s
  retry path.
- `error` — `{scope: "api"|"tool"|"agent", class:, message:, fatal: bool}`,
  written wherever an exception is rescued.

`log_viz` should render these inline; a run with retries is a run whose latency
numbers need an asterisk.

### 1.4 No durations

Every duration is currently a subtraction of `at` stamps by the reader, which
works only because events are flushed synchronously and never interleave. That
is a property worth not depending on.

**Fix.** Add explicit `duration_ms`:

| Event | Measures |
| --- | --- |
| `response` | the model round-trip, timed around `@client.call` in `agent.rb:53` |
| `tool_result` | tool execution, timed around `@registry.dispatch` |
| `turn_end` | wall-clock for the whole turn |
| `session_end` | wall-clock for the session |

This is the field that separates "the agent is thinking" from "the MUD is slow"
— a distinction Layer 2 needs when it starts calling `mud_manager` over MCP.

### 1.5 `prompt` events dominate the file

`Logger#prompt` serializes **the entire message history on every iteration**.
Measured: in the largest session on disk
(`20260804T171943Z-6e8a2f67.jsonl`, 224 KB) the `prompt` events account for
**191 KB — 85% of the file**. Growth is quadratic in turn length. A multi-hour
world-mapping run is the worst case for this shape, and Layer 2 makes runs
longer, not shorter.

**What actually reads it:** `log_viz/lib/log_viz/session.rb:77–86` reads
`event["messages"]&.last`, and only when `pending_user` is set — i.e. it wants
*the user message that opened the turn*, nothing else. `context_window` is read
from the `session_start` snapshot (`session.rb:155`), not from `prompt`.

**Fix.** Keep `message_count`, `tool_count`, `tools`, `context_window` on every
`prompt` event. Include `messages` **only when the last message's role is
`user`** — which is exactly the case `log_viz` consumes, so the viewer needs no
change and the reconstruction stays possible from `response` / `tool_result`
events. Optionally gate full-history dumps behind `Boukensha.debug?`, as
`Logger#raw` already is.

Expected effect on the measured file: ~191 KB → a few KB.

### 1.6 `limit_reached` and `compaction` have never run

**0 occurrences across all 62 sessions.** Both are implemented —
`logger.rb` (`limit_reached`, `compaction`), fired from `agent.rb:40–45` and
`compact_if_needed` — and both are on the path a long mapping session takes for
the first time. `log_viz` already switches on `compaction` (`session.rb:86`).

**CLOSED 05-08.** Both fired, via `examples/compaction_gate.py` — three short
turns on one context with the threshold overridden on the context object rather
than in `settings.yaml`, so an interrupted run leaves no dangerous config
behind. `limit_reached` ×2, `compaction` ×2 (dropping 7 messages then 6), 4.1
cents, and **no 400** — the failure the 12-context journal warned about did not
occur, because compaction runs at a turn boundary where the message list already
ends cleanly.

Closing the gate surfaced two defects, both real and both **out of scope this
week** (§5.3's minimum path), recorded here because the first will bite as soon
as a mapping run gets long:

### 1.6.1 Compaction cannot fire mid-turn

`Agent.run` calls `_compact_if_needed()` at `agent.py:63`, **outside and before**
the `while True` loop. Compaction is therefore evaluated **once per turn, at
turn start**, when a one-shot run's context is still empty.

**A mapping run is one long turn.** Its context only grows — the 05-08 run went
from 4,117 to 20,568 tokens across 80 iterations with no opportunity to compact
at any point. A long enough run reaches the context window and fails instead of
compacting, and that is the project's core use case rather than an edge of it.

It also explains why the 400 above did not appear: a mid-turn compaction is
exactly the one that could orphan a `tool_result`, and mid-turn compaction
currently cannot happen. **The two findings are the same fact seen from
opposite sides** — fixing the first makes the second reachable, so they have to
be fixed together.

### 1.6.2 `wrap_up` deflates the context reading

A turn ending on `max_iterations` calls the model once more with **tools
disabled** (`wrap_up`). That call's `input_tokens` excludes all 26 tool
definitions, and `record_usage` writes it straight into `current_tokens`. Turn 1
of the gate reported **917 tokens** with ~4.5k actually in play; turn 3 reported
948 after genuinely spending 13,946.

Compounded with §1.6.1 the effect is perverse: **compaction is least likely to
fire right after the turns that worked hardest**, because those are the turns
that end on a ceiling and therefore end with a deflated reading.

---

## 2. Cross-session aggregation

62 session files, no rollup. One playthrough proves nothing — every question the
brief asks is about a *population* of runs.

**Deliverable:** a reader (extending `log_viz`, or a `bin/` script feeding it)
that walks `.boukensha/sessions/*.jsonl` and reports per session and in
aggregate:

- turns, iterations, wall-clock
- total input/output tokens, total `cost_usd`
- tool-call counts by name, **and error rate by tool name** (needs §1.1)
- turn end reasons: `completed` / `max_iterations` / `max_tokens` (needs §1.2 for
  the session-level equivalent)
- API retry and error counts (needs §1.3)
- p50/p95 model latency and tool latency (needs §1.4)

**Constraint:** it must run over the 62 files already on disk without
special-casing them. Older sessions lack the new fields; they should read as
absent, not as zero — an unmeasured error rate and a zero error rate are
different claims, and conflating them is the same class of bug as §1.1.

This rollup is also the natural home for the Layer 2 aggregates later, so its
reader shape should not assume agent-only events.

### 2.1 Storage: SQLite

Decided 05-08-2026; see [`obs_plan.md`](obs_plan.md) §5 for the wider technology
decision. **Zero installs** — the `sqlite3` CLI is already on the box (3.45.3)
and Python's `sqlite3` is stdlib (3.46.0, JSON functions confirmed working). The
Ruby `sqlite3` gem is *not* installed, which is fine: the rollup is a read-side
tool and does not have to be Ruby. That only changes if the aggregate view moves
into `log_viz` later — one `gem install sqlite3` at that point, and worth
deferring until there is a reason to render it in a browser.

DuckDB was considered and rejected. Its advantage is querying the JSONL glob in
place with no ingest step; at 62 files and ~700 KB the performance argument that
normally favours it is irrelevant, and an unfamiliar tool is an extra debugging
surface in a week already spent on signal problems.

**The ingest step pays for itself twice.**

- **It forward-fills the correlation key once.** `turn` and `iteration` appear
  only on their own events — `tool_call`, `tool_result` and `response` carry
  neither. `log_viz` already reconstructs them by carrying
  `current_turn` / `current_iteration` forward while scanning
  (`log_viz/lib/log_viz/session.rb:71–76`), and every future reader would have to
  repeat that. Doing it at ingest turns the key Layer 2 needs into an indexed
  column.
- **NULL gives the absent-vs-zero rule for free.** The constraint above requires
  older sessions' missing fields to read as absent rather than zero. Store them
  NULL and SQLite does it automatically: `AVG` skips NULLs, `COUNT(col)` counts
  only non-null.

**Schema.** One wide table; promote only what gets grouped and filtered on, keep
the original object for the tail.

```sql
CREATE TABLE events (
  id            INTEGER PRIMARY KEY,
  session_id    TEXT    NOT NULL,
  seq           INTEGER NOT NULL,   -- line number within the file
  phase         TEXT    NOT NULL,
  at            TEXT    NOT NULL,   -- ISO-8601
  turn          INTEGER,            -- forward-filled at ingest
  iteration     INTEGER,            -- forward-filled at ingest
  name          TEXT,               -- tool name, where applicable
  ok            INTEGER,            -- NULL for files predating the §1.1 fix
  duration_ms   INTEGER,
  input_tokens  INTEGER,
  output_tokens INTEGER,
  cost_usd      REAL,
  raw           TEXT    NOT NULL    -- the original object, for json_extract
);
CREATE INDEX idx_session ON events(session_id);
CREATE INDEX idx_phase   ON events(phase);
```

Keeping `raw` means Layer 2's journey events land in the same table with no
migration — `json_extract(raw, '$.room_id')` covers whatever that schema turns
out to be.

**Example queries** for two of the §2 bullets:

```sql
-- error rate by tool (§1.1 must land first, or ok is NULL throughout)
SELECT name,
       COUNT(*)    AS calls,
       SUM(ok = 0) AS failures,
       ROUND(100.0 * SUM(ok = 0) / COUNT(*), 1) AS pct
FROM events WHERE phase = 'tool_result'
GROUP BY name ORDER BY failures DESC;

-- cost and turns per session
SELECT session_id, COUNT(DISTINCT turn) AS turns, ROUND(SUM(cost_usd), 4) AS usd
FROM events GROUP BY session_id ORDER BY usd DESC;
```

**The watcher, and the hazard it introduced.** `--watch` rebuilds whenever the
session logs change, because Metabase's auto-refresh re-runs its *queries* and
not this pipeline — a dashboard refreshing over a database nobody rebuilds shows
stale numbers more often, with a spinner that reads as "live".

But a long-running watcher holds whatever code it imported at startup, and this
ingest **drops and recreates**. So editing a parser under a running watcher does
not merely fail to add the new events — it **deletes them from a database
something else built correctly**. Observed on 05-08: a watcher started at 15:57
stripped every `journey.progression` row out of the warehouse for an hour, ten
seconds at a time, while the parser that produced them sat correct on disk and
its tests passed.

Fixed by having the watcher compare `boukensha/**/*.py` mtimes against its own
start time and `os.execv` itself before rebuilding. **The check runs before the
rebuild, not after**, because a rebuild with stale parsers is the destructive
act.

**Operational rules.**

- `.boukensha/sessions.db` is a **derived artifact** — gitignored, regenerable
  from the JSONL at any time. The JSONL stays the source of truth. The
  `.gitignore` precedent is the generated CircleMUD world data.
- **Ingest is idempotent by rebuild**, not by append: drop and recreate. It is
  sub-second at this scale and removes a whole class of partial-state bug.
- Build it **after** §1.1–1.4 land — otherwise it is an aggregator over columns
  that are still empty.

---

## 3. Event schema after Layer 1

Changed and new events (unchanged phases omitted):

| Phase | Status | Fields added |
| --- | --- | --- |
| `prompt` | changed | `messages` now conditional (§1.5) |
| `tool_result` | changed | `ok` now truthful; `duration_ms` |
| `response` | changed | `duration_ms` |
| `turn_end` | changed | `duration_ms` |
| `api_retry` | **new** | `attempt`, `delay_s`, `status`, `model` |
| `error` | **new** | `scope`, `class`, `message`, `fatal` |
| `session_end` | **new** | `reason`, `turns`, `total_tokens`, `total_cost_usd`, `duration_s` |

All events keep the existing `session_id` + `at` stamping from
`Logger#write_log`. Nothing is renamed and nothing is removed, so every existing
session file stays readable — required, since §2 has to run over them.

---

## 4. `log_viz` impact

- §1.5 is designed to need **no** viewer change (see the analysis above).
- `api_retry`, `error`, `session_end` need new `when` branches in
  `session.rb`'s event switch and entry types to render. `compaction`,
  `reasoning` and `plan` are the precedent for how that is done.
- §2's aggregate view is new — `views/index.erb` already lists sessions with
  peak-context and cost chips, so it is the place to extend rather than a new
  app.

---

## 5. Python only

**Decided 05-08.** The app is Python from here, so `week2_capable/` — branched
that day from `week1_baseline/python/12_context`, which stays frozen as week 1's
artifact — is the only tree that changes. The Ruby analysis throughout this document stays
because that is where the defects were first found and the file references are
still the clearest statement of each one — but `week1_baseline/ruby/12_context/`
is not being edited.

Ruby remains as a runtime rather than a codebase, exactly as week 1 concluded:

| Stays | Role |
| --- | --- |
| `mud-manager --mcp` | the MCP daemon, spawned as a subprocess; Python's only route to the MUD |
| `log_viz` | a JSONL reader; works unchanged against Python-written sessions |

`log_viz` being Ruby is now a feature rather than a parity chore — **a Python
session rendering correctly in a Ruby viewer is a free check that the event
schema is what the reader expects**, and it is the cheapest schema test
available.

---

## 6. Tests

Existing test dirs (`week1_baseline/ruby/12_context/test/`,
`week2_capable/test/`) are the pattern to follow.

| Test | Asserts |
| --- | --- |
| `test_tool_result_errors` | a tool returning a failure logs `ok: false`; a raising tool logs `ok: false`; a successful tool logs `ok: true` |
| `test_session_end` | clean exit, interrupt and mid-turn exception each write `session_end` with the right `reason` |
| `test_api_errors` | a retried call emits `api_retry`; a fatal `ApiError` emits `error` with `fatal: true` |
| `test_prompt_payload` | `messages` present when the last role is `user`, absent otherwise; `message_count` always present |
| `test_durations` | `duration_ms` present and plausible on `response`, `tool_result`, `turn_end` |
| `test_rollup` | the aggregator runs over a fixture set mixing old and new schema; missing fields report as absent, not zero |

---

## 7. Order of work

1. §1.1 result type — blocks the error rate in §2.
2. §1.2 `session_end` + §1.3 error/retry phases.
3. §1.4 durations.
4. §1.5 prompt payload — verify `log_viz` renders unchanged.
5. §1.6 forced limit/compaction run — **gate before any long session**.
6. §2 rollup — SQLite ingest (§2.1) over all 62 existing files.

**Exit gate for Layer 1:** a run with a deliberately failing tool, a forced
`max_iterations` stop, a forced compaction and a `Ctrl-C` produces a session file
in which each of those four events is individually identifiable — and the rollup
reports them without hand-editing. At that point the agent stream can be trusted
as the control, and Layer 2 can start.

---

## 8. Open decisions

- **§1.1 A or B.** Recommendation is B; A is cheaper and reversible if the blast
  radius turns out worse than it looks.
- **Does `session_end` carry totals, or does the rollup re-derive them?**
  Carrying them makes each file self-describing (the argument
  `Logger#execution_metadata` already makes for per-response cost) but duplicates
  state the reader can compute.
- **Do `api_retry` events belong in the session file at all**, or in a separate
  operational log? They are the one class of event here that is about *our*
  infrastructure rather than the agent's behaviour.
