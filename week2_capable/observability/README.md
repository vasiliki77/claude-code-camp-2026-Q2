# The BI layer — Metabase over `sessions.db`

Dashboards over the session warehouse. This is the last stage of the pipeline:

```
agent  →  JSONL  →  sessions.db  →  Metabase
         (truth)    (warehouse)     (this)
```

## Run it

From a fresh clone, three commands:

```sh
# 1. build the warehouse from the session logs (free, offline)
cd ../                       # week2_capable
BOUKENSHA_DIR="$(cd .. && pwd)/.boukensha" ../.venv/bin/python examples/ingest_sessions.py

# 2. start Metabase
cd observability
docker compose up -d

# 3. build the dashboard
python3 provision.py
```

Then open the URL it prints. Sign in with
`observability@arcaneloop.local` / `ArcaneLoop2026!` (override with
`MB_ADMIN_EMAIL` / `MB_ADMIN_PASSWORD`).

`provision.py` is standard-library only — no virtualenv needed — and idempotent:
run it again and it updates in place rather than creating duplicates.

**Verified from scratch**: `docker compose down -v` destroys the application
database entirely, and the two commands above rebuild the whole dashboard.

## Why a provisioning script instead of a committed dashboard

Metabase stores accounts, questions and dashboards in its own application
database, separate from the data it reads. The OSS edition has no serialization
export — that is a paid feature — so a dashboard cannot be checked into the repo
as a file.

Rebuilding through the API is the reproducible alternative, and it has a side
benefit: **the questions are readable as SQL in `provision.py`** rather than
buried in a UI. What the dashboard claims, and how it computes it, is reviewable
in a diff.

## `session_id` is the correlation key

The same identifier addresses a run in both tools:

| | |
| --- | --- |
| log_viz | `http://localhost:4567/sessions/<session_id>` |
| Metabase | the **Session** filter at the top of the dashboard |
| SQLite | `SELECT … FROM events WHERE session_id = '<session_id>'` |
| On disk | `.boukensha/sessions/<session_id>.jsonl` |

They match because they all derive from the session filename — log_viz serves
`/sessions/:id` from `<id>.jsonl`, and the ingest reads the same value out of
the file. Checked across all 69 sessions.

That makes the path run both ways:

- **Aggregate → detail.** Something looks wrong in a chart; click the session in
  the index and log_viz opens that run's turn-by-turn trace.
- **Detail → aggregate.** Something looks odd in a trace; paste its id into the
  Session filter and the whole dashboard narrows to that run.

The filter is a free-text box rather than a dropdown, because a native-SQL
variable cannot enumerate its own values. Copy an id from the index or from a
log_viz URL.

## What the two tools each show

They are not redundant — they read the same events for different questions.

| | log_viz | Metabase |
| --- | --- | --- |
| Scope | one session | across all sessions |
| Shows | turn-by-turn trace, prompts, per-call cost, context pressure | aggregates, rates, the journey findings |
| Journey events | **no** — it predates Layer 2 | yes |
| `session_end` | no | yes |

log_viz is Ruby and deliberately unmodified this week, so it ignores phases it
does not know rather than failing on them.

## Keeping it honest

**`sessions.db` is a cache and goes stale.** It is rebuilt from the JSONL, never
appended to. Metabase reads the database, not the log files.

**Metabase's auto-refresh does not help**, and is actively misleading about it:
it re-runs the *queries*, not the pipeline that fills the database. A dashboard
refreshing every minute over a database nobody is rebuilding shows the same
stale numbers more often, with a spinner that reads as "live". Observed exactly
that — 70 sessions on disk, 69 in the database, a dashboard refreshing happily.

Leave the watcher running:

```sh
cd ../          # week2_capable
BOUKENSHA_DIR="$(cd .. && pwd)/.boukensha" ../.venv/bin/python examples/ingest_sessions.py --watch
```

It polls the sessions directory and rebuilds within ten seconds of a session
appearing *or growing* — the second matters, because a long run appends for
minutes before it ends. Without it, run `ingest_sessions.py` by hand after every
agent run.

The database is mounted **read-only** into the container. Metabase must not
write to it, and anything it did write would be destroyed by the next ingest.

**Dashboards are not version-controlled** — they live in the container's
application database. `provision.py` is the source of truth for them; the
container is disposable.
