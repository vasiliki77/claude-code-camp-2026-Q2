require "yaml"

module MudManager
  module Mcp
    # Where the daemon gets host, port and credentials.
    #
    # Plan §5: connect/login are deterministic *framework* concerns, not
    # decisions we want an LLM making. So credentials never arrive as tool
    # arguments — they come from the environment, exactly as
    # `examples/live_session_test.rb` already does.
    #
    # Precedence, highest first:
    #   1. explicit keyword arguments (tests, embedding)
    #   2. MUD_HOST / MUD_PORT / MUD_NAME / MUD_PASSWORD / MUD_TIMEOUT
    #   3. the `mud:` block of <BOUKENSHA_DIR>/settings.yaml
    #   4. Session's own defaults
    #
    # Tier 3 exists because the bootcamp repo already keeps these in
    # `.boukensha/settings.yaml`, and making a bootcamper maintain the same four
    # values twice is how they drift.
    class Config
      DEFAULT_HOST = MudManager::Session::DEFAULT_HOST
      DEFAULT_PORT = MudManager::Session::DEFAULT_PORT

      attr_reader :host, :port, :name, :password, :timeout

      def initialize(host: nil, port: nil, name: nil, password: nil, timeout: nil, settings: nil)
        settings ||= self.class.load_settings

        @host     = host     || ENV["MUD_HOST"]     || settings["host"]     || DEFAULT_HOST
        @port     = (port    || ENV["MUD_PORT"]     || settings["port"]     || DEFAULT_PORT).to_i
        # settings.yaml calls it `username`; the env var is MUD_NAME because the
        # MUD's own prompt asks for a name. Accept both spellings from YAML.
        @name     = name     || ENV["MUD_NAME"]     || settings["username"] || settings["name"]
        @password = password || ENV["MUD_PASSWORD"] || settings["password"]
        @timeout  = (timeout || ENV["MUD_TIMEOUT"]  || MudManager::Session::DEFAULT_TIMEOUT).to_f
      end

      # Credentials are only needed at login time, so this is checked lazily by
      # SessionPool rather than at construction — a `--list-tools` or
      # `--dump-spec` run must work with no credentials configured at all.
      def credentials?
        !to_s_or_nil(@name).nil? && !to_s_or_nil(@password).nil?
      end

      def missing_credentials_message
        missing = []
        missing << "MUD_NAME" if to_s_or_nil(@name).nil?
        missing << "MUD_PASSWORD" if to_s_or_nil(@password).nil?
        "missing credentials: #{missing.join(', ')} " \
          "(set the environment variables, or add mud.username / mud.password " \
          "to <BOUKENSHA_DIR>/settings.yaml)"
      end

      def to_h
        { "host" => host, "port" => port, "name" => name, "timeout" => timeout }
      end

      # Deliberately no password in the string form — this gets logged.
      def to_s
        "#<MudManager::Mcp::Config #{host}:#{port} name=#{name.inspect}>"
      end

      # Read the `mud:` block out of settings.yaml, if there is one. Returns {}
      # rather than raising: a daemon started with env vars set has no reason to
      # care that the bootcamp config directory is absent.
      def self.load_settings(dir = ENV["BOUKENSHA_DIR"])
        return {} if dir.nil? || dir.empty?

        path = File.join(dir, "settings.yaml")
        return {} unless File.exist?(path)

        loaded = YAML.safe_load_file(path) || {}
        mud = loaded["mud"]
        mud.is_a?(Hash) ? mud : {}
      rescue StandardError => e
        warn "[mud-manager] ignoring unreadable settings at #{path}: #{e.message}"
        {}
      end

      private

      def to_s_or_nil(value)
        s = value.to_s.strip
        s.empty? ? nil : s
      end
    end
  end
end
