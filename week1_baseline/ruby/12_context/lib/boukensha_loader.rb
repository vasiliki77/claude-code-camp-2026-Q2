# BoukenshaLoader resolves which step folder to load from, then boots the REPL.
#
# Resolution order:
#   1. BOUKENSHA_PATH environment variable (selects which *step* lib to load)
#   2. ~/.boukensharc  (a file containing a single path)
#   3. The lib/ directory bundled inside this gem (step 10 — the latest release)
#
# Config directory (settings.yaml, .env, system.md) is separate:
#   BOUKENSHA_DIR=~/.boukensha  (default; set to override)
#
# MUD connection details come from settings.yaml (mud: block) by default.
# The legacy MUD_NAME / MUD_HOST / MUD_PORT / MUD_PASSWORD env vars are still
# honoured and take precedence over config when set.
#
# Examples:
#   boukensha                                                              # uses bundled lib + ~/.boukensha
#   BOUKENSHA_PATH=~/Sites/boukensha/04_api_client boukensha              # loads step 4
#   BOUKENSHA_DIR=~/projects/mybot/.boukensha boukensha                   # custom config dir
#   echo ~/Sites/boukensha/12_context > ~/.boukensharc && boukensha
module BoukenshaLoader
  # Absolute path to this gem's own bundled boukensha lib.
  BUNDLED_LIB = File.expand_path("../boukensha.rb", __FILE__)

  # Permanent defaults for the env vars above.
  RC_FILE = File.expand_path("~/.boukensharc")

  # ~/.boukensharc parsed into a settings hash. No file => no settings.
  #
  # Carried forward from step 09, which extended the rc file from "one bare
  # path" to KEY=value lines. Without it, ~/.boukensharc can only say *which
  # lib* to load and not *where the config lives* — and the global command
  # bypasses bin/ruby/*, so it never gets BOUKENSHA_DIR from a launcher.
  # A bare path still parses, so an old rc file keeps working.
  def self.rc
    @rc ||= parse_rc
  end

  def self.parse_rc
    return {} unless File.exist?(RC_FILE)

    File.readlines(RC_FILE, chomp: true).each_with_object({}) do |line, out|
      line = line.strip
      next if line.empty? || line.start_with?("#")

      if line.include?("=")
        key, value = line.split("=", 2)
        out[key.strip.upcase] = value.strip
      else
        # The original format: the whole file is just the step path.
        out["BOUKENSHA_PATH"] = line
      end
    end
  end

  def self.resolve
    # 1. Env var wins over the rc file.  2. Then the rc file.
    from_env = ENV["BOUKENSHA_PATH"]
    dir      = from_env || rc["BOUKENSHA_PATH"]

    # 3. Neither is set — the lib bundled inside this gem.
    return BUNDLED_LIB if dir.nil? || dir.empty?

    expanded = File.expand_path(dir)
    main     = File.join(expanded, "lib", "boukensha.rb")
    return main if File.exist?(main)

    source = from_env ? "BOUKENSHA_PATH" : "~/.boukensharc"
    abort <<~MSG
      boukensha: #{source} points to
             #{expanded}
             but no lib/boukensha.rb was found there.
             Make sure it points to a step folder, e.g.:
             BOUKENSHA_PATH=~/Sites/boukensha/12_context boukensha
    MSG
  end

  # Boukensha::Config reads BOUKENSHA_DIR from ENV, so the rc file's value has to
  # land in ENV before the step's lib is required. ||= keeps the same precedence
  # rule as resolve: a real env var always wins over the rc file.
  def self.apply_config_dir
    dir = rc["BOUKENSHA_DIR"]
    return if dir.nil? || dir.empty?

    ENV["BOUKENSHA_DIR"] ||= File.expand_path(dir)
  end

  def self.load_and_start_repl
    apply_config_dir
    main = resolve
    step_dir = File.dirname(File.dirname(main))

    if ENV["BOUKENSHA_DEBUG"]
      puts "[boukensha] loading from: #{step_dir}"
      puts "[boukensha] config dir:   #{ENV['BOUKENSHA_DIR'] || File.expand_path('~/.boukensha')}"
    end

    require main

    unless Boukensha.respond_to?(:repl)
      abort <<~MSG
        boukensha: the step at #{step_dir}
               does not support the interactive REPL (added in step 7).
               Run its examples directly, e.g.:
                 ruby #{step_dir}/examples/*.rb
               Or point BOUKENSHA_PATH at step 7 or later.
      MSG
    end

    # --no-tui falls back to the plain terminal REPL (no charm-ruby).
    #
    # This step's flag, restored after the step-10 loader was carried forward
    # over it. Carrying a whole file forward is how a later step's capability
    # gets silently dropped — the same failure this loader's rc-file parsing was
    # itself brought here to fix, inflicted in the opposite direction.
    no_tui = ARGV.delete("--no-tui")

    repl_opts = { tui: !no_tui }

    if ENV["MUD_NAME"]
      # Legacy env-var override still works and takes precedence over config.
      repl_opts[:working_dir] = false
      repl_opts[:mud] = {
        host:     ENV.fetch("MUD_HOST",     "localhost"),
        port:     ENV.fetch("MUD_PORT",     "4000").to_i,
        name:     ENV.fetch("MUD_NAME"),
        password: ENV.fetch("MUD_PASSWORD") { abort "boukensha: MUD_NAME is set but MUD_PASSWORD is missing." }
      }
    end
    # If MUD_NAME is not set, Boukensha.repl will fall back to config.mud_* values
    # automatically (via mud_opts_from_config inside Boukensha.repl).

    # BOUKENSHA_MCP=1 routes the MUD tools through the `mud-manager` daemon
    # instead of linking MudManager into this process. Same 26 tools, same
    # credentials, different side of a process boundary.
    #
    # Opt-in on purpose: without it the terminal command behaves exactly as it
    # did before the daemon existed, so nothing that worked stops working.
    if %w[1 true yes].include?(ENV["BOUKENSHA_MCP"].to_s.downcase)
      repl_opts[:working_dir] = false
      # Both paths register the same 26 names; leaving Tools::Mud on as well
      # would open a second MUD connection and let one set silently overwrite
      # the other.
      repl_opts[:mud] = false
      repl_opts[:mcp] = true
    end

    Boukensha.repl(**repl_opts)
  end
end
