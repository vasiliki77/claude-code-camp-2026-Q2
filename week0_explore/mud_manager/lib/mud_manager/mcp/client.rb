require "json"
require "open3"
require_relative "errors"

module MudManager
  module Mcp
    # A minimal stdio MCP client.
    #
    # Plan §7 says the Python/Go/Rust/Java tracks point their framework's
    # existing MCP client at the daemon. Ruby's boukensha has no MCP client, so
    # this is it — and it is deliberately small, because its size is the
    # argument: ~100 lines is what "speak MCP over stdio" actually costs, and
    # every track that already has a client pays zero.
    #
    # The lifecycle guarantee from plan §3: the daemon is a *child process*, so
    # the MUD session dies with it. No ports, no orphaned connections, no
    # cleanup step to forget.
    class Client
      class TransportError < Error
        def initialize(message)
          super(message, code: "TRANSPORT_ERROR")
        end
      end

      PROTOCOL_VERSION = "2024-11-05".freeze

      attr_reader :server_info, :tools

      def initialize(command, args = [], env: {})
        @command = command
        @args = args
        @env = env.transform_keys(&:to_s).transform_values { |v| v.nil? ? nil : v.to_s }
        @next_id = 0
        @server_info = nil
        @tools = []
      end

      # Spawn the daemon and complete the MCP handshake. Returns self so the
      # common case is one line at a call site.
      def start
        @stdin, @stdout, @stderr, @wait = Open3.popen3(@env, @command, *@args)
        # Anything the daemon writes to stderr is diagnostics, not protocol.
        # Drain it on a thread so a chatty daemon can never fill the pipe buffer
        # and deadlock the conversation on stdout.
        @stderr_thread = Thread.new do
          @stderr.each_line { |line| warn "[mud-manager] #{line.chomp}" }
        rescue IOError
          # pipe closed on shutdown
        end

        result = request("initialize", {
          "protocolVersion" => PROTOCOL_VERSION,
          "capabilities" => {},
          "clientInfo" => { "name" => "boukensha", "version" => MudManager::VERSION }
        })
        @server_info = result["serverInfo"] || {}

        notify("notifications/initialized")

        @tools = request("tools/list")["tools"] || []
        self
      end

      def call_tool(name, arguments = {})
        result = request("tools/call", { "name" => name.to_s, "arguments" => arguments })
        text = Array(result["content"])
               .select { |c| c["type"] == "text" }
               .map { |c| c["text"] }
               .join

        # isError is a *successful* JSON-RPC result describing a failed tool.
        # Returned as text rather than raised: the agent loop feeds this straight
        # back to the model, which can then correct itself.
        text
      end

      def ping
        request("ping")
        true
      end

      def stop
        return unless @wait

        begin
          @stdin.close unless @stdin.closed?
        rescue IOError
          # already gone
        end
        # The daemon exits when stdin closes. Give it a moment before insisting.
        unless @wait.join(2)
          begin
            Process.kill("TERM", @wait.pid)
          rescue Errno::ESRCH
            # exited between the join timing out and the signal
          end
        end
        @stderr_thread&.kill
        @stdout.close rescue nil
        @stderr.close rescue nil
        @wait = nil
      end

      def running?
        !@wait.nil? && @wait.alive?
      end

      private

      def request(method, params = nil)
        id = (@next_id += 1)
        frame = { "jsonrpc" => "2.0", "id" => id, "method" => method }
        frame["params"] = params if params
        write(frame)

        response = read_until_id(id)
        if (err = response["error"])
          raise Error.new(err["message"].to_s, code: "RPC_ERROR", data: { "rpc_code" => err["code"] })
        end

        response["result"] || {}
      end

      def notify(method, params = nil)
        frame = { "jsonrpc" => "2.0", "method" => method }
        frame["params"] = params if params
        write(frame)
      end

      def write(frame)
        raise TransportError, "daemon is not running" unless @stdin && !@stdin.closed?

        @stdin.puts(JSON.generate(frame))
        @stdin.flush
      rescue Errno::EPIPE
        raise TransportError.new("daemon closed the connection")
      end

      # Skip any frame that is not the reply we are waiting for — a
      # server-initiated notification may legitimately arrive mid-conversation.
      def read_until_id(id)
        loop do
          line = @stdout.gets
          raise TransportError.new("daemon exited without responding") if line.nil?

          line = line.strip
          next if line.empty?

          begin
            frame = JSON.parse(line)
          rescue JSON::ParserError
            # Not protocol. Most likely a stray puts in the daemon — report it
            # rather than hanging, since that bug is otherwise invisible.
            warn "[mud-manager] non-JSON on stdout: #{line}"
            next
          end

          return frame if frame["id"] == id
        end
      end
    end
  end
end
