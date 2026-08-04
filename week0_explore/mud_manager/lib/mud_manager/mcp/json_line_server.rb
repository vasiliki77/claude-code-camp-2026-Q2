require "json"
require_relative "errors"
require_relative "tool_spec"

module MudManager
  module Mcp
    # The bespoke newline-delimited JSON protocol from plan §3 Option B.
    #
    # This is the *substrate* the MCP facade sits on, and it is kept as a
    # first-class mode for two reasons the plan gives (§4.3): it is the escape
    # hatch for a track that wants to write a client by hand, and it is the
    # teaching artifact — implementing a ~40-line client against this is a
    # transferable skill in a way that wiring up an MCP library is not.
    #
    # One JSON object per line, in and out. Request:
    #
    #   {"id":1,"op":"connect"}
    #   {"id":2,"op":"tools"}
    #   {"id":3,"op":"call","name":"look","args":{}}
    #   {"id":4,"op":"send","raw":"kill goblin"}
    #   {"id":5,"op":"poll","timeout":2}
    #   {"id":6,"op":"status"}
    #   {"id":7,"op":"close"}
    #
    # Response, matching the plan's sketch exactly:
    #
    #   {"id":3,"ok":true,"text":"You see a goblin...\n<100hp 50m 30v>"}
    #   {"id":3,"ok":false,"error":{"code":"TIMEOUT","message":"..."}}
    #
    # Every request may carry a "session" key to address a named session
    # (open-Q #1); omitting it uses the default one.
    class JsonLineServer
      def initialize(dispatcher, input: $stdin, output: $stdout)
        @dispatcher = dispatcher
        @input = input
        @output = output
      end

      def run
        @input.each_line do |line|
          line = line.strip
          next if line.empty?

          write(handle_line(line))
        end
      ensure
        @dispatcher.pool.close_all
      end

      # Exposed for tests: one line in, one response hash out.
      def handle_line(line)
        request = begin
          JSON.parse(line)
        rescue JSON::ParserError => e
          return failure(nil, ProtocolError.new("invalid JSON: #{e.message}"))
        end

        unless request.is_a?(Hash)
          return failure(nil, ProtocolError.new("request must be a JSON object"))
        end

        handle(request)
      end

      private

      def handle(request)
        id = request["id"]
        op = request["op"].to_s
        session_id = request["session"] || SessionPool::DEFAULT_ID

        case op
        when ""
          failure(id, ProtocolError.new("missing 'op'"))
        when "ping"
          success(id, "text" => "pong")
        when "tools"
          success(id, "tools" => ToolSpec.mcp_tools)
        when "status"
          success(id, "text" => @dispatcher.pool.status(session_id))
        when "connect"
          # Explicit connect is unnecessary — every gameplay op connects lazily —
          # but it is exposed so a client can pay the ~1-2s login cost up front
          # rather than inside its first timed command.
          @dispatcher.pool.session(session_id)
          success(id, "text" => @dispatcher.pool.status(session_id))
        when "close"
          closed = @dispatcher.pool.close(session_id)
          success(id, "text" => closed ? "closed" : "no such session")
        when "sessions"
          success(id, "sessions" => @dispatcher.pool.ids)
        when "poll"
          text = @dispatcher.call("poll", { "timeout" => request["timeout"] }, session_id: session_id)
          success(id, "text" => text)
        when "send"
          raw = request["raw"] || request["command"]
          text = @dispatcher.call("send_raw", { "command" => raw }, session_id: session_id)
          success(id, "text" => text)
        when "call", "primitive"
          text = @dispatcher.call(request["name"], request["args"] || {}, session_id: session_id)
          success(id, "text" => text)
        else
          failure(id, ProtocolError.new("unknown op #{op.inspect}"))
        end
      rescue Error => e
        failure(request["id"], e)
      rescue StandardError => e
        failure(request["id"], Error.new("#{e.class}: #{e.message}", code: "INTERNAL"))
      end

      def success(id, payload)
        { "id" => id, "ok" => true }.merge(payload)
      end

      # Structured, not prose — open-Q #3. A client branches on error.code.
      def failure(id, error)
        { "id" => id, "ok" => false, "error" => error.to_h }
      end

      def write(response)
        @output.puts(JSON.generate(response))
        @output.flush
      end
    end
  end
end
