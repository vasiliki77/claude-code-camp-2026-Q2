import os

from . import backends, runtime
from .agent import Agent
from .client import Client
from .config import Config
from .context import Context
from .logger import Logger
from .prompt_builder import PromptBuilder
from .registry import Registry
from .run_dsl import RunDSL
from .tasks import Player

# Which env var holds the key for each backend. Ollama is absent on purpose —
# a local server needs no key.
_API_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "ollama_cloud": "OLLAMA_API_KEY",
}


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
    """The top-level entry point. Wires together every primitive so the caller
    only has to describe *what* to do, not *how* to plumb it.

        def define_tools(dsl):
            @dsl.tool("read_file",
                      description="Read a file from disk",
                      parameters={"path": {"type": "string", "description": "File path"}})
            def read_file(path):
                return Path(path).read_text()

        result = boukensha.run(task="Summarise boukensha/run.py", tools=define_tools)

    Options:
      task:              (required) The user message to hand the agent.
      system:            System prompt. Defaults to the player task's prompt.
      model:             Model name. Defaults to the player task's model.
      backend:           "anthropic", "openai", "gemini", "ollama", or
                         "ollama_cloud". Defaults to the player task's provider.
      api_key:           Defaults to the matching env var (loaded from
                         .boukensha/.env). Not needed for "ollama".
      ollama_host:       Ollama base URL.
      log:               Optional JSONL path override. Defaults to
                         .boukensha/sessions/<session-id>.jsonl.
      max_output_tokens: Per-reply output cap. Defaults to the task setting.
      tools:             Optional callable receiving a RunDSL, for registering
                         tools. Ruby takes an instance_eval'd block here.

    Note the defaults differ from Ruby's doc comment, which claims `system` and
    `model` come from `config.system_prompt` / `config.model`. Config exposes no
    such readers — both come from Tasks::Player, as the code below does.
    """
    # Assigned before the try so the finally can close it even if construction
    # fails. Ruby's `ensure` gets this for free: a local assigned anywhere in
    # the method body exists (as nil) from parse time.
    logger = None

    try:
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
            # Ruby calls .to_sym here; Python has no symbols and every
            # comparison downstream is string-based, so it stays a string.
            backend = task_class.provider(task_settings)
        if api_key is None and backend in _API_KEY_ENV:
            api_key = os.environ.get(_API_KEY_ENV[backend])

        ctx = Context(task=task_class, system=system)
        registry = Registry(ctx)

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

        builder = PromptBuilder(ctx, be)
        client = Client(builder)
        effective_max_iterations = task_class.max_iterations(task_settings)
        # `or`, not `is None` — matching Ruby's `||`, which is a truthiness test,
        # so an explicit 0 falls through to the task default. This is the reverse
        # of the guard in Agent._call_opts, deliberately: diverging here would
        # make the two languages disagree.
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
        agent = Agent(
            context=ctx,
            registry=registry,
            builder=builder,
            client=client,
            logger=logger,
            task_settings=task_settings,
            max_iterations=effective_max_iterations,
            max_output_tokens=effective_max_output_tokens,
        )

        ctx.add_message("user", task)
        return agent.run()
    finally:
        if logger:
            logger.close()
