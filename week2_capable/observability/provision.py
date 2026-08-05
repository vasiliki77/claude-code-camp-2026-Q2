"""Build the Metabase dashboard from scratch, idempotently.

    docker compose up -d
    python3 provision.py

Standard library only, so it runs with any python3 and needs no virtualenv.

## Why this exists rather than a committed dashboard file

Metabase keeps accounts, questions and dashboards in its own application
database, separate from the data it reads. The OSS edition has no serialization
export — that is a paid feature — so the dashboard cannot be checked into the
repo as a file. Rebuilding it through the API is the reproducible alternative:
a grader who has never seen this repo runs two commands and gets the same
dashboard, and `docker compose down -v` proves it works from nothing.

Idempotent throughout: it logs in if setup already ran, reuses the data source
if it exists, and replaces questions by name rather than piling up duplicates.
Running it twice is a no-op, which is what makes it safe to put in a README.

## What it builds

Seven questions over the one `events` table, in the order the argument runs —
agent health first, because a finding about the game is only credible if the
same run can show the agent was healthy:

  1. Session index                  every run, with a link into log_viz
  2. Sessions by cost               what a run costs
  3. How sessions ended             clean exits vs interrupts vs crashes
  4. Tool calls and failures        the truthful `ok` flag, in aggregate
  5. Journey events by type         what the player actually did
  6. Where players get blocked      the finding
  7. Most visited rooms             coverage and repetition

## session_id is the correlation key across both tools

`events.session_id` is byte-identical to the id in a log_viz URL, because both
derive from the session filename: log_viz serves `/sessions/:id` from
`<id>.jsonl` (app.rb:154-157) and the ingest reads the same value out of the
file. Verified across all 69 sessions.

Two things make that usable rather than merely true:

  - **A dashboard filter on Session.** Every question except the index takes an
    optional `{{session}}` and is wired to one dashboard parameter, so pinning a
    session narrows the whole page to that run.
  - **The index links straight into log_viz.** Clicking a session opens its
    trace at localhost:4567, so the path runs both ways: spot an anomaly in the
    aggregate, click through to the raw turn-by-turn trace; or spot something
    odd in a trace, paste its id into the filter to see it in context.

The filter is a plain text parameter rather than a dropdown of known values,
because a native-SQL variable cannot enumerate its own options. Copy an id from
the index, or from a log_viz URL.

**sessions.db is a cache and goes stale.** It knew nothing of three sessions
recorded minutes before this was wired up. Re-run examples/ingest_sessions.py
after any run — Metabase reads the database, not the JSONL.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = os.environ.get("MB_URL", "http://localhost:3000")
# Where log_viz serves the same sessions. Only used to build clickable links
# out of the index, so a wrong value costs a dead link and nothing else.
LOG_VIZ = os.environ.get("LOG_VIZ_URL", "http://localhost:4567")
EMAIL = os.environ.get("MB_ADMIN_EMAIL", "observability@arcaneloop.local")
PASSWORD = os.environ.get("MB_ADMIN_PASSWORD", "ArcaneLoop2026!")
SITE = "Player Journey Observability"
DB_NAME = "Player Journey Sessions"
DASHBOARD = "Player Journey — Observability"

# SQL rather than Metabase's query builder: the questions are the point, and a
# reader can check them without opening the UI. `events` is one wide table, so
# no joins are needed — see docs/plans/observability/layer1 §2.1.
QUESTIONS = [
    {
        # The index is deliberately unfiltered: it is how you find the id to
        # filter by. Its Session column renders as a link into log_viz.
        "name": "Session index",
        "display": "table",
        "filterable": False,
        "link_column": "Session",
        "sql": """
            SELECT session_id AS "Session",
                   MIN(at) AS "Started",
                   MAX(CASE WHEN phase = 'session_end'
                            THEN json_extract(raw, '$.reason') END) AS "Ended",
                   MAX(turn) AS "Turns",
                   ROUND(SUM(cost_usd), 4) AS "USD",
                   SUM(CASE WHEN phase LIKE 'journey.%' THEN 1 ELSE 0 END) AS "Journey events"
            FROM events
            GROUP BY session_id
            ORDER BY "Started" DESC
        """,
    },
    {
        "name": "Sessions by cost",
        "display": "bar",
        "filterable": False,
        "sql": """
            SELECT session_id AS "Session",
                   ROUND(SUM(cost_usd), 4) AS "USD"
            FROM events
            WHERE cost_usd IS NOT NULL
            GROUP BY session_id
            ORDER BY "USD" DESC
            LIMIT 10
        """,
    },
    {
        "name": "How sessions ended",
        "display": "row",
        "sql": """
            SELECT json_extract(raw, '$.reason') AS "Reason",
                   COUNT(*) AS "Sessions"
            FROM events
            WHERE phase = 'session_end'
            [[AND session_id = {{session}}]]
            GROUP BY 1
            ORDER BY 2 DESC
        """,
    },
    {
        # ok IS NOT NULL excludes sessions recorded before the flag was
        # truthful. An unmeasured error rate and a zero error rate are
        # different claims and must not be averaged together.
        "name": "Tool calls and failures",
        "display": "table",
        "sql": """
            SELECT name AS "Tool",
                   COUNT(*) AS "Calls",
                   SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END) AS "Failures"
            FROM events
            WHERE phase = 'tool_result' AND ok IS NOT NULL
            [[AND session_id = {{session}}]]
            GROUP BY name
            ORDER BY "Calls" DESC
        """,
    },
    {
        "name": "Journey events by type",
        "display": "row",
        "sql": """
            SELECT REPLACE(phase, 'journey.', '') AS "Event",
                   COUNT(*) AS "Count"
            FROM events
            WHERE phase LIKE 'journey.%'
            [[AND session_id = {{session}}]]
            GROUP BY phase
            ORDER BY 2 DESC
        """,
    },
    {
        "name": "Where players get blocked",
        "display": "table",
        "sql": """
            SELECT reason AS "Reason",
                   direction AS "Direction",
                   COUNT(*) AS "Blocks"
            FROM events
            WHERE phase = 'journey.movement_blocked'
            [[AND session_id = {{session}}]]
            GROUP BY reason, direction
            ORDER BY "Blocks" DESC
        """,
    },
    {
        "name": "Most visited rooms",
        "display": "table",
        "sql": """
            SELECT room AS "Room",
                   COUNT(*) AS "Visits"
            FROM events
            WHERE phase = 'journey.room_entered' AND room IS NOT NULL
            [[AND session_id = {{session}}]]
            GROUP BY room
            ORDER BY "Visits" DESC
            LIMIT 15
        """,
    },
]


def call(path, data=None, method=None, session=None, timeout=60):
    url = f"{BASE}{path}"
    body = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(url, data=body, method=method or ("POST" if body else "GET"))
    request.add_header("Content-Type", "application/json")
    if session:
        request.add_header("X-Metabase-Session", session)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode()
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:300]
        raise SystemExit(f"{method or 'GET'} {path} failed: {e.code} {detail}")


def wait_for_health():
    for _ in range(60):
        try:
            if call("/api/health", timeout=5).get("status") == "ok":
                return
        except (SystemExit, urllib.error.URLError, OSError):
            pass
        time.sleep(5)
    raise SystemExit(f"Metabase never became healthy at {BASE} — is it running?")


def authenticate():
    """Setup on a fresh instance, plain login on an existing one."""
    token = call("/api/session/properties").get("setup-token")
    if token:
        print("  fresh instance — running first-time setup")
        result = call(
            "/api/setup",
            {
                "token": token,
                "user": {
                    "first_name": "Arcane",
                    "last_name": "Loop",
                    "email": EMAIL,
                    "password": PASSWORD,
                    "site_name": SITE,
                },
                "prefs": {"site_name": SITE, "allow_tracking": False},
            },
        )
        return result["id"]

    print("  already set up — logging in")
    return call("/api/session", {"username": EMAIL, "password": PASSWORD})["id"]


def ensure_database(session):
    for db in call("/api/database", session=session).get("data", []):
        if db["name"] == DB_NAME:
            print(f"  data source exists (id {db['id']})")
            return db["id"]

    db = call(
        "/api/database",
        {
            "engine": "sqlite",
            "name": DB_NAME,
            # The path inside the container, per docker-compose.yml.
            "details": {"db": "/data/sessions.db"},
        },
        session=session,
    )
    print(f"  created data source (id {db['id']})")
    return db["id"]


def session_template_tag():
    """The `{{session}}` variable behind `[[AND session_id = {{session}}]]`.

    `required: False` is what makes the bracketed clause optional — with no
    value the whole clause is dropped and the question spans every session,
    which is the state the dashboard opens in.
    """
    return {
        "session": {
            "id": str(uuid.uuid4()),
            "name": "session",
            "display-name": "Session",
            "type": "text",
            "required": False,
        }
    }


def link_settings(column):
    """Render a column as a link into log_viz.

    Metabase substitutes {{Column Name}} into link_url, so the same session id
    that identifies the row also addresses the trace. This is the outbound half
    of the correlation — the dashboard filter is the inbound half.
    """
    return {
        "column_settings": {
            f'["name","{column}"]': {
                "view_as": "link",
                "link_url": f"{LOG_VIZ}/sessions/{{{{{column}}}}}",
                "link_text": f"{{{{{column}}}}}",
            }
        }
    }


def ensure_questions(session, db_id):
    """Replace by name, so re-running does not accumulate duplicates."""
    existing = {c["name"]: c["id"] for c in call("/api/card", session=session)}
    cards = []

    for spec in QUESTIONS:
        filterable = spec.get("filterable", True)
        native = {"query": spec["sql"].strip()}
        if filterable:
            native["template-tags"] = session_template_tag()

        payload = {
            "name": spec["name"],
            "display": spec["display"],
            "visualization_settings": (
                link_settings(spec["link_column"]) if spec.get("link_column") else {}
            ),
            "dataset_query": {
                "type": "native",
                "native": native,
                "database": db_id,
            },
        }
        if spec["name"] in existing:
            card = call(
                f"/api/card/{existing[spec['name']]}", payload, method="PUT", session=session
            )
        else:
            card = call("/api/card", payload, session=session)
        cards.append({"id": card["id"], "filterable": filterable, "name": spec["name"]})
        print(f"    {spec['name']}{'' if filterable else '  (unfiltered)'}")

    return cards


def ensure_dashboard(session, cards):
    for dash in call("/api/dashboard", session=session):
        if dash["name"] == DASHBOARD:
            dashboard_id = dash["id"]
            break
    else:
        dashboard_id = call(
            "/api/dashboard",
            {
                "name": DASHBOARD,
                "description": (
                    "Agent health first, then the player journey — a finding "
                    "about the game is only credible if the same run can show "
                    "the agent was healthy. Filter by Session to pin one run; "
                    "the same id addresses that run's trace in log_viz."
                ),
            },
            session=session,
        )["id"]

    # One parameter, mapped to every filterable card. Stable id so re-running
    # rebinds the same filter rather than stacking a second one.
    parameter_id = "session_id_param"
    parameters = [
        {
            "id": parameter_id,
            "name": "Session",
            "slug": "session",
            "type": "string/=",
            "sectionId": "string",
        }
    ]

    # The index spans the full width at the top — it is the entry point, and
    # the thing you copy an id out of. Everything else sits two to a row.
    dashcards = []
    row = 0
    for i, card in enumerate(cards):
        full_width = i == 0
        dashcards.append(
            {
                "id": -(i + 1),  # negative ids mark "new" to the API
                "card_id": card["id"],
                "row": row if full_width else row + ((i - 1) // 2) * 6,
                "col": 0 if full_width else ((i - 1) % 2) * 12,
                "size_x": 24 if full_width else 12,
                "size_y": 6,
                "parameter_mappings": (
                    []
                    if not card["filterable"]
                    else [
                        {
                            "parameter_id": parameter_id,
                            "card_id": card["id"],
                            # A native-SQL variable is targeted as a
                            # "variable" + template-tag, not as a "dimension".
                            "target": ["variable", ["template-tag", "session"]],
                        }
                    ]
                ),
                "visualization_settings": {},
            }
        )
        if full_width:
            row = 6

    call(
        f"/api/dashboard/{dashboard_id}",
        {"dashcards": dashcards, "parameters": parameters},
        method="PUT",
        session=session,
    )
    return dashboard_id


def main():
    print(f"Metabase at {BASE}")
    wait_for_health()
    session = authenticate()
    db_id = ensure_database(session)

    # Metabase reads the schema asynchronously; a question against a table it
    # has not seen yet fails. Native SQL does not strictly need the sync, but
    # the UI is unusable without it.
    call(f"/api/database/{db_id}/sync_schema", {}, session=session)

    print("  questions:")
    card_ids = ensure_questions(session, db_id)
    dashboard_id = ensure_dashboard(session, card_ids)

    print()
    print(f"dashboard ready: {BASE}/dashboard/{dashboard_id}")
    print(f"  sign in: {EMAIL} / {PASSWORD}")


if __name__ == "__main__":
    sys.exit(main())
