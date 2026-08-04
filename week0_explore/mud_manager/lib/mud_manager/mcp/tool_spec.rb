require_relative "../primitives"

module MudManager
  module Mcp
    # The single source of truth for the daemon's tool surface.
    #
    # Plan §4.4 wanted a language-neutral `primitives.json`; open-Q #4's answer
    # settled which side is canonical: **Ruby is**. So this file is the origin
    # and `primitives.json` is *generated* from it (see `Spec`), never
    # hand-edited. That direction matters — the enums below are read from
    # `MudManager::Primitives` constants **at call time**, so adding a direction
    # or a channel to the domain module changes the served tool schemas on the
    # next start with no second edit and no drift.
    #
    # The surface is plan §6: the same tools `Boukensha::Tools::Mud` already
    # registers, which makes this a repackaging rather than a redesign. What
    # moves is the `drain -> send_command -> read_until_prompt` round trip,
    # which now lives in the daemon so every language inherits it.
    #
    # Deliberately absent (plan §5): `connect`, `login`, `disconnect`. Session
    # lifecycle is a framework concern handled internally by SessionPool, and
    # exposing it as LLM-callable tools is wasteful and error-prone. The LLM
    # sees gameplay only.
    module ToolSpec
      module_function

      # Built fresh on every call so Primitives stays canonical. Do not memoize.
      def tools
        p = MudManager::Primitives

        [
          # ── Perception ────────────────────────────────────────────────────
          {
            "name" => "look",
            "primitive" => "look",
            "group" => "perception",
            "description" =>
              "Look at the current room or at a specific target. Call with NO arguments to " \
              "describe the current room (do NOT pass target: 'room'). Pass a target to inspect " \
              "a specific item, mob, or player. Use preposition 'in' to look inside a container, " \
              "'at' to inspect something, or a direction to peek into an adjacent room.",
            "args" => {
              "target" => arg("string", "Item, mob, or player to inspect. Omit entirely to describe the current room."),
              "preposition" => arg("string", "Where to look", enum: p::LOOK_PREPS)
            }
          },
          {
            "name" => "examine",
            "primitive" => "examine",
            "group" => "perception",
            "description" => "Examine a target in detail (more verbose than look).",
            "args" => {
              "target" => arg("string", "The item, mob, or player to examine", required: true)
            }
          },
          {
            "name" => "check",
            "primitive" => "info_self",
            "group" => "perception",
            "description" => "Query information about your character or surroundings.",
            "args" => {
              "kind" => arg("string", "What to check", enum: p::INFO_SELF, required: true)
            }
          },

          # ── Movement ──────────────────────────────────────────────────────
          {
            "name" => "move",
            "primitive" => "move",
            "group" => "movement",
            "description" => "Move one step in a compass direction, or up/down.",
            "args" => {
              "direction" => arg("string", "Direction to move", enum: p::DIRECTIONS, required: true)
            }
          },
          {
            "name" => "flee",
            "primitive" => "flee",
            "group" => "movement",
            "description" => "Attempt to flee from combat in a random available direction.",
            "args" => {}
          },
          {
            "name" => "set_position",
            "primitive" => "set_position",
            "group" => "movement",
            "description" =>
              "Change body position. Use 'rest' or 'sleep' between fights to recover HP and " \
              "mana. You must be standing to move or fight.",
            "args" => {
              "position" => arg("string", "Body position", enum: p::POSITIONS, required: true)
            }
          },
          {
            "name" => "track",
            "primitive" => "track",
            "group" => "movement",
            "description" =>
              "Attempt to track a mob or player by name, revealing which direction they are " \
              "in. Requires the Track skill.",
            "args" => {
              "target" => arg("string", "Name of the mob or player to track", required: true)
            }
          },

          # ── Combat ────────────────────────────────────────────────────────
          {
            "name" => "attack",
            "primitive" => "attack",
            "group" => "combat",
            "description" =>
              "Attack a target. Style 'kill' is the standard approach; 'murder' bypasses the " \
              "mercy check; 'hit' is a one-off strike.",
            "args" => {
              "target" => arg("string", "Name of the mob or player to attack", required: true),
              "style" => arg("string", "Attack style", enum: p::ATTACK_STYLES, default: "kill")
            }
          },
          {
            "name" => "skill_strike",
            "primitive" => "skill_strike",
            "group" => "combat",
            "description" => "Use a combat skill against a target.",
            "args" => {
              "skill" => arg("string", "Combat skill to use", enum: p::STRIKE_SKILLS, required: true),
              "target" => arg("string", "Name of the mob or player", required: true)
            }
          },
          {
            "name" => "consider",
            "primitive" => "consider",
            "group" => "combat",
            "description" =>
              "Assess a mob's relative strength before engaging. Returns a phrase such as " \
              "'You could kill it easily' or 'Death awaits you'. Always consider before " \
              "attacking an unknown mob.",
            "args" => {
              "target" => arg("string", "Name of the mob to consider", required: true)
            }
          },

          # ── Communication ─────────────────────────────────────────────────
          {
            "name" => "say",
            "primitive" => "say_local",
            "group" => "communication",
            "description" => "Speak or emote in the current room.",
            "args" => {
              "text" => arg("string", "What to say or emote", required: true),
              "mode" => arg("string", "How to speak", enum: p::LOCAL_SAY, default: "say")
            }
          },
          {
            "name" => "tell",
            "primitive" => "say_targeted",
            "group" => "communication",
            "description" => "Send a private message to a specific player.",
            "args" => {
              "target" => arg("string", "Player name to message", required: true),
              "text" => arg("string", "The message", required: true),
              "mode" => arg("string", "How to address them", enum: p::TARGETED_SAY, default: "tell")
            }
          },
          {
            "name" => "channel_say",
            "primitive" => "say_channel",
            "group" => "communication",
            "description" => "Broadcast a message over a global channel.",
            "args" => {
              "channel" => arg("string", "Channel to broadcast on", enum: p::CHANNELS, required: true),
              "text" => arg("string", "The message to broadcast", required: true)
            }
          },

          # ── Inventory & equipment ─────────────────────────────────────────
          {
            "name" => "get_item",
            "primitive" => "get",
            "group" => "inventory",
            "description" => "Pick up an item from the room or from a container.",
            "args" => {
              "item" => arg("string", "Name of the item to get", required: true),
              "container" => arg("string", "Container to get it from"),
              "count" => arg("integer", "Number of items to get")
            }
          },
          {
            "name" => "drop_item",
            "primitive" => "drop",
            "group" => "inventory",
            "description" => "Drop, donate, or junk an item.",
            "args" => {
              "item" => arg("string", "Name of the item", required: true),
              "mode" => arg("string", "How to dispose of it", enum: p::DROP_MODES, default: "drop"),
              "count" => arg("integer", "Number of items")
            }
          },
          {
            "name" => "put_item",
            "primitive" => "put",
            "group" => "inventory",
            "description" => "Put an item into a container.",
            "args" => {
              "item" => arg("string", "Name of the item to put", required: true),
              "container" => arg("string", "Name of the container", required: true),
              "count" => arg("integer", "Number of items")
            }
          },
          {
            "name" => "equip_item",
            "primitive" => "equip",
            "group" => "inventory",
            "description" => "Wear, wield, hold, grab, or remove an item.",
            "args" => {
              "item" => arg("string", "Name of the item", required: true),
              "action" => arg("string", "What to do with it", enum: p::EQUIP_OPS, required: true),
              "body_loc" => arg("string", "Body location to wear it on, e.g. 'head', 'finger'")
            }
          },
          {
            "name" => "consume_item",
            "primitive" => "consume",
            "group" => "inventory",
            "description" => "Eat, drink, taste, or sip a consumable item.",
            "args" => {
              "item" => arg("string", "Name of the item to consume", required: true),
              "mode" => arg("string", "How to consume it", enum: p::CONSUME_MODES, default: "eat")
            }
          },

          # ── Magic ─────────────────────────────────────────────────────────
          {
            "name" => "cast_spell",
            "primitive" => "cast",
            "group" => "magic",
            "description" =>
              "Cast a spell, optionally at a target. Use the full spell name, e.g. " \
              "'cure light wounds' or 'magic missile'.",
            "args" => {
              "spell" => arg("string", "Full spell name", required: true),
              "target" => arg("string", "Target mob, player, or object")
            }
          },
          {
            "name" => "use_magic_item",
            "primitive" => "use_magic_item",
            "group" => "magic",
            "description" => "Activate a magic item: quaff a potion, recite a scroll, or use a wand/staff.",
            "args" => {
              "item" => arg("string", "Name of the item to activate", required: true),
              "mode" => arg("string", "How to activate it", enum: p::SPELL_ITEM, required: true),
              "target_args" => arg("string", "Optional target arguments, e.g. a mob name for a wand")
            }
          },

          # ── Utility ───────────────────────────────────────────────────────
          {
            "name" => "shop",
            "primitive" => "shop",
            "group" => "utility",
            "description" => "Interact with a shop NPC: list stock, buy, sell, or value an item.",
            "args" => {
              "action" => arg("string", "Shop action", enum: p::SHOP_OPS, required: true),
              "args" => arg("string", "Item name or number")
            }
          },
          {
            "name" => "practice",
            "primitive" => "practice",
            "group" => "utility",
            "description" => "List your known skills at a guildmaster, or practice a specific skill.",
            "args" => {
              "skill" => arg("string", "Skill name to practice. Omit to list all.")
            }
          },
          {
            "name" => "save_character",
            "primitive" => "save_char",
            "group" => "utility",
            "description" => "Save your character to disk so progress is not lost on disconnect.",
            "args" => {}
          },
          {
            "name" => "send_raw",
            "primitive" => nil, # bypasses Primitives entirely — that is the point
            "group" => "utility",
            "description" =>
              "Send an arbitrary command string to the MUD and return the response. Use this " \
              "as an escape hatch when no structured tool fits, e.g. 'who' or 'help backstab'.",
            "args" => {
              "command" => arg("string", "The raw command to send", required: true)
            }
          },

          # ── Session-aware, non-gameplay ───────────────────────────────────
          # `poll` is open-Q #2's answer: async chatter (combat ticks, other
          # players) that arrives while the agent is idle would otherwise only
          # surface folded into the *next* command's response. Server-initiated
          # MCP notifications would be the richer fix; poll is the simpler one
          # and the plan says start here.
          {
            "name" => "poll",
            "primitive" => nil,
            "group" => "session",
            "description" =>
              "Collect any unsolicited output that has arrived since the last command — " \
              "combat rounds, other players talking, weather. Returns an empty string if " \
              "nothing happened. Call this when idle or waiting for something to occur.",
            "args" => {
              "timeout" => arg("number", "Seconds to wait for output before giving up. Default 0 (return immediately).")
            }
          },
          {
            "name" => "mud_status",
            "primitive" => nil,
            "group" => "session",
            "description" =>
              "Report whether the MUD session is currently connected, and to what. Connection " \
              "is automatic — you do not need to connect or log in yourself.",
            "args" => {}
          }
        ]
      end

      def tool_names
        tools.map { |t| t["name"] }
      end

      def find(name)
        tools.find { |t| t["name"] == name.to_s }
      end

      # An argument descriptor. `required` and `default` are mutually
      # exclusive in practice: a defaulted argument is by definition optional.
      def arg(type, description, enum: nil, required: false, default: nil)
        spec = { "type" => type, "description" => description }
        spec["enum"] = enum.to_a if enum
        spec["required"] = true if required
        spec["default"] = default unless default.nil?
        spec
      end

      # Render one tool as an MCP tool definition (JSON Schema input_schema).
      def to_mcp(tool)
        properties = {}
        required = []

        tool["args"].each do |name, spec|
          prop = { "type" => spec["type"], "description" => spec["description"] }
          prop["enum"] = spec["enum"] if spec["enum"]
          prop["default"] = spec["default"] if spec.key?("default")
          properties[name] = prop
          required << name if spec["required"]
        end

        schema = { "type" => "object", "properties" => properties }
        # Omit an empty `required` rather than emitting `[]` — some clients
        # treat the presence of the key as meaningful.
        schema["required"] = required unless required.empty?

        { "name" => tool["name"], "description" => tool["description"], "inputSchema" => schema }
      end

      def mcp_tools
        tools.map { |t| to_mcp(t) }
      end
    end
  end
end
