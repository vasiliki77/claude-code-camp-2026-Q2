require_relative "helper"

class TestDispatcher < Minitest::Test
  include DaemonTest

  def test_lazy_connect_happens_on_the_first_gameplay_call
    with_daemon do |_mud, dispatcher|
      # Plan §5: nobody calls connect. The pool is cold until a tool runs.
      refute dispatcher.pool.open?, "session must not be opened eagerly"

      dispatcher.call("look", {})

      assert dispatcher.pool.open?, "first gameplay call must connect and log in"
    end
  end

  def test_status_does_not_trigger_a_connection
    with_daemon do |_mud, dispatcher|
      text = dispatcher.call("mud_status", {})

      assert_match(/disconnected/, text)
      refute dispatcher.pool.open?, "a status check must never dial the MUD"
    end
  end

  def test_builds_the_right_raw_command_through_primitives
    with_daemon do |mud, dispatcher|
      dispatcher.call("move", { "direction" => "north" })
      dispatcher.call("attack", { "target" => "goblin" })
      dispatcher.call("attack", { "target" => "orc", "style" => "murder" })
      dispatcher.call("cast_spell", { "spell" => "magic missile", "target" => "orc" })
      dispatcher.call("get_item", { "item" => "sword", "container" => "bag", "count" => 2 })

      assert_equal [
        "north",
        "kill goblin",
        "murder orc",
        "cast 'magic missile' orc",
        "get 2 sword bag"
      ], gameplay_commands(mud)
    end
  end

  def test_look_with_no_arguments_sends_a_bare_look
    with_daemon do |mud, dispatcher|
      dispatcher.call("look", {})

      assert_equal ["look"], gameplay_commands(mud)
    end
  end

  def test_empty_strings_are_treated_as_absent
    # The model reaches for "" constantly when it means "no value". Primitives
    # normalizes this for look only; the daemon has to do it everywhere.
    with_daemon do |mud, dispatcher|
      dispatcher.call("look", { "target" => "", "preposition" => "" })

      assert_equal ["look"], gameplay_commands(mud)
    end
  end

  def test_returns_the_mud_response_text
    with_daemon(responses: { "look" => "You are in a dark room.\r\n" }) do |_mud, dispatcher|
      text = dispatcher.call("look", {})

      assert_match(/dark room/, text)
    end
  end

  def test_unknown_tool_is_a_structured_error
    with_daemon do |_mud, dispatcher|
      err = assert_raises(MudManager::Mcp::UnknownToolError) do
        dispatcher.call("teleport", {})
      end

      assert_equal "UNKNOWN_TOOL", err.code
      assert_equal({ "code" => "UNKNOWN_TOOL",
                     "message" => "No tool named \"teleport\"",
                     "data" => { "tool" => "teleport" } }, err.to_h)
    end
  end

  def test_missing_required_argument_is_rejected_before_connecting
    with_daemon do |_mud, dispatcher|
      err = assert_raises(MudManager::Mcp::ValidationError) do
        dispatcher.call("examine", {})
      end

      assert_equal "INVALID_ARGUMENTS", err.code
      refute dispatcher.pool.open?, "a bad call must not open a session"
    end
  end

  def test_bad_enum_value_reports_the_allowed_set
    with_daemon do |_mud, dispatcher|
      err = assert_raises(MudManager::Mcp::ValidationError) do
        dispatcher.call("move", { "direction" => "widdershins" })
      end

      # Primitives' own message lists the allowed values, which is exactly what
      # a confused caller needs — so the daemon forwards it rather than
      # replacing it with something vaguer.
      assert_match(/expected one of/, err.message)
      assert_match(/north/, err.message)
    end
  end

  def test_unknown_argument_is_rejected
    with_daemon do |_mud, dispatcher|
      err = assert_raises(MudManager::Mcp::ValidationError) do
        dispatcher.call("move", { "direction" => "north", "speed" => "fast" })
      end

      assert_match(/unknown argument/, err.message)
    end
  end

  def test_non_integer_count_is_rejected
    with_daemon do |_mud, dispatcher|
      assert_raises(MudManager::Mcp::ValidationError) do
        dispatcher.call("get_item", { "item" => "sword", "count" => "several" })
      end
    end
  end

  def test_send_raw_bypasses_primitives
    with_daemon do |mud, dispatcher|
      dispatcher.call("send_raw", { "command" => "wiggle ears frantically" })

      assert_equal ["wiggle ears frantically"], gameplay_commands(mud)
    end
  end

  def test_poll_returns_empty_when_nothing_happened_and_does_not_connect
    with_daemon do |_mud, dispatcher|
      assert_equal "", dispatcher.call("poll", {})
      refute dispatcher.pool.open?, "polling an unopened session is not a reason to connect"
    end
  end

  def test_poll_collects_async_chatter
    with_daemon do |mud, dispatcher|
      dispatcher.call("look", {}) # connect
      mud.broadcast("A goblin hits you hard!\r\n")

      text = dispatcher.call("poll", { "timeout" => 2 })

      assert_match(/goblin hits you/, text)
    end
  end

  def test_multiple_named_sessions_are_independent
    # open-Q #1: "We should be able to handle multiple sessions."
    with_daemon do |_mud, dispatcher|
      dispatcher.call("look", {}, session_id: "alice")
      dispatcher.call("look", {}, session_id: "bob")

      assert_equal %w[alice bob], dispatcher.pool.ids.sort
      assert dispatcher.pool.open?("alice")
      assert dispatcher.pool.open?("bob")
      refute dispatcher.pool.open?, "the default session was never used"
    end
  end

  def test_missing_credentials_is_a_structured_error
    mud = MudManager::FakeMud.new(password: PASSWORD).start
    config = MudManager::Mcp::Config.new(
      host: "127.0.0.1", port: mud.port, name: nil, password: nil, settings: {}
    )
    dispatcher = MudManager::Mcp.dispatcher(config)

    err = assert_raises(MudManager::Mcp::Error) { dispatcher.call("look", {}) }
    assert_equal "MISSING_CREDENTIALS", err.code
    assert_match(/MUD_NAME/, err.message)
  ensure
    mud&.stop
  end

  def test_wrong_password_surfaces_as_login_failed
    mud = MudManager::FakeMud.new(password: "correct").start
    config = MudManager::Mcp::Config.new(
      host: "127.0.0.1", port: mud.port, name: NAME, password: "wrong",
      timeout: 3.0, settings: {}
    )
    dispatcher = MudManager::Mcp.dispatcher(config)

    err = assert_raises(MudManager::Mcp::Error) { dispatcher.call("look", {}) }
    assert_equal "LOGIN_FAILED", err.code
  ensure
    mud&.stop
  end
end
