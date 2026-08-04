require "minitest/autorun"
require "tmpdir"

$LOAD_PATH.unshift File.expand_path("../lib", __dir__)

require "boukensha"

# The REPL's built-in commands.
#
# These never reach the model, so they are the cheapest honest gate in the
# project: no API key, no MUD, no network, and a real regression (a command
# that stops being recognised and gets sent to the agent as a prompt instead)
# shows up immediately. The TUI drives the same three methods, so testing the
# plain REPL covers both front-ends.
class TestReplCommands < Minitest::Test
  def setup
    @dir     = Dir.mktmpdir
    @context = Boukensha::Context.new(system: "s", context_window: 1000)
    @logger  = Boukensha::Logger.new(log: File.join(@dir, "session.jsonl"))
    @repl    = Boukensha::Repl.new(
      context:  @context,
      registry: Boukensha::Registry.new(@context),
      builder:  nil,
      client:   nil,
      logger:   @logger,
      model:    "fake-model",
      version:  Boukensha::VERSION
    )
    @output = []
    @repl.on_output { |line| @output << line.to_s }
  end

  def teardown
    @logger.close
    FileUtils.remove_entry(@dir)
  end

  def fill_history(pairs)
    pairs.times do |i|
      @context.add_message(:user, "turn #{i}")
      @context.add_message(:assistant, [{ "type" => "tool_use", "id" => "t#{i}", "name" => "look", "input" => {} }])
      @context.add_message(:tool_result, "result #{i}", tool_use_id: "t#{i}")
    end
  end

  def test_unknown_input_is_not_a_command
    assert_nil @repl.handle_command("look at the fountain")
    assert_nil @repl.handle_command("/nonsense")
  end

  def test_exit_and_quit
    assert_equal :quit, @repl.handle_command("/exit")
    assert_equal :quit, @repl.handle_command("/quit")
  end

  def test_help_lists_every_command_it_handles
    assert_equal :command, @repl.handle_command("/help")

    help = @output.join("\n")
    %w[/clear /compact /exit /help].each do |command|
      assert_includes help, command
    end
  end

  def test_clear_wipes_history_and_the_gauge_but_keeps_tools
    fill_history(3)
    @context.register_tool(Boukensha::Tool.new("look", "look around", {}, proc {}))
    @context.update_tokens(700)

    assert_equal :command, @repl.handle_command("/clear")

    assert_empty @context.messages
    assert_equal 0, @context.current_tokens
    assert_equal 1, @context.tool_count
  end

  def test_compact_drops_messages_and_reports_how_many
    fill_history(10)
    before = @context.messages.size

    assert_equal :command, @repl.handle_command("/compact")

    dropped = before - @context.messages.size

    assert_operator dropped, :>, 0
    assert_includes @output.join("\n"), "#{dropped} messages dropped"
  end

  def test_compact_on_a_short_history_is_a_no_op_not_an_error
    @context.add_message(:user, "hello")

    assert_equal :command, @repl.handle_command("/compact")
    assert_equal 1, @context.messages.size
    assert_includes @output.join("\n"), "0 messages dropped"
  end

  def test_banner_reports_the_mud_route
    assert_includes @repl.banner, "mud:"
    assert_includes @repl.banner, "(not configured)"
  end
end
