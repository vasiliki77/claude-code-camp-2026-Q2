#!/usr/bin/env python3
"""A throwaway MCP server with nothing to do with MUDs.

It exists so that "tools/mcp.py is generic" is proven by demonstration rather
than asserted in a comment. If MUD assumptions creep back into the host layer,
the tests using this server fail loudly.

Two tools, no state, no dependencies. Mirrors the Ruby one in the daemon's
test/support so the two languages' host layers are exercised identically.
"""
import json
import sys

TOOLS = [
    {
        "name": "add",
        "description": "Add two numbers together.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "first addend"},
                "b": {"type": "number", "description": "second addend"},
            },
            "required": ["a", "b"],
        },
    },
    {
        "name": "shout",
        "description": "Uppercase some text.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "the text"}},
            "required": ["text"],
        },
    },
]


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        message = json.loads(line)
        if message.get("id") is None:
            continue  # notification — act on nothing, answer nothing

        method = message.get("method")
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "tiny-calculator", "version": "1.0.0"},
            }
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            args = (message.get("params") or {}).get("arguments") or {}
            name = (message.get("params") or {}).get("name")
            if name == "add":
                text = str(float(args.get("a", 0)) + float(args.get("b", 0)))
            elif name == "shout":
                text = str(args.get("text", "")).upper()
            else:
                text = "no such tool"
            result = {"content": [{"type": "text", "text": text}], "isError": False}
        else:
            result = {}

        print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)


if __name__ == "__main__":
    main()
