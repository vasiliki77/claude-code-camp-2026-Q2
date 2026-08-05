import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boukensha  # noqa: E402


class ContextTestCase(unittest.TestCase):
    """Context — token accounting and compaction.

    Every assertion here is free: no API key, no MUD, no network. That matters
    because compaction is the one step-12 behaviour that fires only deep into a
    long session, which is the worst possible place to discover it is wrong.
    """

    def ctx(self, window=1000, threshold=0.85):
        return boukensha.Context(
            task=boukensha.Player,
            system="s",
            context_window=window,
            compaction_threshold=threshold,
        )

    # A history of complete tool pairs, oldest first:
    #   user, assistant(tool_use), tool_result, user, assistant(tool_use), ...
    def with_tool_pairs(self, context, pairs):
        for i in range(pairs):
            context.add_message("user", f"turn {i}")
            context.add_message(
                "assistant",
                [{"type": "tool_use", "id": f"t{i}", "name": "look", "input": {}}],
            )
            context.add_message("tool_result", f"result {i}", tool_use_id=f"t{i}")
        return context


class TestTokenAccounting(ContextTestCase):
    def test_usage_fraction_and_pct(self):
        c = self.ctx(window=1000)
        c.update_tokens(250)

        self.assertAlmostEqual(0.25, c.usage_fraction())
        self.assertEqual(25, c.usage_pct())

    def test_usage_fraction_survives_a_zero_window(self):
        c = self.ctx(window=0)
        c.update_tokens(500)

        self.assertEqual(0.0, c.usage_fraction())
        self.assertEqual(0, c.usage_pct())

    def test_turn_tokens_accumulate_and_reset(self):
        c = self.ctx()
        c.add_turn_tokens(100, 50)
        c.add_turn_tokens(200, 25)

        self.assertEqual(375, c.turn_tokens)

        c.reset_turn_tokens()

        self.assertEqual(0, c.turn_tokens)

    def test_turn_tokens_tolerate_none(self):
        c = self.ctx()
        c.add_turn_tokens(None, None)

        self.assertEqual(0, c.turn_tokens)


class TestCompactionTrigger(ContextTestCase):
    def test_needs_compaction_at_the_boundary(self):
        c = self.ctx(window=1000, threshold=0.85)

        c.update_tokens(849)
        self.assertFalse(c.needs_compaction())

        c.update_tokens(850)
        self.assertTrue(c.needs_compaction())

    def test_threshold_can_be_overridden_per_call(self):
        c = self.ctx(window=1000, threshold=0.85)
        c.update_tokens(500)

        self.assertTrue(c.needs_compaction(threshold=0.4))


class TestCompaction(ContextTestCase):
    def test_drops_roughly_the_oldest_forty_percent(self):
        c = self.with_tool_pairs(self.ctx(), 10)  # 30 messages
        before = len(c.messages)

        dropped = c.compact_messages()

        self.assertGreaterEqual(dropped, 12)
        self.assertEqual(before - dropped, len(c.messages))

    def test_resets_current_tokens_so_the_next_response_reports_the_truth(self):
        c = self.with_tool_pairs(self.ctx(), 10)
        c.update_tokens(900)

        c.compact_messages()

        self.assertEqual(0, c.current_tokens)

    def test_keeps_at_least_two_messages(self):
        c = self.ctx()
        c.add_message("user", "a")
        c.add_message("assistant", "b")

        self.assertEqual(0, c.compact_messages())
        self.assertEqual(2, len(c.messages))

    def test_never_orphans_a_tool_result(self):
        """The invariant the drop point is snapped for.

        Dropping purely by count orphans a tool_result whose tool_use went with
        it, which Anthropic answers with a 400 — and with the MUD tools
        registered, tool pairs are most of the history, so an unsnapped drop
        lands mid-pair more often than not.
        """
        for pairs in range(1, 21):
            with self.subTest(pairs=pairs):
                c = self.with_tool_pairs(self.ctx(), pairs)
                c.compact_messages()

                live_ids = {
                    block["id"]
                    for m in c.messages
                    if m.role == "assistant" and isinstance(m.content, list)
                    for block in m.content
                    if block.get("type") == "tool_use"
                }

                for m in c.messages:
                    if m.role == "tool_result":
                        self.assertIn(m.tool_use_id, live_ids)

    def test_surviving_history_always_opens_on_a_user_turn(self):
        for pairs in range(1, 21):
            with self.subTest(pairs=pairs):
                c = self.with_tool_pairs(self.ctx(), pairs)
                c.compact_messages()

                if c.messages:
                    self.assertEqual("user", c.messages[0].role)

    def test_clear_messages_also_zeroes_the_gauge(self):
        c = self.with_tool_pairs(self.ctx(), 3)
        c.update_tokens(700)

        c.clear_messages()

        self.assertEqual([], c.messages)
        self.assertEqual(0, c.current_tokens)


if __name__ == "__main__":
    unittest.main()
