# 11 · A Terminal UI (Python)

Python port of the Ruby baseline step
[`week1_baseline/ruby/11_tui`](../../ruby/11_tui/README.md).

`boukensha.repl()` gains a `tui=` keyword (default `True`) wrapping the plain
REPL in a full-screen terminal UI. **The REPL keeps owning every piece of
session logic** — turn counting, slash commands, agent dispatch. The TUI only
replaces how input is read and output is written.

```
┌──────────────────────────────────────┐
│  conversation viewport (scrollable)  │
├──────────────────────────────────────┤
│  progress / idle line                │
├──────────────────────────────────────┤
│  input box                           │
├──────────────────────────────────────┤
│  status bar (always on)              │
└──────────────────────────────────────┘
```

## Run

```sh
./week1_baseline/bin/python/11_tui              # the TUI
./week1_baseline/bin/python/11_tui --no-tui     # plain REPL, exactly step 10's
```

`--no-tui` is parsed in `examples/example.py`. Ruby reaches its TUI through the
installed gem's `bin/boukensha` via `boukensha_loader.rb` — a packaging concept
this port has excluded since step 10 — while every Python step's launcher runs
the example directly. A one-line divergence in *where* the flag is parsed, not
in what it does.

## Keys

| Key | Action |
| --- | --- |
| `enter` | submit |
| `escape` | cancel the running turn (see below) |
| `ctrl+l` | `/clear` |
| `pageup` / `pagedown` | scroll history |
| `ctrl+c` / `ctrl+d` | quit |

Slash commands (`/help`, `/quiet`, `/loud`, `/clear`, `/exit`) work in both modes.

## charm → Textual

Ruby uses `charm` — bubbletea, lipgloss and bubbles, a Go runtime reached
through a native FFI binding. There is no Python binding to Bubble Tea, so this
targets [Textual](https://github.com/Textualize/textual): the closest conceptual
match to bubbletea's reactive model/update/view loop, pure Python with no
per-platform build step, and with a headless test harness Ruby's setup has no
equivalent of.

**`patches/bubbletea/` is deliberately not ported.** It works around a
burst-input bug in that FFI binding, where a multi-byte `read()` lost all but
the first keypress. Textual has no FFI boundary of that shape, so there is
nothing to patch.

## `Repl`'s new public surface

Three pieces, so a TUI can drive the session without reimplementing any of it:

| Method | Purpose |
| --- | --- |
| `on_output(callback)` | route output through `callback` instead of stdout |
| `handle_command(line)` | dispatch a slash command → `"quit"` / `"command"` / `None` |
| `run_turn(line)` | run one turn (was private) |

`banner()` and `mud_status()` also became public — the TUI renders the first
into its conversation log and derives the status bar's route label from the
second.

Ruby needed `attr_reader` for `logger`, `context`, `model` and `version`;
Python's attributes were public already.

## Technical Considerations

### Esc cancels at a boundary, not mid-request

Ruby's Esc handler calls `Thread#raise(Interrupt)` on the turn thread, landing
wherever that thread currently is — including inside a blocking read, because
MRI checks for pending interrupts around blocking I/O.

Python has no safe equivalent. `PyThreadState_SetAsyncExc` only fires the next
time the target thread returns to Python bytecode, so it **cannot** cut short an
HTTP call already in flight; it would take effect once that call returned
anyway, which is exactly when it no longer matters.

So cancellation here is cooperative: `Agent(cancel_event=...)` checks a
`threading.Event` at the top of each loop iteration and raises `TurnCancelled`.

> **Accepted gap:** Esc does not interrupt a single in-flight backend call, only
> takes effect at the next iteration or tool-call boundary. A deliberate,
> documented divergence — not a missed port.

### Widget mutation crosses a queue

The Repl's output callback and the logger subscriber both fire on the background
turn thread. Textual widgets may only be touched from the app's own event loop,
so everything crosses a `queue.Queue` and is drained on tick — the same shape
Ruby uses, for the same reason.

### The tick timer is stopped on unmount

Textual keeps firing an interval while the app tears down, by which point the
widgets it queries are gone. Without stopping it, quitting crashes with
`NoMatches` — intermittently, depending on whether a tick lands inside the
teardown window. Found by the test suite rather than by use, because suite
timing differs from interactive timing.

## Tests

```sh
.venv/bin/python -m unittest discover -s test
```

61 tests. Beyond step 10's 38:

- `test_repl_composability.py` — `handle_command` return values and side
  effects, output routed through the callback with **nothing reaching stdout**,
  `run_turn` routing results and all three error types, and `Agent` raising
  `TurnCancelled` at the next boundary without a backend call.
- `test_tui.py` — driven through Textual's headless harness (`app.run_test()`
  / `Pilot`): typing and submitting, slash-command dispatch, `ctrl+l`, Esc
  setting the cancel event mid-turn (and being harmless when idle), the status
  bar's route label in all three states, and a failed turn still clearing the
  progress line. **Ruby ships no automated coverage for its own `Tui`** — this
  is a net gain the harness makes possible, not scope creep.

The `tui=False` REPL is diffed byte-for-byte against step 10's, which is the
only fully deterministic gate this step has; a full-screen app is not diffable.

## Divergences from Ruby

- **`tui=` is on `repl()` only.** `run()` is untouched — Ruby's `Tui` only ever
  wraps `Repl`.
- **`Tui.run()`, not `Tui.start()`.** Textual's entry point is `run()`. `Tui`
  has no `start`, so there is exactly one way to launch it.
- **The `Tui` import is guarded.** A missing `textual` degrades to the plain
  REPL rather than breaking every import of the package — including the tests
  and `mcp_mud_demo.py`.
- **`_output` mimics Ruby's `puts`**, which leaves a trailing newline alone
  where Python's `print` adds a second. Byte-identity with step 10 depends on it.
- **Version is `0.11.0`**, matching this repo's Ruby step 11. The instructor's
  is `0.11.1`.
- **`textual` is pinned** (`==8.2.8`), matching the other two requirements.
  Textual's widget API moves between majors; an unpinned install later may not
  have `RichLog`.
