#!/usr/bin/env python3
"""Interactive driver that orchestrates the mud-player subagent via the Agent SDK.

The mud-player agent is defined programmatically (`AgentDefinition`, passed
into `ClaudeAgentOptions(agents=...)`) instead of being auto-discovered from
`.claude/agents/`. Its description and prompt are still authored as a plain
markdown file with YAML frontmatter (`agents/mud-player.md`) — this script
loads and parses that file itself, rather than relying on Claude Code's
filesystem discovery to do it.
"""

import asyncio
from pathlib import Path

from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    TextBlock,
    ToolUseBlock,
)

ROOT = Path(__file__).parent.parent
AGENT_NAME = "mud-player"


def load_agent_definition(md_path: Path) -> AgentDefinition:
    """Parse a `.claude/agents`-style markdown file: YAML frontmatter + prompt body."""
    text = md_path.read_text()
    if not text.startswith("---\n"):
        raise ValueError(f"{md_path} is missing YAML frontmatter")
    _, frontmatter, body = text.split("---\n", 2)

    fields = {}
    for line in frontmatter.splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()

    return AgentDefinition(
        description=fields["description"],
        prompt=body.strip(),
        tools=["Bash", "Read", "Write"],
        model="sonnet",
    )


def build_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        agents={AGENT_NAME: load_agent_definition(ROOT / "agents" / "mud-player.md")},
        cwd=str(ROOT),
        system_prompt=(
            "You are an orchestrator. For any request to connect to, "
            "explore, or play the MUD, delegate to the "
            f"'{AGENT_NAME}' subagent via the Agent tool rather than acting "
            "on the MUD directly. Always invoke it synchronously (do not "
            "set run_in_background / launch it as a background task) and "
            "wait for its complete response before replying to the user."
        ),
    )


async def run_turn(client: ClaudeSDKClient, prompt: str) -> None:
    await client.query(prompt)
    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text)
                elif isinstance(block, ToolUseBlock):
                    print(f"[using tool: {block.name}]")


async def main() -> None:
    options = build_options()
    async with ClaudeSDKClient(options=options) as client:
        print("mud-player orchestrator ready. Type a request, or 'exit' to quit.")
        while True:
            try:
                prompt = await asyncio.to_thread(input, "> ")
            except EOFError:
                break
            prompt = prompt.strip()
            if not prompt:
                continue
            if prompt.lower() in {"exit", "quit"}:
                break
            await run_turn(client, prompt)


if __name__ == "__main__":
    asyncio.run(main())
