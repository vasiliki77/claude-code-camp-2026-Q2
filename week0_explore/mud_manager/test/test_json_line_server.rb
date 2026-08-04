require "json"
require_relative "helper"

class TestJsonLineServer < Minitest::Test
  include DaemonTest

  def with_server(responses: {})
    with_daemon(responses: responses) do |mud, dispatcher|
      yield mud, MudManager::Mcp::JsonLineServer.new(dispatcher)
    end
  end

  def send_line(server, hash)
    server.handle_line(JSON.generate(hash))
  end

  def test_call_returns_the_plan_s_success_shape
    with_server(responses: { "look" => "A dusty road.\r\n" }) do |_mud, server|
      response = send_line(server, { "id" => 3, "op" => "call", "name" => "look", "args" => {} })

      assert_equal 3, response["id"]
      assert_equal true, response["ok"]
      assert_match(/dusty road/, response["text"])
    end
  end

  def test_failure_carries_a_structured_error_not_prose
    # open-Q #3: foreign clients must branch on a code, not parse a message.
    with_server do |_mud, server|
      response = send_line(server, { "id" => 4, "op" => "call", "name" => "move",
                                     "args" => { "direction" => "sideways" } })

      assert_equal 4, response["id"]
      assert_equal false, response["ok"]
      assert_equal "INVALID_ARGUMENTS", response["error"]["code"]
      assert_kind_of String, response["error"]["message"]
    end
  end

  def test_send_op_forwards_a_raw_command
    with_server do |mud, server|
      response = send_line(server, { "id" => 1, "op" => "send", "raw" => "kill goblin" })

      assert response["ok"]
      assert_equal ["kill goblin"], gameplay_commands(mud)
    end
  end

  def test_tools_op_lists_the_surface
    with_server do |_mud, server|
      response = send_line(server, { "id" => 1, "op" => "tools" })

      assert response["ok"]
      assert_equal 26, response["tools"].length
      assert(response["tools"].all? { |t| t.key?("inputSchema") })
    end
  end

  def test_status_and_explicit_connect
    with_server do |_mud, server|
      before = send_line(server, { "id" => 1, "op" => "status" })
      assert_match(/disconnected/, before["text"])

      connected = send_line(server, { "id" => 2, "op" => "connect" })
      assert connected["ok"]
      assert_match(/connected to/, connected["text"])
    end
  end

  def test_named_sessions_over_the_wire
    with_server do |_mud, server|
      send_line(server, { "id" => 1, "op" => "connect", "session" => "alice" })
      send_line(server, { "id" => 2, "op" => "connect", "session" => "bob" })

      response = send_line(server, { "id" => 3, "op" => "sessions" })
      assert_equal %w[alice bob], response["sessions"].sort
    end
  end

  def test_close_reports_whether_a_session_existed
    with_server do |_mud, server|
      send_line(server, { "id" => 1, "op" => "connect" })

      assert_equal "closed", send_line(server, { "id" => 2, "op" => "close" })["text"]
      assert_equal "no such session", send_line(server, { "id" => 3, "op" => "close" })["text"]
    end
  end

  def test_malformed_json_does_not_kill_the_server
    with_server do |_mud, server|
      response = server.handle_line("{not json")

      assert_equal false, response["ok"]
      assert_equal "PROTOCOL_ERROR", response["error"]["code"]
    end
  end

  def test_missing_and_unknown_ops
    with_server do |_mud, server|
      assert_equal "PROTOCOL_ERROR", send_line(server, { "id" => 1 })["error"]["code"]
      assert_equal "PROTOCOL_ERROR", send_line(server, { "id" => 2, "op" => "dance" })["error"]["code"]
    end
  end
end
