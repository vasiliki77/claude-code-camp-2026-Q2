import os
import sys
from pathlib import Path

# Make the step package importable when run as `python examples/example.py`
# (the direct analogue of Ruby's `require_relative "../lib/boukensha"`).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from boukensha import (  # noqa: E402
    Agent,
    Client,
    Config,
    Context,
    Player,
    PromptBuilder,
    Registry,
    backends,
)

config = Config()
player_settings = config.tasks("player")
system_prompt = Player.system_prompt(
    player_settings,
    user_prompts_dir=config.user_prompts_dir,
    default_prompts_dir=Config.PROMPTS_DIR,
)
# Tools resolve paths against the step folder, not the process CWD, so the
# agent explores this step's own files wherever it is launched from.
base_dir = Path(__file__).resolve().parents[1]

ctx = Context(task=Player, system=system_prompt)
registry = Registry(ctx)

provider = Player.provider(player_settings)
model = Player.model(player_settings)

# The task settings pick the provider; the provider picks the backend. Every
# backend serializes the same Context into a different shape.
if provider == "anthropic":
    backend = backends.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], model=model)
elif provider == "openai":
    backend = backends.OpenAI(api_key=os.environ["OPENAI_API_KEY"], model=model)
elif provider == "gemini":
    backend = backends.Gemini(api_key=os.environ["GEMINI_API_KEY"], model=model)
elif provider == "ollama":
    backend = backends.Ollama(model=model)
elif provider == "ollama_cloud":
    backend = backends.OllamaCloud(api_key=os.environ["OLLAMA_API_KEY"], model=model)
else:
    raise ValueError(f"Unsupported provider for player task: {provider}")

builder = PromptBuilder(ctx, backend)
client = Client(builder)
agent = Agent(
    context=ctx,
    registry=registry,
    builder=builder,
    client=client,
    task_settings=player_settings,
)


@registry.tool(
    "read_file",
    description="Read the contents of a file from disk",
    parameters={"path": {"type": "string", "description": "The file path to read"}},
)
def read_file(path):
    return (base_dir / path).read_text()


@registry.tool(
    "list_directory",
    description="List the files in a directory",
    parameters={"path": {"type": "string", "description": "The directory path to list"}},
)
def list_directory(path):
    return ", ".join(
        f for f in os.listdir(base_dir / path) if not f.startswith(".")
    )


ctx.add_message(
    "user",
    "Read the README.md file and summarise what this MUD player assistant framework can do.",
)

print("=== BOUKENSHA Step 5: Agent Loop ===")
print()
print(f"Config: {config}")
print(f"Provider: {provider}")
print(f"Model: {model}")
print(f"Max iterations: {Player.max_iterations(player_settings)}")
print(f"Max output tokens: {Player.max_output_tokens(player_settings)}")
print()

result = agent.run()

print()
print("=== FINAL RESPONSE ===")
print(result)
