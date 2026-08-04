require_relative "../primitives"
require_relative "errors"
require_relative "tool_spec"

module MudManager
  module Mcp
    # Turns a tool call into a MUD round trip.
    #
    # Plan §6: every tool does what the `send_cmd` lambda in
    # `Boukensha::Tools::Mud` does today — drain stale bytes, send the
    # primitive, read until CircleMUD's prompt sentinel. That logic moves *into
    # the daemon* here, which is precisely how the other four language tracks
    # inherit it for free.
    #
    # The argument-to-primitive mapping below is written out longhand, one tool
    # per branch, rather than derived reflectively from method signatures.
    # Primitives mixes positional and keyword arguments per method with no
    # regular pattern, so a clever mapping would be a guess that fails silently
    # on the next primitive added. A boring `case` fails loudly instead.
    class Dispatcher
      def initialize(pool)
        @pool = pool
        @p = MudManager::Primitives
      end

      attr_reader :pool

      # Returns the MUD's response text. Raises Mcp::Error subclasses, which
      # both protocol layers know how to serialise.
      def call(name, args = {}, session_id: SessionPool::DEFAULT_ID)
        tool = ToolSpec.find(name)
        raise UnknownToolError, name unless tool

        args = normalize_args(tool, args)

        # These three never touch Primitives, and two of them must not trigger
        # a lazy connect.
        case tool["name"]
        when "mud_status" then return @pool.status(session_id)
        when "poll"       then return poll(session_id, args["timeout"])
        when "send_raw"   then return round_trip(session_id, args["command"])
        end

        round_trip(session_id, build_command(tool, args))
      end

      private

      # ---------- the round trip ----------

      def round_trip(session_id, command)
        session = @pool.session(session_id)
        # Drain first so read_until_prompt sees only bytes this command caused —
        # leftover login output or an async tick would otherwise be returned as
        # if it were the answer.
        session.drain
        session.send_command(command)
        session.read_until_prompt
      rescue MudManager::Session::Error => e
        raise Error.from_session(e)
      end

      # Unsolicited output only. Deliberately does not connect: polling an
      # unopened session is a legitimate "nothing has happened" answer, not a
      # reason to dial the MUD.
      def poll(session_id, timeout)
        return "" unless @pool.open?(session_id)

        session = @pool.session(session_id)
        text = if timeout && timeout.to_f > 0
                 session.read_until_quiet(0.3, timeout: timeout.to_f)
               else
                 session.drain
               end
        text.to_s
      rescue MudManager::Session::Error => e
        raise Error.from_session(e)
      end

      # ---------- argument handling ----------

      def normalize_args(tool, args)
        args = (args || {}).each_with_object({}) { |(k, v), h| h[k.to_s] = v }
        spec = tool["args"]

        args.each_key do |key|
          unless spec.key?(key)
            raise ValidationError.new(
              "unknown argument #{key.inspect} for #{tool['name']} " \
              "(accepts: #{spec.keys.join(', ')})",
              tool: tool["name"]
            )
          end
        end

        spec.each do |key, arg_spec|
          value = args[key]

          # Treat "" as absent. The LLM reaches for the empty string constantly
          # when it means "no value", and Primitives already normalizes it for
          # look/door but not elsewhere.
          value = nil if value.is_a?(String) && value.strip.empty?
          value = arg_spec["default"] if value.nil? && arg_spec.key?("default")

          if value.nil?
            if arg_spec["required"]
              raise ValidationError.new(
                "missing required argument #{key.inspect} for #{tool['name']}",
                tool: tool["name"]
              )
            end

            args.delete(key)
            next
          end

          args[key] = coerce(tool, key, arg_spec, value)
        end

        args
      end

      def coerce(tool, key, arg_spec, value)
        case arg_spec["type"]
        when "integer"
          Integer(value)
        when "number"
          Float(value)
        else
          value.to_s
        end
      rescue ArgumentError, TypeError
        raise ValidationError.new(
          "argument #{key.inspect} for #{tool['name']} must be #{arg_spec['type']}, " \
          "got #{value.inspect}",
          tool: tool["name"]
        )
      end

      # ---------- tool -> primitive ----------

      def build_command(tool, a)
        method, positional, keyword = primitive_call(tool["name"], a)
        # Ruby 3 separates positional and keyword arguments strictly: a hash
        # splatted with `*` arrives as a positional argument, so every
        # keyword-taking primitive would raise. Hence the explicit `**`.
        @p.public_send(method, *positional, **keyword)
      rescue ArgumentError => e
        # Primitives raises ArgumentError for a bad enum value, and its message
        # already lists the allowed set — exactly what a confused caller needs.
        raise ValidationError.new(e.message, tool: tool["name"])
      end

      # Returns [method, positional_args, keyword_args] for Primitives.
      def primitive_call(name, a)
        case name
        when "look"           then [:look, [], { target: a["target"], preposition: a["preposition"] }]
        when "examine"        then [:examine, [a["target"]], {}]
        when "check"          then [:info_self, [a["kind"]], {}]
        when "move"           then [:move, [a["direction"]], {}]
        when "flee"           then [:flee, [], {}]
        when "set_position"   then [:set_position, [a["position"]], {}]
        when "track"          then [:track, [a["target"]], {}]
        when "attack"         then [:attack, [a["style"], a["target"]], {}]
        when "skill_strike"   then [:skill_strike, [a["skill"], a["target"]], {}]
        when "consider"       then [:consider, [a["target"]], {}]
        when "say"            then [:say_local, [a["mode"], a["text"]], {}]
        when "tell"           then [:say_targeted, [a["mode"], a["target"], a["text"]], {}]
        when "channel_say"    then [:say_channel, [a["channel"], a["text"]], {}]
        when "get_item"       then [:get, [a["item"]], { container: a["container"], count: a["count"] }]
        when "drop_item"      then [:drop, [a["mode"], a["item"]], { count: a["count"] }]
        when "put_item"       then [:put, [a["item"], a["container"]], { count: a["count"] }]
        when "equip_item"     then [:equip, [a["action"], a["item"]], { body_loc: a["body_loc"] }]
        when "consume_item"   then [:consume, [a["mode"], a["item"]], {}]
        when "cast_spell"     then [:cast, [a["spell"]], { target: a["target"] }]
        when "use_magic_item" then [:use_magic_item, [a["mode"], a["item"]], { target_args: a["target_args"] }]
        when "shop"           then [:shop, [a["action"]], { args: a["args"] }]
        when "practice"       then [:practice, [a["skill"]], {}]
        when "save_character" then [:save_char, [], {}]
        else
          # Unreachable via `call`, which checks ToolSpec first. Reachable if
          # someone adds a tool to ToolSpec and forgets this table — which is
          # the failure this method is shaped to make loud.
          raise Error.new("tool #{name.inspect} has no primitive mapping", code: "INTERNAL")
        end
      end
    end
  end
end
