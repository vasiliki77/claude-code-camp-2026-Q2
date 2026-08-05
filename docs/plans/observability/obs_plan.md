# Observability Plan — Week 2

Umbrella plan for observability week. Splits the work into four layers, fixes
their dependency order, and records the decisions that have to be settled before
Layer 2 can be designed. Layer 1 has its own plan in [`layer1`](layer1);
Layers 2–4 get theirs once Layer 1's event substrate is trustworthy.
[`architecture.md`](architecture.md) draws how the pieces fit together and why.

---

## 1. What this week is actually for

Two audiences read the telemetry, and they are not asking the same question.

| Stream | Reader | Question |
| --- | --- | --- |
| **Agent telemetry** | us | Is the agent working, and what does a run cost? |
| **Journey telemetry** | Arcane Loop QnA | Where do players get confused, blocked, bored, overpowered? |

The second is the deliverable. In an ordinary service telemetry exists to keep
the product healthy; here **the telemetry is the product** — the report Arcane
Loop is paying for is a rendering of the agent's own event stream. That inverts
the usual priorities: the journey stream has to be first-class, structured and
queryable from the start, not something reconstructed out of logs at the end of
the week.

**The requirement that binds both streams together is attribution.** When the
agent stops making progress in a zone, that is either

- a **game** defect — the player journey is genuinely blocked, which is a
  finding; or
- an **agent** defect — bad tool call, exhausted context, hallucinated command,
  which is a bug and *not* a finding.

Every claim handed to QnA is worthless if those two cannot be told apart. That
is the single design constraint this week exists to satisfy, and it is why
Layer 1 comes first: the agent stream is the control against which the journey
stream is read.

---

## 2. Current state, measured

Read off the 62 session files in `.boukensha/sessions/` and the step-12 sources
at `week1_baseline/ruby/12_context/lib/boukensha/`.

**What already works.** `Logger` writes one JSONL file per session, flushed per
event, stamped with `session_id` and ISO-8601 `at`. Phases in use across the 62
files: `session_start` (62), `turn` (21), `iteration` (85), `prompt` (85),
`response` (85), `tool_call` (68), `tool_result` (68), `turn_end` (34),
`plan` (6). Per-response usage and cost are **fully populated — 85/85 `response`
events carry `usage`, `input_tokens`, `output_tokens` and `cost_usd`**, routed
through the `Usage` module so they are not Anthropic-only. `log_viz` already
reads these files as traces rather than logs.

That last point corrects an assumption made before opening the repo: token
accounting is *not* inert. It works per response. The gap is narrower and
elsewhere — see below.

**What does not work.** Each of these is verified, not suspected:

| Gap | Evidence |
| --- | --- |
| `ok` on `tool_result` is wrong | `agent.rb:203` logs `ok: true` unless the tool *raises*. A `run_command` 30s timeout is recorded `"ok": true` with the error text in `result`. Error rate computed from this field undercounts silently. Same defect in Python at `agent.py:290`. |
| No `session_end` | `Logger#close` writes nothing. **0 of 62** files record how the session ended — a clean exit and a crash are indistinguishable. |
| No durations | Latency exists only as a difference of `at` stamps. No per-call or per-tool duration field. |
| API failures are invisible | `agent.rb:148` rescues `ApiError` and logs `turn_end`, but emits no error event. A failed run and a completed one look alike. |
| `turn_end.tokens` mostly absent | 30 of 34 null. The 4 populated ones are the four newest files (all after 18:12 on 04-08) — i.e. `Context#turn_tokens` arrived with step 12 and the older sessions predate it. Not a bug; a coverage note. |
| `limit_reached` / `compaction` never observed | **0 occurrences in 62 sessions.** Both paths exist in `logger.rb` and have never run. A long world-mapping session is exactly what fires them for the first time. |
| `prompt` re-serializes the whole history every iteration | **85% of the largest session file (191 KB of 224 KB)** is `prompt` events. Growth is quadratic in turn length. A multi-hour mapping run is the worst case for this shape. |
| No cross-session view | 62 files, no rollup. One playthrough proves nothing about retention; the findings need N runs aggregated. |

---

## 3. The four layers

### Layer 1 — Agent telemetry (the control)

Repair and complete the existing stream so it can be trusted as evidence. Fix
the `ok` flag, add `session_end` and an error phase, add durations, stop the
`prompt` bloat, add cross-session aggregation. Nothing here is new architecture
— it is making the substrate honest.

Detailed plan: [`layer1`](layer1).

### Layer 2 — Journey telemetry (the deliverable)

A second event stream emitted from the MUD tool calls, correlated to Layer 1 by
`session_id` + `turn` + `iteration` so any finding traces back to the exact model
call that produced it. The correlation is nearly free — `Logger#write_log`
already stamps `session_id` — and it is what makes a finding auditable when QnA
pushes back on it.

Candidate events, drawn from what `MudManager::Primitives` already exposes
(`week0_explore/mud_manager/lib/mud_manager/primitives.rb`, 40+ primitives across
`perception`, `movement`, `combat`, `objects`, `communication`):

- `room_entered` — room identity, exits seen, first visit or repeat
- `movement_blocked` — direction and the MUD's refusal text
- `command_rejected` — `Huh?!?`, `You do not see that here`
- `combat_resolved` — target, hp delta, outcome, flee
- `progression` — xp / level / gold deltas

The four report categories then become measurable rather than impressionistic:

| Category | Signal |
| --- | --- |
| Confused | command-rejection rate; repeated `look`/`examine` on one target; re-reading an already-described room |
| Blocked | same exit attempted N times and refused; a room whose only exits are locked with no key reachable upstream |
| Bored | turns-per-newly-discovered-room rising; repeated identical command sequences; runs of rooms with no interactable content |
| Overpowered | combat won at ~zero hp loss; xp/turn spiking; level far above the zone's design level |

**Layer 2 cannot be designed until §4's decisions are settled**, because where
the events are emitted determines what they can contain.

### Layer 3 — The world graph

Rooms as nodes, exits as edges, each annotated with the Layer 2 events that
occurred there. This is simultaneously the "map the world" deliverable, the
substrate the blocked/bored analysis runs over, and the most legible artifact to
put in front of a non-engineer. Progression paths are traversals of it.

Depends on Layer 2 having a stable room identity — see §4.2.

### Layer 4 — Memory and compaction

Also in scope this week. `Context#compact_messages!` drops the oldest 40% of
messages and snaps to a user boundary — **pure deletion: no summarization,
nothing persisted** — and it has fired **0 times in 62 sessions**. So the
behaviour most likely to first appear mid-play is the one with the least
evidence behind it, exactly as [week 1](../../technical_journal/week1.md)
predicted.

Memory and observability are the same question from two ends: you cannot judge a
compaction strategy without telemetry showing *what was dropped* and *whether
the agent re-discovered it*. The world graph (Layer 3) is the natural thing to
compact *into* — a map is a summary of exploration that survives the messages
being dropped.

**Scoped down to observation only this week** (see §5.3): force compaction, log
what it destroys, and record whether the agent re-walked mapped ground.
Redesigning it is a separate piece of work.

**Observed 05-08.** Compaction fired for the first time in any recorded session
and behaved as written — it drops the oldest messages and keeps nothing. Two
defects surfaced with it, detailed in [`layer1`](layer1) §1.6.1–1.6.2 and
deferred:

- **It cannot fire mid-turn.** The check sits outside the agent loop, so a
  single long turn — which is exactly what a mapping run is — grows without ever
  compacting until it hits the context window.
- **`wrap_up` deflates the reading it depends on**, because the wind-down call
  excludes tool definitions from `input_tokens`.

Both sharpen the case for this layer rather than weakening it: **the redesign
this layer contemplates is not optional polish.** As it stands the agent cannot
compact during the one activity the project exists to perform, and the world
graph is the summary it should be compacting into.

---

## 4. Decisions to settle

These block Layer 2's design and should be answered during Layer 1, not after.

### 4.1 Where do journey events get emitted?

Three options, and they are not equivalent:

| Option | Where | Trade-off |
| --- | --- | --- |
| **A — in `mud_manager`** | the Ruby gem, at primitive level | Sees raw MUD output before any model interpretation; cleanest attribution. But the gem runs over MCP as a *subprocess*, so it does not know `session_id`/`turn` — correlation has to be threaded in over the wire. |
| **B — in `boukensha`** | the MCP tool wrapper, `tools/mcp.rb` | Already inside the agent, so `session_id`/`turn`/`iteration` are in scope for free. Sees the tool result as a string, so parsing MUD prose happens here. |
| **C — post-hoc** | a reader over the existing JSONL | Zero instrumentation cost, works on the 62 sessions already on disk. But it can only see what `tool_result` recorded, and it re-parses on every read. |

Leaning **B**, with the parsing rules kept in a module that C could also call —
that keeps correlation free and leaves the door open to re-deriving journey
events from archived sessions. Worth an explicit decision before Layer 2 starts.

### 4.2 What is a room's identity?

The agent sees room *descriptions*, not vnums. Two rooms with identical
descriptions (a corridor tile repeated) are one node or two depending on how
identity is defined, and the whole graph's shape follows from the answer.
Options: description hash; description hash + exit set; path-from-origin. Needs
settling before Layer 3 — it is the highest-leverage modelling choice in the
project.

### 4.3 Does the journey stream share the session file?

Same JSONL with a `phase` namespace (`journey.room_entered`), or a sibling
`journeys/` file keyed by `session_id`? Sharing keeps correlation trivial and
`log_viz` gets it for free; separating keeps QnA's artifact clean and lets the
two streams be retained on different schedules.

---

## 5. Technology decisions

Recorded 05-08-2026. **Cost was not the deciding factor.** OpenTelemetry is
Apache-2.0, and every backend worth considering — Jaeger, Grafana + Tempo,
SigNoz, Langfuse, Phoenix — self-hosts at $0. "Free" narrows nothing here, so
the decision turned on what the deliverable is and what the stack can afford to
carry.

| Concern | Choice | New dependency |
| --- | --- | --- |
| Emission | existing `Logger`, stdlib JSON on both sides | none |
| Storage (source of truth) | JSONL in `.boukensha/sessions/` | none |
| Trace viewing | `log_viz` (Sinatra), already reads these as traces | none |
| Aggregation | **SQLite** — schema in [`layer1`](layer1) §2.1 | none: `sqlite3` CLI and Python's stdlib `sqlite3` are both already present |
| World graph (Layer 3) | Graphviz for static SVG, Mermaid for embedding in the journal | Graphviz (distro package) |
| Charts | inline SVG in ERB, as `log_viz` already does for context bars | none |

Current dependency footprint for reference — Ruby: `dotenv`, `charm`,
`mud_manager`; Python: `python-dotenv`, `PyYAML`, `textual`; `log_viz`:
`sinatra`, `puma`, `rackup`. Layer 1 adds nothing to any of them.

### 5.1 Not OpenTelemetry — and when to revisit

Two reasons, neither of them price:

1. **No general-purpose tracing backend renders the deliverable.** Jaeger shows
   spans and latency; it will never show that a room is a dead end or that a
   door needs a key no reachable NPC carries. The world map and the journey
   findings are domain artifacts that have to be built either way — at which
   point the tracing backend is just a second home for the same data.
2. **Operational weight.** CircleMUD already runs in Docker on WSL2. A collector
   plus Tempo plus Grafana is three more containers and a config surface, during
   a week whose week-1 record is largely *signal* problems — a stdio server
   indistinguishable from a hang, an env var ignored in silence. Putting a
   network hop between emission and storage adds exactly that failure class.

**Revisit when there is a genuinely distributed trace to follow** — if
`mud_manager` moves across a network boundary and one trace ID has to span both
processes. Waiting is cheap by construction: `turn` → span, `iteration` → child
span, `tool_call` → child span is a converter over the same JSONL, not a
rewrite, and the correlation fields Layer 2 needs (`session_id` + `turn` +
`iteration`) are the same ones an exporter would want.

A third reason, recorded because it is the one most likely to be questioned:
**the course reference implementation uses OpenTelemetry with Docker, and this
project deliberately diverges.** Reproducing a collector plus a tracing backend
reproduces the *emission* and *trace-explorer* half of an observability
pipeline. The half that carries the weight here — landing telemetry in a
queryable store, reconciling two streams into one canonical shape, and serving a
report off it — is not what a collector does, and is exactly what §3's layers
and [`layer1`](layer1) §2.1 build. Skipping the collector removes containers,
not capability.

### 5.2 Known limit of JSONL-on-disk

No retention policy, no rotation, no index. Irrelevant at 62 sessions / ~700 KB,
and more so once [`layer1`](layer1) §1.5 removes the prompt bloat. If mapping
runs ever produce gigabytes, that is the signal to revisit storage — not before.

### 5.3 Scope: the minimum effective path

Week 2 is self-directed — the theme is fixed, the implementation is not. The
scope below is chosen as the shortest path that still produces the deliverable
the brief asks for: an agent that maps the world and reports where players get
confused, blocked, bored or overpowered.

Everything cut is cut for one of two reasons — **it does not serve that
deliverable**, or **it duplicates something already covered**.

| In | Out, and why |
| --- | --- |
| `session_end`, and a truthful `ok` flag | durations, `api_retry`/`error` phases — agent-health polish; nothing in the report depends on them |
| `prompt` payload trim | kept only because long mapping runs otherwise write 200 KB+ files |
| three journey event types: `room_entered`, `movement_blocked`, `command_rejected` | the fuller event set in §3 — three carry all four report categories |
| one SQLite table, one ingest, canned queries | a second table and a canonical view joining them — one table answers the same questions at this size |
| Graphviz world graph | a BI tool — the graph *is* the dashboard for this deliverable |
| compaction exercised and observed (§3, Layer 4) | compaction redesigned — a separate piece of work with its own plan |
| `log_viz` as it stands | OTel collector and tracing backend — see §5.1 |

**The cheap version of the `ok` fix is the one to take**: read the MCP `isError`
flag for MCP tools and the `error:` prefix for local ones, rather than the
result-type refactor in [`layer1`](layer1) §1.1 option B. It is a handful of
lines, it is correct for every tool the MUD work actually calls, and the refactor
stays available if a later week needs it.

---

## 6. Deliberately out of scope

- **No evals.** Scoring whether the agent played *well* is a different week.
  This week only has to make what it did visible.
- **No live Arcane Loop data.** CircleMUD is the whole environment, per the
  brief.

---

## 7. Order of work and verification gates

Scoped to the minimum effective path of §5.3.

1. **`session_end` + truthful `ok`.** *Gate:* a deliberately failing tool and a
   `Ctrl-C` both show up correctly in the JSONL.
2. **`prompt` payload trim.** *Gate:* a long session's file is dominated by real
   events rather than re-serialized history, and `log_viz` renders it unchanged.
3. **Decisions §4.1–4.3 recorded** in this document before Layer 2 starts.
4. **Layer 2 — three journey event types.** *Gate:* every journey event resolves
   back to a `session_id` + `turn` + `iteration` present in the agent stream.
5. **SQLite ingest + canned queries.** *Gate:* runs over all 62 existing files
   without special-casing; absent fields read as absent, not zero.
6. **Layer 3 graph.** *Gate:* a mapping run over a known CircleMUD zone
   reproduces that zone's real topology.
7. **Layer 4 — force compaction and observe it.** *Gate:* the `compaction` event
   appears for the first time in a real session, and the queries can say whether
   the agent re-walked ground it had already mapped.

**Python only, decided 05-08.** The app is Python from here, so
`week2_capable/` is the single tree that changes and the
week-1 parity discipline no longer applies. Ruby does not disappear — it stays
as a *runtime*: `mud-manager --mcp` is a Ruby gem and remains the MCP daemon,
and `log_viz` is a Ruby reader of the JSONL that works unchanged against
Python-written sessions. Neither is edited.

One consequence worth recording: decision §4.1 settles itself. Python has no
in-process MUD tool module — the MCP path is the only path — so emitting journey
events in the MCP wrapper covers every MUD call there is.
