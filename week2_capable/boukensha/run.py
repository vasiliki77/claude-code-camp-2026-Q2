import os
import sys
from types import SimpleNamespace

from . import backends, models, runtime, tools as tools_lib
from .agent import Agent
from .client import Client
from .config import Config
from .context import Context
from .logger import Logger
from .prompt_builder import PromptBuilder
from .registry import Registry
from .repl import Repl
from .run_dsl import RunDSL
from .tasks import Player

try:
    from .tui import Tui
except ImportError:  # textual not installed — degrade to the plain REPL
    Tui = None
from .version import VERSION

# Which env var holds the key for each backend. Ollama is absent on purpose —
# a local server needs no key.
_API_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "ollama_cloud": "OLLAMA_API_KEY",
}

# Default prefix for the MUD server's tools, so they arrive as `tbamud__look`.
#
# Named after the *engine*, not the config key: a second entry called "mud" is
# plausible, a second tbaMUD is not. This string lives here and in settings.yaml
# only — tools/mcp.py applies whatever prefix it is handed and must never know
# the word "tbamud".
MUD_PREFIX = "tbamud"


# Ruby's step 10 also ships Tools::Mud — 480 lines driving MudManager::Session
# directly, in-process. **Python has no equivalent and is not getting one.**
# It obtains the same 26 tools by spawning `mud-manager --mcp` and asking what
# it has, which is the entire reason that daemon exists. So there is no `mud:`
# option here, only `mcp:`; a reader diffing the two languages should see the
# gap and know it is deliberate.
def _mud_env_from_config(cfg):
    """MUD_* for the daemon's environment, from settings.yaml.

    An inherited MUD_* wins over config: the child's environment is these values
    merged over the parent's, so reading os.environ first is what keeps the
    documented precedence true across the process boundary.
    """
    candidates = {
        "MUD_HOST": os.environ.get("MUD_HOST") or cfg.mud_host,
        "MUD_PORT": os.environ.get("MUD_PORT") or (str(cfg.mud_port) if cfg.mud_port else None),
        "MUD_NAME": os.environ.get("MUD_NAME") or cfg.mud_username,
        "MUD_PASSWORD": os.environ.get("MUD_PASSWORD") or cfg.mud_password,
    }
    return {k: str(v) for k, v in candidates.items() if v is not None}


def _mud_server_from_config(cfg):
    """An explicit mcp_servers["mud"] entry wins over the built-in preset — it is
    the more specific statement of intent. Its env layers over the mud: block so
    a partial entry still gets credentials."""
    entry = cfg.mcp_servers.get("mud")
    if not entry or not entry.get("command"):
        return None

    return {**entry, "env": {**_mud_env_from_config(cfg), **(entry.get("env") or {})}, "label": "mud"}


def _mcp_opts(mcp, cfg):
    """Resolve the mcp: option into tools.mcp.register keyword arguments.

    `is None` / `is False`, never truthiness. Ruby distinguishes three states —
    nil means "use config", false means "skip entirely", a Hash means "explicit"
    — and in Python None and False are *both* falsy, so `if not mcp` would
    collapse the first two. That bug is invisible in normal use: it only shows
    for someone who explicitly disables the route, which is exactly the person
    least likely to be running the test suite.
    """
    if mcp is None or mcp is False:
        return None

    defaults = _mud_server_from_config(cfg) or {
        "command": os.environ.get("MUD_MANAGER_BIN") or "mud-manager",
        "args": ["--mcp"],
        "env": _mud_env_from_config(cfg),
        "prefix": MUD_PREFIX,
        "required": True,
        "label": "mud",
    }

    return defaults if mcp is True else {**defaults, **mcp}


def _register_all_mcp(registry, mcp, cfg):
    """Register the MUD server (if mcp: asked for it) plus every other
    mcp_servers entry. Returns the live clients, which the caller must close.

    Servers are spawned eagerly, at registration: you cannot register tools you
    have not discovered, and discovery needs a running server.
    """
    entries = []

    mud_entry = _mcp_opts(mcp, cfg)
    if mud_entry:
        entries.append(mud_entry)

    for name, entry in cfg.mcp_servers.items():
        # "mud" is owned by the mcp: option, resolved above.
        if name == "mud" or not entry.get("command"):
            continue
        entries.append({**entry, "label": name})

    clients = []
    for entry in entries:
        kwargs = {k: entry.get(k) for k in ("command", "args", "env", "prefix", "label")}
        try:
            clients.append(tools_lib.mcp.register(registry, **kwargs))
        except Exception as e:
            # required=True (the default) means a failure to spawn raises: you
            # configured it, so its absence is a problem. required=False means
            # warn and carry on, right for a decorative server.
            if entry.get("required", True):
                raise
            print(
                f"[boukensha] optional MCP server {entry.get('label')!r} failed to start: "
                f"{e} — continuing without its tools"
            )

    return clients


def _exit_reason(explicit=None):
    """How the session ended, for Logger.close.

    Called from a finally block, where sys.exc_info() still reports whatever
    exception is currently propagating — that is how an unhandled crash gets
    told apart from a clean return without restructuring the control flow.
    A caller that already handled its exception passes `explicit` instead,
    because by then exc_info() has been cleared.
    """
    if explicit:
        return explicit

    exc = sys.exc_info()[0]
    if exc is None:
        return "completed"
    if issubclass(exc, KeyboardInterrupt):
        return "interrupted"

    return "error"


def _close_mcp_clients(clients):
    """One server failing to shut down must not strand the others."""
    for client in clients or []:
        try:
            client.close()
        except Exception as e:
            print(f"[boukensha] error closing MCP server: {e}")


# Ruby's Boukensha.repl is Boukensha.run copy-pasted with a different tail: the
# ~45 lines from `cfg = config` down to the Logger are identical in both. Python
# factors them out here rather than carrying two copies that have to be kept in
# step by hand through the remaining iterations.
def _build_session(
    *,
    system,
    model,
    backend,
    api_key,
    ollama_host,
    log,
    context_window,
    max_output_tokens,
    tools,
    working_dir,
    allowed_commands,
    shell_timeout,
    mcp,
):
    cfg = runtime.config()  # loads .env; populates the environment
    task_class = Player
    task_settings = cfg.tasks(task_class.task_name())

    if system is None:
        system = task_class.system_prompt(
            task_settings,
            user_prompts_dir=cfg.user_prompts_dir,
            default_prompts_dir=Config.PROMPTS_DIR,
        )
    if model is None:
        model = task_class.model(task_settings)
    if backend is None:
        # Ruby calls .to_sym here; Python has no symbols and every comparison
        # downstream is string-based, so it stays a string.
        backend = task_class.provider(task_settings)
    if api_key is None and backend in _API_KEY_ENV:
        api_key = os.environ.get(_API_KEY_ENV[backend])
    # A model fact, looked up before any backend exists — which is the whole
    # reason models.py is a module of its own rather than a backend method.
    if context_window is None:
        context_window = models.context_window(model)

    ctx = Context(
        task=task_class,
        system=system,
        working_dir=working_dir,
        context_window=context_window,
        compaction_threshold=task_class.compaction_threshold(task_settings),
    )
    registry = Registry(ctx)

    # `working_dir=False` opts out entirely; None means "not specified" and the
    # caller-facing default supplies os.getcwd(). Both are falsy, which is why
    # the check is on the truthy value rather than `is not None`.
    if working_dir:
        tools_lib.file_system.register(registry, working_dir=working_dir)
        tools_lib.shell.register(
            registry,
            working_dir=working_dir,
            timeout=shell_timeout,
            allowed_commands=allowed_commands,
        )

    mcp_clients = _register_all_mcp(registry, mcp, cfg)

    # Everything from here can raise — an unknown backend most obviously — and
    # the servers are already spawned. Without this the caller never receives
    # the session, so its finally: has nothing to close and the subprocesses
    # leak. Ruby has the same exposure and the same fix would apply there.
    try:
        # The caller's turn: the registry exists now, and the tools it collects
        # have to be in the context before the builder serializes them below.
        if tools:
            tools(RunDSL(registry))

        if backend == "anthropic":
            be = backends.Anthropic(api_key=api_key, model=model)
        elif backend == "openai":
            be = backends.OpenAI(api_key=api_key, model=model)
        elif backend == "gemini":
            be = backends.Gemini(api_key=api_key, model=model)
        elif backend == "ollama":
            be = backends.Ollama(host=ollama_host, model=model)
        elif backend == "ollama_cloud":
            be = backends.OllamaCloud(api_key=api_key, model=model)
        else:
            raise ValueError(
                f"Unknown backend {backend!r}. Use anthropic, openai, gemini, "
                "ollama, or ollama_cloud."
            )
    except BaseException:
        _close_mcp_clients(mcp_clients)
        raise

    builder = PromptBuilder(ctx, be)
    client = Client(builder)
    effective_max_iterations = task_class.max_iterations(task_settings)
    effective_max_turn_tokens = task_class.max_turn_tokens(task_settings)
    # `or`, not `is None` — matching Ruby's `||`, which is a truthiness test, so
    # an explicit 0 falls through to the task default. This is the reverse of
    # the guard in Agent._call_opts, deliberately: diverging here would make the
    # two languages disagree.
    effective_max_output_tokens = max_output_tokens or task_class.max_output_tokens(
        task_settings
    )
    logger = Logger(
        log=log,
        snapshot={
            "task": task_class.task_name(),
            "max_iterations": effective_max_iterations,
            "max_turn_tokens": effective_max_turn_tokens,
            "max_output_tokens": effective_max_output_tokens,
            "context_window": context_window,
            "model": model,
            "provider": backend,
        },
    )

    return SimpleNamespace(
        cfg=cfg,
        context=ctx,
        registry=registry,
        builder=builder,
        client=client,
        logger=logger,
        task_settings=task_settings,
        max_iterations=effective_max_iterations,
        max_turn_tokens=effective_max_turn_tokens,
        max_output_tokens=effective_max_output_tokens,
        model=model,
        backend=backend,
        api_key=api_key,
        mcp_clients=mcp_clients,
    )


def run(
    *,
    task,
    system=None,
    model=None,
    backend=None,
    api_key=None,
    ollama_host="http://localhost:11434",
    log=None,
    context_window=None,
    max_output_tokens=None,
    tools=None,
    working_dir=None,
    allowed_commands=None,
    shell_timeout=30,
    mcp=None,
    on_event=None,
    max_iterations=None,
):
    """One-shot run: send a single task, get a response, return.

    See step 07's README for the options carried over from earlier steps. New
    here:

    working_dir:      roots all file and shell tools at this directory,
                      registering tools.file_system and tools.shell
                      automatically. Defaults to the current directory.
                      Pass working_dir=False to opt out entirely.
    allowed_commands: list of executable names run_command may invoke.
                      None permits everything; [] permits nothing.
    shell_timeout:    seconds before a command is killed (default 30).
    mcp:              MCP servers to register. True means the MUD daemon with
                      settings from config; a dict overrides parts of that;
                      None or False registers nothing. Any mcp_servers entry in
                      settings.yaml other than "mud" is registered regardless.
    on_event:         called with every log event as it is written, for
                      progress output. Without it a run prints nothing until it
                      finishes. Same hook the TUI subscribes to.
    max_iterations:   overrides tasks.<name>.max_iterations for this run only.
                      The ceiling is what bounds cost, and a caller that wants
                      a short run should not have to edit settings.yaml and
                      remember to put it back.

    There is deliberately no `mud:` option. Ruby registers 480 lines of MUD
    tools in-process; Python gets the same 26 over MCP from `mud-manager`.
    """
    # Assigned before the try so the finally can close it even if construction
    # fails. Ruby's `ensure` gets this for free: a local assigned anywhere in
    # the method body exists (as nil) from parse time.
    session = None
    if working_dir is None:
        working_dir = os.getcwd()

    try:
        session = _build_session(
            system=system,
            model=model,
            backend=backend,
            api_key=api_key,
            ollama_host=ollama_host,
            log=log,
            context_window=context_window,
            max_output_tokens=max_output_tokens,
            tools=tools,
            working_dir=working_dir,
            allowed_commands=allowed_commands,
            shell_timeout=shell_timeout,
            mcp=mcp,
        )
        # Subscribed before the agent starts, so the caller sees every event.
        # run() is otherwise silent for its whole duration — the agent loop
        # prints nothing — which on a long run is indistinguishable from a
        # hang. Repl has the TUI for this; run() had nothing.
        if on_event:
            session.logger.subscribe(on_event)

        agent = Agent(
            context=session.context,
            registry=session.registry,
            builder=session.builder,
            client=session.client,
            logger=session.logger,
            task_settings=session.task_settings,
            # `is None`, not `or`: 0 is a meaningful value here — it disables
            # the ceiling — and would be swallowed by truthiness.
            max_iterations=(
                session.max_iterations if max_iterations is None else max_iterations
            ),
            max_turn_tokens=session.max_turn_tokens,
            max_output_tokens=session.max_output_tokens,
        )

        session.context.add_message("user", task)
        return agent.run()
    finally:
        if session:
            session.logger.close(reason=_exit_reason())
            # MCP servers are our child processes; leaving one running would
            # leak both a process and whatever connection it holds. Subprocess
            # lifetime is session lifetime, which is only true if somebody
            # actually ends it.
            _close_mcp_clients(session.mcp_clients)


def repl(
    *,
    system=None,
    model=None,
    backend=None,
    api_key=None,
    ollama_host="http://localhost:11434",
    log=None,
    context_window=None,
    max_output_tokens=None,
    tools=None,
    working_dir=None,
    allowed_commands=None,
    shell_timeout=30,
    mcp=None,
    tui=True,
):
    """Interactive REPL: register tools once, then loop — reading tasks from
    stdin, running the agent, and printing replies — until the user types exit
    or sends EOF.

    Conversation history accumulates across every turn so the agent always sees
    the full transcript.

    Options are the same as run(), minus `task` (the user supplies tasks
    interactively). system/model/backend/api_key all default to config values.
    """
    session = None
    reason = None
    if working_dir is None:
        working_dir = os.getcwd()

    try:
        session = _build_session(
            system=system,
            model=model,
            backend=backend,
            api_key=api_key,
            ollama_host=ollama_host,
            log=log,
            context_window=context_window,
            max_output_tokens=max_output_tokens,
            tools=tools,
            working_dir=working_dir,
            allowed_commands=allowed_commands,
            shell_timeout=shell_timeout,
            mcp=mcp,
        )
        repl_instance = Repl(
            context=session.context,
            registry=session.registry,
            builder=session.builder,
            client=session.client,
            logger=session.logger,
            task_settings=session.task_settings,
            max_iterations=session.max_iterations,
            max_turn_tokens=session.max_turn_tokens,
            max_output_tokens=session.max_output_tokens,
            config_dir=session.cfg.dir,
            provider=session.backend,
            model=session.model,
            version=VERSION,
            api_key=session.api_key,
            mcp=session.mcp_clients,
        )

        # Textual's entry point is run(), not start(). Tui deliberately has no
        # start method, so there is exactly one way to launch it rather than
        # carrying Ruby's name where it no longer fits the library.
        if tui and Tui is not None:
            Tui(repl_instance).run()
        else:
            repl_instance.start()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        # Recorded explicitly: this except swallows the interrupt, so by the
        # time the finally runs sys.exc_info() is already clear and the session
        # would otherwise be filed as a clean exit.
        reason = "interrupted"
    finally:
        if session:
            session.logger.close(reason=_exit_reason(reason))
            _close_mcp_clients(session.mcp_clients)
