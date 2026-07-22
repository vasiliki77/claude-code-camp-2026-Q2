# Plan: Replace filesystem subagent loading with `AgentDefinition`

## Context

`03a_subagent_sdk` defines the `mud-player` subagent the "filesystem" way:
a markdown file with YAML frontmatter at `.claude/agents/mud-play.md`, which
Claude Code / the Agent SDK auto-discovers by scanning that directory at
startup. The frontmatter (`name`, `description`) plus the markdown body
(the agent's system prompt) are parsed off disk.

`03b_subagent_sdk` currently has only a copy of that same file
(`.claude/agents/mud-play.md`) and no driver script yet. The goal is to stop
relying on filesystem discovery and instead construct the subagent
programmatically with the Agent SDK's `AgentDefinition`, passed directly into
`ClaudeAgentOptions(agents={...})` from a driver script.

## Changes

1. **Add a Python driver script** — `03b_subagent_sdk/main.py`, using the
   `claude-agent-sdk` Python package (consistent with `mud.py` /
   `update_memory.py` already being Python).

   ```python
   from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, AgentDefinition

   MUD_PLAYER_PROMPT = """<body of mud-play.md, unchanged>"""

   options = ClaudeAgentOptions(
       agents={
           "mud-player": AgentDefinition(
               description="<description from the frontmatter, unchanged>",
               prompt=MUD_PLAYER_PROMPT,
               tools=["Bash", "Read", "Write"],   # only what mud.py/update_memory.py need
               model="sonnet",
           ),
       },
       cwd="03b_subagent_sdk",
   )

   async def main():
       async with ClaudeSDKClient(options=options) as client:
           await client.query(sys.argv[1] if len(sys.argv) > 1 else "explore the MUD")
           async for message in client.receive_response():
               ...  # print/stream text blocks
   ```

   The frontmatter `description` and the markdown body of
   `mud-play.md` map directly onto `AgentDefinition(description=..., prompt=...)`
   — no behavioral change to the agent's instructions, just where they live
   (in code vs. on disk).

2. **Bring over the supporting files 03a already has**, since the prompt
   references them by path:
   - `scripts/mud.py`, `scripts/update_memory.py`, `scripts/.gitignore`
   - `data/player.md`, `data/world.md`

   Copied to `03b_subagent_sdk/scripts/` and `03b_subagent_sdk/data/` (top
   level, not under `.claude/agents/`, since nothing requires them to live
   inside the agents folder once the agent definition itself isn't
   filesystem-discovered). Path references inside the prompt text get updated
   from `.claude/agents/scripts/...` / `.claude/agents/data/...` to
   `scripts/...` / `data/...` accordingly.

3. **Remove `.claude/agents/mud-play.md`.** Once the definition lives in
   `main.py` as an `AgentDefinition`, the markdown file is dead weight — and
   keeping it around risks the SDK loading *two* competing definitions for
   the same agent name.

4. **Top-level orchestration prompt.** Following the `01_plain_agent`
   pattern, keep a short instruction (either a `CLAUDE.md` or the top-level
   `query()`/`client.query()` call) telling the main agent to delegate MUD
   play to the `mud-player` subagent via the `Task` tool, rather than acting
   on the MUD directly.

## Open questions

- **Language**: defaulting to Python for the driver script since the
  existing tooling (`mud.py`, `update_memory.py`) is Python and the repo has
  no Node/TS setup elsewhere in this exercise. Say the word if you'd rather
  use the TypeScript SDK (`@anthropic-ai/claude-agent-sdk`) instead.
- **Entry point shape**: a one-shot script (`main.py "<goal>"`) vs. an
  interactive loop. I'd default to one-shot with a CLI arg for the goal,
  matching how the earlier exercises are invoked.

A: We want to implement a full replacement and delete week0_explore/explore_architecture/03b_subagent_sdk/.claude/agents/mud-play.md.
B: We want to load a markdown file
C: Name the driver script `run_agent.py`. The script should receive the user's request as an interactive loop