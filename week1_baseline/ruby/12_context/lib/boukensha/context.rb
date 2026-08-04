require_relative "tool"
require_relative "message"

module Boukensha
  class Context
    attr_reader :task, :system, :messages, :tools, :context_window, :working_dir,
                :turn_tokens, :compaction_threshold
    attr_accessor :current_tokens

    def initialize(system:, task: nil, context_window: 200_000, working_dir: nil, compaction_threshold: 0.85)
      @task                 = task
      @system               = system
      @context_window       = context_window
      @working_dir          = working_dir ? File.expand_path(working_dir) : nil
      @compaction_threshold = compaction_threshold
      @messages             = []
      @tools                = {}
      @current_tokens       = 0
      @turn_tokens          = 0
    end

    def register_tool(tool)
      @tools[tool.name] = tool
    end

    def add_message(role, content, tool_use_id: nil)
      @messages << Message.new(role, content, tool_use_id)
    end

    # Update the known context size from the last API response's input_tokens.
    def update_tokens(n)
      @current_tokens = n.to_i
    end

    # Reset the cumulative per-turn spend counter. Called at the top of a turn.
    def reset_turn_tokens
      @turn_tokens = 0
    end

    # Add one API call's input+output tokens to the cumulative per-turn total.
    # This is the spend budget — distinct from current_tokens (window pressure).
    def add_turn_tokens(input, output)
      @turn_tokens += input.to_i + output.to_i
    end

    # Fraction of the context window currently in use (0.0–1.0).
    def usage_fraction
      @context_window > 0 ? @current_tokens.to_f / @context_window : 0.0
    end

    # Integer percentage (0–100).
    def usage_pct
      (usage_fraction * 100).round
    end

    # True when we should compact before the next API call. Defaults to the
    # configured compaction_threshold (a fraction of context_window).
    def needs_compaction?(threshold: compaction_threshold)
      usage_fraction >= threshold
    end

    # Drop the oldest messages to free space, keeping roughly target_fraction of
    # them and at least 2. Resets current_tokens to 0 (the next API response
    # reports the true new size). Returns the number of messages dropped.
    def compact_messages!(target_fraction: 0.60)
      return 0 if @messages.size <= 2

      drop_count = [((@messages.size * (1.0 - target_fraction)).ceil), @messages.size - 2].min
      drop_count = snap_to_user([drop_count, 0].max)

      @messages = @messages.drop(drop_count)
      @current_tokens = 0
      drop_count
    end

    # Drop all conversation history, keeping tools and system prompt intact.
    def clear_messages!
      @messages = []
      @current_tokens = 0
    end

    def tool_count = @tools.size
    def turn_count = @messages.size

    def to_s
      "#<Context task=#{task&.task_name} turns=#{turn_count} tools=#{tool_count} " \
        "window=#{context_window} current=#{current_tokens}>"
    end

    private

    # Advance a drop point until the first surviving message is a plain :user
    # turn.
    #
    # Dropping purely by count orphans any :tool_result whose :tool_use was
    # dropped with it — Anthropic answers that with a 400, and separately
    # requires a conversation to open on a user turn. With the MUD tools
    # registered, tool pairs are most of the history, so an unsnapped drop lands
    # mid-pair more often than not.
    #
    # Snapping forward only ever drops *more*, never less, so the invariant
    # holds unconditionally. The newest message is always a user turn (both
    # Boukensha.run and Repl#run_turn append the input before the agent runs),
    # so the scan always terminates on a real index.
    def snap_to_user(index)
      index += 1 while index < @messages.size && @messages[index].role != :user
      index
    end
  end
end
