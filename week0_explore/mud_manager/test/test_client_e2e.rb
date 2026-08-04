require_relative "helper"

# End-to-end through a real subprocess: this is the only test that proves the
# thing the plan is actually for — an agent in another process spawns
# `mud-manager --mcp`, discovers tools, and plays. Everything else stubs out the
# process boundary that is the whole design.
class TestClientE2E < Minitest::Test
  include DaemonTest

  BIN = File.expand_path("../bin/mud-manager", __dir__)

  def with_client(responses: {})
    mud = MudManager::FakeMud.new(password: PASSWORD, responses: responses).start

    client = MudManager::Mcp::Client.new(
      RbConfig.ruby, [BIN, "--mcp"],
      env: {
        "MUD_HOST" => "127.0.0.1",
        "MUD_PORT" => mud.port.to_s,
        "MUD_NAME" => NAME,
        "MUD_PASSWORD" => PASSWORD,
        # Blank it so a settings.yaml on this machine cannot influence the test.
        "BOUKENSHA_DIR" => ""
      }
    ).start

    yield mud, client
  ensure
    client&.stop
    mud&.stop
  end

  def test_handshake_reports_the_daemon
    with_client do |_mud, client|
      assert_equal "mud-manager", client.server_info["name"]
      assert_equal MudManager::VERSION, client.server_info["version"]
    end
  end

  def test_discovers_the_full_tool_surface
    with_client do |_mud, client|
      assert_equal 26, client.tools.length
      assert_includes client.tools.map { |t| t["name"] }, "look"
    end
  end

  def test_plays_the_mud_across_the_process_boundary
    with_client(responses: { "look" => "A mossy clearing.\r\n" }) do |mud, client|
      text = client.call_tool("look", {})

      assert_match(/mossy clearing/, text)
      assert_equal ["look"], gameplay_commands(mud)
    end
  end

  def test_session_survives_between_calls
    # The point of a daemon rather than a per-command CLI (plan §2): one login,
    # many commands, state preserved in between.
    with_client do |mud, client|
      client.call_tool("move", { "direction" => "north" })
      client.call_tool("move", { "direction" => "east" })
      client.call_tool("look", {})

      assert_equal %w[north east look], gameplay_commands(mud)
      # One login dance total, not one per command — the difference between a
      # daemon and the per-invocation CLI the plan rejects in §2.
      assert_equal 1, mud.logins
    end
  end

  def test_tool_error_comes_back_as_readable_text
    with_client do |_mud, client|
      text = client.call_tool("move", { "direction" => "widdershins" })

      assert_match(/INVALID_ARGUMENTS/, text)
      assert client.running?, "a bad tool call must not kill the daemon"
    end
  end

  def test_daemon_exits_when_stdin_closes
    mud = MudManager::FakeMud.new(password: PASSWORD).start
    client = MudManager::Mcp::Client.new(
      RbConfig.ruby, [BIN, "--mcp"],
      env: { "MUD_HOST" => "127.0.0.1", "MUD_PORT" => mud.port.to_s,
             "MUD_NAME" => NAME, "MUD_PASSWORD" => PASSWORD, "BOUKENSHA_DIR" => "" }
    ).start

    client.call_tool("look", {})
    client.stop

    refute client.running?, "subprocess lifetime is the session lifetime (plan §3)"
  ensure
    mud&.stop
  end
end
