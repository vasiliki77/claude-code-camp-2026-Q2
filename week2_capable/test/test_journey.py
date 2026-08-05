"""Layer 2 parsers — see docs/plans/observability/obs_plan.md §3.

Every string in this file is copied verbatim from the 05-08 mapping corpus
(.boukensha/sessions/20260805T102026Z-a9c47c88.jsonl, 81 tool calls) or the
compaction-gate session beside it. Nothing here is invented, because the first
draft of these parsers was wrong in ways only real output showed: the exit line
is `[ Exits: n s ]` and not `Obvious exits:`, and a successful move into an
unlit room says only "It is pitch black...".
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from boukensha import journey  # noqa: E402

MOVE_OK = (
    "Behind The Temple Altar\r\n   You are on a dirt path leading away from the "
    "Temple Altar which is south\r\nof here.  To the north, the path continues "
    "through the lush contryside of\r\nMidgaard towards the Dragonhelm Mountains "
    "far off to the north.\r\n[ Exits: n s ]\r\n\r\n22H 100M 81V (news) (motd) > "
)
DOOR_CLOSED = "The door seems to be closed.\r\n\r\n22H 100M 76V (news) (motd) > "
NOT_HERE = "You do not see that here.\r\n\r\n22H 100M 83V (news) (motd) > "
LEVEL_GATE = (
    "This zone is above your recommended level.\r\n\r\n22H 100M 79V (news) (motd) > "
)
PITCH_BLACK = "It is pitch black...\r\n\r\n22H 100M 74V (news) (motd) > "
SCORE = (
    "You are 18 years old.\r\nYou have 22(22) hit, 100(100) mana and 83(83) "
    "movement points.\r\n\r\n22H 100M 83V (news) (motd) > "
)


class TestPromptAndVitals(unittest.TestCase):
    def test_vitals_come_off_every_reply(self):
        _body, vitals = journey.split_prompt(MOVE_OK)

        self.assertEqual({"hp": 22, "mana": 100, "movement": 81}, vitals)

    def test_prompt_is_removed_from_the_body(self):
        body, _vitals = journey.split_prompt(DOOR_CLOSED)

        self.assertEqual("The door seems to be closed.", body)

    def test_ansi_is_stripped(self):
        body, _ = journey.split_prompt("\x1b[0;33mThe Temple Square\x1b[0m")

        self.assertEqual("The Temple Square", body)


class TestRoomEntered(unittest.TestCase):
    def event(self, result, args=None):
        events = journey.parse("tbamud__move", args or {"direction": "north"}, result)
        return events[0] if events else None

    def test_a_move_yields_the_room_and_its_exits(self):
        event = self.event(MOVE_OK)

        self.assertEqual("room_entered", event["event"])
        self.assertEqual("Behind The Temple Altar", event["room"])
        self.assertEqual(["n", "s"], event["exits"])
        self.assertEqual("north", event["direction"])

    def test_the_room_name_is_not_confused_with_the_description(self):
        """The description's first line is indented; the title is not."""
        self.assertEqual("Behind The Temple Altar", self.event(MOVE_OK)["room"])

    def test_a_score_readout_is_not_a_room(self):
        """`You are 18 years old.` has no exit line. Guessing from punctuation
        rather than from the exit line misfiles exactly this."""
        self.assertEqual([], journey.parse("tbamud__check", {"kind": "score"}, SCORE))

    def test_a_dark_room_is_still_a_room(self):
        """The move succeeded — dropping it loses the node and the edge, and
        leaves a hole that looks like the agent never moved."""
        event = self.event(PITCH_BLACK)

        self.assertEqual("room_entered", event["event"])
        self.assertTrue(event["dark"])
        self.assertEqual("north", event["direction"])

    def test_dark_rooms_are_not_collapsed_into_one_node(self):
        """A placeholder name would merge every unlit room and invent edges
        between unrelated places. Identity waits on obs_plan.md §4.2."""
        self.assertIsNone(self.event(PITCH_BLACK)["room"])


class TestBlockedAndRejected(unittest.TestCase):
    def test_a_closed_door_blocks_the_move(self):
        event = journey.parse("tbamud__move", {"direction": "east"}, DOOR_CLOSED)[0]

        self.assertEqual("movement_blocked", event["event"])
        self.assertEqual("closed_door", event["reason"])
        self.assertEqual("east", event["direction"])

    def test_a_level_gate_is_a_distinct_reason(self):
        """A closed door is a puzzle; a level gate is a progression wall. QnA
        needs them apart — they are different findings."""
        event = journey.parse("tbamud__move", {"direction": "north"}, LEVEL_GATE)[0]

        self.assertEqual("movement_blocked", event["event"])
        self.assertEqual("level_gated", event["reason"])

    def test_the_direction_comes_from_the_call_not_the_reply(self):
        """"The door seems to be closed." never says which door."""
        event = journey.parse("tbamud__move", {"direction": "down"}, DOOR_CLOSED)[0]

        self.assertEqual("down", event["direction"])
        self.assertNotIn("down", event["text"])

    def test_an_unrecognized_target_is_a_rejection_not_a_block(self):
        event = journey.parse("tbamud__look", {"target": "statue"}, NOT_HERE)[0]

        self.assertEqual("command_rejected", event["event"])
        self.assertEqual("statue", event["target"])

    def test_a_non_move_refusal_is_never_reported_as_movement(self):
        events = journey.parse("tbamud__look", {"target": "x"}, LEVEL_GATE)

        self.assertEqual("command_rejected", events[0]["event"])


class TestToolNaming(unittest.TestCase):
    def test_prefixed_and_bare_names_behave_the_same(self):
        """Registration prefixes are a config choice; the parser must not care."""
        args = {"direction": "north"}
        prefixed = journey.parse("tbamud__move", args, MOVE_OK)
        bare = journey.parse("move", args, MOVE_OK)

        self.assertEqual(prefixed, bare)


class TestQuietCases(unittest.TestCase):
    def test_an_empty_reply_yields_nothing(self):
        self.assertEqual([], journey.parse("tbamud__poll", {}, ""))

    def test_a_reply_with_only_a_prompt_yields_nothing(self):
        self.assertEqual([], journey.parse("tbamud__poll", {}, "22H 100M 83V > "))


if __name__ == "__main__":
    unittest.main()
