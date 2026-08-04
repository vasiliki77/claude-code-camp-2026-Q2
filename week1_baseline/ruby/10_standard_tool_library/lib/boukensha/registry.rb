require_relative "errors"

module Boukensha
  class Registry
    # Exposed so a caller can ask what is already registered before registering.
    # Tools::Mcp needs this to detect name collisions between MCP servers —
    # #tool would otherwise let a second registration silently clobber a first.
    attr_reader :context

    def initialize(context)
      @context = context
    end

    def tool(name, description:, parameters: {}, &block)
      tool = Tool.new(name.to_s, description, parameters, block)
      @context.register_tool(tool)
      tool
    end

    def dispatch(name, args = {})
      tool = @context.tools[name.to_s]
      raise UnknownToolError, "No tool registered as '#{name}'" unless tool
      tool.block.call(**args.transform_keys(&:to_sym))
    end
  end
end