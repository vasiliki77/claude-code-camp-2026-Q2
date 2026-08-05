"""Build .boukensha/sessions.db from the session JSONL, and report over it.

See docs/plans/observability/layer1 §2.1 for the schema decision and
obs_plan.md §5 for why SQLite rather than DuckDB.

    python examples/ingest_sessions.py            # rebuild, then print the report
    python examples/ingest_sessions.py --report   # report only, no rebuild
    python examples/ingest_sessions.py --watch    # rebuild whenever a session changes

Leave `--watch` running in a terminal and Metabase's auto-refresh does what it
looks like it does. Without it, auto-refresh re-runs the *queries* against a
database nothing is rebuilding — the same stale numbers, more often.

The database is a **cache**. The JSONL is the source of truth, stays tracked in
git, and this rebuilds from scratch every time — dropping and recreating rather
than appending, which is sub-second at this scale and removes a whole class of
partial-state bug. .boukensha/sessions.db* is gitignored.

## Journey events are derived here, not emitted live

obs_plan.md §4.1 weighed three emission points. This takes option C — parse at
ingest — because `tool_result` already carries the MUD's full reply, so nothing
is lost by deriving journey events after the fact, and two things are gained:
no agent change is needed, and the parsers apply retroactively to every session
already on disk, including the 62 recorded before Layer 2 existed.

Live emission (option B) remains available and is a small change; it becomes
worth doing when something needs to *react* to a journey event during a run
rather than read it afterwards.

## Two things the ingest does that a reader should not repeat

- **Forward-fills turn and iteration.** Only the `turn` and `iteration` events
  carry those numbers; `tool_call`, `tool_result` and `response` do not. log_viz
  re-derives them while scanning (log_viz/lib/log_viz/session.rb:71-76) and so
  would every other reader. Doing it once here makes the correlation key a
  plain indexed column.
- **Leaves missing fields NULL.** Sessions predating a field must read as
  *absent*, not zero — an unmeasured error rate and a zero error rate are
  different claims. SQLite's aggregates already do the right thing with NULL.
"""

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from boukensha import journey  # noqa: E402

# BOUKENSHA_DIR when set (what the launchers export), else the repo-root
# .boukensha — week2_capable/examples/ -> week2_capable -> repo root. Resolved
# rather than hardcoded so this runs from any checkout.
BOUKENSHA_DIR = Path(
    os.environ.get("BOUKENSHA_DIR")
    or Path(__file__).resolve().parents[2] / ".boukensha"
)
SESSIONS = BOUKENSHA_DIR / "sessions"
DB = BOUKENSHA_DIR / "sessions.db"

SCHEMA = """
DROP TABLE IF EXISTS events;
CREATE TABLE events (
  id            INTEGER PRIMARY KEY,
  session_id    TEXT    NOT NULL,
  seq           INTEGER NOT NULL,
  phase         TEXT    NOT NULL,
  at            TEXT,
  turn          INTEGER,
  iteration     INTEGER,
  name          TEXT,
  ok            INTEGER,
  duration_ms   INTEGER,
  input_tokens  INTEGER,
  output_tokens INTEGER,
  cost_usd      REAL,
  room          TEXT,
  direction     TEXT,
  reason        TEXT,
  raw           TEXT    NOT NULL
);
CREATE INDEX idx_session ON events(session_id);
CREATE INDEX idx_phase   ON events(phase);
CREATE INDEX idx_room    ON events(room);
"""


def rows_for(path):
    """Every event in one session file, plus the journey events derived from it.

    Journey rows are inserted immediately after the tool_result they came from,
    sharing its turn and iteration, so ordering in the table matches the story
    the file tells.
    """
    session_id = path.stem
    # Defaults to 1, not None. Only Repl emits `turn` events; a one-shot run
    # never does, so forward-filling from those events alone leaves every row
    # of a run like the 05-08 mapping session with turn=NULL — and
    # COUNT(DISTINCT turn) then reports 0 turns for 80 iterations of work.
    # Every event after session_start belongs to *some* turn, and the first one
    # is 1 on both paths.
    turn = 1
    iteration = None
    pending_call = None

    for seq, line in enumerate(path.read_text(errors="replace").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # A run killed mid-write can leave a torn final line. Skip it rather
            # than lose the whole session.
            continue

        phase = event.get("phase")
        if phase == "turn":
            turn = event.get("n")
        elif phase == "iteration":
            iteration = event.get("n")

        yield {
            "session_id": event.get("session_id") or session_id,
            "seq": seq,
            "phase": phase or "?",
            "at": event.get("at"),
            "turn": turn,
            "iteration": iteration,
            "name": event.get("name"),
            "ok": None if event.get("ok") is None else int(bool(event["ok"])),
            "duration_ms": event.get("duration_ms"),
            "input_tokens": event.get("input_tokens"),
            "output_tokens": event.get("output_tokens"),
            "cost_usd": event.get("cost_usd"),
            "room": None,
            "direction": None,
            "reason": None,
            "raw": line,
        }

        # The arguments live on tool_call and the reply on tool_result; the
        # parser needs both, because a refusal never names the direction.
        if phase == "tool_call":
            pending_call = event
        elif phase == "tool_result" and pending_call is not None:
            for derived in journey.parse(
                pending_call.get("name"),
                pending_call.get("args"),
                event.get("result"),
            ):
                yield {
                    "session_id": event.get("session_id") or session_id,
                    "seq": seq,
                    "phase": f"journey.{derived['event']}",
                    "at": event.get("at"),
                    "turn": turn,
                    "iteration": iteration,
                    "name": derived.get("command"),
                    "ok": None,
                    "duration_ms": None,
                    "input_tokens": None,
                    "output_tokens": None,
                    "cost_usd": None,
                    "room": derived.get("room"),
                    "direction": derived.get("direction"),
                    "reason": derived.get("reason"),
                    "raw": json.dumps(derived, separators=(",", ":")),
                }
            pending_call = None


def build():
    db = sqlite3.connect(DB)
    db.executescript(SCHEMA)
    files = sorted(SESSIONS.glob("*.jsonl"))
    total = 0
    for path in files:
        rows = list(rows_for(path))
        db.executemany(
            "INSERT INTO events (session_id,seq,phase,at,turn,iteration,name,ok,"
            "duration_ms,input_tokens,output_tokens,cost_usd,room,direction,reason,raw) "
            "VALUES (:session_id,:seq,:phase,:at,:turn,:iteration,:name,:ok,"
            ":duration_ms,:input_tokens,:output_tokens,:cost_usd,:room,:direction,:reason,:raw)",
            rows,
        )
        total += len(rows)
    db.commit()
    print(f"ingested {total} rows from {len(files)} sessions -> {DB}")
    return db


def report(db):
    def show(title, sql):
        rows = db.execute(sql).fetchall()
        print(f"\n=== {title} ===")
        if not rows:
            print("  (none)")
        for row in rows:
            print("  " + " | ".join("-" if v is None else str(v) for v in row))

    show(
        "sessions by cost",
        "SELECT session_id, COUNT(DISTINCT turn) turns, ROUND(SUM(cost_usd),4) usd "
        "FROM events GROUP BY session_id HAVING usd IS NOT NULL "
        "ORDER BY usd DESC LIMIT 5",
    )
    show(
        "tool error rate (NULL ok = session predates the fix)",
        "SELECT name, COUNT(*) calls, SUM(ok=0) failures "
        "FROM events WHERE phase='tool_result' AND ok IS NOT NULL "
        "GROUP BY name ORDER BY failures DESC, calls DESC LIMIT 8",
    )
    show(
        "how sessions ended",
        "SELECT json_extract(raw,'$.reason') reason, COUNT(*) "
        "FROM events WHERE phase='session_end' GROUP BY 1",
    )
    show(
        "journey events",
        "SELECT phase, COUNT(*) FROM events WHERE phase LIKE 'journey.%' "
        "GROUP BY phase ORDER BY 2 DESC",
    )
    show(
        "most visited rooms",
        "SELECT room, COUNT(*) visits FROM events "
        "WHERE phase='journey.room_entered' AND room IS NOT NULL "
        "GROUP BY room ORDER BY visits DESC LIMIT 8",
    )
    show(
        "why players get blocked",
        "SELECT reason, direction, COUNT(*) FROM events "
        "WHERE phase='journey.movement_blocked' GROUP BY reason, direction "
        "ORDER BY 3 DESC",
    )
    show(
        "rejected commands (the confusion signal)",
        "SELECT name, json_extract(raw,'$.text') msg, COUNT(*) FROM events "
        "WHERE phase='journey.command_rejected' GROUP BY name, msg ORDER BY 3 DESC LIMIT 8",
    )


def fingerprint():
    """Cheap change detector: how many session files there are, and the newest
    modification time among them. Catches both a new session and an existing one
    still being appended to."""
    paths = list(SESSIONS.glob("*.jsonl"))
    return len(paths), max((p.stat().st_mtime for p in paths), default=0)


def watch(interval=10):
    """Rebuild whenever the session logs change.

    Metabase's auto-refresh re-runs its *queries*; it does not re-run this. The
    dashboard is a view over a cache, so without something rebuilding the cache
    a refreshing dashboard shows the same stale numbers more often — which looks
    like live data and is not. This is that something.

    Polling rather than inotify: stdlib only, works the same on WSL and macOS,
    and at one directory of small files the cost is unmeasurable.
    """
    print(f"watching {SESSIONS} every {interval}s — Ctrl-C to stop")
    last = None
    try:
        while True:
            current = fingerprint()
            if current != last:
                build()
                sessions, _ = current
                print(f"  {sessions} sessions — dashboard is current\n", flush=True)
                last = current
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nstopped watching")


if __name__ == "__main__":
    if "--watch" in sys.argv:
        watch()
    elif "--report" in sys.argv:
        report(sqlite3.connect(DB))
    else:
        report(build())
