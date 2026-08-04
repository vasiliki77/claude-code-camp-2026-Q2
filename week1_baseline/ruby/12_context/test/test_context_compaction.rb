require "minitest/autorun"

$LOAD_PATH.unshift File.expand_path("../lib", __dir__)

require "boukensha"

# Context — token accounting and compaction.
#
# Every assertion here is free: no API key, no MUD, no network. That matters
# because compaction is the one step-12 behaviour that only fires deep into a
# long session, which is the worst possible place to discover it is wrong.
class TestContextCompaction < Minitest::Test
  def ctx(window: 1000, threshold: 0.85)
    Boukensha::Context.new(system: "s", context_window: window, compaction_threshold: threshold)
  end

  # A history of complete tool pairs, oldest first:
  #   user, assistant(tool_use), tool_result, user, assistant(tool_use), ...
  def with_tool_pairs(context, pairs)
    pairs.times do |i|
      context.add_message(:user, "turn #{i}")
      context.add_message(:assistant, [{ "type" => "tool_use", "id" => "t#{i}", "name" => "look", "input" => {} }])
      context.add_message(:tool_result, "result #{i}", tool_use_id: "t#{i}")
    end
    context
  end

  # ---------- token accounting -------------------------------------------

  def test_usage_fraction_and_pct
    c = ctx(window: 1000)
    c.update_tokens(250)

    assert_in_delta 0.25, c.usage_fraction, 0.0001
    assert_equal 25, c.usage_pct
  end

  def test_usage_fraction_survives_a_zero_window
    c = ctx(window: 0)
    c.update_tokens(500)

    assert_equal 0.0, c.usage_fraction
    assert_equal 0, c.usage_pct
  end

  def test_turn_tokens_accumulate_and_reset
    c = ctx
    c.add_turn_tokens(100, 50)
    c.add_turn_tokens(200, 25)

    assert_equal 375, c.turn_tokens

    c.reset_turn_tokens

    assert_equal 0, c.turn_tokens
  end

  def test_turn_tokens_tolerate_nil_counts
    c = ctx
    c.add_turn_tokens(nil, nil)

    assert_equal 0, c.turn_tokens
  end

  # ---------- the trigger --------------------------------------------------

  def test_needs_compaction_at_the_boundary
    c = ctx(window: 1000, threshold: 0.85)

    c.update_tokens(849)
    refute_predicate c, :needs_compaction?

    c.update_tokens(850)
    assert_predicate c, :needs_compaction?
  end

  def test_threshold_can_be_overridden_per_call
    c = ctx(window: 1000, threshold: 0.85)
    c.update_tokens(500)

    assert c.needs_compaction?(threshold: 0.4)
  end

  # ---------- compaction ---------------------------------------------------

  def test_drops_roughly_the_oldest_forty_percent
    c = with_tool_pairs(ctx, 10)   # 30 messages
    before = c.messages.size

    dropped = c.compact_messages!

    assert_operator dropped, :>=, 12
    assert_equal before - dropped, c.messages.size
  end

  def test_resets_current_tokens_so_the_next_response_reports_the_truth
    c = with_tool_pairs(ctx, 10)
    c.update_tokens(900)

    c.compact_messages!

    assert_equal 0, c.current_tokens
  end

  def test_keeps_at_least_two_messages
    c = ctx
    c.add_message(:user, "a")
    c.add_message(:assistant, "b")

    assert_equal 0, c.compact_messages!
    assert_equal 2, c.messages.size
  end

  # The invariant the drop point is snapped for. Dropping purely by count
  # orphans a tool_result whose tool_use went with it, which Anthropic answers
  # with a 400 — and with the MUD tools registered, tool pairs are most of the
  # history, so an unsnapped drop lands mid-pair more often than not.
  def test_never_orphans_a_tool_result
    1.upto(20) do |pairs|
      c = with_tool_pairs(ctx, pairs)
      c.compact_messages!

      live_ids = c.messages
                  .select { |m| m.role == :assistant && m.content.is_a?(Array) }
                  .flat_map { |m| m.content.select { |b| b["type"] == "tool_use" }.map { |b| b["id"] } }

      c.messages.select { |m| m.role == :tool_result }.each do |result|
        assert_includes live_ids, result.tool_use_id,
                        "orphaned tool_result after compacting #{pairs} pairs"
      end
    end
  end

  def test_surviving_history_always_opens_on_a_user_turn
    1.upto(20) do |pairs|
      c = with_tool_pairs(ctx, pairs)
      c.compact_messages!

      next if c.messages.empty?

      assert_equal :user, c.messages.first.role,
                   "history opened on #{c.messages.first.role} after compacting #{pairs} pairs"
    end
  end

  def test_clear_messages_also_zeroes_the_gauge
    c = with_tool_pairs(ctx, 3)
    c.update_tokens(700)

    c.clear_messages!

    assert_empty c.messages
    assert_equal 0, c.current_tokens
  end
end
