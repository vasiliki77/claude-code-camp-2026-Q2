require "minitest/autorun"
require "tmpdir"
require "json"

$LOAD_PATH.unshift File.expand_path("../lib", __dir__)

require "boukensha"

# The agent's two circuit breakers and the compaction trigger.
#
# All three only fire deep into a long or expensive turn, which is exactly
# where they are most awkward to observe. A scripted client reaches them in
# milliseconds and without an API key.
class TestAgentLimits < Minitest::Test
  FakeBackend = Struct.new(:model)

  # Answers "tool_use" until told otherwise, so the loop keeps going.
  class ScriptedBuilder
    attr_reader :backend

    def initialize(stop_reason: "tool_use")
      @backend     = FakeBackend.new("fake-model")
      @stop_reason = stop_reason
    end

    def parse_response(_response)
      if @stop_reason == "tool_use"
        { stop_reason: "tool_use",
          content: [{ "type" => "tool_use", "id" => "t1", "name" => "noop", "input" => {} }] }
      else
        { stop_reason: "end_turn", content: [{ "type" => "text", "text" => "done" }] }
      end
    end

    # The wind-down call is tools-disabled, so it must not loop forever.
    def wind_down! = @stop_reason = "end_turn"
  end

  class ScriptedClient
    attr_reader :calls

    def initialize(builder, input_tokens:, output_tokens:)
      @builder = builder
      @usage   = { "input_tokens" => input_tokens, "output_tokens" => output_tokens }
      @calls   = 0
    end

    def call(**opts)
      @calls += 1
      # tools: [] marks the wind-down call — answer it as a normal reply.
      @builder.wind_down! if opts[:tools] == []
      { "usage" => @usage, "content" => [] }
    end
  end

  def run_agent(input_tokens: 100, output_tokens: 10, context_window: 1000, **agent_opts)
    Dir.mktmpdir do |dir|
      context = Boukensha::Context.new(system: "s", context_window: context_window)
      context.add_message(:user, "go")

      registry = Boukensha::Registry.new(context)
      registry.tool("noop", description: "does nothing") { "ok" }

      builder = ScriptedBuilder.new
      client  = ScriptedClient.new(builder, input_tokens: input_tokens, output_tokens: output_tokens)
      logger  = Boukensha::Logger.new(log: File.join(dir, "session.jsonl"))

      Boukensha::Agent.new(context: context, registry: registry, builder: builder,
                           client: client, logger: logger, **agent_opts).run
      logger.close

      events = File.readlines(logger.path).map { |line| JSON.parse(line) }
      yield context, events, client
    end
  end

  def test_iteration_ceiling_stops_the_turn_and_winds_down
    run_agent(max_iterations: 3) do |_context, events, _client|
      limit = events.find { |e| e["phase"] == "limit_reached" }

      assert_equal "max_iterations", limit["kind"]
      assert_equal 3, limit["max"]
      assert_equal "max_iterations", events.last["reason"]
    end
  end

  # The ceiling step 12 adds: a turn can be cheap in tool calls and still
  # expensive in tokens, so iterations alone do not bound spend.
  def test_token_ceiling_stops_a_turn_the_iteration_ceiling_would_not
    run_agent(input_tokens: 400, output_tokens: 100,
              max_iterations: 100, max_turn_tokens: 1200) do |context, events, _client|
      limit = events.find { |e| e["phase"] == "limit_reached" }

      assert_equal "max_tokens", limit["kind"]
      assert_operator context.turn_tokens, :>=, 1200
      assert_equal "max_tokens", events.last["reason"]
    end
  end

  def test_zero_disables_a_ceiling
    run_agent(max_iterations: 2, max_turn_tokens: 0) do |_context, events, _client|
      assert_equal "max_iterations", events.find { |e| e["phase"] == "limit_reached" }["kind"]
    end
  end

  # Compaction runs before the first call of a turn, on the usage the *previous*
  # turn ended with — the only moment where dropping messages is safe.
  def test_compaction_fires_when_the_window_is_nearly_full
    Dir.mktmpdir do |dir|
      context = Boukensha::Context.new(system: "s", context_window: 1000, compaction_threshold: 0.85)
      15.times do |i|
        context.add_message(:user, "turn #{i}")
        context.add_message(:assistant, [{ "type" => "tool_use", "id" => "t#{i}", "name" => "noop", "input" => {} }])
        context.add_message(:tool_result, "ok", tool_use_id: "t#{i}")
      end
      context.update_tokens(900)   # 90% — over the threshold

      registry = Boukensha::Registry.new(context)
      registry.tool("noop", description: "does nothing") { "ok" }

      builder = ScriptedBuilder.new(stop_reason: "end_turn")
      client  = ScriptedClient.new(builder, input_tokens: 100, output_tokens: 10)
      logger  = Boukensha::Logger.new(log: File.join(dir, "session.jsonl"))

      before = context.messages.size
      Boukensha::Agent.new(context: context, registry: registry, builder: builder,
                           client: client, logger: logger).run
      logger.close

      events     = File.readlines(logger.path).map { |line| JSON.parse(line) }
      compaction = events.find { |e| e["phase"] == "compaction" }

      refute_nil compaction, "compaction never fired at 90% of the window"
      assert_equal 900,  compaction["before"]
      assert_equal 1000, compaction["context_window"]
      assert_operator compaction["dropped"], :>, 0
      assert_operator context.messages.size, :<, before
    end
  end

  def test_no_compaction_below_the_threshold
    run_agent(input_tokens: 100, context_window: 1000) do |_context, events, _client|
      assert_nil events.find { |e| e["phase"] == "compaction" }
    end
  end
end
