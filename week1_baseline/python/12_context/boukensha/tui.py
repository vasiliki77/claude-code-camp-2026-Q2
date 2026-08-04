import queue
import threading
import time

from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.containers import Vertical
from textual.widgets import Input, RichLog, Static

from . import usage as usage_mod
from .agent import Agent
from .errors import TurnCancelled

SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
TICK_SECONDS = 0.06  # Ruby's TICK_MS = 60


def _fmt_tokens(n):
    n = int(n or 0)
    return f"{round(n / 1000.0, 1)}k" if n >= 1000 else str(n)


class Tui(App):
    """A full-screen terminal UI wrapping a Repl.

    Ruby uses charm (bubbletea + lipgloss + bubbles), a Go runtime reached
    through a native FFI binding. There is no Python binding to Bubble Tea, so
    this is Textual — the closest conceptual match to bubbletea's reactive
    model/update/view loop, pure Python with no per-platform build step, and
    with a headless test harness Ruby's setup has no equivalent of.

    Ruby's `patches/bubbletea` is deliberately not ported: it works around a
    burst-input bug in that FFI binding, where a multi-byte read() lost all but
    the first keypress. Textual has no FFI boundary of that shape.

    **The Repl keeps owning every piece of session logic** — turn counting,
    slash commands, agent dispatch. This class only replaces how input is read
    and output is written. Four zones, matching Ruby's layout:

        ┌──────────────────────────────────────┐
        │  conversation viewport (scrollable)  │
        ├──────────────────────────────────────┤
        │  progress / idle line                │
        ├──────────────────────────────────────┤
        │  input box                           │
        ├──────────────────────────────────────┤
        │  status bar (always on)              │
        └──────────────────────────────────────┘
    """

    # Ruby colours the context readout inline via lipgloss; Textual has no
    # equivalent, so the same three states are CSS classes toggled on the
    # widget. The `.idle.ctx-*` selectors are deliberate: the idle line is the
    # one that shows context usage, and a bare `.idle` rule would otherwise win
    # on specificity and paint the warning grey.
    CSS = """
    Screen { layout: vertical; }
    #conversation { height: 1fr; border: none; padding: 0 1; }
    #progress { height: 1; padding: 0 1; color: $accent; }
    #progress.idle { color: $text-disabled; }
    #progress.idle.ctx-warn { color: $warning; }
    #progress.idle.ctx-alert { color: $error; }
    #prompt { height: 3; border: none; }
    #status { height: 1; background: $panel; color: $text; }
    #status.ctx-warn { color: $warning; }
    #status.ctx-alert { color: $error; }
    """

    # Thresholds for context-usage colour coding.
    CTX_WARN_PCT = 70
    CTX_ALERT_PCT = 85

    BINDINGS = [
        ("ctrl+c", "quit_app", "Quit"),
        ("ctrl+d", "quit_app", "Quit"),
        ("escape", "cancel_turn", "Cancel turn"),
        ("ctrl+l", "clear_history", "Clear"),
        ("pageup", "scroll_back", "Scroll up"),
        ("pagedown", "scroll_forward", "Scroll down"),
    ]

    def __init__(self, repl):
        super().__init__()
        self._repl = repl
        # Both the Repl's output callback and the logger subscriber fire on the
        # background turn thread. Textual widgets may only be touched from the
        # app's own event loop, so everything crosses this queue and is drained
        # on tick — the same Queue + drain-on-tick shape Ruby uses, for the same
        # reason.
        self._inbox = queue.Queue()
        self._turn_thread = None
        # Step 12 removed the session token totals that used to live here. They
        # were a sum that grew unbounded past /clear and never described what
        # the next call would send — Context.current_tokens does, and it is what
        # the compaction trigger reads, so the display and the behaviour now
        # agree by construction.
        self._turn_count = 0
        self._live = self._fresh_live()

    @staticmethod
    def _fresh_live():
        return {
            "active": False,
            "spinner_idx": 0,
            "start_time": None,
            "elapsed": 0.0,
            "current_action": "",
            "iteration": 0,
            "max_iterations": 0,
            "tool_call_count": 0,
            "turn_input_tokens": 0,
            "turn_output_tokens": 0,
        }

    # ---------- layout ------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Vertical(
            RichLog(id="conversation", wrap=True, markup=False, auto_scroll=True),
            Static("", id="progress", classes="idle"),
            # Input, not TextArea: Ruby pins its TextArea to height 1, so Enter
            # means submit. Textual's TextArea would make Enter insert a newline
            # and silently break the whole interaction model.
            Input(placeholder="Type a message…", id="prompt"),
            Static("", id="status"),
        )

    def on_mount(self):
        self.query_one("#conversation", RichLog).write(self._repl.banner())
        self._repl.on_output(self._enqueue_output)
        self._repl.logger.subscribe(self._enqueue_event)
        self.query_one("#prompt", Input).focus()
        self._timer = self.set_interval(TICK_SECONDS, self._tick)
        self._render_progress()
        self._render_status()

    def on_unmount(self):
        # The interval keeps firing while the app tears down, by which point the
        # widgets it queries are gone and query_one raises NoMatches. Without
        # this the app crashes on quit — intermittently, because it depends on
        # whether a tick lands inside the teardown window.
        if getattr(self, "_timer", None) is not None:
            self._timer.stop()
            self._timer = None

    # ---------- thread-safe intake ------------------------------------------

    def _enqueue_output(self, text):
        self._inbox.put(("output", text))

    def _enqueue_event(self, event):
        self._inbox.put(("event", event))

    def _tick(self):
        # Stopping the timer in on_unmount is the fix; this is the belt to its
        # braces, because a tick already in flight when unmount runs would still
        # reach the queries below.
        if not self.is_running:
            return

        try:
            self._tick_body()
        except NoMatches:
            return

    def _tick_body(self):
        self._drain()

        if self._live["active"]:
            self._live["spinner_idx"] = (self._live["spinner_idx"] + 1) % len(SPINNER_FRAMES)
            if self._live["start_time"]:
                self._live["elapsed"] = time.monotonic() - self._live["start_time"]

        self._render_progress()
        self._render_status()

    def _drain(self):
        log = self.query_one("#conversation", RichLog)
        while True:
            try:
                kind, payload = self._inbox.get_nowait()
            except queue.Empty:
                return

            if kind == "output":
                log.write(payload)
            else:
                self._handle_event(payload, log)

    def _handle_event(self, event, log):
        phase = str(event.get("phase") or "")

        if phase == "iteration":
            self._live["iteration"] = int(event.get("n") or 0)
            # The enforced ceiling comes from the task's settings, so read the
            # one the agent reported rather than the class default it may have
            # overridden.
            self._live["max_iterations"] = int(event.get("max") or 0)
            self._live["current_action"] = "Thinking…"
        elif phase == "tool_call":
            self._live["current_action"] = f"Calling tool: {event.get('name')}"
            self._live["tool_call_count"] += 1
        elif phase == "tool_result":
            self._live["current_action"] = "Awaiting result…"
        elif phase == "response":
            # Through usage.py, not usage["input_tokens"]: those are Anthropic's
            # key names, and the live ↑/↓ counters would read 0 all turn on any
            # other provider.
            counts = usage_mod.tokens(event.get("usage"))
            self._live["turn_input_tokens"] += counts["input"] or 0
            self._live["turn_output_tokens"] += counts["output"] or 0
        elif phase == "compaction":
            log.write(
                f"[context compacted — {event.get('dropped')} messages "
                "dropped to free space]"
            )
        elif phase == "turn_complete":
            self._live["active"] = False
            self._turn_count += 1
        elif phase == "turn_interrupted":
            log.write("[interrupted]")
        elif phase == "turn_error":
            self._live["active"] = False
            log.write(f"[error] {event.get('error')}")

    # ---------- rendering ---------------------------------------------------

    def _render_progress(self):
        widget = self.query_one("#progress", Static)
        context = self._repl.context

        if self._live["active"]:
            frame = SPINNER_FRAMES[self._live["spinner_idx"]]
            secs = int(self._live["elapsed"])
            max_iterations = self._live["max_iterations"] or Agent.MAX_ITERATIONS
            widget.remove_class("idle")
            self._apply_ctx_class(widget, None)
            widget.update(
                f"{frame} {self._live['current_action']}  "
                f"(iter {self._live['iteration']}/{max_iterations} · {secs}s · "
                f"↑ {_fmt_tokens(self._live['turn_input_tokens'])} · "
                f"↓ {_fmt_tokens(self._live['turn_output_tokens'])} · "
                f"{self._live['tool_call_count']} calls)"
            )
        else:
            pct = context.usage_pct()
            widget.add_class("idle")
            self._apply_ctx_class(widget, pct)
            # The idle line keeps the absolute pair; the status bar carries only
            # the percentage, which is what the colour coding is for.
            widget.update(
                f"  [ready]   ctx {_fmt_tokens(context.current_tokens)} / "
                f"{_fmt_tokens(context.context_window)} ({pct}%)   "
                f"{self._turn_count} turns"
            )

    def _render_status(self):
        ver = self._repl.version or "0.0.0"
        model = self._repl.model or "(model)"
        pct = self._repl.context.usage_pct()
        tools = self._repl.context.tool_count()
        clock = time.strftime("%H:%M:%S")

        widget = self.query_one("#status", Static)
        self._apply_ctx_class(widget, pct)
        indicator = " ⚠" if pct >= self.CTX_ALERT_PCT else ""
        widget.update(
            f" boukensha v{ver} · {model}  ·  ctx {pct}%{indicator}  ·  "
            f"{tools} tools{self._mud_route()}  ·  {clock} "
        )

    # A percentage of None means "not a context readout right now" — the busy
    # progress line — and clears both classes.
    def _apply_ctx_class(self, widget, pct):
        alert = pct is not None and pct >= self.CTX_ALERT_PCT
        warn = pct is not None and self.CTX_WARN_PCT <= pct < self.CTX_ALERT_PCT

        widget.set_class(alert, "ctx-alert")
        widget.set_class(warn, "ctx-warn")

    def _mud_route(self):
        """Which route the MUD tools arrived by.

        The banner says this in full, but it is written once into the
        conversation log and scrolls away within a screenful — after which the
        only persistent readout is a tool *count*, which cannot distinguish
        "26 tools from a daemon" from "26 tools in-process". Derived from Repl
        rather than recomputed, so there is one source of truth for which route
        is live.
        """
        status = self._repl.mud_status()
        if "over MCP" in status:
            return "  ·  mud:mcp"
        if "not configured" in status:
            return ""
        return "  ·  mud:direct"

    # ---------- input -------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted):
        text = (event.value or "").strip()
        self.query_one("#prompt", Input).value = ""
        if not text:
            return

        log = self.query_one("#conversation", RichLog)

        if text.startswith("/"):
            outcome = self._repl.handle_command(text)
            self._drain()  # surface the command's own output immediately
            if outcome == "quit":
                self.exit()
            elif outcome is None:
                log.write(f"> {text}")
                self._launch_turn(text)
            return

        log.write(f"> {text}")
        self._launch_turn(text)

    def _launch_turn(self, text):
        if self._turn_thread and self._turn_thread.is_alive():
            return

        self._live = self._fresh_live()
        self._live.update(active=True, start_time=time.monotonic(), current_action="Thinking…")

        self._turn_thread = threading.Thread(
            target=self._run_turn_thread, args=(text,), daemon=True
        )
        self._turn_thread.start()

    def _run_turn_thread(self, text):
        try:
            self._repl.run_turn(text)
        except TurnCancelled:
            self._enqueue_event({"phase": "turn_interrupted"})
        except Exception as e:  # noqa: BLE001 — the UI must survive any turn failure
            self._enqueue_event({"phase": "turn_error", "error": str(e)})
        finally:
            # Always, so the progress line clears even on an unexpected error.
            self._enqueue_event({"phase": "turn_complete"})

    # ---------- actions -----------------------------------------------------

    def action_quit_app(self):
        self.exit()

    def action_cancel_turn(self):
        """Cooperative cancellation — see errors.TurnCancelled.

        Takes effect at the agent's next iteration boundary, not mid-request.
        Ruby's Thread#raise can land inside a blocking read; Python's equivalent
        cannot, so this is a documented behavioural gap rather than a port bug.
        """
        event = getattr(self._repl, "_cancel_event", None)
        if self._turn_thread and self._turn_thread.is_alive() and event is not None:
            event.set()
            self.query_one("#progress", Static).update("⠿ cancelling at next step…")

    def action_clear_history(self):
        self._repl.handle_command("/clear")
        self._turn_count = 0
        self._session_input_tokens = 0
        self._session_output_tokens = 0
        self._drain()

    def action_scroll_back(self):
        self.query_one("#conversation", RichLog).scroll_page_up()

    def action_scroll_forward(self):
        self.query_one("#conversation", RichLog).scroll_page_down()
