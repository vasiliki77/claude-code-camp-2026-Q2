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

### 2026-07-21 , Architecture 2: Agent Skills (Claude CLI)

Working in `week0_explore/explore_architecture/02_agent_skills/`, asked Claude Code (CLI) directly:

> create a skill in this folder that will help me play the MUD, the MUD is running at localhost:4000 and the credentials are dummy/helloworld, you can create your own scripts in the skills script to help manage the connection

Also visited https://github.com/anthropics/skills and added it as a plugin marketplace to try installing pre-built skills from it:

```
/plugin marketplace add anthropics/skills
```

Then, from the CLI:

```
> /reload-skills
  L Reloaded skills: 14 skills available (no changes)

> /plugin
  L ✓ Installed skill-creator. Run /reload-plugins to apply.

> /reload-skills
  L Reloaded skills: 15 skills available (no changes)

> /skills
  L No changes
```

Then asked Claude Code to build the skill itself, invoking the newly-installed `skill-creator` plugin rather than hand-rolling a `SKILL.md`.

**Building the skill:**
- Before writing anything, the agent connected directly to `localhost:4000` with a throwaway Python script to observe the real login handshake, rather than assuming a generic MUD flow. This surfaced a `*** PRESS RETURN:` gate sitting between the password prompt and the account menu , a fixed send-sequence (name, then password, then menu choice) would have desynced right there. The final login logic waits for whichever prompt actually shows up and answers that, instead of guessing timings.
- Design constraint: a MUD connection is stateful (room, fight, inventory all live in one TCP socket) but coding-harness tool calls are one-shot. A plain `nc`/`telnet` invocation per command would log back in from scratch every time and lose everything. Solved by having the skill's script (`mud.py`) start a small background daemon that owns the socket for the whole session; each CLI call (`start` / `send` / `read` / `expect` / `status` / `stop`) is a thin client talking to that daemon over a Unix socket. This is effectively the `mud_manager` that Architecture 1's conclusions called for , and this time the agent was explicitly told to build it, rather than reaching for it unprompted under a plain CLAUDE.md.
- Combat turned out to be asynchronous: sending `kill <mob>` returns only the opening round, and the rest of the fight arrives unprompted over the following seconds. This required two distinct primitives , `send` (waits for the next game prompt) and `read` (drains whatever shows up on its own) , which only became obvious by actually starting a fight against a live "beastly fido" and watching the output arrive in pieces.
- Found via live testing that TBAMUD's `autoexits`/`autoloot`/`autogold` are **toggles, not switches**: the server ignores a trailing `on`, and the values persist on the character between sessions. A naive "enable these at every login" approach silently flips them *off* every other session , caught only by running the setup step twice and noticing the second run undid the first. Fixed by reading the `toggle` table first and only sending the commands that are actually out of place.
- Skipped skill-creator's standard subagent-based eval loop: it runs the with-skill and baseline variants in parallel, which for a shared live game character means two sessions fighting over one login. Verified correctness instead by scripting direct probes against the real server (login flow, cross-process state persistence, pager walking, combat) and by a live end-to-end task (asked it to find the in-game bakery and list its menu; it navigated Midgaard's Main Street and returned the correct stock and prices).

**Skill discovery gotcha:** the skill was first written straight into `week0_explore/explore_architecture/02_agent_skills/mud-player/` , a plain folder in the repo. `/reload-skills` never picked it up, silently. Skills are only auto-discovered from `~/.claude/skills/` (user-level) or a `.claude/skills/` directory (project-level, or nested for directory-scoped skills) , dropping a `SKILL.md` anywhere else in a repo does nothing on its own. Moved it to `02_agent_skills/.claude/skills/mud-player/`, after which `/reload-skills` found it immediately.

**Conclusions:**
- Explicitly asking for a skill with bundled scripts produced exactly the reusable connection manager that Architecture 1 was missing , the deterministic login/pager/toggle handling now lives in code once, instead of being re-derived (and re-broken) by the model on every run.
- Grounding the skill against the live server before writing documentation mattered more than expected: several behaviors (the PRESS RETURN gate, toggle-vs-switch semantics, async combat) are not the kind of thing a model would get right from CircleMUD's general reputation alone, and would have shipped as plausible-looking but wrong.
- The skill-creator plugin's eval methodology assumes the task is repeatable/parallelizable; a shared stateful live-game character breaks that assumption and needs a different verification strategy (direct scripted probes + one live supervised task).
- Skill placement is not obvious from the skill's own content , it depends entirely on which directory the harness scans. Worth remembering this constraint before the next architecture.


## Skill Enhancement: State Persistence & Goal Tracking

Enhanced mud-player with persistent markdown-based memory for multi-session goals (e.g., "reach level 7 and defeat the Massive Minotaur").

**Added files:**
- `data/player.md` — character state: level, experience, location, vitals, goals with checkboxes
- `data/world.md` — world knowledge: map, mob locations, goal targets
- `scripts/update_memory.py` — parses transcript.log and syncs player.md with current state

**How it works:**
1. Agent reads `data/player.md` at session start to understand current progress and goals
2. Plays the game normally via mud.py
3. After significant milestones (leveling up, discovering new areas), runs `python3 scripts/update_memory.py`
4. The script extracts vitals/level/location from the transcript using regex and updates player.md
5. Next session starts with up-to-date character state in the markdown file
6. Agent can edit goals/progress-notes directly to mark achievements or adjust strategy

**Learning outcome:**
This demonstrates **how agents maintain persistent state across sessions using plain text as a data store**. Rather than a database or code-based memory, markdown files serve as a human-readable, agent-editable knowledge base. The update script pattern (parse output → extract facts → update file) is generalizable: any game or task with structured output can have a similar state-sync layer.

**Key insight from building this:**
The extraction regex patterns (`VITALS_RE`, `LEVEL_RE`, `EXP_RE`, `LOCATION_RE`) are game-specific and brittle. A more robust approach would use the MUD's own query protocol (e.g., MSDP if available) or a wrapper layer that structures output. For a bootcamp exercise, though, simple regex extraction is enough to show the concept.

**Conclusions:**
- Agents naturally want to offload state management to persistent files, not carry it in context
- Markdown is a good format: human-readable, agent-editable, version-controllable
- The update script approach (extract → update) avoids the "agent continuously re-derives facts" problem from Architecture 1
- For true multi-agent coordination or complex state, this approach would need a schema/validation layer, but for single-agent learning tasks it's sufficient

## 2026-07-21 , Playing the Game: Getting Stuck, and the World-Data Escape

With the skill and memory files in place, actually tried to level the character from 1 to 2.
This surfaced a failure mode neither earlier architecture note anticipated: **the game world
itself can trap an agent in a state its tools can't recover from.**

### The dungeon trap

The character ended up in a pitch-black dungeon (a sewer complex under the Guild of Swordsmen,
spanning zones 70/71/73) with no light source. In this state:
- `look` and `scan` return only "It is pitch black..." / "too dark to see anything" , no room
  name, no mob names, nothing to act on.
- `scan` occasionally reported "you can hear shuffling" in a direction, proving mobs were nearby,
  but `kill <name>` against ~20 guessed mob names (rat, bat, ghost, zombie, spider, wraith, shade,
  spirit, apparition, spectre, phantom, creature, thing, mob, something...) all failed with "That
  player is not here."
- Added a `reset` command to `mud.py` (quit + reconnect) hoping it would act like a soft respawn.
  It didn't , tbaMUD stores character location server-side, so `reset` just reconnects into the
  exact same dark room. This is a good example of a recovery mechanism that works perfectly for
  its intended failure (dropped connection) and does nothing for a different one (bad world
  state) , the two look similar from the outside but need different fixes.
- ~200+ blind movement commands (systematically trying every direction at every junction) failed
  to find an exit. Movement points and hunger/thirst also compound the problem: moving in the
  dark still costs moves, hunger/thirst silently cap HP/move regen even while resting, and there
  was no food or water reachable from inside the dungeon.
- At one point deliberately tried to **let the character die** on the theory that death respawns
  at the Temple of Midgaard (a real tbaMUD mechanic). Never got the chance to test it , the actual
  fix arrived first.

### The fix: read the world data instead of guessing at it

The user pointed at `week0_explore/preview/data/world/{wld,mob,zon}/*.json` , the same generated
JSON that `.gitignore`'d as build output back on day 1 (see the setup section above), now useful
as ground truth about the game world:
- `wld/<zone>.json` gives every room's exits as `{dir, room_linked}` , enough to BFS a path
  between any two room ids once you know the graph.
- `zon/<zone>.json` turned out to be the file that actually matters for "what can I fight and
  where" , it lists concrete `{mob, room, max}` spawn placements. The `mob/<zone>.json` file only
  has mob templates (level, aliases, xp) keyed by id; without the `zon` file there's no way to
  know where a given mob template actually appears in the world.
- Even fully in the dark, the in-game `exits` command still lists direction letters (just not
  descriptions) , enough to execute a pre-computed path blindly. The moment the path reached any
  lit room, `exits` also printed neighbor room *names*, which could be grepped against the wld
  json to re-confirm exact position.
- Using this, mapped a real path out: Zone 73 room 7345 → 10 moves → Zone 73 room 7300 → `up` into
  Zone 71 → `up` again into Zone 70 room 7004 → 5 more moves → Zone 70 room 7030 → `up` into
  Midgaard room 3030 ("The Dump"), one door from the main farming area. Walked it for real,
  verifying each step's exit count against the json before committing to the next, and it worked
  on the first attempt.

### Farming, and a second trap: town guards join fights

Once out, the `zon` file for Midgaard (zone 30) gave exact spawn rooms for the beginner-safe mobs
the user separately supplied (beastly fido, janitor, beggar, odif yltsaeb , all level 1, all
"The perfect match!" on `consider`). Farmed ~760 of the 2000 xp needed for level 2 in one sitting,
cycling between four known fido rooms plus the janitor/beggar spots.

Bought a small sword (78g, Weapon Shop on Main Street) after noticing bare-fisted attacks missed
constantly , a cheap early weapon purchase measurably cut the miss rate, more valuable than it
sounds for a "just farm safe mobs" strategy.

Then hit a second unanticipated failure mode: **a Peacekeeper standing passively in a room joined
a fight against a fido that had nothing to do with it**, and HP went from 22 to 3 within a couple
of rounds while fleeing , a near-death event from a mob that was never the intended target. Town
guards (Peacekeeper, cityguard, knight) turn out to police *any* violence they witness, not just
attacks on themselves. Several rooms (the East Gate, the Guild of Swordsmen entrance, the
Grunting Boar bar) stack multiple guards at once and are effectively no-fight zones regardless of
what "safe" mob might also be standing there. A level-20 "green gelatinous blob" also wanders
through Temple Square , a reminder that even a town hub can contain something instantly lethal
that `consider` would have caught, if it had been checked before engaging.

Both `data/player.md` and `data/world.md` were rewritten with all of this , the tested dungeon
escape path, the confirmed safe-farming room table, and the guard/blob traps , so a future session
can resume grinding directly instead of re-discovering any of it.

### Conclusions

- **State recovery tools need to match the actual failure mode.** `reset` (quit/reconnect) is the
  right fix for a dropped session, but was reached for reflexively when the real problem was
  "wrong place in an unrecoverable-by-restart game world." Worth designing recovery commands
  against a taxonomy of failures, not just the first one encountered.
- **Guessing at world content (mob names, safe fights, room layouts) from live `look`/`scan` output
  alone is fragile once visibility is limited** , the same brittleness the day-1 note flagged
  for regex-based memory extraction shows up again here, just for world knowledge instead of
  player state. Ground-truth data (the `wld`/`zon`/`mob` json) beat blind exploration outright
  once the user pointed at it.
- **A skill's bundled scripts (`mud.py`) handled the mechanical parts fine (movement, combat
  loop, resting) , the trap wasn't in the tooling, it was in the strategy layer above it** (which
  room to enter, which mob to trust, whether a guard is nearby). This suggests skills for
  open-ended live environments benefit from a reference doc of *world* facts (danger zones, spawn
  tables) in addition to a reference doc of *how to operate the tool*, which is why this session's
  fix was almost entirely additions to `world.md`/`player.md` rather than to `mud.py` itself.
- **"Perfect match" on `consider` is about relative combat odds, not about total safety** , it
  says nothing about third parties (guards) joining in. Checking `look` for bystanders before
  every fight, not just `consider` on the target, is now part of the documented playbook.

