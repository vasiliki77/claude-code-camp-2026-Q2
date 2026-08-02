# BoukenshaLoader resolves which step folder to load from, then boots the REPL.
#
# Two settings, each resolved the same way — env var first, then ~/.boukensharc,
# then a built-in default:
#
#   BOUKENSHA_PATH  which step folder's lib to load  (default: the lib bundled in this gem)
#   BOUKENSHA_DIR   config dir holding settings.yaml, .env, prompts/  (default: ~/.boukensha)
#
# ~/.boukensharc holds KEY=value lines, using the same names as the env vars:
#
#   BOUKENSHA_PATH=~/Sites/boukensha/08_the_repl_loop
#   BOUKENSHA_DIR=~/Sites/boukensha/.boukensha
#
# A line with no "=" is read as BOUKENSHA_PATH, so the original one-line
# "the whole file is just a path" format still works.
#
# Examples:
#   boukensha                                                   # rc file, else bundled lib + ~/.boukensha
#   BOUKENSHA_PATH=~/Sites/boukensha/04_api_client boukensha    # loads step 4, overriding the rc file
#   BOUKENSHA_DIR=~/projects/mybot/.boukensha boukensha         # custom config dir for one run
module BoukenshaLoader
  # Absolute path to this gem's own bundled boukensha lib.
  BUNDLED_LIB = File.expand_path("../boukensha.rb", __FILE__)

  # Permanent defaults for the two env vars above.
  RC_FILE = File.expand_path("~/.boukensharc")

  # ~/.boukensharc parsed into a settings hash. No file => no settings.
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
             BOUKENSHA_PATH=~/Sites/boukensha/08_the_repl_loop boukensha
    MSG
  end

  # Boukensha::Config reads BOUKENSHA_DIR from ENV, so the rc file's value has to
  # land in ENV before the step's lib is required. ||= keeps the same precedence
  # rule as resolve: a real env var always wins over the rc file.
  #
  # Deliberately no existence check — Config treats a missing settings.yaml or
  # .env as empty, and a config dir you have not filled in yet is a normal state.
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

    Boukensha.repl
  end
end
