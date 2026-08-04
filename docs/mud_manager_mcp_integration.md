# MudManager over MCP — how it is wired

Verified 04-08-2026 against the live tbaMUD on `localhost:4000`.

Implements [`docs/plans/mud_manager/generic_interfacing`](plans/mud_manager/generic_interfacing).

---

## 1. What the FakeMud is and is not

**The FakeMud is not part of the integration.** It appears in exactly two
places, both of them test scaffolding:

| Where | Why |
| --- | --- |
| `week0_explore/mud_manager/test/*` | so `rake test` runs with no MUD installed |
| `10_standard_tool_library/examples/mcp_mud_demo.rb` | only when `MUD_HOST` is unset, so the demo runs anywhere |

Nothing in `lib/` references it. `bin/mud-manager` never loads it.
`Boukensha::Tools::Mcp` has never heard of it. It is a local telnet server that
performs the CircleMUD login dance so tests do not need a real world — the same
role a stub HTTP server plays for a client library.

The production path uses `settings.yaml`. Proof, with every `MUD_*` variable
explicitly unset:

```console
$ env -u MUD_HOST -u MUD_PORT -u MUD_NAME -u MUD_PASSWORD mud-manager --config
#<MudManager::Mcp::Config localhost:4000 name="dummy">
credentials: set
```

Those values came from `.boukensha/settings.yaml`, not from a fake.

## 2. The daemon against the real MUD

```console
$ printf '%s\n' '{"id":1,"op":"call","name":"look","args":{}}' \
                '{"id":2,"op":"call","name":"check","args":{"kind":"exits"}}' \
  | mud-manager --stdio-json
```

```text
--- id=1 ok=true ---
The Temple Of Midgaard
   You are in the southern end of the temple hall in the Temple of Midgaard.
   The temple has been constructed from giant marble blocks, eternal in
appearance, and most of the walls are covered by ancient wall paintings...

--- id=2 ok=true ---
Obvious exits:
north - By The Temple Altar
east  - The Midgaard Donation Room
south - The Temple Square
west  - The Reading Room
down  - The Temple Square

22H 100M 83V (news) (motd) >
```

That is the real Midgaard, reached with no code from this repo other than the
gem itself.

## 3. Boukensha is an MCP host

The generic layer is the point. Boukensha does not have "a MUD module that uses
MCP internally" — it can host **any** MCP server, and the MUD is one entry in a
config file.

```
   Boukensha::Mcp::Client  ── generic stdio MCP client (JSON-RPC 2.0)
            │
   Boukensha::Tools::Mcp   ── registers whatever a server advertises
            │
            ├─► mud-manager --mcp   ─► MudManager::Session ─► MUD
            ├─► npx server-filesystem
            └─► any other MCP server
```

`Boukensha::Tools::Mcp` contains **no MUD knowledge at all** — no telnet, no
primitives, no login, not one tool name. It knows a command to spawn and it
knows MCP. Proven by demonstration rather than assertion:
`test/support/tiny_mcp_server.rb` is a two-tool calculator with nothing to do
with MUDs, and `test_registers_a_non_mud_server` drives it through the same code
path. If MUD assumptions creep back into the host layer, that test fails.

Spawning a subprocess with a command, args and env is not coupling — it is the
MCP stdio transport's standard configuration shape, the same triple every MCP
host uses. Passing credentials through the server's environment is likewise
standard: the spec has no "send credentials over the wire" concept for stdio
servers, deliberately.

### The two routes to the MUD

Both are live and they are not interchangeable.

| | `Tools::Mud` | `Tools::Mcp` |
| --- | --- | --- |
| Where the session lives | this Ruby process | a separate process |
| Who knows about telnet | boukensha | only the daemon |
| Tool definitions | hardcoded in `tools/mud.rb` (480 lines) | discovered at runtime |
| Tool names | `look`, `attack` | `tbamud__look`, `tbamud__attack` |
| Works from Python/Go/Rust | no | yes — same daemon |
| Turned on by | `mud:` (default when `settings.yaml` has a host) | `mcp:` / `BOUKENSHA_MCP=1` |

`mcp: true` sets `mud: false` for you, so the two never both register.

### Prefixes are client-side

MCP tools are namespaced `#{prefix}__#{name}`. The MUD's prefix is **`tbamud`** —
named after the engine, not the config key, because a second entry called `mud`
is plausible and a second tbaMUD is not.

**The daemon still advertises bare names.** `tbamud__look` in the registry is
`look` on the wire — which is why §2's JSON-line example uses `"name":"look"` and
is still correct. If a daemon test ever needs updating for a prefix, the prefix
leaked across the boundary and that is a bug, not a rename.

`Tools::Mcp` applies whatever prefix it is handed and must never know the string
`"tbamud"`; that lives only in `settings.yaml` and in `Boukensha::MUD_PREFIX`.

Collisions **raise**. Prefixing makes them unlikely, not impossible — two entries
can share a prefix — and `Registry#tool` would otherwise let the second
registration silently clobber the first, which is a bug that would be maddening
to debug.

## 4. How to turn it on

### From the terminal

```sh
BOUKENSHA_MCP=1 boukensha
```

```text
╔══════════════════════════════════════╗
║  BOUKENSHA MUD Assistant (v0.10.0)   ║
╚══════════════════════════════════════╝
  config:    /home/vasiliki/Projects/claude-code-camp-2026-Q2/.boukensha
  provider:  anthropic (claude-haiku-4-5)  ✓ API key set
  mud:       via mud-manager 0.2.0 (26 tools over MCP)
```

Without the variable the banner reads `mud: localhost:4000 (Reachable)` and the
in-process path is used, exactly as before the daemon existed. **Opt-in — nothing
that worked stops working.**

### From code

```ruby
Boukensha.run(
  task: "Look around and tell me where I am.",
  working_dir: false,
  mud: false,      # in-process path off
  mcp: true        # the "mud" server, from settings.yaml
)
```

`mcp: true` resolves `mcp_servers["mud"]` if present, otherwise builds a preset
from the `mud:` block. Override any part by passing a Hash instead:

```ruby
mcp: { command: "/path/to/mud-manager", args: ["--mcp"], prefix: "tbamud" }
```

### Servers as data — `mcp_servers`

The MUD has no privileged position in the config. It is one entry:

```yaml
mcp_servers:
  mud:
    command: mud-manager
    args: [--mcp]
    prefix: tbamud
    # env is layered over the mud: block, so credentials are not repeated

  filesystem:
    command:  npx
    args:     [-y, "@modelcontextprotocol/server-filesystem", /tmp]
    prefix:   fs
    required: false
```

**A third-party server needs no boukensha code — only an entry here.** Every
entry except `mud` (which the `mcp:` option owns) is registered automatically by
`run`/`repl`.

| Key | Default | Meaning |
| --- | --- | --- |
| `command` | — | executable to spawn; entry is skipped if absent |
| `args` | `[]` | argv |
| `env` | `{}` | environment for the child; where credentials go |
| `prefix` | none | `#{prefix}__#{tool}`; omit for bare names |
| `required` | **`true`** | `true` → a spawn failure raises. `false` → warn and continue |

`required: true` is the default because a server you bothered to configure and
which then fails is a problem you want to hear about. Mark the decorative ones
`required: false`.

**Servers are spawned eagerly**, at registration — you cannot register tools you
have not discovered, and discovery needs a running server. N servers cost N
spawns at boot even for ones the model never calls. Fine at one or two; worth
revisiting beyond that.

> **"Server" means an MCP server process** — one entry, one subprocess. It never
> means a MUD. Connecting to several MUDs is a different axis and the daemon
> already solves it: `SessionPool` holds multiple named sessions inside **one**
> `mud-manager`. Two MUDs is two sessions in one server, not two servers.

## 5. Where the credentials go

Plan §5: an LLM never sees them. `connect` and `login` are not tools.

```
settings.yaml (mud:) ──► Boukensha.mud_env_from_config
                              │  (an inherited MUD_* wins over config)
                              ▼
                    child process environment
                              │
                              ▼
                   MudManager::Mcp::Config ──► SessionPool
                                                  │
                                                  ▼
                                   lazy connect + login on the
                                   first gameplay tool call
```

The model only ever sees gameplay tools. The session opens on first use and
transparently reconnects if the socket drops, so a stateful session looks
stateless from above — which is what makes the MCP mapping clean.

## 6. Verification

| Check | Command | Result |
| --- | --- | --- |
| Daemon unit + protocol + subprocess e2e | `cd week0_explore/mud_manager && rake test` | 51 runs, 0 failures |
| Boukensha as an MCP host | `ruby -Ilib -Itest test/test_tools_mcp.rb` | 11 runs, 0 failures |
| `mcp_servers` config parsing | `ruby -Ilib -Itest test/test_config_mcp_servers.rb` | 6 runs, 0 failures |
| Tool surface | `mud-manager --list-tools` | 26 tools |
| Config resolution | `mud-manager --config` | reads `settings.yaml` |
| No-API-call demo | `ruby examples/mcp_mud_demo.rb --dry` | 26 `tbamud__` tools |
| Real MUD, real movement | §2 above, and `move north` / `move south` through the registry | walked Midgaard and back |

`test_client_e2e.rb` is the one that matters on the daemon side: it spawns the
real binary as a subprocess. Everything else stubs out the process boundary that
is the design.

**The daemon's 51 tests were not edited when the prefix landed.** That is the
check that the prefix is genuinely client-side — if a daemon test had needed
updating, the abstraction had leaked.

**`rake test` fails if `primitives.json` is stale.** It is generated from
`MudManager::Primitives` (Ruby is canonical) and is the contract other language
tracks generate from — a diff in it is a change other people depend on.

## 7. Known gaps

1. **Optional arguments are advertised as required.** `Backends::Anthropic#tools`
   (`anthropic.rb:61`) does `required: tool.parameters.keys.map(&:to_s)` —
   every parameter, regardless of intent. So `look`'s optional `target` is
   presented as mandatory. Pre-existing; affects `Tools::Mud` identically. The
   daemon still validates correctly, so the symptom is a model that
   over-supplies arguments, not breakage. The fix belongs in the backend.

2. **The global `boukensha` command runs the *installed gem's* loader.** Editing
   `10_standard_tool_library/lib/boukensha_loader.rb` changes nothing until
   `gem build && gem install`, or unless `BOUKENSHA_PATH` points at the step
   folder. The verification above used `ruby bin/boukensha` with
   `BOUKENSHA_PATH` set, which loads the step's own copy.

3. **`~/.boukensharc` multi-key support was carried from step 09 to step 10**
   during this work, because the single-bare-path parser aborted on the existing
   rc file. Steps 11 and 12 still need it.

4. **Async chatter needs polling.** `poll` is the answer to plan open-Q #2;
   server-initiated MCP notifications would be richer. The model must call
   `poll` to see combat rounds that land while it is idle.

5. **Multi-session is implemented but only reachable over the JSON-line
   protocol.** Sessions are keyed by id (open-Q #1), but the MCP facade uses a
   single implicit `"default"` — an LLM has no business choosing session ids.

6. **Non-text content blocks are dropped.** `Mcp::Client#call_tool` keeps
   `type == "text"` and discards `image` / `audio` / `resource`. Irrelevant to
   the MUD — `read_until_prompt` returns a String and there is no path to a
   non-text MUD result — and deliberately deferred until a second server needs
   it. Note the deeper limit is not in the client: `agent.rb:134` does
   `result.to_s`, so **even a perfect client could not carry an image to the
   model**. That fix touches `Context`, `Agent` and all five backends.

7. **The client exists twice.** `Boukensha::Mcp::Client` and
   `MudManager::Mcp::Client` are near-identical. Deliberate: `mud_manager`
   serves five language tracks and must not depend on boukensha, so a test-only
   dependency edge would be backwards. Boukensha's copy is canonical for
   boukensha; the daemon's stays test-scoped and should not grow features.
