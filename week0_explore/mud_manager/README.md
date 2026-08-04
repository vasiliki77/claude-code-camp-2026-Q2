# MudManager

> **This directory is not a week-0 snapshot.** Its siblings under
> `week0_explore/` are pinned exploration artifacts — read them as "here is
> where we were in week 0". This one is a **living, versioned, installable
> gem**: week-1 step 10 depends on it, later weeks will too, and it moves
> forward independently of the folder it sits in.
>
> That mismatch is deliberate and was argued rather than overlooked. The
> alternative — a frozen copy here plus a real copy elsewhere — means two
> `MudManager::Session` implementations, which is the single thing this gem's
> whole design exists to prevent. If the placement ever becomes more confusing
> than it is convenient, the fix is a top-level `mud_manager/`; the hard part
> (one gem, one binary) is already done, and what remains is a `git mv` and two
> path constants.

Two halves with opposite portability profiles, and one binary that serves them
to any language.

| | What it is | Why it matters |
| --- | --- | --- |
| `MudManager::Session` | **Stateful.** A long-lived telnet socket, a background reader thread, telnet IAC stripping, `read_until_prompt`, and the multi-step login dance. | Expensive and bug-prone to reimplement. Nobody should write this twice. |
| `MudManager::Primitives` | **Stateless.** Validates enum arguments and returns a command string (`"kill goblin"`, `"cast 'fireball' orc"`). No I/O, no state. | Essentially a data table. Any language can render it. |
| `MudManager::Mcp` | **The daemon.** One process that owns the sessions and exposes them over stdio, as MCP or as a line protocol. | So Python/Go/Rust/Java agents drive a MUD without reimplementing the first row. |

That split is the whole design. See
[`docs/plans/mud_manager/generic_interfacing`](../../docs/plans/mud_manager/generic_interfacing)
for the reasoning; the short version is that the answer to *"how do we port
MudManager to four languages?"* is **don't** — run it once, behind a protocol.

## Install

```sh
gem build mud_manager.gemspec
gem install ./mud_manager-0.2.0.gem
```

One gem, one binary. There is no separate `mud_manager_mcp` to keep
version-locked: the daemon is an *interface* over this gem's domain, the two
have one release cadence, and packaging them apart would tax exactly the people
the daemon exists to help — a Go bootcamper who should not need a Ruby toolchain
opinion, let alone two gems' worth.

The namespace boundary (`lib/mud_manager/mcp/`) still shows where the seam is.
It just doesn't charge anyone rent.

```sh
mud-manager --version
mud-manager --list-tools     # 26 tools
```

## Run the daemon

```sh
mud-manager --mcp            # MCP over stdio (JSON-RPC 2.0)  [default]
mud-manager --stdio-json     # newline-delimited JSON protocol
mud-manager --config         # show resolved connection settings
mud-manager --dump-spec      # print primitives.json
```

Agents spawn it as a **subprocess**, so the MUD session's lifetime is the
subprocess's lifetime — no ports to manage, nothing to clean up if the agent
crashes.

### Connection settings

Credentials never arrive as tool arguments. An LLM has no business choosing them,
and `connect`/`login` are deterministic framework concerns. They come from:

1. `MUD_HOST`, `MUD_PORT`, `MUD_NAME`, `MUD_PASSWORD`, `MUD_TIMEOUT`
2. the `mud:` block of `$BOUKENSHA_DIR/settings.yaml`
3. `Session`'s own defaults (`localhost:4000`)

The daemon connects **lazily**, on the first gameplay tool call, and silently
reconnects if the socket drops. From above the daemon boundary a stateful
session looks stateless — which is what makes the MCP mapping clean.

## The tool surface

26 tools: 24 gameplay (`look`, `move`, `attack`, `cast_spell`, `shop`, …) plus
`poll` and `mud_status`. `send_raw` is the escape hatch for anything unmodelled.

`connect`, `login` and `disconnect` are deliberately **not** tools.

### `primitives.json` is generated, never edited

`MudManager::Primitives` is canonical. `ToolSpec` reads its enum constants *at
call time*, and `primitives.json` is rendered from that:

```sh
rake spec        # or: mud-manager --write-spec
```

Add a direction to `Primitives::DIRECTIONS` and the served MCP schema changes on
the next start, with no second edit anywhere. That file is what other language
tracks generate typed builders from, so **a diff in it is a change to a contract
other people depend on** — check it, don't just commit it. `rake test` fails if
the checked-in copy is stale.

## Errors

Every failure crossing the boundary carries a machine-readable code, so a
foreign client can branch instead of parsing prose:

```json
{"id":4,"ok":false,"error":{"code":"INVALID_ARGUMENTS","message":"invalid direction: \"sideways\" (expected one of north, east, south, west, up, down)"}}
```

`TIMEOUT`, `CONNECTION_FAILED`, `LOGIN_FAILED`, `MISSING_CREDENTIALS`,
`INVALID_ARGUMENTS`, `UNKNOWN_TOOL`, `PROTOCOL_ERROR`, `SESSION_ERROR`,
`INTERNAL`.

Under MCP, a *failed tool call* is a successful JSON-RPC result carrying
`isError: true` — so the model reads the failure and corrects itself, rather
than the transport erroring out underneath it.

## Multiple sessions

Sessions are keyed by id. MCP uses a single implicit `"default"` session; the
JSON-line protocol lets a caller name them:

```json
{"id":1,"op":"call","name":"look","args":{},"session":"alice"}
```

## Tests

```sh
rake test
```

51 tests, no real MUD required — `MudManager::FakeMud` is a local telnet server
that runs the CircleMUD login dance and terminates responses with the `"> "`
prompt sentinel. It is a fake *MUD*, not a fake MCP server, which is why it
lives at `MudManager::FakeMud` rather than under `Mcp`.

`test/test_client_e2e.rb` is the one that matters: it spawns the real binary as
a subprocess and plays through it. Everything else stubs out the process
boundary that is the entire design.

## Examples

```sh
# Against a real MUD:
MUD_NAME=YourCharacter MUD_PASSWORD=yourpassword ruby examples/live_session_test.rb

# The daemon driving an agent, with a fake MUD and no API calls:
ruby ../../week1_baseline/ruby/10_standard_tool_library/examples/mcp_mud_demo.rb --dry
```

## Uninstall

```sh
gem uninstall mud_manager
```
