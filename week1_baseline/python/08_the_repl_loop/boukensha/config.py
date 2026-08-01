import os
from functools import reduce
from pathlib import Path

import yaml
from dotenv import load_dotenv


class Config:
    # The .boukensha config directory is resolved in this order:
    #   1. BOUKENSHA_DIR environment variable (set before loading .env)
    #   2. ~/.boukensha  (default)
    DEFAULT_DIR = Path.home() / ".boukensha"

    # Default prompts shipped alongside the library code.
    PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

    def __init__(self):
        self.dir = self._resolve_dir()
        self._load_env()
        self.settings = self._load_settings()

    # ---------- tasks -----------------------------------------------------

    # With no argument: returns the full tasks hash from settings.yaml.
    # With a name: returns that task's settings hash, e.g. tasks("player").
    def tasks(self, name=None):
        all_tasks = self.dig("tasks") or {}
        return all_tasks.get(name) if name else all_tasks

    # The user's prompts directory for task prompt overrides.
    @property
    def user_prompts_dir(self):
        return self.dir / "prompts"

    # ---------- MUD connection --------------------------------------------
    # Declared but unread: nothing in this step consults them. Present up to
    # step 05, deleted in step 06, restored here — mirroring Ruby.

    @property
    def mud_host(self):
        return self.dig("mud", "host") or "localhost"

    @property
    def mud_port(self):
        return self.dig("mud", "port") or 4000

    @property
    def mud_username(self):
        return self.dig("mud", "username")

    @property
    def mud_password(self):
        return self.dig("mud", "password")

    # ---------- low-level helpers -----------------------------------------

    # Fetch a nested key path from settings, e.g. dig("mud", "host")
    def dig(self, *keys):
        def step(node, key):
            return node.get(key) if isinstance(node, dict) else None

        return reduce(step, keys, self.settings)

    def __str__(self):
        return (
            f"#<Boukensha::Config dir={self.dir} "
            f"tasks={','.join(self.tasks().keys())}>"
        )

    __repr__ = __str__

    # ---------- private ---------------------------------------------------

    def _resolve_dir(self):
        # 1. Explicit override
        override = os.environ.get("BOUKENSHA_DIR")
        if override:
            return Path(override).expanduser().resolve()

        # 2. .boukensha in the current working directory
        cwd_dir = Path.cwd() / ".boukensha"
        if cwd_dir.is_dir():
            return cwd_dir

        # 3. ~/.boukensha default
        return Path(self.DEFAULT_DIR).expanduser().resolve()

    def _load_env(self):
        env_file = self.dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)

    def _load_settings(self):
        settings_file = self.dir / "settings.yaml"
        if not settings_file.exists():
            raise FileNotFoundError(
                f"No settings.yaml found in config dir {self.dir}. "
                "Set BOUKENSHA_DIR or create the file."
            )
        return yaml.safe_load(settings_file.read_text()) or {}
