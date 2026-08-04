module Boukensha
  # Where each provider hides its token counts.
  #
  # Every backend normalizes its *content*; none of them normalize their usage
  # accounting, and the differences are two-layered — the envelope the counts
  # live in, and the names of the counts themselves:
  #
  #   Anthropic / OpenAI  response["usage"]["input_tokens"|"output_tokens"]
  #   OpenAI (chat)       response["usage"]["prompt_tokens"|"completion_tokens"]
  #   Gemini              response["usageMetadata"]["promptTokenCount"|"candidatesTokenCount"]
  #   Ollama              response["prompt_eval_count"|"eval_count"]   (top level)
  #
  # Both readers of that data live one shim away from being Anthropic-only:
  # Agent needs the integers to drive the turn budget and the compaction
  # trigger, Logger needs them to price the call. They read the same numbers, so
  # the key lists live here once rather than in both.
  module Usage
    INPUT_KEYS  = %w[input_tokens prompt_tokens promptTokenCount prompt_eval_count].freeze
    OUTPUT_KEYS = %w[output_tokens completion_tokens candidatesTokenCount eval_count].freeze

    # The sub-hash a provider's counts live in, or nil when the response carries
    # none. Ollama has no envelope at all, so its top-level counts are lifted
    # into one.
    def self.envelope(response)
      return nil unless response.is_a?(Hash)
      return response["usage"] if response["usage"]
      return response["usageMetadata"] if response["usageMetadata"]

      lifted = (INPUT_KEYS + OUTPUT_KEYS).each_with_object({}) do |key, out|
        out[key] = response[key] if response.key?(key)
      end
      lifted.empty? ? nil : lifted
    end

    # { input: Integer|nil, output: Integer|nil } from an envelope.
    def self.tokens(envelope)
      envelope ||= {}
      {
        input: first_integer(envelope, INPUT_KEYS),
        output: first_integer(envelope, OUTPUT_KEYS)
      }
    end

    def self.first_integer(hash, keys)
      keys.each do |key|
        value = hash[key] || hash[key.to_sym]
        return Integer(value) unless value.nil?
      end
      nil
    rescue ArgumentError, TypeError
      nil
    end
    private_class_method :first_integer
  end
end
