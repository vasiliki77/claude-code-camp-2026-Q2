module MudManager
end

require_relative "mud_manager/version"
require_relative "mud_manager/primitives"
require_relative "mud_manager/session"

# The MCP/JSON-line daemon. Requiring it here means `gem install mud_manager`
# gives you both the library and the `mud-manager` binary's runtime with one
# require — which is the whole point of keeping this in one gem rather than two.
require_relative "mud_manager/mcp"
