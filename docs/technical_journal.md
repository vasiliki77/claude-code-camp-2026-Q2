# Technical Journal

## 2026-07-20 — Repository Setup & Housekeeping

- Starting week0 on week1, hoping I will catch up.
- Repository was created from the official GitHub template ("Use this template"), not by forking or cloning the example repo.
- Discovered 338 Windows `Zone.Identifier` files committed under `week1_baseline/ruby/` (NTFS alternate-data-stream metadata left over from copying files via Windows/WSL). Untracked and deleted — junk/generated files.
- Updated `.gitignore`:
  - `*Zone.Identifier` — prevent the artifacts above from being re-added.
  - `node_modules/` — standard dependency directory exclusion.
  - `week0_explore/preview/data/world/**/*.json` — ~1,142 generated JSON files produced by `week0_explore/bin/convert-world`. Reproducible build output, not source.

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

## Week 0 — Exploration

### Primary Challenge

> Level up enough to defeat the Massive Minotaur in the Newbie zone.

### Architecture 1: Plain Agent File (CLAUDE.md + Markdown Memory)

**Setup:** `week0_explore/explore_architecture/01_plain_agent/CLAUDE.md` — a simple system prompt defining a Player Journey Agent that plays tbaMUD (a CircleMUD continuation) on the player's behalf.

- Connects via telnet/nc to `localhost:4000`, credentials `dummy` / `helloworld`.
- Told to persist working state each loop in `data/player.md` and `data/world.md` — no code-based memory system.
- Tested with Haiku 4.5, then Sonnet 4.6 to see if a stronger model would resolve the issues below.

**Observations:**
- The coding harness read local files unrelated to the loop, going off task and wasting tokens.
- The agent created throwaway files to open a socket and run commands rather than reusing a stable interface — suggesting we should persist a common interface for the MUD (e.g. a `mud_manager`).
- When its rigid script failed to log in, it went hunting for config files. The login/interface approach was flawed; a `mud_manager` would remove this obstacle for small models.
- It struggled to connect at all, and lacked enough information about the MUD's text interface to log in or recognize its own mistakes.
- Increasing model intelligence (Haiku 4.5 → Sonnet 4.6) did not help.

**Conclusions:**
- A better prompt or a TUI reference artifact might get it logging in, but the login flow is fixed and deterministic — better handled by a script than by spending tokens re-deriving it every run.
- Coding harnesses tend to go off task and write code we don't need. At this stage, a coding harness is not a good fit.
- Building our own MUD SDK is justified: the agent clearly *wants* to manage the connection via script and execute common commands over the port.
- An MCP server wrapping that SDK might drive the agent better at this architectural level.
- Given the complexity of world and player state, hand-updated markdown likely won't be sufficient — though whether the coding harness's agentic loop could handle it at all is still open.

> Tomorrow: use coding harnesses for coding; for specialized agents, build your own loop.

### 2026-07-21 — Architecture 2: Agent Skills (Claude CLI)

Working in `week0_explore/explore_architecture/02_agent_skills/`, asked Claude Code (CLI) directly:

> create a skill in this folder that will help me play the MUD, the MUD is running at localhost:4000 and the credentials are dummy/helloworld, you can create your own scripts in the skills script to help manage the connection

Also added https://github.com/anthropics/skills as a plugin marketplace:

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

Then asked Claude Code to build the skill via the newly-installed `skill-creator` plugin rather than hand-rolling a `SKILL.md`.

**Building the skill:**

- **Grounded the login flow before writing it.** The agent connected to `localhost:4000` with a throwaway Python script to observe the real handshake instead of assuming a generic MUD flow. This surfaced a `*** PRESS RETURN:` gate between the password prompt and the account menu — a fixed send-sequence would have desynced right there. Final logic waits for whichever prompt actually arrives and answers that.
- **A daemon, because MUD state lives in one socket.** Room, fight, and inventory all live in a single TCP connection, but harness tool calls are one-shot — a plain `nc`/`telnet` per command logs back in from scratch every time. Solved by having `mud.py` start a background daemon that owns the socket for the whole session; each CLI call (`start` / `send` / `read` / `expect` / `status` / `stop`) is a thin client talking to it over a Unix socket. This is the `mud_manager` Architecture 1's conclusions called for — this time built because the agent was explicitly told to, not reached for unprompted.
- **Combat is asynchronous.** `kill <mob>` returns only the opening round; the rest arrives unprompted over the following seconds. Forced two distinct primitives — `send` (waits for the next game prompt) and `read` (drains whatever shows up on its own). Only became obvious by starting a real fight against a live "beastly fido" and watching the output arrive in pieces.
- **`autoexits`/`autoloot`/`autogold` are toggles, not switches.** The server ignores a trailing `on`, and values persist on the character between sessions — so "enable these at every login" silently flips them *off* every other session. Caught only by running setup twice and noticing the second run undid the first. Fixed by reading the `toggle` table first and sending only what's out of place.
- **Skipped skill-creator's subagent eval loop.** It runs with-skill and baseline variants in parallel; with a shared live game character that means two sessions fighting over one login. Verified instead with scripted probes against the real server (login flow, cross-process state persistence, pager walking, combat) plus one live end-to-end task — asked it to find the in-game bakery and list its menu, and it navigated Midgaard's Main Street and returned the correct stock and prices.

**Skill discovery gotcha:** the skill was first written into `02_agent_skills/mud-player/` — a plain repo folder. `/reload-skills` never picked it up, silently. Skills are only auto-discovered from `~/.claude/skills/` (user-level) or a `.claude/skills/` directory (project-level, or nested for directory-scoped skills). Moving it to `02_agent_skills/.claude/skills/mud-player/` fixed it immediately.

**Conclusions:**
- Explicitly asking for a skill *with bundled scripts* produced the reusable connection manager Architecture 1 was missing. Deterministic login/pager/toggle handling now lives in code once, instead of being re-derived and re-broken every run.
- Grounding against the live server before writing docs mattered more than expected. The PRESS RETURN gate, toggle-vs-switch semantics, and async combat are not things a model gets right from CircleMUD's general reputation — they would have shipped as plausible-looking but wrong.
- skill-creator's eval methodology assumes the task is repeatable and parallelizable. A shared stateful live-game character breaks that and needs scripted probes plus one supervised live task instead.
- Skill placement is invisible from the skill's own content — it depends entirely on which directory the harness scans.

### Skill Enhancement: State Persistence & Goal Tracking

Enhanced mud-player with persistent markdown memory for multi-session goals (e.g. "reach level 7 and defeat the Massive Minotaur").

**Added files:**
- `data/player.md` — level, experience, location, vitals, goals with checkboxes
- `data/world.md` — map, mob locations, goal targets
- `scripts/update_memory.py` — parses `transcript.log` and syncs `player.md`

**How it works:**
1. Agent reads `data/player.md` at session start for current progress and goals.
2. Plays normally via `mud.py`.
3. After milestones (level-up, new area), runs `update_memory.py`.
4. The script regex-extracts vitals/level/location from the transcript and updates `player.md`.
5. Next session starts with up-to-date state.
6. Agent edits goals and progress notes directly to mark achievements.

**Conclusions:**
- Demonstrates agents maintaining state across sessions using plain text as a data store — markdown as a human-readable, agent-editable, version-controllable knowledge base instead of a database.
- The extract → update pattern generalizes: any task with structured output can have a similar state-sync layer.
- It avoids Architecture 1's "agent continuously re-derives facts" problem.
- The extraction regexes are game-specific and brittle. A robust version would use the MUD's own query protocol (MSDP, if available) or a wrapper that structures output. For a bootcamp exercise, simple regex is enough to show the concept. *(This brittleness came due in Architecture 3a — see below.)*
- For multi-agent coordination or complex state this would need a schema/validation layer; for single-agent learning tasks it's sufficient.

### Playing the Game: Getting Stuck, and the World-Data Escape

With the skill and memory files in place, tried to actually level from 1 to 2. This surfaced a failure mode neither earlier note anticipated: **the game world itself can trap an agent in a state its tools can't recover from.**

**The dungeon trap** — character stuck in a pitch-black sewer complex under the Guild of Swordsmen (zones 70/71/73) with no light source:

- `look` and `scan` return only "It is pitch black..." — no room name, no mob names, nothing to act on.
- `scan` occasionally reported "you can hear shuffling" in a direction, proving mobs were nearby, but `kill <name>` against ~20 guessed names (rat, bat, ghost, zombie, spider, wraith, shade, spirit, apparition, spectre, phantom, creature, thing, mob, something…) all failed with "That player is not here."
- Added a `reset` command to `mud.py` (quit + reconnect) hoping for a soft respawn. tbaMUD stores location server-side, so it reconnects into the same dark room. **A recovery mechanism that works perfectly for its intended failure (dropped connection) and does nothing for a different one (bad world state)** — the two look similar from outside but need different fixes.
- ~200+ blind movement commands, systematically trying every direction at every junction, failed to find an exit. Compounding: movement in the dark still costs moves, hunger/thirst silently cap HP/move regen even while resting, and no food or water was reachable inside.
- Deliberately tried to let the character die, on the theory that death respawns at the Temple of Midgaard (a real tbaMUD mechanic). Never got the chance to test it — the actual fix arrived first.

**The fix: read the world data instead of guessing at it.** The user pointed at `week0_explore/preview/data/world/{wld,mob,zon}/*.json` — the same generated JSON `.gitignore`'d as build output on day 1, now ground truth about the world:

- `wld/<zone>.json` gives every room's exits as `{dir, room_linked}` — enough to BFS a path between any two room ids.
- `zon/<zone>.json` is the file that actually answers "what can I fight and where": concrete `{mob, room, max}` spawn placements. `mob/<zone>.json` has only templates (level, aliases, xp) keyed by id — useless for location on its own.
- Even fully in the dark, `exits` still lists direction letters (just not descriptions) — enough to execute a pre-computed path blindly. On reaching any lit room, `exits` also prints neighbor room *names*, greppable against the `wld` json to re-confirm position.
- Mapped path out: Zone 73 room 7345 → 10 moves → 7300 → `up` into Zone 71 → `up` into Zone 70 room 7004 → 5 moves → 7030 → `up` into Midgaard room 3030 ("The Dump"), one door from the main farming area. Walked it for real, verifying each step's exit count against the json before committing. Worked first attempt.

**Farming, and a second trap: town guards join fights.**

- The Midgaard `zon` file (zone 30) gave exact spawn rooms for the beginner-safe mobs the user supplied — beastly fido, janitor, beggar, odif yltsaeb, all level 1, all "The perfect match!" on `consider`. Farmed ~760 of the 2000 xp for level 2 in one sitting, cycling four fido rooms plus the janitor/beggar spots.
- Bought a small sword (78g, Weapon Shop on Main Street) after noticing bare-fisted attacks missed constantly. A cheap early weapon measurably cut the miss rate — more valuable than it sounds for a "just farm safe mobs" strategy.
- Then: **a Peacekeeper standing passively in a room joined a fight against a fido that had nothing to do with it**, and HP went 22 → 3 within a couple of rounds while fleeing. Town guards (Peacekeeper, cityguard, knight) police *any* violence they witness, not just attacks on themselves.
- Several rooms stack multiple guards and are effectively no-fight zones regardless of what "safe" mob is also standing there: the East Gate, the Guild of Swordsmen entrance, the Grunting Boar bar.
- A level-20 "green gelatinous blob" also wanders through Temple Square — even a town hub can contain something instantly lethal that `consider` would have caught, if checked before engaging.

Both `data/player.md` and `data/world.md` were rewritten with all of this — the tested escape path, the confirmed safe-farming room table, and the guard/blob traps — so a future session can resume grinding instead of re-discovering it.

**Conclusions:**
- **State recovery tools need to match the actual failure mode.** `reset` is right for a dropped session, but was reached for reflexively when the real problem was "wrong place in an unrecoverable-by-restart world." Design recovery commands against a taxonomy of failures, not just the first one encountered.
- **Guessing at world content from live `look`/`scan` alone is fragile once visibility is limited.** The same brittleness flagged for regex-based memory extraction shows up again, for world knowledge instead of player state. Ground-truth data beat blind exploration outright.
- **The trap wasn't in the tooling, it was in the strategy layer above it.** `mud.py` handled movement, combat loop, and resting fine; what failed was deciding which room to enter and which mob to trust. Skills for open-ended live environments need a reference doc of *world* facts (danger zones, spawn tables) alongside the doc of *how to operate the tool* — which is why this session's fix was almost entirely additions to `world.md`/`player.md`, not `mud.py`.
- **"Perfect match" on `consider` is about relative combat odds, not total safety.** It says nothing about third parties joining in. Checking `look` for bystanders before every fight is now part of the playbook.

### 2026-07-21 — Architecture 3a: Porting the Skill to a Subagent

Moved the Architecture 2 skill into `week0_explore/explore_architecture/03_subagent_sdk/` as a **subagent**: `.claude/agents/mud-play.md`, frontmatter `name: mud-player`, with `scripts/` alongside it. Same `mud.py` daemon, same memory-file idea — different invocation contract.

The interesting result is that **the port was not a copy, and every way it broke was a path or a missing asset, not logic.**

**What the port broke:**

- **Relative script paths.** Every command in the agent read `python3 scripts/mud.py …`. That resolved fine from the skill directory; a subagent runs from the project root, so all 16 call sites were dead. Rewritten to `.claude/agents/scripts/mud.py`, with an explicit note in the agent that paths are relative to the project root.
- **`references/tbamud.md` was never copied** — it exists nowhere in the repo. The agent still instructed itself to read it "rather than guessing at syntax", i.e. a dangling pointer that costs a wasted turn and then gets guessed at anyway. Replaced with the in-game equivalents: `send commands`, `send "help <topic>"`.
- **`data/player.md` and `data/world.md` were never copied either**, so `update_memory.py` failed outright with `player.md not found`. Recreated both — and the world knowledge (escape path, safe-farming table, guard traps) had to be reconstructed *from this journal*, since the original files were gone.
- **`__pycache__/` had been committed.** Removed, `.gitignore` added.

**Pre-existing bugs, surfaced only by running it:**

The Architecture 2 note predicted the extraction regexes were brittle. They were, and worse than "brittle" — they produced confident garbage rather than failing:

- `extract_location` grabbed the first longish line in the transcript window regardless of content. It had been writing `Current Room: You are hungry.` Rewritten to anchor on the `[ Exits: … ]` block autoexits prints, and read the room name off the prompt line above it. Verified against the real transcript: returns `The Dump`, `Market Square`, and `None` when no room block is in range.
- `extract_vitals` used `.search`, taking the *oldest* prompt in the window rather than the most recent. Now takes the last.
- Max HP/mana/moves were hardcoded as `/ 22`, `/ 100`, `/ 83` — correct only for this one level-1 character, and silently wrong the moment it levels. Now preserves the max already in the file, widening it if a current value exceeds it, since the prompt never reports maxima.

**Verification — the *scripts*, not the agent.** This distinction matters and was blurred on the first write-up of this entry. Everything below was driven from the shell by calling `mud.py` directly. The `mud-player` subagent was never spawned, so the one thing the port actually changed — whether an agent file's `.claude/agents/scripts/…` paths resolve from the cwd a spawned subagent gets — **remains untested.** The scripts work; the agent contract is unproven.

Full live round trip against the running server:

| Command | Result |
|---|---|
| `start` | Connected as `dummy`; server had a linkdead character and reconnected cleanly |
| `setup --wimpy 8` | Converged — `already ON` for autoexits/autoloot/autogold, `already OFF` for brief, wimpy set |
| `send look score` | Both ran in order; room and score parsed |
| `send "drink fountain"` | Quoted multi-word arg passed through intact |
| `read` / `status` / `log` | Returned the transcript tail with the vitals footer |
| `expect` | Timed out as designed and reported the miss rather than hanging or dropping output |
| `reset` | Quit and reconnected, back in the Temple with state intact |

Used `mud.py start`, not `nc localhost 4000` — the server was already listening, and a second raw connection fights the daemon for the character, which is the whole reason the daemon exists.

**Conclusions:**

- **Porting a skill to an agent is not a file move.** A skill resolves bundled paths relative to its own directory; an agent file is just a prompt, so every path has to be written relative to the harness's working directory. Nothing warns you — the agent loads fine and fails at the first `Bash` call.
- **Bundled assets are silent dependencies.** `references/` and `data/` are invisible in the skill's contract, so they get left behind. The `data/` loss was recoverable only because the journal happened to record its contents in enough detail — which is an argument for this journal, and against treating agent-maintained markdown as the sole home for hard-won knowledge.
- **A dangling file pointer is worse than no pointer.** "Read `references/tbamud.md`" sends the agent to a file that doesn't exist; it burns a turn and then guesses anyway. If an asset doesn't survive a port, the instruction referencing it has to change too.
- **Documentation drift only surfaces by running the thing.** The location regex had been "working" in the sense of producing output. Plausible garbage in a memory file is worse than a crash, because the next session reads it as fact.
- **The character is the real persistent store, not the markdown.** Score on reconnect read 760 exp with 1240 needed — exactly matching the "~760 of the 2000 xp" recorded during Architecture 2. Server-side character state survived an entire architecture change while the local memory files did not. Worth remembering when deciding what memory is actually *for*: it holds what the server can't tell you (the escape path, which rooms have guards), not what it can.

### Architecture 3a continued: Real Agent Spawn, and What "Skill vs Agent" Actually Means

Two loose ends from the entry above got closed the same day, plus a terminology question worth recording because the answer is a harness mechanic, not a naming convention.

**Rebuilt the missing `data/world.md` from this journal, then played manually.** With `data/player.md`/`data/world.md` recreated and the escape-path/spawn-table knowledge restored, drove the character by hand (direct `mud.py` calls, not the agent) toward level 2:

- Cleared hunger/thirst at the Temple Square fountain; confirmed the small sword was still wielded.
- Cross-referenced `zon/30.json` against `mob/*.json` for the full level-≤3 Midgaard spawn table, and it surfaced a hazard the Architecture 2 notes had missed: **Market Square (room 3014) spawns a peacekeeper and a cityguard**, and it's the hub every route from the Temple passes through. Fine to walk through, not to fight in.
- **Finding: the `xp` field in `mob/*.json` is not the xp actually awarded.** Every farmable mob's template says `xp: 100`; a real janitor kill gave **33**. tbaMUD scales the award by level difference, so the world json answers *where* and *what* but not *how much* — any farming estimate built on the raw field is off by roughly 3×. At ~33/kill, the remaining 1240 xp is ~38 kills against ~8 spawns per zone repop — a multi-cycle grind, not a quick session. Stopped by choice at **815 exp / 1185 to go**, full HP, rather than grind it out.
- Wrote a throwaway `farm.py` (scratchpad, not committed) to avoid hand-driving ~38 fights: `look` → abort-if-guard → `kill` → `expect`. Two bugs in it, both misreadings of game text rather than code errors, worth remembering for any future driver script: (1) treated `R.I.P.` as player death, but tbaMUD prints that for *any* death including the mob's — only `You are dead` means the player; (2) its `look`→`kill` sequence is two separate daemon calls, so the bystander check is advisory, not atomic — a guard can still walk in between, which is exactly the Architecture-2 failure that took HP 22→3. `--wimpy` remains the only real mid-fight backstop. Also silently dropped `consider`, which the agent doc says to run before *every* fight — harmless here, but a reminder that a wrapper script can quietly discard a documented safety step.

**Closed the open verification gap by actually spawning `mud-player`.** Asked it, with a deliberately thin prompt (destination only, no path hints), to walk the character back to the Temple. Confirmed via `mud.py status` afterward: character landed in **The Temple Of Midgaard**, `[ Exits: n e s w d ]`, 22/22 HP — the ATM-in-the-wall line in the room description confirms it's the right room, not just a similarly-worded one. This is the first time the agent's own `.claude/agents/scripts/mud.py` paths were exercised by a real spawned subagent rather than by direct shell calls, so the open risk flagged above is now resolved: **the port's paths work from the actual invocation path, not just from my shell.** (The run was stopped mid-task on request, before its planned `update_memory.py` sync could be confirmed complete — so whether `player.md` reflects the new room is unknown, separately from the path question being settled.)

**"Skill" and "agent" are harness discovery mechanisms, not properties of `mud.py`.** A side conversation nailed this down precisely, prompted by asking whether `mud-play.md` could just be told to "run as a skill":

- `mud.py` itself is inert — the same file, called the same way (`python3 …/mud.py <cmd>`), regardless of whether a skill, an agent, or a bare `Bash` call invokes it. It has no identity as either.
- What *does* have an identity is the markdown definition next to it. `SKILL.md` under `.claude/skills/<name>/` is discovered by the `Skill` tool's directory scan; a `.md` file under `.claude/agents/` is discovered by the `Agent` tool's scan. Same content, different discovery path, different invocation contract (inline-loaded vs. fresh-spawned).
- **Filename is not negotiable for skills** — this reconfirms the Architecture 2 gotcha above. The discovered file must be named exactly `SKILL.md`; dropping `mud-play.md` (that name) into a `.claude/skills/` folder would sit there unnoticed, the same silent failure as before.
- Even renamed correctly, the paths would break in reverse: skills resolve bundled paths relative to *the skill's own directory*, while `mud-play.md`'s paths are project-root-relative (per the fix in this same entry). Copying the file without its `scripts/`/`data/` siblings, and without re-deriving the paths, reproduces the original Architecture 2→3a breakage going the other way.
- Confirmed by diff that `SKILL.md` (Architecture 2) and `mud-play.md` (Architecture 3a) are otherwise byte-identical — frontmatter, daemon rationale, combat/toggle/reporting sections all unchanged. The only divergence is exactly the path-rewrites from this entry, which is a clean confirmation that the port carried the substance over correctly and only the mechanical layer needed fixing.

**Conclusions:**

- **The skill/agent boundary is enforced by directory + filename scanning, not by instruction.** Asking the model to "run it as a skill" cannot make the `Skill` tool find something it didn't discover — the available-skills list for a session is fixed by what actually got scanned, not by what's requested mid-conversation.
- **A byte-diff is a cheap, strong verification tool for a port.** Rather than re-reading both files by eye, diffing them confirmed in one command that nothing except the intended path changes had drifted — worth reaching for whenever "did the port change anything it shouldn't have" is the actual question.
- **"Verified" needs to name what was exercised.** The earlier version of this entry said the port was verified, but only the scripts had been called directly — the agent's own invocation path was a separate, larger claim that stayed unproven until it was actually spawned. Distinguishing "the code path works" from "the interface I claimed works, works" caught a real gap here and is worth treating as a standing habit, not a one-off correction.

### 2026-07-22 — Architecture 3b: Programmatic `AgentDefinition`, and a Real Multi-Character Bug

Replaced filesystem discovery in `03b_subagent_sdk/` with an SDK-constructed subagent: `mud-player` is now built in code via Python `claude-agent-sdk`'s `AgentDefinition`, passed into `ClaudeAgentOptions(agents={...})`, instead of `.claude/agents/mud-play.md` being auto-scanned.

**Setup:**
- New driver `scripts/run_agent.py` — interactive loop (`ClaudeSDKClient`, `query()`/`receive_response()` per turn), not one-shot.
- Prompt still authored as markdown with YAML frontmatter, at `agents/mud-player.md` (renamed from an initial `prompts/`). `run_agent.py` parses it itself — split on `---\n`, `key: value` per frontmatter line, no yaml dependency — rather than relying on directory scanning.
- Copied `scripts/mud.py`, `scripts/update_memory.py`, `data/player.md`, `data/world.md` from `03a_subagent_sdk/`; rewrote path references in the prompt from `.claude/agents/scripts/…`/`.claude/agents/data/…` to `scripts/…`/`data/…`.
- Deleted `.claude/agents/mud-play.md` — two competing definitions under the same agent name otherwise.
- `claude-agent-sdk` wasn't installed anywhere in the repo; installed via pip (0.2.125).

**Harness quirk: restricting the orchestrator's own tools broke subagent spawning.**
- This CLI names the subagent tool `Agent`, not `Task` as the plan assumed.
- `ClaudeAgentOptions(tools=["Task"])` (wrong name), and separately `tools=["Agent"]` or `disallowed_tools=[...]`, both made `AgentDefinition(tools=["Bash","Read","Write"])` fail: `Agent 'mud-player' would be spawned with zero tools — refusing. Its tools list resolved to nothing: unrecognized [Bash, Read, Write]` — despite those being valid top-level tool names.
- Fix: leave the orchestrator's `tools` unset; enforce delegation only via `system_prompt`.
- The `Agent` tool also launches subagents as background/async tasks non-deterministically by default (returns before the subagent finishes, resumed later via `SendMessage`). Added an explicit "invoke synchronously, do not set run_in_background" line to `system_prompt` to get a reliable same-turn answer.

**Real bug, found live: user asked to run `dummy` and `smarty` as two concurrent subagents; session got stuck.**
- Root cause: `mud.py`'s `state_dir()` keyed sessions only by `host-port`, so both characters shared one daemon/socket/transcript at `~/.mud-player/localhost-4000/`.
- Compounding: "smarty" wasn't an existing character, so the server dropped into its new-character wizard (confirm name → password → retype password → sex → class) — a flow `login()` never handled, so it timed out (`daemon.err`: `timed out waiting for a login prompt`).
- The smarty subagent wrote its own ad-hoc `scripts/create_char.py` to walk the wizard by hand, then got stuck in an infinite retry loop at the class prompt (kept resending something the server rejected — `That's not a class.` on repeat). That loop, not the daemon, is what actually wedged the user's terminal.

**Fixes to `scripts/mud.py`:**
- `state_dir()` now keys on `host-port-user`. Verified: `dummy` and `smarty` running concurrently in separate dirs (`~/.mud-player/localhost-4000-dummy`, `…-smarty`), independent `score` queries — dummy hungry/thirsty, smarty not.
- `login()` extended to handle the creation wizard natively: `did i get that right` → `y`, `give me a password` → password, `retype password` → password, `what is your sex` → `--sex`, `select a class` → `--class`. New flags `--sex {M,F}` (default `M`) / `--class {C,T,W,M}` (default `W`), only consulted when `--user` is a brand-new name. Exact prompt sequence learned by probing the raw socket with a throwaway script first.
- `cmd_reset()` had a pre-existing latent bug, surfaced but not caused by this session: always hardcoded reconnecting as `dummy`/`helloworld` regardless of whose session was being reset. Fixed to forward the real invocation's args (`argparse.Namespace(**vars(args))`).
- Removed `scripts/create_char.py` — superseded by native `login()` handling.
- Verified end-to-end: created a disposable brand-new character (`Newbington`) via `mud.py` alone, no manual script, reached the game in one call.

**Conclusions:**
- **A tool name assumed from a plan doc isn't guaranteed to match the runtime.** The plan said "Task tool"; this harness calls it `Agent`. Worth confirming the real name before coding a restriction around it.
- **Restricting a parent's tool list can break its subagents' tool resolution**, in this harness at least — not just the parent's own capabilities. Soft enforcement via `system_prompt` proved more reliable than a hard `tools`/`disallowed_tools` restriction.
- **The single-shared-daemon assumption from Architecture 2/3a (one character at a time) breaks silently once two agents share a host:port.** Nothing errored at the "two characters" framing — it just handed the second agent the first agent's session.
- **A stuck subagent will improvise around a real gap rather than surface it as a clean error.** `create_char.py` was a reasonable workaround for a genuine missing feature (character creation), but its own bug turned a fixable gap into a silent infinite loop — worth treating "the agent wrote its own script mid-task" as a signal to check for a missing base capability, not just as resourcefulness.
