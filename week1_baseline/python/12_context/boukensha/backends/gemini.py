from .base import Base, dig


class Gemini(Base):
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    MODELS = {
        "gemini-3.5-flash": {
            "context_window": 1_048_576,
            "cost_per_million": {"input": 1.5, "output": 9.0},
            "usage_unit": "tokens",
        },
        "gemini-3.1-flash-lite": {
            "context_window": 1_048_576,
            "cost_per_million": {"input": 0.25, "output": 1.5},
            "usage_unit": "tokens",
        },
        # Dropped in step 12 to match Ruby, which is the reference
        # implementation: the two tables are the same lookup in two languages,
        # and Models derives windows from them, so drift between them is a
        # silent difference in when compaction fires. Re-adding an entry is four
        # lines — but add it to both.
        #   gemini-2.5-pro         1_048_576  in 1.25 / out 10.0
        #   gemini-2.5-flash       1_048_576  in 0.30 / out 2.50
        #   gemini-2.5-flash-lite  1_048_576  in 0.10 / out 0.40
        #   gemini-3.1-pro-preview-customtools  1_048_576  in 2.0 / out 12.0
        #     (also commented out on the Ruby side; needs thinkingLevel: LOW)
    }

    def __init__(self, *, api_key, model):
        self.api_key = api_key
        self._configure_model(model)

    def to_messages(self, messages):
        serialized = []
        for msg in messages:
            if msg.role == "assistant":
                serialized.append(
                    {"role": "model", "parts": self._assistant_parts(msg.content)}
                )
            elif msg.role == "tool_result":
                serialized.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "functionResponse": {
                                    "name": msg.tool_use_id,
                                    "response": {"content": msg.content},
                                }
                            }
                        ],
                    }
                )
            else:
                serialized.append({"role": msg.role, "parts": [{"text": msg.content}]})
        return serialized

    def to_tools(self, tools):
        if not tools:
            return []

        return [
            {
                "functionDeclarations": [
                    {
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
            }
        ]

    def to_payload(self, context, *, max_output_tokens=1024, tools=None):
        return {
            "systemInstruction": {"parts": [{"text": context.system}]},
            "contents": self.to_messages(context.messages),
            "tools": self.to_tools(context.tools) if tools is None else tools,
            "generationConfig": {
                "maxOutputTokens": max_output_tokens,
                "thinkingConfig": self._thinking_config(),
            },
        }

    def headers(self):
        return {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }

    def url(self):
        return f"{self.BASE_URL}/{self.model}:generateContent"

    # Normalizes a Gemini generateContent response into the common shape:
    #   {"stop_reason": "tool_use" | "end_turn",
    #    "content": [{"type": "text", "text": ...}
    #                | {"type": "tool_use", "id": ..., "name": ..., "input": {...}}]}
    #
    # Gemini doesn't assign call ids, so the function name is reused as the id
    # (Gemini also matches functionResponse back to a call by name).
    def parse_response(self, response):
        parts = dig(response, "candidates", 0, "content", "parts") or []

        content = []
        tool_used = False

        for part in parts:
            if part.get("functionCall"):
                fc = part["functionCall"]
                content.append(
                    {
                        "type": "tool_use",
                        "id": fc.get("name"),
                        "name": fc.get("name"),
                        "input": fc.get("args") or {},
                        "signature": part.get("thoughtSignature"),
                    }
                )
                tool_used = True
            elif part.get("thought"):
                # Gemini flags a thinking part rather than typing it, so the
                # check must come before the plain-text branch — a reasoning
                # part also carries "text".
                content.append(
                    {
                        "type": "reasoning",
                        "text": str(part.get("text") or ""),
                        "signature": part.get("thoughtSignature"),
                    }
                )
            elif part.get("text"):
                content.append({"type": "text", "text": part["text"]})

        return {
            "stop_reason": "tool_use" if tool_used else "end_turn",
            "content": content,
        }

    # ---------- private ---------------------------------------------------

    def _thinking_config(self):
        if self.model == "gemini-3.1-pro-preview-customtools":
            # Full disable is not supported on this model.
            return {"thinkingLevel": "LOW"}

        return {"thinkingBudget": 0}

    # Rebuilds Gemini "model" parts from normalized content blocks
    # (the inverse of parse_response). thoughtSignature is echoed back only when
    # present — Gemini rejects a null one.
    def _assistant_parts(self, content):
        blocks = (
            [{"type": "text", "text": content}]
            if isinstance(content, str)
            else content
        )

        parts = []
        for b in blocks:
            kind = b.get("type")
            if kind == "tool_use":
                part = {"functionCall": {"name": b["name"], "args": b["input"]}}
            elif kind == "reasoning":
                part = {"text": str(b.get("text") or ""), "thought": True}
            else:
                part = {"text": b["text"]}

            if b.get("signature"):
                part["thoughtSignature"] = b["signature"]

            parts.append(part)

        return parts
