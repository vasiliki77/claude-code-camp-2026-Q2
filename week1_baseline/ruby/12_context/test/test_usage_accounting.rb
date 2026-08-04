require "minitest/autorun"
require "tmpdir"
require "json"

$LOAD_PATH.unshift File.expand_path("../lib", __dir__)

require "boukensha"

# Token accounting across providers.
#
# Every backend normalizes its *content*; none of them normalize their usage
# accounting. Reading response["usage"]["input_tokens"] — Anthropic's names —
# is why this file exists: on Gemini or Ollama both counters sit at zero, the
# turn budget never trips, the compaction trigger never fires and the context
# gauge reads 0% all session. No error, no log line, nothing to notice.
class TestUsageAccounting < Minitest::Test
  ANTHROPIC = { "usage" => { "input_tokens" => 120, "output_tokens" => 30 } }.freeze
  OPENAI_CHAT = { "usage" => { "prompt_tokens" => 120, "completion_tokens" => 30 } }.freeze
  GEMINI = { "usageMetadata" => { "promptTokenCount" => 120, "candidatesTokenCount" => 30 } }.freeze
  OLLAMA = { "prompt_eval_count" => 120, "eval_count" => 30 }.freeze

  PROVIDERS = { anthropic: ANTHROPIC, openai_chat: OPENAI_CHAT, gemini: GEMINI, ollama: OLLAMA }.freeze

  # ---------- the shim -----------------------------------------------------

  def test_every_provider_shape_yields_the_same_counts
    PROVIDERS.each do |name, response|
      tokens = Boukensha::Usage.tokens(Boukensha::Usage.envelope(response))

      assert_equal 120, tokens[:input],  "#{name} input_tokens"
      assert_equal 30,  tokens[:output], "#{name} output_tokens"
    end
  end

  def test_a_response_with_no_usage_at_all
    assert_nil Boukensha::Usage.envelope({ "content" => [] })

    tokens = Boukensha::Usage.tokens(nil)

    assert_nil tokens[:input]
    assert_nil tokens[:output]
  end

  def test_unparseable_counts_do_not_raise
    tokens = Boukensha::Usage.tokens({ "input_tokens" => "not a number" })

    assert_nil tokens[:input]
  end

  # ---------- the agent, end to end ---------------------------------------

  FakeBackend = Struct.new(:model) do
    def usage_unit = :tokens
  end

  class FakeBuilder
    attr_reader :backend

    def initialize = @backend = FakeBackend.new("fake-model")

    def parse_response(_response)
      { stop_reason: "end_turn", content: [{ "type" => "text", "text" => "done" }] }
    end
  end

  class FakeClient
    def initialize(response) = @response = response

    def call(**_opts) = @response
  end

  def run_one_turn(response)
    Dir.mktmpdir do |dir|
      context = Boukensha::Context.new(system: "s", context_window: 1000)
      context.add_message(:user, "hello")

      logger = Boukensha::Logger.new(log: File.join(dir, "session.jsonl"))
      agent  = Boukensha::Agent.new(
        context:  context,
        registry: Boukensha::Registry.new(context),
        builder:  FakeBuilder.new,
        client:   FakeClient.new(response),
        logger:   logger
      )
      agent.run
      logger.close

      events = File.readlines(logger.path).map { |line| JSON.parse(line) }
      yield context, events
    end
  end

  def test_turn_tokens_and_context_gauge_track_every_provider
    PROVIDERS.each do |name, response|
      run_one_turn(response) do |context, _events|
        assert_equal 150, context.turn_tokens,    "#{name}: turn budget saw nothing"
        assert_equal 120, context.current_tokens, "#{name}: context gauge saw nothing"
        assert_equal 12,  context.usage_pct,      "#{name}: gauge percentage"
      end
    end
  end

  def test_response_events_carry_who_answered_and_what_it_cost
    run_one_turn(ANTHROPIC) do |_context, events|
      response = events.find { |e| e["phase"] == "response" }

      assert_equal "fake_backend", response["provider"]
      assert_equal "fake-model",   response["model"]
      assert_equal 120,            response["input_tokens"]
      assert_equal 30,             response["output_tokens"]
    end
  end
end
