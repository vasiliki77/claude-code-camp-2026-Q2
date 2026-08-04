require "json"
require_relative "helper"

class TestMcpServer < Minitest::Test
  include DaemonTest

  def with_server(responses: {})
    with_daemon(responses: responses) do |mud, dispatcher|
      yield mud, MudManager::Mcp::Server.new(dispatcher)
    end
  end

  def rpc(server, hash)
    server.handle_line(JSON.generate(hash))
  end

  def test_initialize_handshake
    with_server do |_mud, server|
      response = rpc(server, {
        "jsonrpc" => "2.0", "id" => 1, "method" => "initialize",
        "params" => { "protocolVersion" => "2024-11-05", "capabilities" => {} }
      })

      assert_equal "2.0", response["jsonrpc"]
      assert_equal 1, response["id"]
      assert_equal "mud-manager", response["result"]["serverInfo"]["name"]
      assert_equal MudManager::VERSION, response["result"]["serverInfo"]["version"]
      assert response["result"]["capabilities"]["tools"]
    end
  end

  def test_notifications_get_no_response
    with_server do |_mud, server|
      # A JSON-RPC notification has no id. Answering one is a protocol
      # violation that some clients treat as fatal.
      assert_nil rpc(server, { "jsonrpc" => "2.0", "method" => "notifications/initialized" })
    end
  end

  def test_tools_list
    with_server do |_mud, server|
      response = rpc(server, { "jsonrpc" => "2.0", "id" => 2, "method" => "tools/list" })
      tools = response["result"]["tools"]

      assert_equal 26, tools.length
      assert_includes tools.map { |t| t["name"] }, "cast_spell"
      # Schemas are served centrally — this is the anti-drift property from §4.
      assert_equal "object", tools.first["inputSchema"]["type"]
    end
  end

  def test_tools_call_returns_text_content
    with_server(responses: { "north" => "You walk north.\r\n" }) do |mud, server|
      response = rpc(server, {
        "jsonrpc" => "2.0", "id" => 3, "method" => "tools/call",
        "params" => { "name" => "move", "arguments" => { "direction" => "north" } }
      })
      result = response["result"]

      assert_equal false, result["isError"]
      assert_equal "text", result["content"].first["type"]
      assert_match(/You walk north/, result["content"].first["text"])
      assert_equal ["north"], gameplay_commands(mud)
    end
  end

  def test_a_failed_tool_call_is_a_result_not_a_transport_error
    # MCP models tool failure as a normal result with isError, precisely so the
    # model can read the failure and correct itself. Raising a JSON-RPC error
    # would deny it that chance.
    with_server do |_mud, server|
      response = rpc(server, {
        "jsonrpc" => "2.0", "id" => 4, "method" => "tools/call",
        "params" => { "name" => "move", "arguments" => { "direction" => "widdershins" } }
      })

      assert_nil response["error"], "a bad argument must not fail the transport"
      assert_equal true, response["result"]["isError"]
      # The structured code survives into the text so a client can still branch.
      assert_match(/INVALID_ARGUMENTS/, response["result"]["content"].first["text"])
    end
  end

  def test_unknown_method_is_a_json_rpc_error
    with_server do |_mud, server|
      response = rpc(server, { "jsonrpc" => "2.0", "id" => 5, "method" => "tools/invent" })

      assert_equal(-32601, response["error"]["code"])
    end
  end

  def test_malformed_json_is_a_parse_error
    with_server do |_mud, server|
      response = server.handle_line("{{{")

      assert_equal(-32700, response["error"]["code"])
    end
  end
end
