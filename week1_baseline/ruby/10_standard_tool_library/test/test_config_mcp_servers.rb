require "minitest/autorun"
require "tmpdir"
require "yaml"

$LOAD_PATH.unshift File.expand_path("../lib", __dir__)

require "boukensha"

# Config#mcp_servers — servers as data, not code.
class TestConfigMcpServers < Minitest::Test
  def with_settings(hash)
    Dir.mktmpdir do |dir|
      File.write(File.join(dir, "settings.yaml"), YAML.dump(hash))
      previous = ENV["BOUKENSHA_DIR"]
      ENV["BOUKENSHA_DIR"] = dir
      begin
        yield Boukensha::Config.new
      ensure
        ENV["BOUKENSHA_DIR"] = previous
      end
    end
  end

  def test_absent_block_is_empty_not_nil
    with_settings({ "tasks" => {} }) do |cfg|
      assert_equal({}, cfg.mcp_servers)
    end
  end

  def test_parses_a_full_entry
    with_settings({
      "mcp_servers" => {
        "mud" => {
          "command" => "mud-manager",
          "args" => ["--mcp"],
          "prefix" => "tbamud",
          "env" => { "MUD_HOST" => "localhost", "MUD_PORT" => 4000 }
        }
      }
    }) do |cfg|
      entry = cfg.mcp_servers["mud"]

      assert_equal "mud-manager", entry[:command]
      assert_equal ["--mcp"], entry[:args]
      assert_equal "tbamud", entry[:prefix]
      # Env values are stringified — a YAML integer port would otherwise reach
      # Open3 as an Integer and blow up on spawn.
      assert_equal({ "MUD_HOST" => "localhost", "MUD_PORT" => "4000" }, entry[:env])
    end
  end

  def test_defaults
    with_settings({ "mcp_servers" => { "bare" => { "command" => "thing" } } }) do |cfg|
      entry = cfg.mcp_servers["bare"]

      assert_equal [], entry[:args]
      assert_equal({}, entry[:env])
      assert_nil entry[:prefix]
      # A server you bothered to configure and which then fails is a problem you
      # want to hear about, so required defaults to true.
      assert_equal true, entry[:required]
    end
  end

  def test_required_can_be_turned_off
    with_settings({
      "mcp_servers" => { "decor" => { "command" => "thing", "required" => false } }
    }) do |cfg|
      assert_equal false, cfg.mcp_servers["decor"][:required]
    end
  end

  def test_malformed_entries_do_not_raise
    # A half-written config should surface as "no command" at registration, not
    # as a parse crash before the agent even starts.
    with_settings({ "mcp_servers" => { "broken" => nil, "alsobroken" => "nonsense" } }) do |cfg|
      assert_nil cfg.mcp_servers["broken"][:command]
      assert_nil cfg.mcp_servers["alsobroken"][:command]
    end
  end

  def test_multiple_servers
    with_settings({
      "mcp_servers" => {
        "mud" => { "command" => "mud-manager", "args" => ["--mcp"] },
        "filesystem" => { "command" => "npx", "args" => ["-y", "server-filesystem", "/tmp"] }
      }
    }) do |cfg|
      assert_equal %w[filesystem mud], cfg.mcp_servers.keys.sort
    end
  end
end
