require_relative "../session"
require_relative "errors"

module MudManager
  module Mcp
    # Owns every live MudManager::Session in this process.
    #
    # This is the class the whole plan exists to make possible: the stateful,
    # concurrency-heavy, telnet-aware half of the gem lives here **once**, and
    # no other language ever reimplements it (plan §1).
    #
    # Two behaviours make the stateful session look stateless from above,
    # which is what makes the MCP mapping clean (plan §5):
    #
    #   * **Lazy connect.** Nobody calls `connect` or `login`. The first
    #     gameplay call on a session id opens the socket and runs the login
    #     dance, using credentials from Config — never from tool arguments.
    #   * **Transparent reconnect.** If the socket dropped, the next call
    #     silently re-opens and re-logs in. The gem already models the
    #     `Reconnecting` vs fresh-login distinction, so this costs nothing.
    #
    # Multi-session is open-Q #1's answer ("we should be able to handle multiple
    # sessions"). The plan's own §9.1 wanted to defer it, on the grounds that
    # stdio gives one session per subprocess; the instructor overruled that, so
    # sessions are keyed by id here. The MCP facade uses a single implicit
    # `"default"` id — an LLM has no business choosing session ids — while the
    # JSON-line protocol lets a caller name them explicitly.
    class SessionPool
      DEFAULT_ID = "default".freeze

      def initialize(config)
        @config = config
        @sessions = {}
        @mutex = Mutex.new
      end

      attr_reader :config

      # Fetch a live, logged-in session, connecting on first use and
      # reconnecting if the socket has since dropped.
      def session(id = DEFAULT_ID)
        id = normalize(id)

        @mutex.synchronize do
          existing = @sessions[id]
          return existing if existing&.open?

          # A closed-but-present session means the socket dropped since last
          # time. Discard it and build a fresh one; CircleMUD will report
          # "Reconnecting" and login handles that branch.
          existing&.close if existing
          @sessions[id] = connect_and_login
        end
      end

      # Whether a session exists *and* is open. Never connects — this is what
      # `mud_status` calls, and a status check that dials the phone is a trap.
      def open?(id = DEFAULT_ID)
        s = @sessions[normalize(id)]
        !s.nil? && s.open?
      end

      def status(id = DEFAULT_ID)
        if open?(id)
          "connected to #{@config.host}:#{@config.port} as #{@config.name}"
        else
          "disconnected (a connection will be opened automatically on the next command)"
        end
      end

      def ids
        @sessions.keys
      end

      def close(id = DEFAULT_ID)
        @mutex.synchronize do
          s = @sessions.delete(normalize(id))
          s&.close
          !s.nil?
        end
      end

      def close_all
        @mutex.synchronize do
          @sessions.each_value do |s|
            begin
              s.close
            rescue StandardError
              # shutting down; a failure to close a broken socket is not news
            end
          end
          @sessions.clear
        end
      end

      private

      def normalize(id)
        s = id.to_s.strip
        s.empty? ? DEFAULT_ID : s
      end

      def connect_and_login
        unless @config.credentials?
          raise Error.new(@config.missing_credentials_message, code: "MISSING_CREDENTIALS")
        end

        session = MudManager::Session.new(
          host: @config.host,
          port: @config.port,
          timeout: @config.timeout
        )

        begin
          session.open
          session.login(@config.name, @config.password)
        rescue MudManager::Session::Error => e
          begin
            session.close
          rescue StandardError
            # the connection attempt already failed; closing is best-effort
          end
          raise Error.from_session(e)
        end

        session
      end
    end
  end
end
