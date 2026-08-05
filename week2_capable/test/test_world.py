"""Layer 3 — the world graph and the boredom signal.

See docs/plans/observability/obs_plan.md §3 and §4.2.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from boukensha import world  # noqa: E402


def entered(room, exits, direction="north", command="move", dark=False):
    return {
        "event": "room_entered",
        "command": command,
        "room": room,
        "exits": exits,
        "direction": direction,
        "dark": dark,
    }


class TestRoomIdentity(unittest.TestCase):
    """Settled by measurement: the corpus has 32 titles across 36 rooms."""

    def test_same_title_different_exits_are_different_rooms(self):
        """`The Great Field Of Midgaard` appears with both `ns` and `ensw`.
        Keying on title alone merges them and every edge through them lies."""
        a = world.room_id("The Great Field Of Midgaard", ["n", "s"])
        b = world.room_id("The Great Field Of Midgaard", ["e", "n", "s", "w"])

        self.assertNotEqual(a, b)

    def test_exit_order_does_not_change_identity(self):
        self.assertEqual(
            world.room_id("Market Square", ["n", "e", "s"]),
            world.room_id("Market Square", ["s", "e", "n"]),
        )


class TestGraph(unittest.TestCase):
    def test_a_move_creates_an_edge(self):
        graph = world.build([[entered("A", ["n"]), entered("B", ["s"])]])

        self.assertEqual(2, len(graph["rooms"]))
        self.assertEqual(1, len(graph["edges"]))

    def test_a_look_does_not_create_an_edge(self):
        """`look` re-describes the room you are standing in. Treating it as a
        movement invents a self-loop for every glance around."""
        graph = world.build(
            [[entered("A", ["n"]), entered("A", ["n"], command="look")]]
        )

        self.assertEqual(0, len(graph["edges"]))

    def test_a_block_attaches_to_the_room_it_was_hit_from(self):
        """The journey event knows the direction and the refusal, never the
        origin — the origin only exists once movements are folded into a path.
        This is what produced the Dirt Path finding."""
        graph = world.build(
            [
                [
                    entered("The Dirt Path", ["n", "e", "s", "w"]),
                    {"event": "movement_blocked", "direction": "west", "reason": "level_gated"},
                ]
            ]
        )

        self.assertEqual(1, len(graph["blocked"]))
        self.assertIn("The Dirt Path", graph["blocked"][0]["room"])

    def test_sessions_do_not_chain_into_each_other(self):
        """A reconnect starts at the MUD's start room, not where the last
        session stopped. An edge across that boundary would be invented."""
        graph = world.build([[entered("A", ["n"])], [entered("Z", ["s"])]])

        self.assertEqual(0, len(graph["edges"]))


class TestTedium(unittest.TestCase):
    """The boredom signal — computed from the order rooms were entered, with
    nothing extra recorded."""

    def test_a_perfect_tour_has_no_barren_stretch(self):
        session = [entered(name, ["n"]) for name in ("A", "B", "C", "D")]
        result = world.tedium([session])[0]

        self.assertEqual(1.0, result["revisit_ratio"])
        self.assertEqual(0, result["longest_barren"])

    def test_walking_in_circles_shows_up_as_revisits(self):
        session = [entered(name, ["n"]) for name in ("A", "B", "A", "B", "A", "B")]
        result = world.tedium([session])[0]

        self.assertEqual(2, result["distinct_rooms"])
        self.assertEqual(3.0, result["revisit_ratio"])

    def test_longest_barren_counts_consecutive_moves_finding_nothing(self):
        """The measure closest to what a player feels: not "few rooms" but "a
        long stretch where nothing was new"."""
        session = [entered(n, ["n"]) for n in ("A", "B", "A", "A", "A", "C")]
        result = world.tedium([session])[0]

        self.assertEqual(3, result["longest_barren"])
        self.assertEqual(3, result["distinct_rooms"])

    def test_sessions_are_reported_separately(self):
        """A short session and a long one are not comparable, and averaging
        them hides both."""
        result = world.tedium([[entered("A", ["n"])], [entered("B", ["n"])]])

        self.assertEqual(2, len(result))

    def test_a_session_with_no_movement_is_omitted(self):
        self.assertEqual([], world.tedium([[{"event": "progression", "exp": 1}]]))


if __name__ == "__main__":
    unittest.main()
