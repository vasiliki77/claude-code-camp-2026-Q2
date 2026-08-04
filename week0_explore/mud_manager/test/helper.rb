require "minitest/autorun"

$LOAD_PATH.unshift File.expand_path("../lib", __dir__)

require "mud_manager"
require "mud_manager/fake_mud"

module DaemonTest
  PASSWORD = "swordfish".freeze
  NAME = "Gandalf".freeze

  # Boot a FakeMud and a dispatcher wired to it, run the block, tear both down.
  # Credentials are passed explicitly rather than through ENV so tests never
  # depend on (or clobber) the developer's real MUD settings.
  def with_daemon(responses: {})
    mud = MudManager::FakeMud.new(password: PASSWORD, responses: responses).start
    config = MudManager::Mcp::Config.new(
      host: "127.0.0.1",
      port: mud.port,
      name: NAME,
      password: PASSWORD,
      timeout: 3.0,
      settings: {} # ignore any settings.yaml on this machine
    )
    dispatcher = MudManager::Mcp.dispatcher(config)

    yield mud, dispatcher
  ensure
    dispatcher&.pool&.close_all
    mud&.stop
  end

  # The command the MUD actually received, ignoring login traffic.
  def gameplay_commands(mud)
    mud.commands.reject { |c| c.empty? || c == "1" }
  end
end
