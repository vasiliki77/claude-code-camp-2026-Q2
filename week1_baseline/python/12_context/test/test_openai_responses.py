import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boukensha  # noqa: E402
from boukensha.backends import OpenAI  # noqa: E402


class TestOpenAIResponsesPayload(unittest.TestCase):
    """The Responses API move, gated offline.

    gpt-5.x rejects reasoning_effort + tools on /v1/chat/completions, so step 12
    retargets this backend at /v1/responses — messages become `input` items, the
    system prompt becomes `instructions`, tool defs lose the `function:`
    wrapper, and tool results round-trip as `function_call_output` matched by
    `call_id`. None of that can be checked without either a key or this test,
    and a typo in any of it is a 400 from the one provider nobody runs daily.
    """

    def build_context(self):
        ctx = boukensha.Context(task=boukensha.Player, system="you are a player")
        registry = boukensha.Registry(ctx)
        registry.tool(
            "look", description="Look around", parameters={"target": {"type": "string"}}
        )(lambda target=None: "a room")

        ctx.add_message("user", "look around")
        ctx.add_message(
            "assistant",
            [
                {"type": "reasoning", "text": "thinking", "signature": "sig"},
                {"type": "text", "text": "Looking."},
                {
                    "type": "tool_use",
                    "id": "call_abc",
                    "name": "look",
                    "input": {"target": "room"},
                },
            ],
        )
        ctx.add_message("tool_result", "a room", tool_use_id="call_abc")
        return ctx

    def setUp(self):
        self.backend = OpenAI(api_key="k", model="gpt-5.5")
        self.payload = self.backend.to_payload(self.build_context())

    def test_targets_the_responses_endpoint(self):
        self.assertEqual("https://api.openai.com/v1/responses", self.backend.url())

    def test_system_prompt_becomes_top_level_instructions(self):
        self.assertEqual("you are a player", self.payload["instructions"])
        self.assertNotIn("messages", self.payload)
        self.assertEqual({"effort": "none"}, self.payload["reasoning"])

    def test_tool_definitions_are_flat(self):
        tool = self.payload["tools"][0]

        self.assertEqual("function", tool["type"])
        self.assertEqual("look", tool["name"])
        self.assertNotIn("function", tool)

    def test_a_tool_call_round_trips_by_call_id(self):
        items = self.payload["input"]
        call = next(i for i in items if i.get("type") == "function_call")
        output = next(i for i in items if i.get("type") == "function_call_output")

        self.assertEqual(call["call_id"], output["call_id"])
        self.assertEqual("call_abc", call["call_id"])
        # Arguments go out as a JSON *string*, unlike every other backend.
        self.assertEqual({"target": "room"}, json.loads(call["arguments"]))

    def test_reasoning_blocks_are_not_echoed_back(self):
        self.assertNotIn(
            "reasoning", [i.get("type") for i in self.payload["input"]]
        )

    def test_parse_response_normalizes_output_items(self):
        parsed = self.backend.parse_response(
            {
                "output": [
                    {"type": "reasoning", "summary": [{"text": "thought"}]},
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "hello"}],
                    },
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "look",
                        "arguments": '{"target":"room"}',
                    },
                ]
            }
        )

        self.assertEqual("tool_use", parsed["stop_reason"])
        # Reasoning first, then text, then tool_use — the documented order.
        self.assertEqual(
            ["reasoning", "text", "tool_use"], [b["type"] for b in parsed["content"]]
        )
        self.assertEqual("call_1", parsed["content"][2]["id"])
        self.assertEqual({"target": "room"}, parsed["content"][2]["input"])

    def test_a_plain_reply_ends_the_turn(self):
        parsed = self.backend.parse_response(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "done"}],
                    }
                ]
            }
        )

        self.assertEqual("end_turn", parsed["stop_reason"])


if __name__ == "__main__":
    unittest.main()
