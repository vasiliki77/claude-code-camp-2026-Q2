# Technical Journal

## 2026-07-20 , Repository Setup & Housekeeping

- Starting week0 on week1, hoping I will catch up.
- Repository was created from the official GitHub template ("Use this template"), not by forking or cloning the example repo.
- Discovered 338 Windows `Zone.Identifier` files committed under `week1_baseline/ruby/` (NTFS alternate-data-stream metadata left over from copying files via Windows/WSL). These were untracked and deleted, as they appear to be junk/generated files.
- Updated `.gitignore`:
  - `*Zone.Identifier` , prevent the artifacts above from being re-added.
  - `node_modules/` , standard dependency directory exclusion.
  - `week0_explore/preview/data/world/**/*.json` , this directory holds ~1,142 generated JSON files produced by `week0_explore/bin/convert-world`. These are reproducible build output, not source, so they're excluded the same way `node_modules/` is.

## Environment Setup

Installed `nvm` (Node version manager):

```sh
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/master/install.sh | bash
nvm install 20.20.2
```

Installed `uv` (Python package/project manager, used to run the `circlemud-world-parser`):

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
uv self update
```

Then generated the CircleMUD world preview data, from `week0_explore`:

```sh
cd week0_explore
./bin/convert-world
```

To start the world preview app itself:

```sh
cd week0_explore/preview/web
npm run dev
```

## Week 0 , Exploration

### Primary Challenge

> Level up enough to defeat the Massive Minotaur in the Newbie zone.

### Architecture 1: Plain Agent File (CLAUDE.md + Markdown Memory)

**Setup:** Created `week0_explore/explore_architecture/01_plain_agent/CLAUDE.md` , a simple system prompt defining a Player Journey Agent that plays tbaMUD (a CircleMUD continuation) on the player's behalf, connecting via telnet/nc to `localhost:4000` with credentials `dummy` / `helloworld`. The agent was told to persist its working state each loop using two local markdown files, `data/player.md` and `data/world.md`, rather than any code-based memory system.

Tested first with Haiku 4.5, then again with Sonnet 4.6 to see if a stronger model would resolve the issues below.

**Observations:**
- The coding harness would read local files not pertaining to the loop, taking it off task and wasting tokens/usage.
- The agent ended up creating temporary files to open a socket connection and execute commands, rather than using a stable, reusable interface , suggesting we should be persisting a common interface for the MUD (e.g. a `mud_manager`).
- When it created a rigid script and failed to log in, it went off task looking for config files , its login/interface approach was flawed. A `mud_manager` would remove this obstacle for small models.
- The agent struggled to connect to the MUD in general.
- It attempted to create temporary code files to manage the telnet connection and execute commands, rather than reusing a stable approach.
- It didn't have enough information about the MUD's Text User Interface to log in and recognize its own mistakes.
- It would try to read files unrelated to the task.
- Increasing model intelligence (Haiku 4.5 → Sonnet 4.6) did not help.

**Conclusions:**
- We could probably write a better prompt or provide an artifact giving the agent full knowledge of the MUD's Text User Interface to log in successfully, but since this login flow is fixed/deterministic, it's better to have a script that exactly knows how to log in , so we're not wasting tokens/usage on deterministic user flows.
- Coding harnesses tend to go off task and try to write code we don't need the agent to write. At least at this architecture stage, a coding harness does not appear to be a good fit.
- We're justified in building our own MUD SDK to connect to the MUD, since the agent clearly wants to manage the connection via script and execute common commands over the port.
- If we had an MCP server wrapping our MUD SDK, we might be able to drive the agent better at this architectural level.
- Given the complexity of world and player state data, updating markdown files by hand likely won't be sufficient , though we haven't yet concluded whether the current agentic loop of the coding harness could handle that task regardless.

> Tomorrow: use coding harnesses for coding; for specialized agents, build your own loop.
