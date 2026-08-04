require_relative "lib/mud_manager/version"

Gem::Specification.new do |spec|
  spec.name        = "mud_manager"
  spec.version     = MudManager::VERSION
  spec.summary     = "MudManager — CircleMUD sessions, command primitives, and an MCP daemon"
  spec.description = "Provides MudManager::Session (a long-lived telnet connection with " \
                     "background buffering and IAC stripping), MudManager::Primitives " \
                     "(a stateless library of typed CircleMUD command builders), and the " \
                     "`mud-manager` daemon, which owns the sessions and exposes them to " \
                     "agents in any language over stdio — as an MCP server (JSON-RPC 2.0) " \
                     "or a newline-delimited JSON protocol."
  spec.authors     = ["Andrew Brown"]
  spec.email       = ["andrew@exampro.co"]
  spec.license     = "MIT"

  spec.required_ruby_version = ">= 3.0"

  spec.files = Dir["lib/**/*.rb"] + ["bin/mud-manager", "primitives.json", "README.md"]

  # One `gem install` puts `mud-manager` on PATH. That is the promise that makes
  # the daemon usable by a Rust or Go bootcamper who has no Ruby toolchain and
  # should not need to acquire one.
  spec.bindir      = "bin"
  spec.executables = ["mud-manager"]

  # No external dependencies — socket, thread, json, open3 and yaml are stdlib.
end
