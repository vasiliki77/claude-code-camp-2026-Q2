# 10 · A Standard Tool Library (Python)

Python port of the Ruby baseline step
[`week1_baseline/ruby/10_standard_tool_library`](../../ruby/10_standard_tool_library/README.md).
Same behaviour, same `.boukensha/` config directory.

**Step 09 is skipped.** It is a Ruby *packaging* lesson — gemspec, shebang,
`gem build`/`gem install`, and a loader that chooses among twelve numbered
teaching folders. Its Python analogue would be `pyproject.toml` with
`[project.scripts]`: a different toolchain, not a port. So this folder is a copy
of `08_the_repl_loop`, and Ruby's `boukensha_loader.rb`, `boukensha.gemspec` and
`bin/boukensha` have no counterparts here. That is deliberate, not unfinished.

## The 480 lines that are deliberately missing

Ruby's step 10 ships `lib/boukensha/tools/mud.rb` — 480 lines registering 26 MUD
gameplay tools, each one calling `MudManager::Primitives` and driving a
`MudManager::Session` held in a closure. **There is no `tools/mud.py`, and there
never will be.**

Python gets the same 26 tools by spawning `mud-manager --mcp` and asking it what
it has:

```
Python agent  ──spawn──►  mud-manager --mcp  ──telnet──►  MUD
              ◄─stdio──   (Ruby, already built)
```

This is not a shortcut around the port. It is the entire reason the MCP daemon
exists — `docs/plans/mud_manager/generic_interfacing` §1 argues that nobody
should reimplement the stateful `Session` twice, because that is where the
telnet edge cases, the background reader thread and the login state machine
live. Reimplementing it in Python would be exactly the mistake the plan was
written to prevent.

The consequence worth noticing: **`tools/mcp.py` contains no MUD knowledge at
all** — no telnet, no primitives, no login, not one tool name. It knows a
command to spawn and it knows MCP. Point it at a filesystem server or a
calculator and it registers those instead. `test/support/tiny_mcp_server.py`
exists to prove that by demonstration rather than by comment.

Python needs the `mud-manager` **binary**, not the `mud_manager` gem as a
library — a Ruby runtime, not a Ruby toolchain, and no Ruby knowledge.

## What this step adds

| File | Purpose |
| --- | --- |
| `tools/file_system.py` | `pwd`, `list_directory`, `read_file`, `write_file`, `delete_file`, `search_files` — all rooted at one directory |
| `tools/shell.py` | `run_command`, with a timeout and an optional allow-list |
| `tools/mcp.py` | Registers whatever any MCP server advertises |
| `mcp/client.py` | A stdio MCP client (JSON-RPC 2.0) |
| `config.py` | `mcp_servers` — servers as data in `settings.yaml` |
| `run.py` | `working_dir`, `allowed_commands`, `shell_timeout`, `mcp` options |

## Run

```sh
./week1_baseline/bin/python/10_standard_tool_library --dry
```

`--dry` boots a fake MUD, registers all 26 tools over MCP, dispatches three of
them and exits — **no API calls, nothing billable**. Without `--dry` it runs a
real agent turn.

```
Started FakeMud on 127.0.0.1:36227
Daemon:  mud-manager 0.2.0
Tools:   26

  tbamud__look, tbamud__examine, tbamud__check, tbamud__move, …

tbamud__look -> You look.
bad arg   -> error [INVALID_ARGUMENTS]: invalid direction: "widdershins" …

[dry run OK — 26 tools over MCP, no API calls made]
```

Tool names carry the `tbamud__` prefix — named after the MUD engine, not the
config key. It is applied **client-side**; the daemon still advertises bare
`look` on the wire.

## Tests

```sh
.venv/bin/python -m unittest discover -s test
```

38 tests, no API key and no real MUD needed. The MUD-facing ones drive the Ruby
`FakeMud` as a subprocess rather than porting it — it is a server on a socket,
and the language it is written in is invisible from here. Maintaining two fake
MUDs that must agree on the CircleMUD login dance would be a second thing to
keep in sync for no gain.

## Divergences from Ruby, and why

- **`None` and `False` are both falsy, and Ruby's `nil` and `false` are not
  interchangeable here.** Ruby's `mcp: nil` means "use config" while `mcp: false`
  means "skip entirely". A naive `if not mcp` collapses them, so the checks are
  `is None` / `is False`. Same for `allowed_commands`: `[]` is truthy in Ruby and
  falsy in Python, so `if allowed_commands` would silently permit *everything*
  when the caller asked to permit *nothing*.

- **No `mud:` option**, because there is no in-process MUD path to switch on.

- **Line-buffered pipes and a stderr drain thread.** Ruby's `Open3` + `puts`/
  `gets` work on line boundaries by default; Python needs `text=True`,
  `bufsize=1` and an explicit `flush()` per write, plus a daemon thread draining
  the child's stderr. Omitting either deadlocks — and passes tests before it
  does, which is the worst possible failure schedule.

- **`os.path.abspath`, not `Path.resolve()`, for path containment.** Ruby's
  `File.expand_path` is purely lexical; `Path.resolve()` also follows symlinks
  and treats missing paths differently. Matching Ruby keeps the containment rule
  identical across languages.

- **Ruby step 10 lost step 08's 401 handling** (`authentication failed (401) —
  check your API key`), the same non-linearity that made step 07 look branched
  from step 04/05. **Kept on the Python side** rather than mirrored: it is a
  diagnostic improvement whose loss upstream is clearly accidental, and there is
  precedent both ways (`to_messages` was mirrored, `PROMPTS_DIR` was fixed).

- **A subprocess leak Ruby also has.** If session construction fails *after* the
  MCP servers are spawned — an unknown backend, say — the caller never receives
  the session and its `finally:` has nothing to close. Python guards this
  explicitly; the same fix would apply to Ruby.

## Verification

| Gate | Result |
| --- | --- |
| Tool table, Ruby vs Python, same daemon | **byte-identical**, 26 tools each |
| Filesystem + shell tool output, Ruby vs Python | **byte-identical**, error strings included |
| Non-MUD MCP server registers and dispatches | ✓ (`tiny_mcp_server.py`) |
| Unit tests | 38 pass |

The first gate is the strongest available since step 03, and it exists only
because the daemon is language-neutral: both implementations drive the *same*
`mud-manager` process, so their discovered tool tables must match. **A
difference there is a bug in the client, never in the tools** — which makes it
unusually good at localising failure.

Two things made that diff fail before it passed, both defects in the *check*
rather than the code: Ruby preserves hash insertion order while the Python dump
sorted keys, and `json.dumps` escapes the em dash in two tool descriptions
unless given `ensure_ascii=False` — the same trap step 06 hit when matching the
session log byte-for-byte.
