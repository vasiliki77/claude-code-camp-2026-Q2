class PromptBuilder:
    """Serializes a Context for whichever backend it is given. It does not call
    the API — it only prepares the payload, headers, and URL for the call."""

    def __init__(self, context, backend):
        self.context = context
        self.backend = backend

    def to_messages(self):
        return self.backend.to_messages(self.context.messages)

    def to_tools(self):
        return self.backend.to_tools(self.context.tools)

    def to_api_payload(self, *, max_output_tokens=1024, tools=None):
        return self.backend.to_payload(
            self.context, max_output_tokens=max_output_tokens, tools=tools
        )

    # Delegates to the backend, which normalizes a provider response into the
    # common shape documented on each backend's parse_response:
    #   {"stop_reason": "tool_use" | "end_turn",
    #    "content": [{"type": "text", ...} | {"type": "tool_use", ...}]}
    def parse_response(self, response):
        return self.backend.parse_response(response)

    def headers(self):
        return self.backend.headers()

    def url(self):
        return self.backend.url()
