module Boukensha
  # Model → capability table, folded from every backend's own MODELS constant.
  #
  # `context_window` is a known *model* fact — the physical input ceiling — not a
  # value the user sets. The agent looks it up from its configured model id; the
  # user never configures it in settings.yaml.
  #
  # Derived rather than hand-written because the lookup has to happen *before* a
  # backend is constructed (Boukensha.run sizes the Context first), which is the
  # only reason this module exists at all. A second hand-maintained copy of the
  # same numbers drifts: the static table this replaced said claude-sonnet-4-6
  # was 200k while the Anthropic backend said 1M, and gave every non-Anthropic
  # model the fallback below — the configured gemma4:e4b (128k) would have
  # compacted at a fifth of its real window.
  #
  # Reads the backend classes, so it must be required *after* them (boukensha.rb).
  module Models
    BACKENDS = [
      Backends::Anthropic,
      Backends::OpenAI,
      Backends::Gemini,
      Backends::Ollama,
      Backends::OllamaCloud
    ].freeze

    TABLE = BACKENDS.flat_map { |backend| backend::MODELS.to_a }.to_h.freeze

    # Conservative floor for a model no backend declares. Deliberately small: an
    # unrecognised id compacting early is recoverable, one assuming a window it
    # does not have is a 400 mid-turn.
    DEFAULT_CONTEXT_WINDOW = 32_000

    def self.context_window(model)
      TABLE.dig(model.to_s, :context_window) || DEFAULT_CONTEXT_WINDOW
    end

    def self.known?(model)
      TABLE.key?(model.to_s)
    end
  end
end
