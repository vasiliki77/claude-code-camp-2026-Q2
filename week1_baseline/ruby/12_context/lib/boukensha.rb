require_relative "boukensha/version"
require_relative "boukensha/config"
require_relative "boukensha/tasks/player"

module Boukensha
  @debug  = false
  @config = nil

  def self.config
    @config ||= Config.new
  end

  def self.debug!
    @debug = true
  end

  def self.debug?
    @debug
  end

  # One-shot run: send a single task, get a response, return.
  #
  # working_dir:      roots all tool calls to this directory (default: Dir.pwd).
  #                   Registers Boukensha::Tools::FileSystem (pwd, list_directory,
  #                   read_file, write_file, delete_file, search_files) and
  #                   Boukensha::Tools::Shell (run_command) automatically.
  #                   Pass working_dir: false to opt out entirely.
  #
  # allowed_commands: Array of shell-executable names the agent is allowed to
  #                   run via run_command (e.g. ["ruby", "git"]).
  #                   nil (default) permits everything — useful for demos.
  #                   Pass an empty Array [] to disable run_command entirely.
  #
  # shell_timeout:    Seconds before a run_command is killed (default 30).
  #
  # mud:              Hash of MUD connection options — registers all MUD gameplay
  #                   tools and keeps a single session alive across every tool call.
  #                   When nil (default), config.mud_* values are used if mud_host
  #                   is set in settings.yaml. Pass mud: false to disable entirely.
  #
  # context_window:   The model's input-token ceiling, which the compaction
  #                   trigger is a fraction of. Defaults to
  #                   Models.context_window(model) — a model fact, not a
  #                   preference, so overriding it is for testing compaction
  #                   without burning a real window.
  def self.run(
    task:,
    system:           nil,
    model:            nil,
    backend:          nil,
    api_key:          nil,
    ollama_host:      "http://localhost:11434",
    log:              nil,
    context_window:   nil,
    max_output_tokens: nil,
    working_dir:      Dir.pwd,
    allowed_commands: nil,
    shell_timeout:    30,
    mud:              nil,
    mcp:              nil,
    &block
  )
    cfg           = config                           # loads .env; populates ENV
    task_class    = Tasks::Player
    task_settings = cfg.tasks(task_class.task_name)
    system      ||= task_class.system_prompt(task_settings, user_prompts_dir: cfg.user_prompts_dir, default_prompts_dir: Config::PROMPTS_DIR)
    model       ||= task_class.model(task_settings)
    backend     ||= task_class.provider(task_settings).to_sym
    context_window ||= Models.context_window(model)
    api_key ||= case backend
                when :anthropic    then ENV["ANTHROPIC_API_KEY"]
                when :openai       then ENV["OPENAI_API_KEY"]
                when :gemini       then ENV["GEMINI_API_KEY"]
                when :ollama_cloud then ENV["OLLAMA_API_KEY"]
                end

    ctx      = Context.new(task: task_class, system: system, working_dir: working_dir,
                           context_window: context_window,
                           compaction_threshold: task_class.compaction_threshold(task_settings))
    registry = Registry.new(ctx)

    if working_dir
      Tools::FileSystem.register(registry, working_dir: working_dir)
      Tools::Shell.register(registry, working_dir: working_dir,
                            timeout: shell_timeout, allowed_commands: allowed_commands)
    end

    # mud: nil means "use config if host is set"; mud: false means "skip entirely"
    resolved_mud = mud == false ? nil : (mud || mud_opts_from_config(cfg))
    Tools::Mud.register(registry, **resolved_mud) if resolved_mud

    mcp_clients = register_all_mcp(registry, mcp, cfg)

    RunDSL.new(registry).instance_eval(&block) if block

    be = case backend
         when :anthropic    then Backends::Anthropic.new(api_key: api_key, model: model)
         when :openai       then Backends::OpenAI.new(api_key: api_key, model: model)
         when :gemini       then Backends::Gemini.new(api_key: api_key, model: model)
         when :ollama       then Backends::Ollama.new(host: ollama_host, model: model)
         when :ollama_cloud then Backends::OllamaCloud.new(api_key: api_key, model: model)
         else raise ArgumentError, "Unknown backend #{backend.inspect}. Use :anthropic, :openai, :gemini, :ollama, or :ollama_cloud."
         end

    builder = PromptBuilder.new(ctx, be)
    client  = Client.new(builder)
    effective_max_iterations = task_class.max_iterations(task_settings)
    effective_max_turn_tokens = task_class.max_turn_tokens(task_settings)
    effective_max_output_tokens = max_output_tokens || task_class.max_output_tokens(task_settings)
    logger  = Logger.new(log: log, snapshot: {
      task:              task_class.task_name,
      max_iterations:    effective_max_iterations,
      max_turn_tokens:   effective_max_turn_tokens,
      max_output_tokens: effective_max_output_tokens,
      context_window:    context_window,
      model:             model,
      provider:          backend
    })
    agent   = Agent.new(context: ctx, registry: registry, builder: builder, client: client, logger: logger,
                        task_settings: task_settings, max_iterations: effective_max_iterations,
                        max_turn_tokens: effective_max_turn_tokens,
                        max_output_tokens: effective_max_output_tokens)

    ctx.add_message(:user, task)
    agent.run
  ensure
    logger&.close
    close_mcp_clients(mcp_clients)
  end

  # Interactive REPL — see Boukensha.run for full option documentation.
  #
  # tui: true (default) wraps the REPL in a charm-ruby TUI.  Pass tui: false or
  # use the --no-tui CLI flag to fall back to the plain terminal REPL.
  def self.repl(
    system:           nil,
    model:            nil,
    backend:          nil,
    api_key:          nil,
    ollama_host:      "http://localhost:11434",
    log:              nil,
    context_window:   nil,
    max_output_tokens: nil,
    working_dir:      Dir.pwd,
    allowed_commands: nil,
    shell_timeout:    30,
    mud:              nil,
    mcp:              nil,
    tui:              true,
    &block
  )
    cfg           = config                           # loads .env; populates ENV
    task_class    = Tasks::Player
    task_settings = cfg.tasks(task_class.task_name)
    system      ||= task_class.system_prompt(task_settings, user_prompts_dir: cfg.user_prompts_dir, default_prompts_dir: Config::PROMPTS_DIR)
    model       ||= task_class.model(task_settings)
    backend     ||= task_class.provider(task_settings).to_sym
    context_window ||= Models.context_window(model)
    api_key ||= case backend
                when :anthropic    then ENV["ANTHROPIC_API_KEY"]
                when :openai       then ENV["OPENAI_API_KEY"]
                when :gemini       then ENV["GEMINI_API_KEY"]
                when :ollama_cloud then ENV["OLLAMA_API_KEY"]
                end

    ctx      = Context.new(task: task_class, system: system, working_dir: working_dir,
                           context_window: context_window,
                           compaction_threshold: task_class.compaction_threshold(task_settings))
    registry = Registry.new(ctx)

    if working_dir
      Tools::FileSystem.register(registry, working_dir: working_dir)
      Tools::Shell.register(registry, working_dir: working_dir,
                            timeout: shell_timeout, allowed_commands: allowed_commands)
    end

    resolved_mud = mud == false ? nil : (mud || mud_opts_from_config(cfg))
    Tools::Mud.register(registry, **resolved_mud) if resolved_mud

    mcp_clients = register_all_mcp(registry, mcp, cfg)

    RunDSL.new(registry).instance_eval(&block) if block

    be = case backend
         when :anthropic    then Backends::Anthropic.new(api_key: api_key, model: model)
         when :openai       then Backends::OpenAI.new(api_key: api_key, model: model)
         when :gemini       then Backends::Gemini.new(api_key: api_key, model: model)
         when :ollama       then Backends::Ollama.new(host: ollama_host, model: model)
         when :ollama_cloud then Backends::OllamaCloud.new(api_key: api_key, model: model)
         else raise ArgumentError, "Unknown backend #{backend.inspect}. Use :anthropic, :openai, :gemini, :ollama, or :ollama_cloud."
         end

    builder = PromptBuilder.new(ctx, be)
    client  = Client.new(builder)
    effective_max_iterations = task_class.max_iterations(task_settings)
    effective_max_turn_tokens = task_class.max_turn_tokens(task_settings)
    effective_max_output_tokens = max_output_tokens || task_class.max_output_tokens(task_settings)
    logger  = Logger.new(log: log, snapshot: {
      task:              task_class.task_name,
      max_iterations:    effective_max_iterations,
      max_turn_tokens:   effective_max_turn_tokens,
      max_output_tokens: effective_max_output_tokens,
      context_window:    context_window,
      model:             model,
      provider:          backend
    })

    repl = Repl.new(
      context:    ctx,
      registry:   registry,
      builder:    builder,
      client:     client,
      logger:     logger,
      task_settings: task_settings,
      max_iterations:    effective_max_iterations,
      max_turn_tokens:   effective_max_turn_tokens,
      max_output_tokens: effective_max_output_tokens,
      config_dir: cfg.dir,
      provider:   backend,
      model:      model,
      version:    VERSION,
      api_key:    api_key,
      mud:        resolved_mud,
      mcp:        mcp_clients
    )

    if tui && defined?(Tui)
      Tui.new(repl).start
    else
      repl.start
    end
  rescue Interrupt
    puts "\nInterrupted."
  ensure
    logger&.close
    close_mcp_clients(mcp_clients)
  end

  # One server failing to shut down must not strand the others.
  def self.close_mcp_clients(clients)
    Array(clients).each do |c|
      c.close
    rescue StandardError => e
      warn "[boukensha] error closing MCP server: #{e.message}"
    end
  end
  private_class_method :close_mcp_clients

  # Default prefix for the MUD server's tools.
  #
  # Named after the *engine*, not the config key: a second entry called "mud" is
  # plausible, a second tbaMUD is not, and scoping by engine keeps names
  # distinct without inventing a taxonomy. This string lives here and in
  # settings.yaml only — Tools::Mcp applies whatever prefix it is handed and
  # must never know the word "tbamud".
  MUD_PREFIX = "tbamud".freeze

  # Resolve the mcp: option into Tools::Mcp.register keyword arguments.
  #
  #   nil / false  -> no MCP tools
  #   true         -> the MUD server: the mcp_servers["mud"] entry if there is
  #                   one, else a preset built from the mud: block
  #   Hash         -> passed through, with command/args defaulted
  #
  # The `true` case is the preset. It exists so that turning the daemon on costs
  # no configuration at all, by translating the same settings.yaml `mud:` block
  # that Tools::Mud reads into the environment variables the daemon expects
  # (generic_interfacing §5 — credentials reach the server through its
  # environment, never as tool arguments).
  def self.mcp_opts(mcp, cfg)
    return nil if mcp.nil? || mcp == false

    defaults = mud_server_from_config(cfg) || {
      command:  ENV["MUD_MANAGER_BIN"] || "mud-manager",
      args:     ["--mcp"],
      env:      mud_env_from_config(cfg),
      prefix:   MUD_PREFIX,
      required: true,
      label:    "mud"
    }

    mcp == true ? defaults : defaults.merge(mcp)
  end
  private_class_method :mcp_opts

  # An explicit mcp_servers["mud"] entry wins over the preset — it is the more
  # specific statement of intent. Its env is layered *over* the mud: block so a
  # partial entry (command and prefix only) still gets credentials.
  def self.mud_server_from_config(cfg)
    entry = cfg.mcp_servers["mud"]
    return nil unless entry && entry[:command]

    entry.merge(
      env:   mud_env_from_config(cfg).merge(entry[:env] || {}),
      label: "mud"
    )
  end
  private_class_method :mud_server_from_config

  # Register the MUD server (if mcp: asked for it) plus every other mcp_servers
  # entry. Returns the live clients, which the caller must close.
  #
  # Servers are spawned eagerly, at registration: you cannot register tools you
  # have not discovered, and discovery needs a running server. That means N
  # servers cost N spawns at boot even for ones the model never calls — fine at
  # one or two, worth revisiting beyond that. "Lazy" would really mean
  # "register from a cached manifest", which is a much larger change.
  #
  # required: true (the default) means a failure to spawn raises — you
  # configured it, so its absence is a problem you want to hear about.
  # required: false means warn and carry on, which is right for a decorative
  # server whose tools the agent can do without.
  def self.register_all_mcp(registry, mcp, cfg)
    entries = []

    # "mud" is owned by the mcp: option / BOUKENSHA_MCP, not by the generic
    # loop, so it is resolved separately and skipped below.
    if (mud_entry = mcp_opts(mcp, cfg))
      entries << mud_entry
    end

    cfg.mcp_servers.each do |name, entry|
      next if name == "mud"
      next if entry[:command].to_s.empty?

      entries << entry.merge(label: name)
    end

    entries.each_with_object([]) do |entry, clients|
      args = entry.slice(:command, :args, :env, :prefix, :label)
      args[:args] ||= []
      args[:env]  ||= {}

      begin
        clients << Tools::Mcp.register(registry, **args)
      rescue StandardError => e
        raise if entry.fetch(:required, true)

        warn "[boukensha] optional MCP server #{entry[:label].inspect} failed to start: " \
             "#{e.message} — continuing without its tools"
      end
    end
  end
  private_class_method :register_all_mcp

  # The daemon reads MUD_* from its environment. Only send what is actually
  # configured — an empty string would override the daemon's own defaults with
  # nothing, which is worse than being absent.
  #
  # An inherited MUD_* wins over config. The child's environment is these values
  # merged *over* the parent's, so taking ENV first is what keeps the documented
  # precedence ("env vars take precedence over config") true across the process
  # boundary. Reading config first would silently invert it, and only for the
  # MCP path — the in-process path would still honour the env var, so the two
  # routes to the same tools would disagree about which credentials to use.
  def self.mud_env_from_config(cfg)
    {
      "MUD_HOST"     => ENV["MUD_HOST"]     || cfg.mud_host,
      "MUD_PORT"     => ENV["MUD_PORT"]     || cfg.mud_port&.to_s,
      "MUD_NAME"     => ENV["MUD_NAME"]     || cfg.mud_username,
      "MUD_PASSWORD" => ENV["MUD_PASSWORD"] || cfg.mud_password
    }.compact
  end
  private_class_method :mud_env_from_config

  # Build a mud options hash from config (used when mud: nil is passed to run/repl).
  # Returns nil if no MUD host is configured.
  def self.mud_opts_from_config(cfg)
    return nil unless cfg.mud_host && cfg.mud_username

    {
      host:     cfg.mud_host,
      port:     cfg.mud_port,
      name:     cfg.mud_username,
      password: cfg.mud_password
    }
  end
  private_class_method :mud_opts_from_config
end

require_relative "boukensha/tool"
require_relative "boukensha/message"
require_relative "boukensha/context"
require_relative "boukensha/errors"
require_relative "boukensha/registry"
require_relative "boukensha/prompt_builder"
require_relative "boukensha/usage"
require_relative "boukensha/logger"
require_relative "boukensha/backends/base"
require_relative "boukensha/backends/anthropic"
require_relative "boukensha/backends/gemini"
require_relative "boukensha/backends/ollama"
require_relative "boukensha/backends/ollama_cloud"
require_relative "boukensha/backends/openai"
# Models folds every backend's MODELS table into one lookup, so it has to come
# after all five of them.
require_relative "boukensha/models"
require_relative "boukensha/client"
require_relative "boukensha/agent"
require_relative "boukensha/run_dsl"
require_relative "boukensha/repl"
require_relative "boukensha/tools/file_system"
require_relative "boukensha/tools/shell"
require_relative "boukensha/tools/mud"
require_relative "boukensha/tools/mcp"
require_relative "boukensha/tui"