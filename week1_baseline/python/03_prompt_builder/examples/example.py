import json
import os
import sys
from pathlib import Path

# Make the step package importable when run as `python examples/example.py`
# (the direct analogue of Ruby's `require_relative "../lib/boukensha"`).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from boukensha import Config, Context, Player, PromptBuilder, Registry, backends  # noqa: E402

config = Config()
player_settings = config.tasks("player")
system_prompt = Player.system_prompt(
    player_settings,
    user_prompts_dir=config.user_prompts_dir,
    default_prompts_dir=Config.PROMPTS_DIR,
)

ctx = Context(task=Player, system=system_prompt)
registry = Registry(ctx)


@registry.tool(
    "look",
    description="Look around the current room for details",
    parameters={},
)
def look():
    return "A damp stone corridor stretches north. Torches flicker on the walls."


@registry.tool(
    "move",
    description="Move the player in a direction (north, south, east, west, up, down)",
    parameters={"direction": {"type": "string", "description": "The direction to move"}},
)
def move(direction):
    return f"You move {direction} into a torch-lit corridor."


ctx.add_message(
    "user", "I just arrived in the dungeon. What's around me, and can you move north?"
)
ctx.add_message("assistant", "Let me take a look around first.")
ctx.add_message(
    "tool_result",
    "A damp stone corridor stretches north. Torches flicker on the walls.",
    tool_use_id="toolu_01X",
)

print("=== BOUKENSHA Step 3: Prompt Builder ===")
provider = Player.provider(player_settings)
model = Player.model(player_settings)

# The task settings pick the provider; the provider picks the backend. Every
# backend serializes the same Context into a different shape, which is the
# whole point of this step.
if provider == "anthropic":
    backend = backends.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], model=model)
elif provider == "ollama":
    backend = backends.Ollama(model=model)
elif provider == "ollama_cloud":
    backend = backends.OllamaCloud(api_key=os.environ["OLLAMA_API_KEY"], model=model)
elif provider == "openai":
    backend = backends.OpenAI(api_key=os.environ["OPENAI_API_KEY"], model=model)
elif provider == "gemini":
    backend = backends.Gemini(api_key=os.environ["GEMINI_API_KEY"], model=model)
else:
    raise ValueError(f"Unsupported provider for player task: {provider}")

builder = PromptBuilder(ctx, backend)

print()
print(f"Config: {config}")
print(f"Provider: {provider}")
print(f"Model: {model}")
print(json.dumps(builder.to_api_payload(), indent=2, ensure_ascii=False))
