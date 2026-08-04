#!/usr/bin/env ruby
# frozen_string_literal: true
#
# Step 10 — the MUD tools again, but over MCP.
#
# `examples/example.rb` links MudManager into this process: Tools::Mud holds a
# MudManager::Session in a closure and every tool call drives it directly.
#
# This demo gets the same 26 tools from a *separate process*. Boukensha spawns
# `mud-manager --mcp`, asks it what tools it has, and registers whatever comes
# back. Nothing in boukensha knows what a MUD is.
#
#   ruby examples/mcp_mud_demo.rb --dry    # no API calls, no billing
#   ruby examples/mcp_mud_demo.rb          # real agent run (billable)
#
# By default it boots a FakeMud on a random port so the demo runs with no MUD
# installed. Set MUD_HOST/MUD_PORT/MUD_NAME/MUD_PASSWORD to point at a real one.

$LOAD_PATH.unshift File.expand_path("../lib", __dir__)
require "boukensha"
require "mud_manager/fake_mud"

DRY = ARGV.include?("--dry")

DAEMON = File.expand_path(
  "../../../../week0_explore/mud_manager/bin/mud-manager", __dir__
)

abort "daemon not found at #{DAEMON}" unless File.exist?(DAEMON)

# ── A MUD to talk to ────────────────────────────────────────────────────────
# Only started if the user has not pointed us at a real server.
fake = nil
unless ENV["MUD_HOST"]
  fake = MudManager::FakeMud.new(password: "swordfish").start
  ENV["MUD_HOST"]     = "127.0.0.1"
  ENV["MUD_PORT"]     = fake.port.to_s
  ENV["MUD_NAME"]     = "Gandalf"
  ENV["MUD_PASSWORD"] = "swordfish"
  puts "Started FakeMud on 127.0.0.1:#{fake.port}"
end

mcp = {
  # RbConfig.ruby rather than a bare path: the daemon must run under the same
  # interpreter as this process, not whatever `ruby` resolves to on PATH.
  command: RbConfig.ruby,
  args:    [DAEMON, "--mcp"],
  # Named after the MUD engine, not the config key. Applied client-side —
  # the daemon still advertises bare `look` on the wire.
  prefix:  Boukensha::MUD_PREFIX,
  env: {
    "MUD_HOST"     => ENV["MUD_HOST"],
    "MUD_PORT"     => ENV["MUD_PORT"],
    "MUD_NAME"     => ENV["MUD_NAME"],
    "MUD_PASSWORD" => ENV["MUD_PASSWORD"]
  }
}

begin
  if DRY
    # Register into a throwaway context so we can show the tool surface without
    # touching a model. This is the part of the feature that does not depend on
    # the non-deterministic dependency, so it is the part worth gating on.
    ctx      = Boukensha::Context.new(task: Boukensha::Tasks::Player, system: "")
    registry = Boukensha::Registry.new(ctx)

    client = Boukensha::Tools::Mcp.register(registry, **mcp)
    abort "daemon did not start" unless client

    puts "Daemon:  #{client.server_info['name']} #{client.server_info['version']}"
    puts "Tools:   #{ctx.tools.length}"
    puts
    ctx.tools.keys.each_slice(6) { |row| puts "  #{row.join(', ')}" }
    puts

    # Drive tools through the registry, under their prefixed names, bypassing
    # the model entirely. call_tool returns { text:, error: } — a failed tool
    # call is a normal result, not an exception.
    p = Boukensha::MUD_PREFIX
    puts "#{p}__look -> #{registry.dispatch("#{p}__look", {}).lines.first.to_s.strip}"
    puts "#{p}__move -> #{registry.dispatch("#{p}__move", { 'direction' => 'north' }).lines.first.to_s.strip}"
    puts "bad arg   -> #{registry.dispatch("#{p}__move", { 'direction' => 'widdershins' }).strip}"

    client.close
    puts
    puts "[dry run OK — #{ctx.tools.length} tools over MCP, no API calls made]"
  else
    puts Boukensha.run(
      task: "Look at your surroundings, check your score, then tell me what you see.",
      working_dir: false,  # no filesystem tools
      mud: false,          # the in-process path is off — everything comes over MCP
      mcp: mcp
    )
  end
ensure
  fake&.stop
end
