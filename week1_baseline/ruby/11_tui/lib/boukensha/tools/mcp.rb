require_relative "../mcp/client"

module Boukensha
  module Tools
    # Registers tools discovered from any MCP server.
    #
    # This module contains **no MUD knowledge**: no telnet, no primitives, no
    # login, not one tool name. It knows a command to spawn and it knows MCP.
    # Point it at a filesystem server, a GitHub server, or `mud-manager` and it
    # registers whatever that server advertises.
    #
    # Spawning a subprocess with a command, args and env is not coupling — it is
    # the MCP stdio transport's standard configuration shape, the same
    # `command`/`args`/`env` triple every MCP host uses. Passing credentials
    # through the server's environment is likewise the standard pattern: the
    # spec has no "send credentials over the wire" concept for stdio servers,
    # deliberately.
    #
    #   Boukensha::Tools::Mcp.register(
    #     registry,
    #     command: "mud-manager",
    #     args:    ["--mcp"],
    #     env:     { "MUD_HOST" => "localhost" },
    #     prefix:  "tbamud"
    #   )
    #
    # Returns the live client. The caller owns it and must close it; run/repl do
    # that in their ensure blocks.
    module Mcp
      # Raised when two servers advertise the same tool name.
      #
      # Registry#tool would otherwise let the second registration silently
      # clobber the first, which is a bug that would be maddening to debug: the
      # agent would call `search` and reach the wrong server, with nothing
      # anywhere saying so. Prefixing makes this unlikely, not impossible — two
      # entries can share a prefix — so the check stays regardless.
      class ToolCollisionError < StandardError; end

      # prefix: namespaces every registered name as "#{prefix}__#{name}".
      #
      # It is a property of the *server*, supplied by config, and applied
      # blindly here. This module must never know which prefix belongs to which
      # server — the moment it does, it stops being generic.
      #
      # label: only used in error messages, to name which server collided.
      def self.register(registry, command:, args: [], env: {}, prefix: nil, label: nil)
        # Fully qualified deliberately. Bare `Client` here resolves up the
        # lexical scope — Boukensha::Tools::Mcp → Boukensha::Tools → Boukensha —
        # and finds `Boukensha::Client`, the LLM API client. That silently
        # resolves to the wrong class rather than raising NameError.
        client = Boukensha::Mcp::Client.spawn(command: command, args: args, env: env)
        label ||= client.server_info["name"] || command.to_s

        client.tools.each { |tool| register_one(registry, client, tool, prefix, label) }

        client
      end

      def self.register_one(registry, client, tool, prefix, label)
        remote_name = tool["name"]
        local_name  = prefix.nil? || prefix.to_s.empty? ? remote_name : "#{prefix}__#{remote_name}"

        if (existing = registry.context.tools[local_name])
          raise ToolCollisionError,
                "tool #{local_name.inspect} from #{label} collides with one already registered " \
                "(#{existing.description.to_s[0, 60]}…). Give one of the servers a distinct " \
                "`prefix:` in mcp_servers."
        end

        registry.tool local_name,
                      description: tool["description"].to_s,
                      parameters: parameters_from(tool["inputSchema"] || {}) do |**args|
          # Drop nils rather than forwarding them: the server validates
          # arguments, and an explicit null reads as "provided but empty" where
          # the model meant "not provided".
          result = client.call_tool(remote_name, args.compact.transform_keys(&:to_s))

          # A failed tool call comes back as text, not an exception. The agent
          # loop feeds it straight to the model, which can then correct itself —
          # raising here would abort the run instead.
          result[:text]
        end
      end
      private_class_method :register_one

      # Translate a JSON Schema `inputSchema` into the shape Boukensha::Tool
      # wants: { name => { type:, description: } }.
      #
      # The schema's `required` list is discarded, because
      # `Backends::Anthropic#tools` (anthropic.rb:61) declares *every* parameter
      # required regardless of what is passed. Plumbing `required` through
      # `Boukensha::Tool` is the correct fix, but it changes all tools rather
      # than just MCP ones, so it belongs in its own plan. Harmless against our
      # own daemon, which treats blank strings as absent; it will bite against
      # third-party schemas with genuinely optional parameters.
      def self.parameters_from(schema)
        properties = schema["properties"] || {}

        properties.each_with_object({}) do |(name, prop), out|
          entry = { type: prop["type"] || "string", description: prop["description"].to_s }
          # Enums are the server's anti-drift guarantee — carry them through so
          # the model sees the same allowed values the server validates against.
          if (values = prop["enum"])
            entry[:enum] = values
            entry[:description] = "#{entry[:description]} (one of: #{values.join(', ')})".strip
          end
          out[name.to_sym] = entry
        end
      end
      private_class_method :parameters_from
    end
  end
end
