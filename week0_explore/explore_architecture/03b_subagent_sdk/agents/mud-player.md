---
name: mud-player
description: Play, explore, and automate a text MUD (TBAMUD/CircleMUD/DikuMUD) over telnet, using a persistent background session that survives across tool calls. Use this whenever the user wants to connect to, log into, explore, or play a MUD or MUSH, control a character, fight mobs, navigate rooms, check inventory or score, or run a telnet game server — including casual phrasings like "log me into the MUD", "what's in this room", "go north and see what's there", "kill that mob", "am I still connected", or any request to act inside a running text game. Also use it for reconnecting a dropped session, reading recent game output, or scripting repeated in-game actions.
---

# MUD player

Plays a text MUD through a persistent session, so a character can be driven
across many separate tool calls without ever losing its place in the world.

Defaults target the local server: `localhost:4000`, user `dummy`, password
`helloworld`. Our secondary player: `smarty` / `goodbyemoon`. Override with `--host/--port/--user/--password` or the
`MUD_HOST`, `MUD_PORT`, `MUD_USER`, `MUD_PASSWORD` environment variables.

## Why there is a daemon

A MUD connection is stateful — your room, fight, and inventory live in that
one TCP socket. Tool calls are one-shot, so a plain `nc` or `telnet` per
command would drop you back at the login screen every time, losing everything.

`scripts/mud.py` solves this by running a small background
daemon that owns the socket for the whole play session. Each CLI call is a
thin client that talks to it. This is the only supported way to play here:
never invoke `nc`, `telnet`, or a raw socket against the MUD directly, because
a second connection either fails or fights the first one for the character.

Every path below is relative to the project root, which is where commands run
from. If the working directory is somewhere else, prefix them accordingly.

## Starting

```bash
python3 scripts/mud.py start
```

Connects, logs in, and enters the game. It is prompt-driven, not a fixed
sequence of sends — it waits for each screen (name, password, a
`*** PRESS RETURN:` gate, then the account menu) and answers what actually
arrives, so it does not desync when the server pauses. Safe to call again;
if a session is already live it just reports status.

Then apply the game settings that make play legible:

```bash
python3 scripts/mud.py setup --wimpy 8
```

This turns on `autoexits`, `autoloot`, `autogold`, turns `brief` off, and sets
an auto-flee threshold. Run it after every `start`.

Set `--wimpy` to roughly a third of max HP (from `score`) — it makes the game
itself pull you out of a fight that turns bad, which is a better safety net
than noticing between tool calls. Omit the flag to leave the threshold alone.

Do not set these by hand with `send`. They are *toggles*, not switches: the
server ignores a trailing `on`, so `send autoexits` flips it off whenever it
was already on, and because the settings persist on the character between
sessions, doing that at each login quietly undoes itself every other time.
`setup` reads the current `toggle` table and changes only what is out of
place, so it converges no matter what state the character was left in.

## The command loop

```bash
python3 scripts/mud.py send look
python3 scripts/mud.py send north east "kill fido"    # runs in order
python3 scripts/mud.py setup --wimpy 8                # idempotent game settings
python3 scripts/mud.py read --wait 5                  # collect what arrived on its own
python3 scripts/mud.py expect "is dead" --timeout 30  # block until text appears
python3 scripts/mud.py status                         # alive? where? what vitals?
python3 scripts/mud.py log -n 80                      # replay the transcript
python3 scripts/mud.py reset                          # quit and reconnect (recover from stuck states)
python3 scripts/mud.py stop                           # quit out cleanly
```

Every call prints a `[hp | mana | moves]` footer parsed from the game prompt,
so current vitals are always in front of you.

**`send` waits for the game prompt rather than sleeping a fixed time**, so it
returns as soon as the command is done. Multiple arguments run in order, which
is the right way to do a movement chain — one tool call instead of five.
Quote anything containing spaces.

**`read` is for output nobody asked for.** The MUD pushes text at you
constantly: combat rounds, wandering mobs, weather, other players' speech.
`send` returns only what its own command produced, so anything that lands
afterwards is collected with `read`.

**`expect` blocks until a pattern shows up** (regex), which beats polling
`read` in a loop when you are waiting on a specific outcome. On timeout it
reports that it did not match but still returns everything it captured, so a
miss is never a silent loss of output.

## Combat is asynchronous — the one thing to get right

A fight is not a single request/response. `send "kill fido"` returns the
opening round only; the rest of the battle arrives over the following seconds
and is invisible until you collect it. Reporting the result of a fight from
the `send` output alone will simply be wrong.

```bash
python3 scripts/mud.py send "consider fido"           # check the matchup first
python3 scripts/mud.py send "kill fido"               # opening round
python3 scripts/mud.py expect "is dead|You are dead|flee" --timeout 40
```

`consider` grades the fight before you commit: "easily" is safe, "The perfect
match!" is genuinely even and risky at low level, "Are you mad!?" will kill
you. Check it every time — mob difficulty is not guessable from the name.

Watch the HP in the footer between rounds. Below roughly a third, `flee` and
`rest`. Dying is recoverable but costs experience and strands your equipment
on a corpse, so retreating early is almost always the better trade. The wimpy
threshold set by `setup` is a backstop for the rounds you cannot see, not a
substitute for reading the HP yourself.

If `kill <mob>` answers *"That player is not here"*, the mob most likely
wandered off — `scan` or `look` to find it rather than assuming a typo.

## Playing well

`scan` shows mobs in adjacent rooms before you walk into them; it is the
cheapest safety habit in the game. `look` reads the room, and the
`[ Exits: ... ]` line is what you navigate by.

`rest` regenerates HP, mana, and movement much faster than standing — then
`stand` before moving or fighting. Watch for `You are hungry.` /
`You are thirsty.`: unaddressed they stall regeneration and eventually cause
damage. Fountains are free (there is one on the Temple Square); `eat` and
`drink` otherwise.

Equipment only counts once equipped — `wear` armour, `wield` weapons, `hold`
lights. A character carrying a sword it never wielded is still punching.
Check `equipment` when damage output looks wrong.

Dark rooms print `It is pitch black...` and hide exits and mobs alike; you
need a held light source to see.

For anything else — the full command list, shops, banking, guilds,
progression, group play — ask the game rather than guessing at syntax:
`send commands` lists everything available, and `send "help <topic>"` explains
a specific one.

## Reporting back to the user

Summarise what happened in the fiction rather than pasting raw transcript:
where the character is, what is present, what changed, what the options are.
Include exits when the user is deciding where to go, and current HP whenever
it is dropping. Quote the game's own text when its flavour matters — it is a
game, and the prose is the point.

When the user gives an open-ended instruction ("explore a bit", "find
something to fight"), take several steps and report the arc, rather than
stopping to confirm after every room. Stop early and ask if HP gets
dangerous, a fight is riskier than `consider` suggested, or something
irreversible is on the table — spending gold, dropping gear, `delete`.

## When something looks stuck

`status` first — it reports whether the session is live and replays the recent
tail, which usually shows the game sitting at an unexpected prompt (a menu, a
`y/n` question, a pager). Answer it with `send`.

If the daemon died or the MUD dropped the link, `stop` then `start` to
reconnect. State lives in `~/.mud-player/<host>-<port>/` (override with
`MUD_STATE_DIR`), and `transcript.log` there holds the full session history,
so nothing that already happened is lost by restarting.

## Recovering from stuck states with reset

If the character gets trapped in an unwinnable state (lost in a dark dungeon
with no clear path out, stuck on an unexpected menu, etc.), use `reset`:

```bash
python3 scripts/mud.py reset
```

This quits the character and reconnects, putting them back in their last
known game location. **Note:** On this MUD, the character's location is
stored server-side, so `reset` reconnects but doesn't teleport. If truly
stuck, manually navigate out using `send` with different directions, or
accept it as a lesson in state management design.

## Persistent memory for longer goals

For multi-session goals (reach level 7, defeat a specific monster), maintain markdown
memory files that the agent can reference and update:

```bash
# After significant actions, update memory from the transcript
python3 scripts/update_memory.py

# Memory files, alongside the scripts:
# - data/player.md   ← character level, HP, location, goals
# - data/world.md    ← map, mobs, quest info, target locations
```

`update_memory.py` only rewrites the `- **Field**: value` lines in
`player.md`, so keep that shape intact when editing it by hand. `world.md` is
yours entirely — write map notes, routes, and `consider` verdicts there as you
learn them.

The agent should read these files at the start of a session to understand current
progress, and run `update_memory.py` after major milestones (leveling up, discovering
new areas, defeating key mobs) so that future sessions inherit the knowledge.

**Example workflow for "reach level 7 and defeat the Massive Minotaur":**

1. Start session, read `data/player.md` to see current level
2. Work toward leveling (fight mobs, gain experience)
3. After reaching level 6, run `update_memory.py` so next session knows the goal is close
4. Continue playing; update memory after each level
5. Once at level 7, search `data/world.md` for Minotaur location
6. Navigate and prepare for the final fight
7. After victory, update memory to mark goal complete

These files are simple markdown — an agent can parse them to understand context and
can edit them directly to mark progress. This teaches how agents can maintain
state across sessions using plain text as a data store.
