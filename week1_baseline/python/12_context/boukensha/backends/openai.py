import json

from .base import Base

# https://platform.openai.com/docs/api-reference/responses
#
# gpt-5.x rejects `reasoning_effort` + tools on /v1/chat/completions ("Please
# use /v1/responses"), so this backend targets the Responses API instead of chat
# completions. That changes more than the URL: messages become `input` items,
# the system prompt becomes a top-level `instructions` string, tool defs are
# flat (no `function:` wrapper), and tool results round-trip via
# `function_call_output` items matched by `call_id` rather than a
# `{"role": "tool"}` message.


class OpenAI(Base):
    BASE_URL = "https://api.openai.com/v1/responses"
    MODELS = {
        "gpt-5.5": {
            "context_window": 1_000_000,
            "cost_per_million": {"input": 5.0, "output": 30.0},
            "usage_unit": "tokens",
        },
        "gpt-5.4-mini": {
            "context_window": 400_000,
            "cost_per_million": {"input": 0.75, "output": 4.5},
            "usage_unit": "tokens",
        },
        "gpt-5.4-nano": {
            "context_window": 400_000,
            "cost_per_million": {"input": 0.2, "output": 1.25},
            "usage_unit": "tokens",
        },
    }

    def __init__(self, *, api_key, model):
        self.api_key = api_key
        self._configure_model(model)

    # One message can become several input items — an assistant turn with both
    # prose and two tool calls is three — so this flattens rather than maps.
    def to_input(self, messages):
        items = []
        for msg in messages:
            if msg.role == "tool_result":
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": msg.tool_use_id,
                        "output": str(msg.content),
                    }
                )
            elif msg.role == "assistant":
                items.extend(self._assistant_items(msg.content))
            else:
                items.append({"role": msg.role, "content": msg.content})
        return items

    def to_tools(self, tools):
        return [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": {
                    "type": "object",
                    "properties": tool.parameters,
                    "required": list(tool.parameters),
                },
            }
            for tool in tools.values()
        ]

    def to_payload(self, context, *, max_output_tokens=1024, tools=None):
        return {
            "model": self.model,
            "instructions": context.system,
            "input": self.to_input(context.messages),
            # `is None`, not truthiness: Agent._wrap_up passes an empty list to
            # disable tools, and an empty list is falsy in Python.
            "tools": self.to_tools(context.tools) if tools is None else tools,
            "max_output_tokens": max_output_tokens,
            "reasoning": {"effort": "none"},
        }

    def headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def url(self):
        return self.BASE_URL

    # Normalizes a Responses API `output[]` array into the common shape (see
    # Base for the full content-block contract).
    def parse_response(self, response):
        content = []
        function_calls = []

        for item in response.get("output") or []:
            kind = item.get("type")

            if kind == "reasoning":
                text = "".join(
                    s.get("text") or "" for s in (item.get("summary") or [])
                )
                content.append({"type": "reasoning", "text": text})
            elif kind == "message":
                text = "".join(
                    c.get("text") or ""
                    for c in (item.get("content") or [])
                    if c.get("type") == "output_text"
                )
                if text:
                    content.append({"type": "text", "text": text})
            elif kind == "function_call":
                # Collected, not appended in place: tool_use blocks come after
                # reasoning and text in the normalized order.
                function_calls.append(item)

        for fc in function_calls:
            content.append(
                {
                    "type": "tool_use",
                    "id": fc.get("call_id"),
                    "name": fc.get("name"),
                    # OpenAI hands back arguments as a JSON *string*, unlike
                    # every other backend, which sends an object.
                    "input": json.loads(fc.get("arguments") or "{}"),
                }
            )

        return {
            "stop_reason": "tool_use" if function_calls else "end_turn",
            "content": content,
        }

    # ---------- private ---------------------------------------------------

    # Rebuilds Responses input items from normalized content blocks (the inverse
    # of parse_response). Reasoning blocks are dropped — gpt-5.x does not need
    # them echoed back when reasoning effort is "none".
    def _assistant_items(self, content):
        blocks = (
            [{"type": "text", "text": content}]
            if isinstance(content, str)
            else content
        )

        text = "".join(b["text"] for b in blocks if b.get("type") == "text")
        items = [{"role": "assistant", "content": text}] if text else []

        for b in blocks:
            if b.get("type") != "tool_use":
                continue

            items.append(
                {
                    "type": "function_call",
                    "call_id": b["id"],
                    "name": b["name"],
                    # Compact separators to match Ruby's #to_json; the default
                    # json.dumps spacing would put this on the wire as
                    # '{"path": "x"}' where Ruby sends '{"path":"x"}'.
                    "arguments": json.dumps(b["input"], separators=(",", ":")),
                }
            )

        return items
