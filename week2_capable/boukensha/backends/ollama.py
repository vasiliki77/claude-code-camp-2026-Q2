from .base import Base


class Ollama(Base):
    MODELS = {
        "gemma4:e4b": {
            "context_window": 128_000,
            "cost_per_million": {"input": 0.0, "output": 0.0},
            "usage_unit": "local_compute",
        },
        # Trimmed in step 12 to match Ruby, the reference implementation: Models
        # derives its windows from these tables in both languages, so drift here
        # is a silent difference in when compaction fires. All are local and
        # free — re-add whichever you actually pull, in both languages:
        #   gemma4, gemma4:e2b, deepseek-r1:8b   128_000
        #   gemma4:12b, gemma4:26b, gemma4:31b, qwen3:30b   256_000
        #   qwen3:8b    40_000
    }

    # Ruby writes `initialize(host: "http://localhost:11434", model:)`. Python
    # cannot follow a defaulted parameter with a required one, so the order is
    # swapped here — both are keyword-only, so call sites read the same.
    def __init__(self, *, model, host="http://localhost:11434"):
        self.host = host
        self._configure_model(model)

    def to_messages(self, system, messages):
        serialized = [{"role": "system", "content": system}]
        for msg in messages:
            if msg.role == "tool_result":
                serialized.append(
                    {
                        "role": "tool",
                        "tool_name": msg.tool_use_id,
                        "content": msg.content,
                    }
                )
            elif msg.role == "assistant":
                serialized.append(self._assistant_message(msg.content))
            else:
                serialized.append({"role": msg.role, "content": msg.content})
        return serialized

    def to_tools(self, tools):
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": tool.parameters,
                        "required": list(tool.parameters),
                    },
                },
            }
            for tool in tools.values()
        ]

    def to_payload(self, context, *, max_output_tokens=1024, tools=None):
        return {
            "model": self.model,
            "stream": False,
            "messages": self.to_messages(context.system, context.messages),
            "tools": self.to_tools(context.tools) if tools is None else tools,
            "think": False,
        }

    def headers(self):
        return {"Content-Type": "application/json"}

    def url(self):
        return f"{self.host}/api/chat"

    # Normalizes an Ollama /api/chat response into the common shape:
    #   {"stop_reason": "tool_use" | "end_turn",
    #    "content": [{"type": "text", "text": ...}
    #                | {"type": "tool_use", "id": ..., "name": ..., "input": {...}}]}
    #
    # Ollama doesn't assign call ids, so the function name is reused as the id
    # (Ollama also matches tool results back to a call by name).
    def parse_response(self, response):
        message = response.get("message") or {}
        tool_calls = message.get("tool_calls") or []

        content = []
        # Reasoning first, matching the block order the contract documents.
        # Ollama sends "" rather than omitting either key, so both of these test
        # for a non-empty string rather than mere presence.
        if message.get("thinking"):
            content.append({"type": "reasoning", "text": message["thinking"]})
        if message.get("content"):
            content.append({"type": "text", "text": message["content"]})

        for tc in tool_calls:
            fn = tc.get("function") or {}
            content.append(
                {
                    "type": "tool_use",
                    "id": fn.get("name"),
                    "name": fn.get("name"),
                    "input": fn.get("arguments") or {},
                }
            )

        return {
            "stop_reason": "end_turn" if not tool_calls else "tool_use",
            "content": content,
        }

    # ---------- private ---------------------------------------------------

    # Rebuilds an Ollama assistant message from normalized content blocks
    # (the inverse of parse_response).
    def _assistant_message(self, content):
        blocks = (
            [{"type": "text", "text": content}]
            if isinstance(content, str)
            else content
        )

        text_blocks = [b for b in blocks if b.get("type") == "text"]
        tool_blocks = [b for b in blocks if b.get("type") == "tool_use"]

        message = {
            "role": "assistant",
            "content": "".join(b["text"] for b in text_blocks),
        }
        if tool_blocks:
            message["tool_calls"] = [
                {"function": {"name": b["name"], "arguments": b["input"]}}
                for b in tool_blocks
            ]
        return message
