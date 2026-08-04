require_relative "version"
require_relative "session"
require_relative "primitives"

require_relative "mcp/errors"
require_relative "mcp/config"
require_relative "mcp/tool_spec"
require_relative "mcp/session_pool"
require_relative "mcp/dispatcher"
require_relative "mcp/spec"
require_relative "mcp/json_line_server"
require_relative "mcp/server"
require_relative "mcp/client"

module MudManager
  # The daemon half of the gem.
  #
  # `MudManager::Session` and `MudManager::Primitives` are the domain — a
  # stateful telnet connection and a table of command builders. `MudManager::Mcp`
  # is one *interface* over that domain: a long-lived process that owns the
  # sessions and exposes them to any language over stdio.
  #
  # The namespace boundary is the lesson (plan §1: nobody should reimplement
  # `Session`, everybody can regenerate `Primitives`). It is expressed as a
  # namespace rather than a second gem on purpose — a bootcamper on the Go track
  # should run one `gem install` and get a working binary, not resolve a
  # version-locked pair.
  module Mcp
    module_function

    # Build a dispatcher over a fresh pool. Both servers take one of these.
    def dispatcher(config = Config.new)
      Dispatcher.new(SessionPool.new(config))
    end
  end
end
