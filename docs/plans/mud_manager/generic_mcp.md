# Generic MCP — reconciling `generic_mcp_client.md` with this repository

**Status: subordinate to [`generic_mcp_client.md`](generic_mcp_client.md).**
That plan is the instructor's and is upstream. Where the two disagree, it wins.

This document exists for two reasons:

1. **Its starting state is not ours.** `generic_mcp_client.md` was written
   against a two-gem layout with a `Tools::McpMud` and a `boukensha_bridge.rb`.
   This repository executed `generic_interfacing` differently — one gem, and a
   bridge that was already generic on day one. Roughly a third of its migration
   plan is already done here, and one step of it does not apply at all. §1 maps
   the difference so the plan can be followed without tripping over it.
2. **It is client-only.** It says explicitly: *"it does not touch the daemon."*
   The server side — making `mud-manager` one MCP server rather than the only
   possible one — is genuinely out of its scope. §4 covers that, and is the only
   part of this document that is a *proposal* rather than a translation.

---

## 1. Delta: their starting state vs. this repository

| `generic_mcp_client.md` assumes | This repo actually has | Consequence |
| --- | --- | --- |
| Two gems: `mud_manager` + `mud_manager_mcp` | **One gem** (`single_gem.md` was executed first) | Paths differ throughout §6 |
| `MudManagerMcp::McpClient` | `MudManager::Mcp::Client` | Step 1 applies, new path |
| `boukensha_bridge.rb` inside the daemon gem | **Does not exist** | **Step 2 is already done** |
| `Tools::McpMud` — MUD-specific | `Tools::Mcp` — already generic, already takes `command:`/`args:`/`env:`/`prefix:` | Step 4 is mostly done |
| `config.mud_mode` switch | `mcp:` / `mud:` keywords + `BOUKENSHA_MCP=1` | §9.3's question lands differently |
| `mcp_servers:` in `settings.yaml` | Not present | **Step 3 is the real work** |
| `RegistryDsl` adapter needed | Not needed — we pass `Registry` directly | Already resolved |
| 21 tests | 51 daemon + 7 boukensha | Bigger safety net |
| `prompts/system.md` names tools | **3 lines, names no tools** | §5a's churn is much smaller here |

**What is left to do here, in their numbering:** Step 1 (hoist the client),
Step 3 (`mcp_servers` config), Step 5 (register configured servers), Step 6
(docs). Steps 2 and 4 are substantially complete.

The one genuinely lucky difference: because `Tools::Mcp` was written generic
rather than as `Tools::McpMud`, the MUD-specific part here is already isolated
in `Boukensha.mcp_opts` — a private method that builds the `mud-manager` preset.
That method *is* their "`McpMud` reduced to a preset". It just got there first.

## 2. Decisions adopted wholesale

Taken from their plan without modification. Recording them so they are not
re-litigated when the code is written:

- **§5a — prefix by engine name.** `tbamud__look`, not `mud__look`. The prefix
  is a property of the *server*, lives only in config, and **`Tools::Mcp` must
  not know the word "tbamud"**. Our `Tools::Mcp` already applies `prefix:`
  blindly, so this is a config change, not a code change.
- **§5a — collisions must still raise.** Prefixing makes them unlikely, not
  impossible (two entries could share a prefix). `Registry#tool` currently lets
  the second registration silently clobber the first. Silent clobber is
  expensive to debug; the error is cheap.
- **§5b — spawn eagerly.** Revisit past ~2 servers. Lazy really means "register
  from a cached manifest", which is a much bigger change.
- **§5c — `required: true` by default.** A required server that fails to spawn
  raises; an optional one warns and continues. Our `Tools::Mcp` currently always
  warns-and-continues, which is the *optional* behaviour — so required-mode is
  new and the default must flip.
- **§5d — the daemon keeps its own client.** `mud_manager` must not depend on
  boukensha; it serves five language tracks and a test-only dependency on one of
  them would be backwards. Its copy stays test-scoped and must not grow features.
  *(This supersedes an earlier draft of this document, which wavered on it. The
  instructor's argument is better and the wavering is deleted.)*
- **§4 — defer the required-params fix.** `anthropic.rb:61` marks every
  parameter required. It affects all tools, not just MCP ones, and deserves its
  own plan.
- **Terminology.** "Server" means an MCP server process. Two MUDs is **two
  sessions inside one server**, not two servers — `SessionPool` already handles
  that axis and it is a different one.

## 3. Where an earlier draft of this plan disagreed

Recorded honestly rather than quietly dropped.

### Non-text content blocks — they defer, and they are right to

An earlier version of this document argued for fixing this now: `client.rb`
selects `type == "text"` and silently discards `image`/`audio`/`resource`
blocks, which is the failure shape the week-1 journal keeps naming — *a fallback
that makes a missing input look like an empty input moves the error away from
its cause.*

Their §4 defers it, on the grounds that there is **no path to a non-text MUD
result** and no second server yet. That is the stronger argument: the journal's
principle is about diagnosing failures that actually occur, and this one cannot
occur until a second server exists. Fixing it now would be building a guard for
a code path nobody executes.

**Deferred.** Two notes for whoever picks it up:

- Their §9.4 ("do we ship a second server to prove genericity?") is the trigger.
  The day that is answered yes, this stops being hypothetical.
- The deeper limit is not in the client. `agent.rb:134` does
  `@context.add_message(:tool_result, result.to_s, …)` and `anthropic.rb:42`
  wraps that String in a `tool_result` block. **Even a perfect client cannot
  carry an image to the model.** Fixing content flattening without fixing that
  buys a better error message, not a capability. The real fix touches `Context`,
  `Agent` and all five backends — plan-sized, and a sibling of the §4
  required-params work rather than part of this.

### Prefix naming

An earlier draft proposed the config key as the prefix (`mud__look`). Their §5a
DECIDED on the engine name (`tbamud__look`). Theirs is better: the config key is
a local label, the engine is a property of the thing being talked to, and a
second tbaMUD daemon is more likely than a second config key called `mud`.

## 4. The half their plan does not cover: a reusable server core

Out of scope for `generic_mcp_client.md` by its own statement. Proposed here
because "generic MCP" is only half-true while the *server* can only ever be a MUD.

`mcp/server.rb` is already generic apart from one coupling: it calls
`ToolSpec.mcp_tools` and `@dispatcher.call` by name. Extract a three-method
contract and the MUD becomes one implementation rather than the only one:

```ruby
# MudManager::Mcp::Server.new(provider, input:, output:)
#   provider.tools            -> [ MCP tool definitions ]
#   provider.call(name, args) -> String
#   provider.shutdown
```

`Dispatcher` + `ToolSpec` already satisfy this shape. The change is passing them
in instead of reaching for them — roughly a constructor argument and a
documented contract. `JsonLineServer` gets the same treatment.

**Explicitly do not build an "MCP server framework".** We have exactly one
server. `generic_interfacing` §3 was right that inventing protocol machinery
ahead of a second consumer produces an abstraction shaped like its only user.
The deliverable here is that a second server (a world-parser server, a notes
server) is an afternoon rather than a fork — not a plugin system.

**Sequencing:** this is independent of the client work and lower priority. Do
their plan first. This only becomes urgent if a second server is actually wanted,
which is their §9.4 again.

## 5. Migration, adjusted for this repository

Their §6 steps, with the ones that no longer apply struck and the paths corrected.

**Step 1 — Hoist the client.** `week0_explore/mud_manager/lib/mud_manager/mcp/client.rb`
→ `10_standard_tool_library/lib/boukensha/mcp/client.rb` as `Boukensha::Mcp::Client`.
`clientInfo` version becomes `Boukensha::VERSION`. The daemon keeps its copy (§5d),
so this is a copy-then-diverge, not a move. No logic changes.

**~~Step 2 — Hoist the bridge.~~** Already done: `boukensha/tools/mcp.rb` exists
and is generic. Only its `require "mud_manager"` changes to the hoisted client,
and collision-raising is added.

**Step 3 — Config.** The real work. Add `Config#mcp_servers` reading the
`mcp_servers:` block, normalising keys and defaulting `args: []`, `env: {}`,
`required: true`, `prefix: nil`.

**~~Step 4 — Reduce `McpMud` to a preset.~~** Already done, as
`Boukensha.mcp_opts`. It should learn to resolve an `mcp_servers["mud"]` entry
first and fall back to today's behaviour.

**Step 5 — Register configured servers** in `run`/`repl`, honouring
required/optional. Our `mcp:` keyword and `BOUKENSHA_MCP=1` continue to mean
"the MUD preset"; `mcp_servers` entries register alongside.

**Step 6 — Docs.** `docs/mud_manager_mcp_integration.md` §3's two-route table
gains the generic layer; add an `mcp_servers` section. Its core claims survive.

## 6. Test deltas specific to this repo

Their Group 1 / Group 2 split holds. Concretely here:

- **Group 2, untouched:** all 51 daemon tests. The prefix is applied
  **client-side**; the daemon still advertises `look`. If a daemon test needs
  editing, the prefix leaked across the boundary — that is a bug, not a rename.
  Note `docs/mud_manager_mcp_integration.md:38` shows `{"op":"call","name":"look"}`
  on the JSON-line wire; that is the daemon's name and stays bare. Correct as written.
- **Group 1, names only:** `test/test_tools_mcp.rb` asserts bare names at lines
  50, 51, 59, 68, 94, 95. Under a `tbamud` prefix these become prefixed. **The
  dispatch assertions must still pass untouched** — behaviour is identical, only
  the label moved. If a dispatch assertion needs editing, the refactor broke
  something.
- **Already covering their new-test table:** `test_tools_mcp.rb` has
  `test_prefix_namespaces_the_tools` and `test_missing_daemon_registers_nothing_and_does_not_raise`.
  The latter must be **rewritten** when §5c lands — it currently asserts the
  optional behaviour as the default, which is exactly what flips.
- **Genuinely new:** collision raises; `Config#mcp_servers` parsing; required
  server failure raises; a non-MUD throwaway server proving genericity by
  demonstration.
- **`examples/mcp_mud_demo.rb --dry`** prints discovered tool names, so it is a
  free visual confirmation the prefix landed.

## 7. Open questions

Their §9, answered where this repo already decides it:

1. **Tool-name collisions** — settled by their DECIDED note: prefix by engine,
   and still raise on collision.
2. **Step 10 vs step 11** — still open, and still the biggest call. Their §8
   risk applies here identically: step 10 is a lesson snapshot, and this adds a
   `boukensha/mcp/` namespace plus a config key to it. Note this repo has
   *already* modified step 10 (the `mcp:` keyword, `Tools::Mcp`, `BOUKENSHA_MCP`,
   and the `~/.boukensharc` multi-key carry-forward), so the snapshot is broken
   either way — which weakens the argument for a new step but does not settle it.
3. **Does `mud:` stay special?** Here the mode switch is `mcp:`/`mud:` keywords
   rather than `config.mud_mode`, so there is no `mud_mode` test to break. That
   makes "cut it now" cheaper here than in their repo.
4. **Ship a second server?** Unanswered, and it gates two deferrals — non-text
   content (§3) and the server core (§4). Worth answering deliberately rather
   than by accident.
5. **New here:** the `~/.boukensharc` multi-key change has now been carried
   forward by hand twice (step 09 → step 10). Steps 11 and 12 still need it. If
   this lands as step 11, that debt comes due in the same change.
