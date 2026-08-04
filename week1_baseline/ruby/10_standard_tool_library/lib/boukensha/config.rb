require "yaml"
require "dotenv"
require "pathname"

module Boukensha
  class Config
    # The .boukensha config directory is resolved in this order:
    #   1. BOUKENSHA_DIR environment variable (set before loading .env)
    #   2. ~/.boukensha  (default)
    DEFAULT_DIR = File.join(Dir.home, ".boukensha").freeze

    # Default prompts shipped alongside this step.
    PROMPTS_DIR = File.expand_path("../../../prompts", __dir__).freeze

    attr_reader :dir, :settings

    def initialize
      @dir = resolve_dir
      load_env
      @settings = load_settings
    end

    # ---------- tasks -----------------------------------------------------

    # With no argument: returns the full tasks hash from settings.yaml.
    # With a name: returns that task's settings hash, e.g. tasks(:player).
    def tasks(name = nil)
      all = dig(:tasks) || {}
      name ? (all[name.to_s] || all[name.to_sym]) : all
    end

    # The user's prompts directory for task prompt overrides.
    def user_prompts_dir
      File.join(@dir, "prompts")
    end

    # ---------- MUD connection --------------------------------------------

    def mud_host
      dig(:mud, :host) || "localhost"
    end

    def mud_port
      dig(:mud, :port) || 4000
    end

    def mud_username
      dig(:mud, :username)
    end

    def mud_password
      dig(:mud, :password)
    end

    # ---------- MCP servers -------------------------------------------------

    # MCP servers declared in settings.yaml, as data rather than code:
    #
    #   mcp_servers:
    #     mud:
    #       command: mud-manager
    #       args:    [--mcp]
    #       prefix:  tbamud
    #       env:
    #         MUD_HOST: localhost
    #         MUD_NAME: Gandalf
    #     filesystem:
    #       command:  npx
    #       args:     [-y, "@modelcontextprotocol/server-filesystem", /tmp]
    #       required: false
    #
    # Returns { "mud" => { command:, args:, env:, prefix:, required: }, ... }.
    #
    # "Server" here means an MCP server *process* — one entry, one subprocess.
    # It never means a MUD. Connecting to several MUDs is a different axis, and
    # the daemon already solves it: SessionPool holds multiple named sessions
    # inside one `mud-manager`. Two MUDs is two sessions in one server.
    #
    # `required` defaults to **true**: a server you bothered to configure and
    # which then fails to start is a problem you want to hear about. Mark the
    # decorative ones `required: false` and they warn and are skipped.
    def mcp_servers
      raw = dig(:mcp_servers)
      return {} unless raw.is_a?(Hash)

      raw.each_with_object({}) do |(name, spec), out|
        spec = {} unless spec.is_a?(Hash)
        out[name.to_s] = normalize_server(spec)
      end
    end

    # ---------- low-level helpers -----------------------------------------

    # Fetch a nested key path from settings, e.g. dig(:mud, :host)
    def dig(*keys)
      keys.reduce(@settings) do |node, key|
        case node
        when Hash then node[key.to_s] || node[key.to_sym]
        else nil
        end
      end
    end

    def to_s
      "#<Boukensha::Config dir=#{@dir} tasks=#{tasks.keys.join(',')}>"
    end

    def inspect = to_s

    private

    # YAML may hand us string or symbol keys depending on how it was written, so
    # every lookup goes through fetch_either rather than assuming one.
    def normalize_server(spec)
      env = fetch_either(spec, :env) || {}
      env = {} unless env.is_a?(Hash)

      required = fetch_either(spec, :required)

      {
        command:  fetch_either(spec, :command),
        args:     Array(fetch_either(spec, :args)).map(&:to_s),
        env:      env.each_with_object({}) { |(k, v), h| h[k.to_s] = v.to_s },
        prefix:   fetch_either(spec, :prefix),
        required: required.nil? ? true : !!required
      }
    end

    def fetch_either(hash, key)
      return nil unless hash.is_a?(Hash)

      hash.key?(key.to_s) ? hash[key.to_s] : hash[key.to_sym]
    end

    def resolve_dir
      raw = ENV.fetch("BOUKENSHA_DIR", nil) || DEFAULT_DIR
      Pathname.new(raw).expand_path.to_s
    end

    def load_env
      env_file = File.join(@dir, ".env")
      if File.exist?(env_file)
        Dotenv.load(env_file)
      end
    end

    def load_settings
      settings_file = File.join(@dir, "settings.yaml")
      if File.exist?(settings_file)
        YAML.safe_load(File.read(settings_file)) || {}
      else
        {}
      end
    end
  end
end
