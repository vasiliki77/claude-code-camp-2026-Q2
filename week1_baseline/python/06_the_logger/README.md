# 06 · The Logger (Python)

Python port of the Ruby baseline step
[`week1_baseline/ruby/06_the_logger`](../../ruby/06_the_logger/README.md).
Same behaviour, same `.boukensha/` config directory — see that README for the
design spec. Its prose on why session logging is structured is worth reading;
**its "Logger API" table is not**. That table lists `iteration(n:)` where the
code takes `n:` *and* `max:`, invents a `budget:` parameter for `prompt`, omits
`ok:` / `error:` from `tool_result` and `stop_reason:` from `response`, and
leaves out `limit_reached` and `turn_end` entirely. The API here comes from
`logger.rb`.

This step replaces every `print` in the agent loop with a structured event.
`logger.py` is new, `agent.py` is rewired around it, and `runtime.py` holds the
process-wide config/debug state. **Two things are also deleted**: `LoopError`
(added last step) and `Config`'s four `mud_*` properties.

The artifact this step produces is no longer stdout — it is
`.boukensha/sessions/<session-id>.jsonl`, one JSON object per line. The
[`log_viz`](../../ruby/log_viz/README.md) Sinatra app reads those files back.

## Environment

Shared repo-root `.venv/`, unchanged `requirements.txt` (the logger is pure
stdlib — `json`, `secrets`, `datetime`, `pathlib`):

```sh
python3 -m venv .venv
.venv/bin/pip install -r week1_baseline/python/06_the_logger/requirements.txt
```

Requires `ANTHROPIC_API_KEY`. **This step makes several billable calls per
run** — one per loop iteration.

## Run

```sh
./week1_baseline/bin/python/06_the_logger
```

```
=== BOUKENSHA Step 6: The Logger ===

Config: #<Boukensha::Config dir=<repo>/.boukensha tasks=player>
Provider: anthropic
Model: claude-haiku-4-5
Max iterations: 25
Max output tokens: 1024


=== FINAL RESPONSE ===
…
```

Note the gap where step 05 printed `[iteration 1/25]` and `tool call → …`. Those
lines are gone; the same information is now in the session log.

## The event stream

| Method | Phase | Carries |
|---|---|---|
| *(constructor)* | `session_start` | the `snapshot` dict, merged after `phase` |
| `iteration(n=, max=)` | `iteration` | loop counter and its ceiling |
| `limit_reached(kind=, n=, max=)` | `limit_reached` | which limit tripped |
| `prompt(messages=, tools=)` | `prompt` | message count, serialized messages, tool names |
| `tool_call(name=, args=)` | `tool_call` | tool name and arguments |
| `tool_result(name=, result=, ok=, error=)` | `tool_result` | stringified result, success flag, error message |
| `response(text=, usage=, stop_reason=, task=, backend=)` | `response` | text, token usage, task/provider/model, estimated cost |
| `raw(data=)` | `raw` | the full provider response — **only when debug is on** |
| `turn_end(reason=, iterations=, tokens=)` | `turn_end` | why the turn ended and how many iterations it took |

Every event also gets `session_id` and `at`, appended in that order as the final
two keys.

To capture raw provider responses:

```python
import boukensha
boukensha.set_debug()
```

## Verification

The stdout gate is now nearly the whole of stdout — but it no longer covers the
step's subject, so the JSONL is the real gate. All checks pass.

1. **Deterministic-prefix diff — first 8 lines.** Identical.
   ```sh
   diff <(./week1_baseline/bin/ruby/06_the_logger | head -8) \
        <(./week1_baseline/bin/python/06_the_logger | head -8)
   ```
2. **JSONL structural diff — the real gate.** Both languages run live, then the
   two newest session files are compared on everything that is not free text,
   token counts, ids or timestamps. **10 events each, identical phase sequence,
   identical key list *and key order* on every event**, matching
   `task`/`provider`/`model`/`usage_unit`/`stop_reason`/`ok`/`error`/`reason`,
   and no `", "`, `": "` or `\u` escapes in either raw file.
3. **29 offline logger checks** — timestamp precision, session-id format,
   snapshot merge position, the selective-`compact` asymmetry, separator style,
   em-dash encoding, `raw` gating, `task` serializing as `"player"`,
   `provider_name` across all five backend classes, the usage-key fallbacks, and
   `estimate_cost` at 0 tokens.
4. **25 offline loop-integration checks** with a stubbed client, asserting event
   *sequences* rather than text: normal completion; the placeholder-vs-prose
   choice for a tool-use turn; singular/plural call counts; a raising tool
   producing `ok=false` with the loop continuing; `limit_reached` immediately
   before a single wind-down `response`; `turn_end` keeping the limit reason;
   `ApiError` in the wind-down logging `turn_end` but no `response`; a blank
   wind-down falling back; `max_output_tokens=0` still forwarded.
5. **Live smoke test** — both exit `0`, both session files parse cleanly in
   `log_viz` (5 transcript entries, 2 iterations, `reason=completed`).

Checks 2–4 run from the scratchpad; this repo deliberately has no test framework
and the example remains the smoke test.

## Differences from the Ruby version

- **`runtime.py` exists only in Python.** Ruby puts `config` / `quiet!` /
  `debug!` directly in the `Boukensha` module in `lib/boukensha.rb`, and
  `logger.rb` reaches them at call time. The literal transcription — module state
  in `__init__.py` — is a circular import, because `__init__` imports `logger`
  and `logger` would import `__init__`. A separate module avoids the cycle
  without a deferred-import trick, and everything is re-exported so callers still
  write `boukensha.config()`.

- **`!` and `?` become `set_` and `is_`.** Ruby's `quiet!` / `loud!` / `quiet?` /
  `debug!` / `debug?` map to `set_quiet()` / `set_loud()` / `is_quiet()` /
  `set_debug()` / `is_debug()`. This is the first step to hit Ruby's bang and
  predicate suffixes, so it sets the convention for the rest of the port. A bare
  `quiet()` would be ambiguous between setter and getter at the call site.

- **`quiet` is dead code in this step, in both languages.** Nothing consults
  `is_quiet()` yet. Ported for surface parity with later steps. `is_debug()` *is*
  live — `Logger.raw()` gates on it.

- **Timestamps need `timespec="seconds"`.** Ruby's `Time#iso8601` emits no
  fractional seconds (`2026-08-01T12:50:16+01:00`); Python's `isoformat()`
  defaults to microseconds and would not match.

- **`json.dumps` needs `separators=(",", ":")` *and* `ensure_ascii=False`.**
  Ruby's `JSON.generate` is compact and emits raw UTF-8. The separators issue
  first appeared in step 05 (OpenAI's `function.arguments`); here it applies to
  every line of the deliverable. `ensure_ascii` is new this step and non-obvious:
  the agent logs `"(tool use — N calls)"` with an em dash, which the default
  `json.dumps` would escape to `—`.

- **Key order is part of the output.** Ruby hashes and Python dicts both preserve
  insertion order, so building each event in Ruby's order yields a matching line
  — but only deliberately. Verified per-event by check 2.

- **`.compact` is selective, so a blanket None-strip would be wrong.** Only the
  `response` event's task/provider/model/cost block drops its `None` values.
  `tool_result` deliberately keeps `"error":null` and `turn_end` keeps
  `"tokens":null`.

- **`task.task_name()` must be called.** Ruby's
  `task.respond_to?(:task_name) ? task.task_name : …` returns the string.
  Transcribed literally, Python hands `json.dumps` a bound method object and
  raises `TypeError` — and since `task_name` is a `classmethod`, `hasattr`
  passes, so the bug fires on the very first `response` event.

- **`logger=None` in the signature, `Logger()` in the body.** Ruby's
  `logger: Logger.new` default is evaluated per call; Python evaluates defaults
  once at def-time, which would share one open file handle across every `Agent`
  ever constructed. Same reasoning for `snapshot=None` on `Logger`.

- **`estimate_cost` guards with `is None`.** A genuine 0-token count is truthy in
  Ruby and falsy in Python — the same trap that hit `estimate_cost` in step 03
  for free local models.

- **`first_integer` drops Ruby's symbol-key half.** Ruby checks `hash[key] ||
  hash[key.to_sym]`; a JSON-decoded dict in Python only ever has string keys. The
  multi-key fallback list (`input_tokens` / `prompt_tokens` / `promptTokenCount` /
  `prompt_eval_count`) is kept — it is what lets one logger read every provider's
  usage shape.

- **`ValueError` where Ruby rescues `ArgumentError`.** Ruby's `Integer()` raises
  `ArgumentError` on a non-numeric string; Python's `int()` raises `ValueError`.
  Both also handle `TypeError`.

- **The tool-error string differs, by the same decision as step 05's
  `tool call →` line.** Ruby's `e.class` renders `Boukensha::UnknownToolError`;
  Python's `type(e).__name__` renders `UnknownToolError`. It is a human-readable
  message inside a log field, not data anything parses, and matching Ruby's
  namespace form would mean hardcoding a Ruby module path into Python.

- **`LoopError` is gone, one step after being added.** Step 05 ported it for
  surface parity; Ruby deletes it here. Surface parity is a per-step decision,
  not a standing one.

- **Three Ruby files changed with no Python consequence.** `context.rb` is
  whitespace-only; `config.rb`'s first hunk is alignment (its *real* change is
  deleting the `mud_*` readers, which is mirrored); and
  `prompt_builder.rb` adds `attr_reader :backend`, which Python already had as a
  public attribute.

- Carried over: `PROMPTS_DIR` stays correct at `parents[1]`, diverging from
  Ruby's broken `../../../prompts`; `urllib.request` over `requests`; the
  `@registry.tool(...)` decorator standing in for a Ruby block; `HTTPError`
  caught before `URLError`; the two step-05 truthiness guards
  (`max_output_tokens is None`, `tools is None`).
