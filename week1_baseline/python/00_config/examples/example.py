import os
import sys
from pathlib import Path

# Make the step package importable when run as `python examples/example.py`
# (the direct analogue of Ruby's `require_relative "../lib/boukensha"`).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from boukensha import Config, Player  # noqa: E402

# Override the config directory so the example works from the repo root.
# In real usage a user's ~/.boukensha is picked up automatically.
os.environ.setdefault(
    "BOUKENSHA_DIR", str(Path(__file__).resolve().parents[4] / ".boukensha")
)

config = Config()
player_settings = config.tasks("player")

print("=== Boukensha Step 0: Configuration ===")
print()
print(f"Config dir:     {config.dir}")
print(f"Tasks:          {', '.join(config.tasks().keys())}")
print()
print("-- player task --")
print(f"Provider:       {Player.provider(player_settings)}")
print(f"Model:          {Player.model(player_settings)}")
override = Player.prompt_override(player_settings, "system")
print(f"Prompt override?{str(override).lower()}")
system_prompt = Player.system_prompt(
    player_settings,
    user_prompts_dir=config.user_prompts_dir,
    default_prompts_dir=Config.PROMPTS_DIR,
)
print(f"System prompt:  {(system_prompt or '')[:60]}...")
print()
print(f"MUD host:       {config.mud_host}:{config.mud_port}")
print(f"MUD user:       {config.mud_username}")
print()
api_key_set = os.environ.get("ANTHROPIC_API_KEY") is not None
print(f"API key set?    {str(api_key_set).lower()}")
print()
print(config)
