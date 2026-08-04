require "json"
require "open3"

module Boukensha
  module Mcp
    # A minimal stdio MCP client.
    #
    # Hoisted from `MudManager::Mcp::Client`, which knew nothing about MUDs and
    # was only living in that gem because that is where it happened to be
    # written. The direction of the dependency was the actual defect: boukensha
    # reached into a MUD-named gem to obtain a *generic* protocol client, which
    # is what made MCP look like it needed a bespoke integration per server.
    #
    # Boukensha is an **MCP host**. That is a baseline-agent capability, and it
    # belongs here.
    #
    # The daemon keeps its own copy for its end-to-end tests. That duplication is
    # deliberate: `mud_manager` serves five language tracks, and a test-only
    # dependency on one of them would be backwards. ~180 duplicated lines is a
    # cheaper price than that dependency edge. This copy is canonical for
    # boukensha; the daemon's stays test-scoped and should not grow features.
    #
    #   client = Boukensha::Mcp::Client.spawn(
    #     command: "mud-manager", args: ["--mcp"], env: { "MUD_HOST" => "localhost" }
    #   )
    #   client.tools                      # => [ { "name" => "look", ... }, ... ]
    #   client.call_tool("look", {})      # => { text: "...", error: false }
    #   client.close
    class Client
      class TransportError < StandardError; end

      class RpcError < StandardError
        attr_reader :rpc_code

        def initialize(message, rpc_code: nil)
          super(message)
          @rpc_code = rpc_code
        end
      end

      PROTOCOL_VERSION = "2024-11-05".freeze

      attr_reader :server_info, :tools

      # Spawn and hand back a client that has completed the handshake. The
      # common case is one line at a call site.
      def self.spawn(command:, args: [], env: {})
        new(command, args, env: env).start
      end

      def initialize(command, args = [], env: {})
        @command = command
        @args = Array(args)
        @env = env.to_h.transform_keys(&:to_s).transform_values { |v| v.nil? ? nil : v.to_s }
        @next_id = 0
        @server_info = {}
        @tools = []
      end

      def start
        @stdin, @stdout, @stderr, @wait = Open3.popen3(@env, @command, *@args)

        # Anything on stderr is diagnostics, not protocol. Drain it on a thread
        # so a chatty server can never fill the pipe buffer and deadlock the
        # conversation happening on stdout.
        @stderr_thread = Thread.new do
          @stderr.each_line { |line| warn "[mcp:#{short_name}] #{line.chomp}" }
        rescue IOError
          # pipe closed during shutdown
        end

        result = request("initialize", {
          "protocolVersion" => PROTOCOL_VERSION,
          "capabilities" => {},
          "clientInfo" => { "name" => "boukensha", "version" => Boukensha::VERSION }
        })
        @server_info = result["serverInfo"] || {}

        notify("notifications/initialized")

        @tools = request("tools/list")["tools"] || []
        self
      end

      # Returns { text:, error: } rather than a bare String.
      #
      # MCP models a *failed tool call* as a successful JSON-RPC result carrying
      # `isError` — precisely so the model can read the failure and correct
      # itself. Surfacing that structurally means a caller can decide whether to
      # feed it back to the model, log it, or raise, instead of having to
      # pattern-match prose.
      def call_tool(name, arguments = {})
        result = request("tools/call", { "name" => name.to_s, "arguments" => arguments })

        text = Array(result["content"])
               .select { |c| c["type"] == "text" }
               .map { |c| c["text"] }
               .join("\n")

        { text: text, error: result["isError"] ? true : false }
      end

      def ping
        request("ping")
        true
      end

      def close
        return unless @wait

        begin
          @stdin.close unless @stdin.closed?
        rescue IOError
          # already gone
        end

        # The server exits when stdin closes. Give it a moment before insisting.
        unless @wait.join(2)
          begin
            Process.kill("TERM", @wait.pid)
          rescue Errno::ESRCH
            # exited between the join timing out and the signal
          end
        end

        @stderr_thread&.kill
        begin
          @stdout.close
        rescue StandardError
          nil
        end
        begin
          @stderr.close
        rescue StandardError
          nil
        end
        @wait = nil
      end
      alias stop close

      def running?
        !@wait.nil? && @wait.alive?
      end

      private

      def short_name
        @server_info["name"] || File.basename(@command.to_s)
      end

      def request(method, params = nil)
        id = (@next_id += 1)
        frame = { "jsonrpc" => "2.0", "id" => id, "method" => method }
        frame["params"] = params if params
        write(frame)

        response = read_until_id(id)
        if (err = response["error"])
          raise RpcError.new(err["message"].to_s, rpc_code: err["code"])
        end

        response["result"] || {}
      end

      def notify(method, params = nil)
        frame = { "jsonrpc" => "2.0", "method" => method }
        frame["params"] = params if params
        write(frame)
      end

      def write(frame)
        raise TransportError, "MCP server is not running" if @stdin.nil? || @stdin.closed?

        @stdin.puts(JSON.generate(frame))
        @stdin.flush
      rescue Errno::EPIPE
        raise TransportError, "MCP server closed the connection"
      end

      # Skip any frame that is not the reply we are waiting for — a
      # server-initiated notification may legitimately arrive mid-conversation.
      def read_until_id(id)
        loop do
          line = @stdout.gets
          raise TransportError, "MCP server exited without responding" if line.nil?

          line = line.strip
          next if line.empty?

          begin
            frame = JSON.parse(line)
          rescue JSON::ParserError
            # Not protocol. Almost always a stray `puts` in the server — report
            # it rather than hanging, since that bug is otherwise invisible.
            warn "[mcp:#{short_name}] non-JSON on stdout: #{line}"
            next
          end

          return frame if frame["id"] == id
        end
      end
    end
  end
end
