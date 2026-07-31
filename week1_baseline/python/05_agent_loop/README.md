# 05 · The Agent Loop (Python)

Python port of the Ruby baseline step
[`week1_baseline/ruby/05_agent_loop`](../../ruby/05_agent_loop/README.md).
Same behaviour, same `.boukensha/` config directory — see that README for the
design spec. Its prose on the normalized response shape and on tool-call IDs is
accurate and worth reading; **its file tables and sample output are not**. It
lists seven step-03 files as new, claims `context.rb` changed when it did not,
prints `[iteration 1]` where the code prints `[iteration 1/25]`, and renders
tool args in a Ruby format two versions out of date.

This step is where the agent finally *acts*: send, dispatch any tool calls,
repeat until the model signals `end_turn`. `agent.py` is new — but so is a
`parse_response` on all five backends, an `assistant_message` inverse on three
of them, and a `tools` override threaded through `Client` and `PromptBuilder`.
The loop only stays a single `if stop_reason == "tool_use"` branch because
every provider now normalizes into one shape.

## Environment

Shared repo-root `.venv/`, unchanged `requirements.txt` (the agent is pure
stdlib):

```sh
python3 -m venv .venv
.venv/bin/pip install -r week1_baseline/python/05_agent_loop/requirements.txt
```

Requires `ANTHROPIC_API_KEY`. **This step makes several billable calls per
run** — one per loop iteration.

## Run

```sh
./week1_baseline/bin/python/05_agent_loop
```

```
=== BOUKENSHA Step 5: Agent Loop ===

Config: #<Boukensha::Config dir=<repo>/.boukensha tasks=player>
Provider: anthropic
Model: claude-haiku-4-5
Max iterations: 25
Max output tokens: 1024

[iteration 1/25]
  tool call → read_file({'path': 'README.md'})
  tool result → # 05 · The Agent Loop (Python)…
[iteration 2/25]

=== FINAL RESPONSE ===
…
```

`max_iterations` and `max_output_tokens` are not set in `.boukensha/settings.yaml`,
so they fall back to `Tasks.Base.DEFAULT_MAX_ITERATIONS` (25) and
`DEFAULT_MAX_OUTPUT_TOKENS` (1024).

## The normalized response shape

Every backend implements `parse_response`, converting its provider's raw reply
into one shape that `Agent` alone understands:

```python
{"stop_reason": "tool_use" | "end_turn",
 "content": [{"type": "text", "text": ...},
             {"type": "tool_use", "id": ..., "name": ..., "input": {...}}]}
```

Four backends also implement the inverse — `_assistant_message`
(OpenAI/Ollama/OllamaCloud) or `_assistant_parts` (Gemini) — to rebuild a
provider-specific assistant turn when history is replayed. **Anthropic needs
neither**: its `content` array *is* the normalized shape, so `to_messages`
passes it through untouched.

Gemini, Ollama, and Ollama Cloud assign no tool-call IDs, so they reuse the
function name as the `id` and match results back by name.

## Verification

The stdout gate is weaker here than anywhere before: the example makes several
billable calls and the model chooses how many tools to call and in what order,
so two correct implementations diverge in iteration count, tool sequence, and
final text. Four checks replace it, all passing:

1. **Deterministic-prefix diff — first 9 lines**, through the first iteration
   banner:
   ```sh
   diff <(./week1_baseline/bin/ruby/05_agent_loop | head -9) \
        <(./week1_baseline/bin/python/05_agent_loop | head -9)
   ```
2. **Cross-language normalization — the real gate, and free.** Eight canned raw
   responses (Anthropic tool_use/end_turn, OpenAI tool_calls, Gemini
   functionCall, Ollama tool_calls, Ollama empty-text, a malformed `{}`) fed
   through all five backends' `parse_response`, plus `to_payload`,
   `to_payload(tools=[])`, the wrap-up directive, and the task defaults —
   dumped as JSON from both languages and diffed. **Byte-identical.** This is
   what covers the four backends the example never runs.
3. **Offline loop behaviour** with a stubbed client: a tool call round-trip
   returns the joined text; two tool blocks in one response both dispatch
   before the next call; the assistant message lands *before* its tool results;
   hitting the ceiling makes exactly one wind-down call with `tools=[]` and
   `max_output_tokens=400` without incrementing the counter; a wind-down that
   raises `ApiError` or returns whitespace falls back to the deterministic
   message; `max_output_tokens=0` is still forwarded.
4. **Live smoke test, once** — both exit `0`, reach `=== FINAL RESPONSE ===`,
   and log at least one `tool call →`.

Checks 2 and 3 run from the scratchpad; this repo deliberately has no test
framework and the example remains the smoke test.

## Differences from the Ruby version

- **Two truthiness traps, guarded with `is None`.** Ruby treats `0` and `[]` as
  truthy; Python does not, so the literal translations both break silently.
  - `Agent._call_opts` uses `if self.max_output_tokens is None`. A truth test
    would drop an explicit `max_output_tokens=0`, which Ruby forwards.
  - Every backend's `to_payload` uses
    `self.to_tools(context.tools) if tools is None else tools`. This is the
    dangerous one: `wrap_up` disables tools by passing `tools=[]`, and written
    as `tools or self.to_tools(...)` the empty list is falsy, so the full tool
    set would come back during the one call whose purpose is to stop the agent
    calling tools — silently defeating the iteration ceiling.

- **OpenAI's tool arguments are a JSON string, in both directions, and must be
  compact.** `parse_response` does `json.loads(...)` on
  `function.arguments`; `_assistant_message` does `json.dumps(..., separators=(",", ":"))`.
  The separators matter: Ruby's `#to_json` emits `{"path":"x"}` while Python's
  default `json.dumps` emits `{"path": "x"}`, and that string goes on the wire.
  Caught by verification check 2.

- **`dig()` replaces Ruby's `Hash#dig`.** Ruby's `response.dig("choices", 0,
  "message") || {}` degrades to `nil` on a missing key; a bare Python
  `response["choices"][0]["message"]` chain would raise. `backends/base.py`
  provides a small `dig(node, *keys)` that returns `None` at the first missing
  or non-indexable step, preserving the empty-response behaviour. Verified
  against a malformed `{}` input for every backend.

- **The `tool call → …` log line does not match Ruby, by decision.** Ruby 3.4
  renders the args as `{"path" => "."}`; Python renders `{'path': '.'}`. (The
  Ruby README shows a third format, `{:path=>"."}`, from an older Ruby — the
  rendering is not even stable within Ruby.) It is human-readable progress
  logging in output that is already non-deterministic, so pinning Python to one
  Ruby version's `Hash#inspect` would be a maintenance trap for no gain.

- **`LoopError` is ported but unused.** Ruby declares it in `errors.rb` and
  never raises or rescues it anywhere — the loop winds down via a final
  tools-disabled call instead. Kept for surface parity and flagged in its
  docstring so nobody hunts for the raise site.

- **`int(value)` rather than Ruby's `Integer(value)`** in
  `Tasks.Base._integer_setting`. Ruby's is stricter — it rejects `"08"` and
  trailing garbage — but no settings file exercises that, and Python's
  `ValueError` is already a clear failure for genuinely bad input.

- **`config.py` needed no change.** Ruby's `config.rb` diff for this step is
  real but purely Ruby 3 endless-method sugar (`def mud_host = …`), with
  identical behaviour. Python already had these as properties.

- Carried over: `PROMPTS_DIR` stays correct at `parents[1]`, diverging from
  Ruby's broken `../../../prompts` (settled in step 04); `urllib.request` over
  `requests`; the `@registry.tool(...)` decorator standing in for a Ruby block;
  `HTTPError` caught before `URLError` in the client.
