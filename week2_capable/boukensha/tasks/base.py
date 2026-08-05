from pathlib import Path


class Base:
    """Abstract, stateless task. All behaviour is class methods that accept a
    ``settings`` dict — no instances are created. Concrete subclasses define
    ``task_name``."""

    DEFAULT_MAX_ITERATIONS = 25
    DEFAULT_MAX_OUTPUT_TOKENS = 1024
    DEFAULT_MAX_TURN_TOKENS = 60_000
    DEFAULT_COMPACTION_THRESHOLD = 0.85

    @classmethod
    def task_name(cls):
        raise NotImplementedError(f"{cls.__name__} must define task_name")

    @classmethod
    def provider(cls, settings):
        return cls._fetch(settings, "provider") or _required(
            f"tasks.{cls.task_name()}.provider is required in settings.yaml"
        )

    @classmethod
    def model(cls, settings):
        return cls._fetch(settings, "model") or _required(
            f"tasks.{cls.task_name()}.model is required in settings.yaml"
        )

    @classmethod
    def prompt_override(cls, settings, prompt="system"):
        node = cls._fetch(settings, "prompt_override")
        if not isinstance(node, dict):
            return False
        return node.get(prompt) is True

    @classmethod
    def prompt(cls, settings, name="system", *, user_prompts_dir=None, default_prompts_dir=None):
        if cls.prompt_override(settings, name):
            text = cls._read_user_prompt(name, user_prompts_dir=user_prompts_dir)
            if text:
                return text
        return cls._read_default_prompt(name, default_prompts_dir=default_prompts_dir)

    @classmethod
    def system_prompt(cls, settings, *, user_prompts_dir=None, default_prompts_dir=None):
        return cls.prompt(
            settings,
            "system",
            user_prompts_dir=user_prompts_dir,
            default_prompts_dir=default_prompts_dir,
        )

    @classmethod
    def max_iterations(cls, settings):
        return cls._integer_setting(
            settings, "max_iterations", cls.DEFAULT_MAX_ITERATIONS
        )

    @classmethod
    def max_output_tokens(cls, settings):
        return cls._integer_setting(
            settings, "max_output_tokens", cls.DEFAULT_MAX_OUTPUT_TOKENS
        )

    # The second per-turn circuit breaker: cumulative input+output tokens spent
    # this turn, independent of how many iterations that took. 0 disables it.
    @classmethod
    def max_turn_tokens(cls, settings):
        return cls._integer_setting(
            settings, "max_turn_tokens", cls.DEFAULT_MAX_TURN_TOKENS
        )

    # Fraction of the model's context window at which the agent compacts before
    # its next API call. Lives beside the other limits rather than in a global
    # `agent:` block so a task's ceilings are all configured in one place — a
    # second task will want its own.
    #
    # Deliberately not _integer_setting: int("0.85") raises, and int(0.85) is 0,
    # which would disable compaction in the least visible way available.
    @classmethod
    def compaction_threshold(cls, settings):
        value = cls._fetch(settings, "compaction_threshold")
        if value is None:
            return cls.DEFAULT_COMPACTION_THRESHOLD

        return float(value)

    # ---------- private ---------------------------------------------------

    @classmethod
    def _integer_setting(cls, settings, key, default):
        value = cls._fetch(settings, key)
        if value is None:
            return default

        return int(value)

    @classmethod
    def _fetch(cls, settings, key):
        return settings.get(key) if isinstance(settings, dict) else None

    @classmethod
    def _read_user_prompt(cls, prompt_name, *, user_prompts_dir=None):
        if not user_prompts_dir:
            return None
        return cls._read_file(
            Path(user_prompts_dir) / cls.task_name() / f"{prompt_name}.md"
        )

    @classmethod
    def _read_default_prompt(cls, prompt_name, *, default_prompts_dir=None):
        if not default_prompts_dir:
            return None
        return cls._read_file(Path(default_prompts_dir) / f"{prompt_name}.md")

    @classmethod
    def _read_file(cls, path):
        path = Path(path)
        return path.read_text().strip() if path.exists() else None


def _required(message):
    raise ValueError(message)
