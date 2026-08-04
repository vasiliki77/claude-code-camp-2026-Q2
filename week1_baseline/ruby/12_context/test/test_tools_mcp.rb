require "minitest/autorun"

$LOAD_PATH.unshift File.expand_path("../lib", __dir__)

require "boukensha"
require "mud_manager/fake_mud"

# Boukensha as an MCP host.
#
# These spawn real MCP servers as subprocesses, so they exercise the actual
# thing: an agent framework that knows nothing about MUDs acquiring tools at
# runtime. No API key, no billing, no real MUD.
#
# Tool names carry the `tbamud` prefix here. That is a *client-side* policy —
# the daemon still advertises `look` on the wire. If a daemon test ever needs
# updating for the prefix, the prefix leaked across the boundary and that is a
# bug, not a rename.
class TestToolsMcp < Minitest::Test
  DAEMON = File.expand_path("../../../../week0_explore/mud_manager/bin/mud-manager", __dir__)
  CALCULATOR = File.expand_path("support/tiny_mcp_server.rb", __dir__)
  PASSWORD = "swordfish".freeze
  PREFIX = Boukensha::MUD_PREFIX # "tbamud"

  def setup
    skip "daemon not found at #{DAEMON}" unless File.exist?(DAEMON)
    @mud = MudManager::FakeMud.new(password: PASSWORD).start
    @ctx = Boukensha::Context.new(task: Boukensha::Tasks::Player, system: "")
    @registry = Boukensha::Registry.new(@ctx)
    @clients = []
  end

  def teardown
    @clients.each { |c| c.close rescue nil }
    @mud&.stop
  end

  def register_mud(prefix: PREFIX)
    client = Boukensha::Tools::Mcp.register(
      @registry,
      command: RbConfig.ruby,
      args: [DAEMON, "--mcp"],
      env: {
        "MUD_HOST" => "127.0.0.1",
        "MUD_PORT" => @mud.port.to_s,
        "MUD_NAME" => "Gandalf",
        "MUD_PASSWORD" => PASSWORD,
        "BOUKENSHA_DIR" => ""
      },
      prefix: prefix,
      label: "mud"
    )
    @clients << client
    client
  end

  def register_calculator(prefix: "calc")
    client = Boukensha::Tools::Mcp.register(
      @registry, command: RbConfig.ruby, args: [CALCULATOR], prefix: prefix, label: "calc"
    )
    @clients << client
    client
  end

  # ---------- generic host behaviour ----------------------------------------

  def test_registers_a_non_mud_server
    # The point of the whole refactor: Tools::Mcp has no MUD knowledge. Proven
    # by demonstration rather than assertion — if MUD assumptions creep back in,
    # this fails loudly.
    register_calculator

    assert_equal %w[calc__add calc__shout], @ctx.tools.keys.sort
    assert_equal "42.0", @registry.dispatch("calc__add", { "a" => 2, "b" => 40 })
    assert_equal "HELLO", @registry.dispatch("calc__shout", { "text" => "hello" })
  end

  def test_two_servers_coexist
    register_mud
    register_calculator

    assert @ctx.tools.key?("#{PREFIX}__look")
    assert @ctx.tools.key?("calc__add")
    assert_equal 28, @ctx.tools.length # 26 MUD + 2 calculator
  end

  def test_collision_raises_and_names_the_server
    # Registry#tool would silently clobber. Prefixing makes collisions unlikely,
    # not impossible — two entries can share a prefix — so the check stays.
    register_calculator(prefix: "dup")

    err = assert_raises(Boukensha::Tools::Mcp::ToolCollisionError) do
      register_calculator(prefix: "dup")
    end

    assert_match(/dup__add/, err.message)
    assert_match(/prefix/, err.message)
  end

  def test_bare_names_still_work
    # Proves prefixing is a policy, not baked in.
    register_calculator(prefix: nil)

    assert @ctx.tools.key?("add")
    refute @ctx.tools.key?("calc__add")
  end

  def test_a_failing_server_raises_by_default
    # required: true is the default, and Tools::Mcp itself always raises —
    # the required/optional decision belongs to the caller, not here.
    assert_raises(StandardError) do
      Boukensha::Tools::Mcp.register(@registry, command: "/nonexistent/server")
    end

    assert_empty @ctx.tools
  end

  # ---------- the MUD server over MCP ---------------------------------------

  def test_registers_every_advertised_tool
    register_mud

    assert_equal 26, @ctx.tools.length
    assert @ctx.tools.key?("#{PREFIX}__look")
    assert @ctx.tools.key?("#{PREFIX}__cast_spell")
  end

  def test_registered_tools_dispatch_through_the_registry
    register_mud

    text = @registry.dispatch("#{PREFIX}__move", { "direction" => "north" })

    # Behaviour assertion — must pass untouched. Only the label moved.
    assert_match(/You north/, text)
    assert_includes @mud.commands, "north"
  end

  def test_the_daemon_still_sees_bare_names
    # The prefix is client-side. The wire is unchanged.
    client = register_mud

    assert_includes client.tools.map { |t| t["name"] }, "look"
    refute_includes client.tools.map { |t| t["name"] }, "#{PREFIX}__look"
  end

  def test_schemas_carry_the_enums_from_the_server
    register_mud

    move = @ctx.tools["#{PREFIX}__move"]
    assert_equal MudManager::Primitives::DIRECTIONS, move.parameters[:direction][:enum]
    assert_match(/one of: north/, move.parameters[:direction][:description])
  end

  def test_tool_failure_returns_text_rather_than_raising
    register_mud

    text = @registry.dispatch("#{PREFIX}__move", { "direction" => "widdershins" })

    assert_match(/INVALID_ARGUMENTS/, text)
  end

  def test_one_login_serves_many_tool_calls
    register_mud

    @registry.dispatch("#{PREFIX}__look", {})
    @registry.dispatch("#{PREFIX}__move", { "direction" => "east" })
    @registry.dispatch("#{PREFIX}__check", { "kind" => "score" })

    assert_equal 1, @mud.logins
  end
end
