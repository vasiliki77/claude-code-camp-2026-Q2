import os
from types import SimpleNamespace

from . import backends, runtime
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
from .version import VERSION

# Which env var holds the key for each backend. Ollama is absent on purpose —
# a local server needs no key.
_API_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "ollama_cloud": "OLLAMA_API_KEY",
}


# Ruby's Boukensha.repl is Boukensha.run copy-pasted with a different tail: the
# ~45 lines from `cfg = config` down to the Logger are identical in both. Python
# factors them out here rather than carrying two copies that have to be kept in
# step by hand through the remaining iterations.
def _build_session(
    *, system, model, backend, api_key, ollama_host, log, max_output_tokens, tools
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

    ctx = Context(task=task_class, system=system)
    registry = Registry(ctx)

    # The caller's turn: the registry exists now, and the tools it collects have
    # to be in the context before the builder serializes them below.
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

    builder = PromptBuilder(ctx, be)
    client = Client(builder)
    effective_max_iterations = task_class.max_iterations(task_settings)
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
            "max_output_tokens": effective_max_output_tokens,
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
        max_output_tokens=effective_max_output_tokens,
        model=model,
        backend=backend,
        api_key=api_key,
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
    max_output_tokens=None,
    tools=None,
):
    """One-shot run: send a single task, get a response, return.

    See step 07's README for full documentation of the options.

    Note the defaults differ from Ruby's doc comment, which claims `system` and
    `model` come from `config.system_prompt` / `config.model`. Config exposes no
    such readers — both come from Tasks::Player.
    """
    # Assigned before the try so the finally can close it even if construction
    # fails. Ruby's `ensure` gets this for free: a local assigned anywhere in
    # the method body exists (as nil) from parse time.
    session = None

    try:
        session = _build_session(
            system=system,
            model=model,
            backend=backend,
            api_key=api_key,
            ollama_host=ollama_host,
            log=log,
            max_output_tokens=max_output_tokens,
            tools=tools,
        )
        agent = Agent(
            context=session.context,
            registry=session.registry,
            builder=session.builder,
            client=session.client,
            logger=session.logger,
            task_settings=session.task_settings,
            max_iterations=session.max_iterations,
            max_output_tokens=session.max_output_tokens,
        )

        session.context.add_message("user", task)
        return agent.run()
    finally:
        if session:
            session.logger.close()


def repl(
    *,
    system=None,
    model=None,
    backend=None,
    api_key=None,
    ollama_host="http://localhost:11434",
    log=None,
    max_output_tokens=None,
    tools=None,
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

    try:
        session = _build_session(
            system=system,
            model=model,
            backend=backend,
            api_key=api_key,
            ollama_host=ollama_host,
            log=log,
            max_output_tokens=max_output_tokens,
            tools=tools,
        )
        Repl(
            context=session.context,
            registry=session.registry,
            builder=session.builder,
            client=session.client,
            logger=session.logger,
            task_settings=session.task_settings,
            max_iterations=session.max_iterations,
            max_output_tokens=session.max_output_tokens,
            config_dir=session.cfg.dir,
            provider=session.backend,
            model=session.model,
            version=VERSION,
            api_key=session.api_key,
        ).start()
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        if session:
            session.logger.close()
