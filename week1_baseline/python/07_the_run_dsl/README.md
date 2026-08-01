# 07 · The Run DSL (Python)

Python port of the Ruby baseline step
[`week1_baseline/ruby/07_the_run_dsl`](../../ruby/07_the_run_dsl/README.md).
Same behaviour, same `.boukensha/` config directory — see that README for the
design spec, but note it is titled **"Step 6"** and its `Boukensha.run` doc
comment describes defaults the code does not have (details below).

This step adds one entry point, `boukensha.run(...)`, that wires together every
primitive built so far. The example drops from 92 lines to 34 — everything
between `Config()` and `agent.run()` disappears into `run.py`.

## Environment

Shared repo-root `.venv/`, unchanged `requirements.txt`:

```sh
python3 -m venv .venv
.venv/bin/pip install -r week1_baseline/python/07_the_run_dsl/requirements.txt
```

Requires `ANTHROPIC_API_KEY`. **This step makes several billable calls per
run** — one per loop iteration.

## Run

```sh
./week1_baseline/bin/python/07_the_run_dsl
```

```
=== BOUKENSHA Step 7: The Boukensha.run DSL ===

Config: #<Boukensha::Config dir=<repo>/.boukensha tasks=player>


=== FINAL RESPONSE ===
…
```

## The whole example

```python
def define_tools(dsl):
    @dsl.tool(
        "read_file",
        description="Read the contents of a file from disk",
        parameters={"path": {"type": "string", "description": "The file path to read"}},
    )
    def read_file(path):
        return (base_dir / path).read_text()


result = boukensha.run(
    task="Read the README.md file and summarise …",
    tools=define_tools,
)
```

`run` resolves the config, system prompt, model, provider and API key from
`.boukensha/settings.yaml`; builds the Context, Registry, backend, PromptBuilder,
Client, Logger and Agent; hands you the registry at the one moment it is useful;
and closes the logger on the way out. Every default can be overridden by keyword:
`system`, `model`, `backend`, `api_key`, `ollama_host`, `log`,
`max_output_tokens`.

## Why the `tools=` callback exists

`run` has to build the `Registry` itself, because the registry attaches to the
`Context` that `run` also builds. But the caller is the one who knows which tools
they want — and they must be registered *before* the PromptBuilder serializes
them. So `run` builds the registry, hands control back, then carries on. The
callback is that handoff.

`RunDSL` wraps the registry and exposes only `tool`, so nothing else (`dispatch`
in particular) is reachable from inside the callback.

## Verification

All checks pass.

1. **Deterministic-prefix diff — first 4 lines.** Identical.
   ```sh
   diff <(./week1_baseline/bin/ruby/07_the_run_dsl | head -4) \
        <(./week1_baseline/bin/python/07_the_run_dsl | head -4)
   ```
2. **JSONL structural diff.** Both languages run live; the two newest session
   files match on event count, phase sequence, and key list *and key order* for
   every event. `session_start` now carries
   `task`/`max_iterations`/`max_output_tokens`/`model`/`provider` in that order —
   step 06's was bare.
3. **36 offline `run()` wiring checks**: the `tools=` callback receives a
   `RunDSL` and its registrations reach the Context; omitting `tools=` is legal;
   all five backend names build the right class; `ollama` needs no API key and
   honours `ollama_host`; an unknown backend raises `ValueError`; explicit
   `model` / `system` / `api_key` / `log` / `max_output_tokens` beat the
   defaults; the logger is closed on the success path *and* when the agent
   raises, and is never constructed when backend selection fails first.
4. **11 offline logger checks** for the two new methods: `turn` writes its phase
   with the right key order; a subscriber receives every event in order and only
   after the line is flushed to disk; multiple subscribers all fire; zero
   subscribers is not an error.
5. **Regression:** step 06's loop suite (25 checks) passes unchanged, and 27 of
   its 29 logger checks still pass — the two failures are its assertions that
   `LoopError` and `mud_*` are *absent*, which this step deliberately reverses.
6. **Live smoke test** — both exit `0`, both session files parse in `log_viz`,
   which now renders the iterations bar (25) for the first time, since
   `max_iterations` is in the snapshot. `max_turn_tokens` and `context_window`
   are still absent, so those two bars stay hidden until step 12.

> One check needed tightening. The escape-check in `jsonl_diff.py` originally
> looked for the two characters `\u`, and started failing in **both** languages
> — because the agent's `read_file` tool reads this README, and this README
> describes the check. A literal backslash-u in tool-result text is legitimate;
> the check now matches a real `\uXXXX` escape with a negative lookbehind.

## Differences from the Ruby version

- **No `instance_eval`, so the DSL keeps its receiver.** Ruby runs the block
  through `RunDSL.new(registry).instance_eval(&block)`, which rebinds `self` so
  tools read as a bare `tool "read_file"`. Python cannot rebind name resolution
  inside a function body, so the DSL object is an explicit parameter and you
  write `@dsl.tool(...)`. The mechanism is identical; the "reads like a
  language" part is not reproducible. `RunDSL` is kept anyway so the Ruby
  surface still maps 1:1 — but be honest that in Python it earns very little
  over using the `Registry` directly, since `@registry.tool(...)` has the same
  shape.

- **`run` lives in `boukensha/run.py`, not `__init__.py`.** Ruby puts
  `self.run` directly in `module Boukensha`. A function in `__init__.py` would
  work here (no cycle — `run` is defined after every import), but it would put
  ~60 lines of wiring in a file that is otherwise a manifest. Consistent with
  the `runtime.py` decision from step 06. Callers still write
  `boukensha.run(...)`.

- **`max_output_tokens` uses `or`, not `is None` — the reverse of the usual
  rule.** Ruby's `max_output_tokens || task_class.max_output_tokens(settings)`
  is a truthiness test, so an explicit `0` falls through to the task default.
  Every previous step has been "use `is None`, Ruby's `0` is truthy"; here the
  faithful port is `or`. `Agent._call_opts` still guards `0` correctly one layer
  down, and diverging here would make the two languages disagree. Asserted
  explicitly in check 3.

- **`logger = None` before the `try`.** Ruby's `ensure logger&.close` works
  because a local assigned anywhere in a method body exists (as `nil`) from
  parse time. Python would raise `UnboundLocalError` if construction failed
  before the assignment, so the name is bound up front and the `finally` guards
  on it.

- **`backend` stays a string.** Ruby calls `.to_sym` on the provider and
  compares symbols. Python has no symbols and every comparison downstream is
  string-based.

- **`_subscribers` is initialized in `__init__`.** Ruby lazily creates
  `@subscribers ||= []` inside `subscribe`, because an unset ivar reads as
  `nil`. Python has no such excuse and `write_log` has to handle the empty case
  regardless.

- **The banner keeps Ruby's wording.** The example prints
  `The Boukensha.run DSL`, not `boukensha.run`, so the prefix diff stays clean.
  Same precedent as `Config.__str__`, which emits `#<Boukensha::Config …>` in
  Python for exactly this reason.

- **`turn(n=)` and `subscribe()` are dead code in this step, in both
  languages.** Nothing calls either — the agent only ever calls `turn_end`.
  `log_viz`'s parser already handles a `turn` phase, and the TUI step is the
  obvious consumer of `subscribe`, so both are groundwork. Ported for surface
  parity, and because `subscribe` changes `write_log`'s behaviour.

- **`LoopError` and `mud_*` are back, one step after being deleted — and still
  unused.** See below; this is not a porting decision.

- Carried over: `PROMPTS_DIR` at `parents[1]`; `urllib.request` over `requests`;
  `set_`/`is_` for Ruby's `!`/`?`; `runtime.py` for module state;
  `separators=(",", ":")` with `ensure_ascii=False`; `HTTPError` before
  `URLError`.

## The Ruby steps are not a linear progression

Worth recording, because it explains churn that otherwise looks like a mistake.

Three things step 06 **deleted** are restored here, in their pre-06 form:

| Thing | 04 | 05 | 06 | 07 |
|---|---|---|---|---|
| `LoopError` | absent | added | deleted | **restored** |
| `Config#mud_*` | four-line | endless methods | deleted | **restored, four-line** |
| `context.rb` alignment | misaligned | aligned | aligned | **misaligned again** |

`07/errors.rb` is byte-identical to `05/errors.rb`. `07/config.rb` restores the
four-line `mud_*` bodies that step 05 had rewritten as endless methods, *and*
reverts step 06's `@dir =` alignment and its one-line `load_env` guard. The
evidence says step 07 was branched from around step 04/05 rather than from step
06.

Python mirrors it, per the standing rule that the Ruby is the spec and
divergences get documented rather than silently corrected — a Python tree that
stayed "ahead" would make every later diff harder to read. But the lesson is
that *"what changed between step N and N+1"* is not always *"what the author
intended to change"*, and a diff-driven port has to be able to tell those apart.

## Stale Ruby documentation

Fourth consecutive step with README drift; recording it since the pattern is now
the expectation rather than the surprise.

- The Ruby README is titled **"Step 6 — The Boukensha.run DSL"**.
- The `Boukensha.run` doc comment claims `system:` defaults to
  `config.system_prompt` and `model:` to `config.model`. Step-07 `Config`
  exposes only `dir` and `settings`; both actually come from `Tasks::Player`.
- The same comment says `backend:` defaults to `:anthropic`. It defaults to
  `task_class.provider(task_settings)`, i.e. whatever `settings.yaml` says.

The Python docstring in `run.py` documents the real defaults and notes the
discrepancy.
