require "json"
require_relative "helper"

# primitives.json is the artifact five language tracks generate code from.
# A silent change here breaks people who are not in this repository.
class TestSpec < Minitest::Test
  Spec = MudManager::Mcp::Spec

  def setup
    @doc = JSON.parse(Spec.to_json_text)
  end

  def test_checked_in_file_matches_what_the_generator_produces
    on_disk = File.read(Spec.default_path)

    assert_equal Spec.to_json_text, on_disk,
                 "primitives.json is stale — regenerate with `mud-manager --write-spec`. " \
                 "It is generated, never hand-edited (open-Q #4: Ruby is canonical)."
  end

  def test_carries_the_gem_version
    assert_equal MudManager::VERSION, @doc["version"]
  end

  def test_declares_its_own_provenance
    assert_match(/Ruby is canonical/, @doc["$schema_note"])
  end

  def test_describes_every_served_tool
    assert_equal MudManager::Mcp::ToolSpec.tool_names, @doc["tools"].map { |t| t["name"] }
  end

  def test_enums_survive_into_the_neutral_spec
    # A Go track generating typed builders from this file must get the same
    # allowed values Ruby validates against — that is the whole anti-drift claim.
    move = @doc["tools"].find { |t| t["name"] == "move" }

    assert_equal MudManager::Primitives::DIRECTIONS,
                 move["args"]["direction"]["enum"]
  end

  def test_records_which_primitive_backs_each_tool
    look = @doc["tools"].find { |t| t["name"] == "look" }
    raw  = @doc["tools"].find { |t| t["name"] == "send_raw" }

    assert_equal "look", look["primitive"]
    # send_raw and the session tools deliberately bypass Primitives.
    assert_nil raw["primitive"]
  end
end
