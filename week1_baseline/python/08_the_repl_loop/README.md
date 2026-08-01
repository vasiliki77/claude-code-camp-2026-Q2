# 08 · The REPL Loop (Python)

Python port of the Ruby baseline step
[`week1_baseline/ruby/08_the_repl_loop`](../../ruby/08_the_repl_loop/README.md).
Same behaviour, same `.boukensha/` config directory. Note that Ruby README is
titled **"Step 7 — The REPL Loop"** and calls step 07 "step 6" throughout; its
prose on why the assistant reply must be persisted is accurate and worth
reading.

`repl.py` is the visible new file, but **the step's real subject is memory**: up
to step 07 the agent returned its final text and never stored it, so a second
turn over the same Context would see the user's question and the tool results
but not the answer. `agent.py` gains three `add_message("assistant", …)` calls,
and that is what makes an interactive loop possible at all.

## Environment

Shared repo-root `.venv/`, unchanged `requirements.txt`:

```sh
python3 -m venv .venv
.venv/bin/pip install -r week1_baseline/python/08_the_repl_loop/requirements.txt
```

Requires `ANTHROPIC_API_KEY`. **Each turn makes one or more billable calls.**

## Run

```sh
./week1_baseline/bin/python/08_the_repl_loop
```

```
Config: #<Boukensha::Config dir=<repo>/.boukensha tasks=player>


╔══════════════════════════════════════╗
║  BOUKENSHA MUD Assistant (v0.8.0)    ║
╚══════════════════════════════════════╝
  config:    <repo>/.boukensha
  provider:  anthropic (claude-haiku-4-5)  ✓ API key set

  /quiet or /loud   toggle logging
  /clear           reset conversation history
  /exit or /quit    leave the REPL

boukensha>
```

`/exit` or `/quit` leaves with `Goodbye.`; Ctrl-D (EOF) leaves silently; Ctrl-C
prints `Interrupted.`. All three close the session log.

The example's tools are pointed at the **step 07 folder**, deliberately — it is
a directory with real source files to read.

## What each turn does

`Repl.run_turn` logs a `turn` event, appends the user message, and builds a
**fresh `Agent` over the one shared `Context`**. So the iteration counter resets
every turn while the transcript does not — which is exactly what you want: each
turn gets its own 25-iteration budget, and the model still sees everything said
so far.

`logger.turn(n=)` gets its first caller here; it was added unused in step 07.

## Verification

All checks pass.

1. **Banner diff — byte-identical**, including the two blank lines after
   `Config:`, the 4-space pad inside the box, the uneven spacing on the
   `/clear` line, and the trailing `boukensha> ` with no newline:
   ```sh
   diff <(echo -n "" | ./week1_baseline/bin/ruby/08_the_repl_loop) \
        <(echo -n "" | ./week1_baseline/bin/python/08_the_repl_loop)
   ```
2. **Built-in command script — byte-identical, and free.** No API calls, so this
   can run as often as you like:
   ```sh
   printf '/help\n/quiet\n/loud\n/clear\n\n/exit\n' | ./…/08_the_repl_loop
   ```
   Covers the help text, all three acknowledgement lines, the blank-line skip,
   and `Goodbye.`.
3. **24 offline REPL checks** with a stubbed client: history accumulates across
   turns and the second turn's `prompt` event carries the full transcript; the
   final assistant text is in the Context (**the regression guard for this
   step**); a tool-using turn stores tool-use content *and* the final text,
   exactly once each; `/clear` empties messages but keeps tools and resets the
   turn counter; `logger.turn` fires once per real turn and not for built-ins or
   blank lines; the iteration counter resets per turn, proving a new Agent;
   `ApiError` prints and the REPL survives; EOF exits without `Goodbye.`;
   `KeyboardInterrupt` prints `Interrupted.` and still closes the logger; the
   three-tier config resolution in all three orders; the 401 message, and that
   403 keeps the generic one.
4. **Regression:** the step 05–07 suites all pass unchanged against this
   folder — the loop suite (25), the `run()` wiring suite (36), and the
   `turn`/`subscribe` logger suite (11).
5. **Live smoke test** — both exit 0, both session logs have an identical phase
   sequence starting `session_start, turn, iteration, …`, and both parse in
   `log_viz`.

## Differences from the Ruby version

- **`_build_session()` is Python-only.** Ruby's `Boukensha.repl` is
  `Boukensha.run` copy-pasted with a different tail — the ~45 lines from
  `cfg = config` down to the `Logger` are identical in both. Python factors them
  into one private helper that `run()` and `repl()` each call, then diverge.
  This is a deliberate structural divergence, not a behaviour change: every
  check above passes either way. The reason is that this codebase has already
  shown twice what happens to parallel copies that need hand-syncing — the
  `LoopError`/`mud_*` churn across steps 05–07, and the `BOUKENSHA_DIR` path
  that drifted in 4 of 13 files. Steps 09–12 extend both entry points further.

- **`input()` rather than a `readline()` transcription.** Ruby's `$stdin.gets`
  returns `nil` at EOF; Python's `input()` raises `EOFError`, so the loop breaks
  in an `except` instead of on a falsy return. `input()` also strips the newline
  itself, making Ruby's `.chomp` redundant. **A side effect worth knowing: when
  the `readline` module is available, `input()` gives line editing and history
  for free, so the Python REPL is slightly nicer to use than the Ruby one.**
  Left in — suppressing it would mean giving up standard behaviour to match a
  limitation.

- **`clear_messages()`, no bang.** Ruby's `!` suffix has no Python equivalent.
  It rebinds `self.messages = []` rather than mutating in place, matching
  Ruby's `@messages = []` — anything holding the old list keeps it.

- **The banner's pad is a latent divergence.** `" " * (9 - len(ver))` yields
  `""` in Python when negative; Ruby raises `ArgumentError`. Unreachable while
  `VERSION` is 5 characters, commented at the site.

- **`/quiet` and `/loud` do nothing, in both languages.** They set a flag and
  print "(logging suppressed — type /loud to re-enable)", but **nothing anywhere
  reads `is_quiet()`** — `grep` over the Ruby `08/lib` finds only the
  definition. Ported faithfully rather than fixed: making them actually suppress
  output would put Python ahead of the spec and break the byte-identical command
  diff in check 2. Step 11's TUI is the likely place the flag finally gets read.

- **The `LoopError` handler in `_run_turn` is unreachable.** `LoopError` is
  declared in `errors.py` and raised nowhere, in any step. Kept because Ruby
  rescues it here. Third dead surface carried for parity, after `mud_*` and
  `quiet`.

- Carried over: `runtime.py` for module state; `run.py` for the entry points;
  `set_`/`is_` for Ruby's `!`/`?`; the `tools=` callback standing in for
  `instance_eval`; `separators=(",", ":")` with `ensure_ascii=False`; `or` vs
  `is None` matched to Ruby's own test in each spot.

## `BOUKENSHA_DIR` moved to the launchers

Separately from this step's delta, and mirroring the same change made to
`bin/ruby/*`: all 9 `bin/python/*` launchers now derive `REPO_ROOT` once and
export `BOUKENSHA_DIR` with `:=` (so an external value still wins), and the
`os.environ.setdefault(..., parents[4] / ".boukensha")` block is gone from all 9
`example.py` files. Steps 01 and 02 also lost a now-unused `import os`.

That hand-counted depth is what drifted in 4 of 13 Ruby examples on 01-08;
removing the duplication removes the whole class. Steps 00–03 still diff
byte-identically against Ruby afterwards.

**Trade-off:** `python examples/example.py` run directly now falls back to the
new tier-2 lookup (`./.boukensha` in the cwd) or `~/.boukensha`. From the repo
root that happens to work; from a step folder it does not. Use the launcher, or
set the variable.
