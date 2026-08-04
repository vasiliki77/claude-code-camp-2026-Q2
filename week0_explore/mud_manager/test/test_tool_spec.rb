require_relative "helper"

# The tool surface is the daemon's public contract — five language tracks
# generate against it. These assertions are deliberately about *shape and
# provenance*, not about any one tool's wording.
class TestToolSpec < Minitest::Test
  Spec = MudManager::Mcp::ToolSpec

  def test_serves_the_plan_s_tool_surface
    # Plan §6 lists 24 gameplay tools; poll (open-Q #2) and mud_status bring it
    # to 26. A change here is a change to what every track sees.
    assert_equal 26, Spec.tools.length
  end

  def test_lifecycle_tools_are_not_exposed
    # Plan §5: connect/login/disconnect are framework concerns handled inside
    # SessionPool. Exposing them to an LLM is the mistake this design avoids.
    %w[connect login disconnect mud_connect mud_disconnect].each do |name|
      assert_nil Spec.find(name), "#{name} must not be an LLM-facing tool"
    end
  end

  def test_enums_are_read_from_primitives_at_call_time
    # This is the anti-drift guarantee: Ruby is canonical (open-Q #4), so a new
    # direction in Primitives must appear in the served schema with no second
    # edit anywhere.
    original = MudManager::Primitives::DIRECTIONS

    begin
      MudManager::Primitives.send(:remove_const, :DIRECTIONS)
      MudManager::Primitives.const_set(:DIRECTIONS, %w[north east south west up down starboard].freeze)

      move = Spec.find("move")
      assert_includes move["args"]["direction"]["enum"], "starboard"
    ensure
      MudManager::Primitives.send(:remove_const, :DIRECTIONS)
      MudManager::Primitives.const_set(:DIRECTIONS, original)
    end

    refute_includes Spec.find("move")["args"]["direction"]["enum"], "starboard"
  end

  def test_mcp_rendering_marks_required_arguments
    attack = Spec.mcp_tools.find { |t| t["name"] == "attack" }

    assert_equal %w[target], attack["inputSchema"]["required"]
    # style has a default, so it is optional but still enum-constrained.
    assert_equal "kill", attack["inputSchema"]["properties"]["style"]["default"]
    assert_equal MudManager::Primitives::ATTACK_STYLES,
                 attack["inputSchema"]["properties"]["style"]["enum"]
  end

  def test_tools_with_no_arguments_omit_required
    flee = Spec.mcp_tools.find { |t| t["name"] == "flee" }

    refute flee["inputSchema"].key?("required"),
           "an empty required array is meaningful to some clients; omit the key instead"
    assert_empty flee["inputSchema"]["properties"]
  end

  def test_every_tool_has_a_description
    Spec.tools.each do |tool|
      refute_nil tool["description"]
      refute tool["description"].strip.empty?, "#{tool['name']} has a blank description"
    end
  end
end
