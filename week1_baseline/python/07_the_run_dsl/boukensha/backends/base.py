from ..errors import UnsupportedModelError


def dig(node, *keys):
    """Guarded nested lookup — the analogue of Ruby's Hash#dig / Array#dig.
    Returns None as soon as a step is missing, rather than raising, so a
    malformed provider response degrades to the empty-response path."""
    for key in keys:
        if isinstance(node, dict):
            node = node.get(key)
        elif isinstance(node, list) and isinstance(key, int) and -len(node) <= key < len(node):
            node = node[key]
        else:
            return None
    return node


class Base:
    """Shared backend contract. Subclasses define a MODELS table and the
    serialization methods; this class owns model validation and the model
    metadata (context window, pricing, usage unit)."""

    MODELS = {}

    @classmethod
    def models(cls):
        if not cls.MODELS:
            raise NotImplementedError(f"{cls.__name__} must define MODELS")
        return cls.MODELS

    @classmethod
    def model_info(cls, model):
        return cls.models().get(str(model))

    @classmethod
    def validate_model(cls, model):
        model = str(model)
        if cls.model_info(model):
            return model

        supported = ", ".join(sorted(cls.models()))
        raise UnsupportedModelError(
            f"{cls.__name__} does not support model {model!r}. "
            f"Supported models: {supported}"
        )

    @property
    def context_window(self):
        return self.info["context_window"]

    @property
    def input_token_cost_per_million(self):
        return self.info["cost_per_million"]["input"]

    @property
    def output_token_cost_per_million(self):
        return self.info["cost_per_million"]["output"]

    @property
    def usage_unit(self):
        return self.info["usage_unit"]

    @property
    def usage_level(self):
        return self.info.get("usage_level")

    def estimate_cost(self, *, input_tokens, output_tokens):
        input_cost = self.input_token_cost_per_million
        output_cost = self.output_token_cost_per_million
        # Explicitly None-checked, not truth-checked: a local Ollama model costs
        # 0.0 per million tokens, and 0.0 is falsy in Python (it is truthy in
        # Ruby). A truth check here would report "no price known" for every
        # free model.
        if input_cost is None or output_cost is None:
            return None

        return ((input_tokens * input_cost) + (output_tokens * output_cost)) / 1_000_000.0

    # ---------- private ---------------------------------------------------

    def _configure_model(self, model):
        self.model = self.validate_model(model)
        self.info = self.model_info(self.model)
