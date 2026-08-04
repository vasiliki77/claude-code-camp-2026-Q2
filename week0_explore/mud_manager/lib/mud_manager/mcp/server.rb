require "json"
require_relative "../version"
require_relative "errors"
require_relative "tool_spec"

module MudManager
  module Mcp
    # MCP facade — plan §3 Option C, the blessed interface.
    #
    # Same daemon as JsonLineServer, but speaking JSON-RPC 2.0 with tool
    # discovery instead of a bespoke line format. The payoff (plan §4.2) is that
    # a Python/Go/Rust/Java track writes **zero protocol code**: it points its
    # framework's existing MCP client at `mud-manager --mcp` and gets 26 typed
    # MUD tools with schemas and descriptions, served centrally so they cannot
    # drift between languages.
    #
    # Transport is stdio, deliberately (plan §3): the agent spawns this as a
    # subprocess, so session lifecycle == subprocess lifecycle. Nothing to clean
    # up, no ports to manage — which matters on WSL2.
    #
    # Note the one thing that must never happen on stdout: anything that is not
    # a JSON-RPC frame. Every diagnostic in this process goes to stderr, and
    # MudManager::Session's own `warn` calls already do.
    class Server
      PROTOCOL_VERSION = "2024-11-05".freeze
      SERVER_NAME = "mud-manager".freeze

      # JSON-RPC 2.0 reserved codes.
      PARSE_ERROR = -32700
      INVALID_REQUEST = -32600
      METHOD_NOT_FOUND = -32601
      INVALID_PARAMS = -32602
      INTERNAL_ERROR = -32603

      def initialize(dispatcher, input: $stdin, output: $stdout)
        @dispatcher = dispatcher
        @input = input
        @output = output
      end

      def run
        @input.each_line do |line|
          line = line.strip
          next if line.empty?

          response = handle_line(line)
          # Notifications get no response at all — writing one is a protocol
          # violation that some clients treat as fatal.
          write(response) if response
        end
      ensure
        @dispatcher.pool.close_all
      end

      # Exposed for tests: one line in, one response hash out (or nil for a
      # notification).
      def handle_line(line)
        message = begin
          JSON.parse(line)
        rescue JSON::ParserError => e
          return rpc_error(nil, PARSE_ERROR, "invalid JSON: #{e.message}")
        end

        return rpc_error(nil, INVALID_REQUEST, "request must be a JSON object") unless message.is_a?(Hash)

        handle(message)
      end

      private

      def handle(message)
        id = message["id"]
        method = message["method"].to_s
        params = message["params"] || {}

        # No id means a notification: act on it, answer nothing.
        return handle_notification(method) if id.nil?

        case method
        when "initialize" then rpc_result(id, initialize_result(params))
        when "ping" then rpc_result(id, {})
        when "tools/list" then rpc_result(id, { "tools" => ToolSpec.mcp_tools })
        when "tools/call" then rpc_result(id, call_tool(params))
        else
          rpc_error(id, METHOD_NOT_FOUND, "unknown method #{method.inspect}")
        end
      rescue StandardError => e
        rpc_error(message["id"], INTERNAL_ERROR, "#{e.class}: #{e.message}")
      end

      def handle_notification(method)
        # "notifications/initialized" is the handshake completing; nothing to do.
        # Unknown notifications are ignored by design — the spec requires it.
        @dispatcher.pool.close_all if method == "notifications/cancelled"
        nil
      end

      def initialize_result(params)
        # Echo the client's protocol version when we can speak it, so a newer
        # client is not forced to downgrade unnecessarily.
        requested = params["protocolVersion"].to_s
        version = requested.empty? ? PROTOCOL_VERSION : requested

        {
          "protocolVersion" => version,
          "capabilities" => { "tools" => { "listChanged" => false } },
          "serverInfo" => { "name" => SERVER_NAME, "version" => MudManager::VERSION }
        }
      end

      # A *failed tool call* is not a JSON-RPC error. MCP models it as a normal
      # result carrying isError, precisely so the model can read the failure and
      # recover — an LLM that asked for a nonexistent spell should be told so,
      # not have its transport error out. The structured code is kept in the
      # text so a client can still branch on it (open-Q #3).
      def call_tool(params)
        name = params["name"]
        args = params["arguments"] || {}

        text = @dispatcher.call(name, args)
        { "content" => [{ "type" => "text", "text" => text.to_s }], "isError" => false }
      rescue Error => e
        {
          "content" => [{ "type" => "text", "text" => "error [#{e.code}]: #{e.message}" }],
          "isError" => true
        }
      end

      def rpc_result(id, result)
        { "jsonrpc" => "2.0", "id" => id, "result" => result }
      end

      def rpc_error(id, code, message)
        { "jsonrpc" => "2.0", "id" => id, "error" => { "code" => code, "message" => message } }
      end

      def write(response)
        @output.puts(JSON.generate(response))
        @output.flush
      end
    end
  end
end
