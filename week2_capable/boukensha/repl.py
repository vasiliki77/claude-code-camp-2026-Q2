import threading
from pathlib import Path

from . import runtime
from .agent import Agent
from .errors import ApiError, LoopError, TurnCancelled


class Repl:
    """Repl is the interactive session loop.

    It wraps the same primitives as a single boukensha.run call, but instead of
    running once it stays alive: it reads a task from the user, runs the agent,
    prints the reply, and loops back to the prompt.

    The Context is shared across every turn so conversation history accumulates
    naturally — the agent sees the full transcript each time it is called.

    Built-in commands (not sent to the agent):
      /help     print the command list
      /quiet    suppress detailed logging
      /loud     re-enable logging
      /clear    wipe conversation history (tools stay registered)
      /compact  drop the oldest messages to free context
      /exit     leave the REPL
      /quit     alias for /exit
    """

    PROMPT = "boukensha> "

    HELP = (
        "Commands:\n"
        "  /quiet    suppress logging output\n"
        "  /loud     re-enable logging output\n"
        "  /clear    wipe conversation history (tools stay)\n"
        "  /compact  drop oldest messages to free context\n"
        "  /exit     leave the REPL\n"
        "  /help     show this message\n"
    )

    def __init__(
        self,
        *,
        context,
        registry,
        builder,
        client,
        logger,
        config_dir=None,
        provider=None,
        model=None,
        version=None,
        api_key=None,
        mcp=None,
        task_settings=None,
        max_iterations=None,
        max_turn_tokens=None,
        max_output_tokens=None,
    ):
        self.context = context
        self.registry = registry
        self.builder = builder
        self.client = client
        self.logger = logger
        self.task_settings = task_settings
        self.max_iterations = max_iterations
        self.max_turn_tokens = max_turn_tokens
        self.max_output_tokens = max_output_tokens
        self.config_dir = config_dir
        self.provider = provider
        self.model = model
        self.version = version
        self.api_key = api_key
        self.mcp = mcp or []
        self.turn = 0
        # Set by on_output when something else — the TUI — wants to render this
        # session's output itself. None means "write to stdout", which is what
        # every step before this one did unconditionally.
        self._output_cb = None
        # Exposed so a driving TUI can cancel the turn currently in flight.
        self._cancel_event = None

    # ---------- composability ---------------------------------------------
    #
    # Step 11 splits the REPL into three public pieces so a TUI can drive it
    # without reimplementing any session logic: where output goes
    # (`on_output`), what a slash command does (`handle_command`), and how a
    # turn runs (`run_turn`). `start` becomes a thin terminal loop over them,
    # and the TUI substitutes its own loop.

    def on_output(self, callback):
        """Route output through `callback` instead of stdout."""
        self._output_cb = callback

    def _output(self, s):
        text = str(s)
        if self._output_cb is not None:
            self._output_cb(text)
            return

        # Ruby's `puts` does not add a newline to a string that already ends
        # with one; Python's `print` always does. Matching Ruby matters here
        # rather than being pedantry: the plain (tui=False) REPL is the only
        # deterministic gate this step has, and it is only a gate while it stays
        # byte-identical to step 10's output.
        print(text, end="" if text.endswith("\n") else "\n")

    def handle_command(self, line):
        """Dispatch a slash command.

        Returns "quit" to stop the session, "command" if it was handled, or
        None if `line` is not a command and should be treated as a task.
        """
        if line in ("/exit", "/quit"):
            self._output("Goodbye.")
            return "quit"
        if line == "/help":
            self._output(self.HELP)
            return "command"
        if line == "/quiet":
            runtime.set_quiet()
            self._output("(logging suppressed — type /loud to re-enable)")
            return "command"
        if line == "/loud":
            runtime.set_loud()
            self._output("(logging enabled)")
            return "command"
        if line == "/clear":
            self.context.clear_messages()
            self.turn = 0
            self._output("(conversation history cleared)")
            return "command"
        if line == "/compact":
            dropped = self.context.compact_messages()
            self._output(f"(compacted context — {dropped} messages dropped)")
            return "command"

        return None

    def start(self):
        self._output(self.banner())

        while True:
            # Only prompt when we own stdout. A TUI drives its own input widget
            # and a stray prompt would corrupt its frame.
            if self._output_cb is None:
                print(self.PROMPT, end="", flush=True)

            # Ruby's $stdin.gets returns nil at EOF; Python raises EOFError.
            try:
                line = input()
            except EOFError:
                break

            line = line.strip()
            if not line:
                continue

            outcome = self.handle_command(line)
            if outcome == "quit":
                break
            if outcome == "command":
                continue

            self.run_turn(line)

    # ---------- public, for the TUI ----------------------------------------

    def mud_status(self):
        """The banner's MUD line.

        Ruby has three states here: no MUD, an in-process session ("host:port
        (Reachable)"), and the daemon. Python has only two, because it has no
        in-process path at all — the MUD arrives over MCP or not at all. The two
        it does have print byte-identically to Ruby's, which keeps step 08's
        cross-language banner diff usable as a gate.

        Servers have already handshaked by the time the banner prints
        (registration completes it), so this reports what is true rather than
        probing anything.
        """
        if not self.mcp:
            return "(not configured)"

        names = []
        for client in self.mcp:
            info = client.server_info or {}
            names.append(" ".join(filter(None, [info.get("name") or "mcp", info.get("version")])))

        return f"via {', '.join(names)} ({len(self.context.tools)} tools over MCP)"

    def banner(self):
        key_status = (
            "✗ API key not set"
            if self.api_key is None or not self.api_key.strip()
            else "✓ API key set"
        )
        provider_line = (
            f"{self.provider or 'default'} ({self.model or 'default'})  {key_status}"
        )
        config_exists = bool(self.config_dir) and Path(self.config_dir).is_dir()
        config_line = (
            str(self.config_dir)
            if config_exists
            else f"{self.config_dir or '(default)'}  ✗ directory not found"
        )
        ver = self.version or "?.?.?"
        # Pads the box interior. Ruby raises ArgumentError on a negative count;
        # Python quietly yields "" and the box would be ragged. Unreachable
        # while VERSION is 5 characters.
        pad = " " * (9 - len(ver))

        # The uneven spacing on the /clear line is Ruby's; kept so the two
        # banners diff clean.
        return (
            "\n"
            "╔══════════════════════════════════════╗\n"
            f"║  BOUKENSHA MUD Assistant (v{ver}){pad}║\n"
            "╚══════════════════════════════════════╝\n"
            f"  config:    {config_line}\n"
            f"  provider:  {provider_line}\n"
            f"  mud:       {self.mud_status()}\n"
            "\n"
            "  /quiet or /loud   toggle logging\n"
            "  /clear           reset conversation history\n"
            "  /compact         free context (drop oldest messages)\n"
            "  /exit or /quit    leave the REPL\n"
            "\n"
        )

    def run_turn(self, line):
        self.turn += 1
        # Fresh per turn: a cancel from the previous turn must not carry over.
        self._cancel_event = threading.Event()
        self.logger.turn(n=self.turn)

        self.context.add_message("user", line)

        # A fresh Agent per turn, over the one shared Context — the iteration
        # counter resets while the transcript does not.
        agent = Agent(
            context=self.context,
            registry=self.registry,
            builder=self.builder,
            client=self.client,
            logger=self.logger,
            task_settings=self.task_settings,
            max_iterations=self.max_iterations,
            max_turn_tokens=self.max_turn_tokens,
            max_output_tokens=self.max_output_tokens,
            cancel_event=self._cancel_event,
        )

        try:
            result = agent.run()
        except LoopError as e:
            # Unreachable: LoopError is declared and never raised, in any step.
            # Kept because Ruby rescues it here.
            self._output(f"\n[error] {e}")
            return
        except ApiError as e:
            self._output(f"\n[error] API call failed: {e}")
            return
        except TurnCancelled:
            self._output("\n(interrupted)")
            return

        # Print the final response outside of the logger so it is always
        # visible, even when quiet mode is active.
        self._output(f"\n{result}")
