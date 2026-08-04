# Step 12 — Context Management

When you call an LLM directly you are responsible for the context window. There is no auto-compacting. This step adds proper token tracking, visual warnings, and automatic compaction so the agent never silently blows past the limit.

It also carries forward steps 10–11: the MCP host, the tasks layer, the `KEY=value` `~/.boukensharc`, and the response cost metadata. See `docs/plans/step_deltas/12_context` for what that merge involved and why.

## What's new

### Accurate context tracking

`Context` maintains three distinct counters:

| Attribute | What it measures |
|-----------|-----------------|
| `context_window` | The model's maximum input token capacity, from `Models.context_window(model)` |
| `current_tokens` | Input tokens of the most recent API call — window pressure, drives compaction |
| `turn_tokens` | Cumulative input+output spent this turn — the spend budget, drives `max_turn_tokens` |

Previously `token_budget` (8,192) was displayed as the limit — that was the *output* `max_tokens`, not the context window. And the cumulative session token sum was shown as usage, which grew without bound even after `/clear`. Both are fixed.

The Agent updates `current_tokens` after every API response (including mid-turn tool-use calls), so the display always reflects what the next call will actually send.

Token counts are read through `Boukensha::Usage`, which knows where each provider hides them (`usage.input_tokens`, `usage.prompt_tokens`, `usageMetadata.promptTokenCount`, top-level `prompt_eval_count`). Reading Anthropic's names directly is how a context gauge sits at 0% all session on Gemini or Ollama — no error, nothing to notice.

### `Boukensha::Models`

A model → capability lookup, folded from every backend's own `MODELS` table at load time. `Boukensha.run` needs the window *before* a backend exists, which is the only reason the module exists; deriving it means the numbers cannot drift from the backend that owns them. Unknown models fall back to a conservative 32,000 rather than assuming a large window.

### Context colour coding

The progress and status lines colour the context indicator based on how full the window is:

| Usage | Colour | Meaning |
|-------|--------|---------|
| < 70% | Grey | Normal |
| 70–84% | Yellow | Approaching limit |
| ≥ 85% | Red | Compaction imminent |

A `⚠` also appears in the status bar at 85%+. The bar shows the percentage only — the absolute used/max pair lives on the progress line, because the bar is a fixed width and already carries version, model, tool count, MUD route and clock.

### Auto-compaction

At the start of each agent turn, if `current_tokens / context_window` crosses the task's `compaction_threshold` (default 0.85), the Agent compacts before making any API call:

```
[context compacted — 12 messages dropped to free space]
```

Compaction drops the oldest ~40% of messages (keeping at least 2) and resets `current_tokens` to 0. The first API call after compaction reports the true new size.

**The drop point is snapped forward to a plain user turn.** Dropping purely by count orphans a `tool_result` whose `tool_use` went with it — Anthropic answers that with a 400, and separately requires a conversation to open on a user turn. With the MUD tools registered, tool pairs are most of the history, so an unsnapped drop lands mid-pair more often than not.

### `Context#compact_messages!`

```ruby
dropped = context.compact_messages!(target_fraction: 0.60)
# => 12  (number of messages dropped)
```

### `/compact` command

Manual compaction from the REPL or TUI:

```
boukensha> /compact
(compacted context — 12 messages dropped)
```

### A second circuit breaker

A turn now stops on whichever trips first: `max_iterations` (tool-call count) or `max_turn_tokens` (cumulative input+output tokens this turn). A turn can be cheap in tool calls and expensive in tokens, so iterations alone do not bound spend. Either ceiling triggers the same tools-disabled wind-down call rather than raising. `0` disables a ceiling.

### Limits live with the task

Every per-turn ceiling is configured in one place — the task's block in `settings.yaml`:

```yaml
tasks:
  player:
    provider: anthropic
    model: claude-haiku-4-5
    max_iterations: 25          # tool-call ceiling
    max_turn_tokens: 60000      # spend ceiling for one turn
    max_output_tokens: 1024     # per-call output cap
    compaction_threshold: 0.85  # fraction of the context window
```

All four have defaults, so the block above is optional. `context_window` is deliberately *not* here: it is a model fact, not a preference.

### `Logger#compaction` event

```json
{"phase":"compaction","before":172000,"dropped":12,"context_window":200000}
```

Emitted whenever auto- or manual compaction runs. The TUI subscribes to this event to display the compaction notice in the conversation view.

### Normalized reasoning blocks

Every backend surfaces provider-specific thinking output (Anthropic `thinking`/`redacted_thinking`, Gemini `thought`/`thoughtSignature`, Ollama `message["thinking"]`) as a common `{"type" => "reasoning", ...}` block, logged via `Logger#reasoning`. Signatures round-trip unchanged so a continued turn is not rejected.

### `Boukensha.run` / `Boukensha.repl` — `context_window:` keyword

`token_budget:` is replaced by `context_window:`, defaulting to `Models.context_window(model)`:

```ruby
Boukensha.repl(context_window: 128_000)  # or a small value, to watch compaction fire
```

## Tests

No API key, no MUD, no network:

```sh
ruby test/test_context_compaction.rb   # token maths, drop count, the no-orphan invariant
ruby test/test_usage_accounting.rb     # the same counts from all four provider shapes
ruby test/test_agent_limits.rb         # both ceilings and the compaction trigger
ruby test/test_repl_commands.rb        # /help /clear /compact — never reach the model
ruby test/test_models_table.rb         # Models agrees with every backend
ruby test/test_config_mcp_servers.rb   # mcp_servers: parsed as data
ruby test/test_tools_mcp.rb            # MCP registration against a tiny stub server
```

Run them with plain `ruby`, not `bundle exec` — minitest is a system gem, not a bundled dependency.

## Run the demo

```sh
gem uninstall boukensha
gem build boukensha.gemspec
gem install boukensha-0.12.0.gem

ruby examples/example.rb
ruby examples/mcp_mud_demo.rb --dry   # 26 tools over MCP, no API calls

# from the repo root, with the config dir wired up for you:
bin/12_context

# via the global executable:
BOUKENSHA_DIR=~/Sites/Claude-Code-Camp/.boukensha BOUKENSHA_PATH=~/Sites/Claude-Code-Camp/week1_baseline/ruby/12_context boukensha
BOUKENSHA_MCP=1 boukensha              # MUD tools from the mud-manager daemon
```
