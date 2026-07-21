# World Map & Information

## World data files (ground truth — use these instead of guessing)

The repo ships the actual CircleMUD/tbaMUD world data as JSON, at:
`week0_explore/preview/data/world/{wld,mob,zon}/<zone_number>.json`

- **`wld/<zone>.json`**: room definitions. Each room has an `id`, `name`, `desc`, `flags` (e.g.
  `DARK`), and `exits` — a list of `{"dir": N, "room_linked": <room_id>}` where dir is
  0=North, 1=East, 2=South, 3=West, 4=Up, 5=Down.
- **`zon/<zone>.json`**: **this is the file that tells you where mobs actually spawn.** It has a
  `mobs` list of `{"mob": <mob_id>, "room": <room_id>, "max": <count>}`. The room a mob's template
  lists in `mob/<zone>.json` is NOT its spawn location — only the `zon` file has that. Also has
  `lifespan` (minutes between zone resets — expect multi-minute waits for respawns, don't assume
  something is broken if a farmed room stays empty for a bit) and `reset_mode` (2 = always reset
  regardless of players present, which is what Midgaard zone 30 uses).
- **`mob/<zone>.json`**: mob stats keyed by `id` — `level`, `aliases` (what you type to `kill`),
  `short_desc`, `xp`. Cross-reference the `mob` id from the `zon` file here to find its real name
  and level before deciding whether to fight it.

**Workflow for "I don't know what to fight" or "I'm lost"**: figure out what zone number you're
in from room names via `grep -r` across `wld/*.json` for a room name you can see, load that zone's
`zon` file to see the full mob roster and room ids, then cross-reference `mob/<zone>.json` for
levels before engaging anything unfamiliar.

Even in pitch-black rooms, the in-game `exits` command still lists direction letters (not
descriptions) — that's enough to do a manual walk if you already know the graph from the wld
json. Once you reach ANY lit room, `exits` shows neighboring room *names*, which you can grep in
the wld json to pin down your exact room id and re-sync your position.

## Midgaard (zone 30) — the safe town zone

### Key Locations (room ids from wld/30.json, useful for `grep`)
- **3005 Temple Square** — fountain (`drink fountain`, free, cures thirst), Clerics' Guild west,
  Grunting Boar Inn east. **Danger: a level-20 green gelatinous blob wanders through here.** Do
  not engage. Peacekeepers also pass through.
- **Market Square** — central hub, N to Temple Square, S to Common Square, E/W to Main Street.
- **3025 The Common Square** — fido spawn point, connects to Poor Alley (W), Dark Alley (E,
  dangerous — see below), Market Square (N), The Dump (S).
- **3030 The Dump** — the exit from the sewer dungeon comes up here (see "Dungeon escape route"
  below). Also a fido spawn point.
- **3024 The Eastern End Of Poor Alley** — fido spawn point, Grubby Inn to the south. A
  Peacekeeper frequently stands/wanders here — check before fighting.
- **Poor Alley** (further west of 3024) / **Wall Road** / **the Bridge** — mostly empty, leads to
  the west city wall and river, not useful for farming.
- **Grubby Inn** (south of 3024) — beggar spawn point.
- **3012 / 3016 Main Street** (two separate rooms, both called "Main Street") — both are fido
  spawn points with high capacity (max 15 each in the zone file). 3016 is next to the Weapon Shop
  and the Guild of Swordsmen entrance (ground level, not the dungeon).
- **3006 Grunting Boar Inn entrance** — janitor spawn point, but a cityguard often stands here too.
- **The Grunting Boar** (bar, east of the inn entrance) — has a level-2 "drunk" (safe on paper) but
  routinely has **two Peacekeepers** in it. Skip unless the room is clear of guards.

### Shops & Services
- **General Store** (north from the western Main Street junction) — sells cashcards, boxes, bags,
  lanterns, torches. **No food here** despite the name.
- **Bakery** (north from west Main Street, per earlier session) — sells danish, bread, waybread.
  Go here if the banked fido meat runs out.
- **Weapon Shop** (north from the eastern Main Street junction, near the Guild of Swordsmen) —
  small sword 78g, warhammer 65g, wooden club 15g, dagger 13g, long sword 780g, flail 812g. Buying
  even a cheap weapon fixed a lot of missed bare-fisted attacks — do this early.
- **Pet Shop** (south from the western Main Street junction) — just a shop (Pet Shop Boy NPC), NOT
  a place to find fightable kittens/puppies despite what the zone file suggests (their spawn room,
  3032 "PETSHOP STOREROOM", has no player-reachable exits).

### Guilds & Training
- **Guild of Swordsmen entrance** (south of the eastern Main Street junction) — ground-level
  entrance has an ATM, a cityguard, AND a knight guarding it. Do not fight here. The practice
  yard/dungeon stairwell is further in (see dungeon section — this is where the earlier stuck
  session fell into Zone 70).

## Safe grinding loop (confirmed, 2026-07-21)

Farmed ~760 exp in one sitting cycling between these rooms. All mobs here are confirmed level 1
and "The perfect match!" on `consider`:

| Mob | Aliases | Spawns at (room ids) |
|---|---|---|
| beastly fido | `fido` | 3024, 3025, 3016, 3012 (max 15 each — biggest farm target) |
| the janitor | `janitor` | 3006 (watch for cityguard there) |
| the beggar | `beggar` | 3044 (Poor Alley), 3048 (Grubby Inn), max 2 each |
| the odif yltsaeb | `odif`, `yltsaeb` | 3026 Dark Alley — **only 1 spawn, but shares the room with up to 5 level-5 mercenaries, skip it** |

**Loop**: Common Square (3025) → Poor Alley junction (3024) → Grubby Inn (south) → back up → Market
Square → both Main Street rooms (3012, 3016) → Grunting Boar Inn entrance (3006, check for
cityguard first). If a room is empty, move to the next one rather than waiting in place — cycle
through all of them once, then start the loop again; that spacing roughly matches the zone's
respawn timer instead of wasting turns on one dead spot.

**Before every kill**: `look` first to check no Peacekeeper/cityguard/knight is present, THEN
`consider <mob>`, THEN `kill`. Guards will jump into fights they witness — this caused a
22→3 HP near-death event in one session. If a guard is in the room, walk away and farm elsewhere;
don't try to out-position it.

## Dungeon escape route (Zones 70/71/73 — the sewer complex under the Guild of Swordsmen)

A previous session got a character stuck here indefinitely (pitch black, couldn't identify mobs to
fight, `reset` just reconnects to the same server-side location). This was solved by reading the
`wld`/`zon` json for zones 70, 71, and 73, BFS-ing a path in the data, then walking it for real
using the in-game `exits` command (which lists direction letters even in the dark) to verify each
step against the expected room's exit count.

**Full path out, if a character ever ends up back down there** (zone 73 → zone 70 → Midgaard):
1. From Zone 73 room 7345 ("The Pool"): `east, east, north, north, north, north, east, east,
   south, south` → arrives at room 7300 ("Cave Entrance").
2. `up` → room 7102 in Zone 71 ("Under The Dark Pit").
3. `up` again → room 7004 in Zone 70 ("The Dark Pit" — also a bat/level-1 mob spawn room, worth a
   `kill bat` attempt here since you're passing through).
4. From 7004: `east, east, south, east, north` → room 7030 ("The Quadruple Junction Under The
   Dump").
5. `up` → **pops out at Midgaard room 3030, "The Dump"**, one door from the Common Square fido
   farm. Escape complete.

If starting from a different dungeon room than 7345, load `wld/73.json`, `wld/71.json`,
`wld/70.json`, find your room by matching visible exit counts/neighbor names against the json
(the in-game `exits` command shows neighbor names once you reach any lit room, e.g. "Cave Room",
"The Spongy Room", "The Square Lair" — grep these in the wld files to identify your room id), and
BFS a path to room 7300 (Zone 73) or 7030 (Zone 70) using the same dir-letter exit graph.

**Zone 73 mobs are NOT beginner-friendly** — its `zon` file spawns things like a sea hag (level
14), naga (level 12), basilisk (level 13), red dragon (level 19). Don't try to fight anything down
there; just navigate through. Zone 70 does have real level-1 mobs (bat, spider — see its `mob`
json aliases) if a light source is ever available.

## Goal Targets
- **Massive Minotaur** — Location: Newbie zone (north of Midgaard, not yet located precisely).
  Status: PRIMARY GOAL once level 2 is reached. Strategy: engage cautiously, `consider` first,
  retreat if the fight looks even-or-worse — the janitor fight alone once dropped HP from 22 to 9,
  so a mob strong enough to be a "goal" fight deserves real caution, not the fido-farming mindset.

## Discovered Facts
- Wimpy threshold helps auto-flee at low HP, but it's not instant safety — HP can still drop fast
  between checks, and fleeing itself can cost HP. Retreat well before the threshold, not at it.
- Mobs wander between rooms; if `kill <mob>` says "not here," `scan`/`look` before assuming a typo.
- Combat is asynchronous (use `read`/`expect` to capture rounds after the opening one).
- Dark areas need a light source to navigate `look`/`scan` properly, but `exits` still works blind
  (direction letters only, no neighbor names).
- Guards (Peacekeeper, cityguard, knight) will intervene in fights happening in their room, even
  against a mob the guard normally ignores. Treat any guarded room as a no-fight zone.
- HP/mana/moves regen (even while resting) stalls while hungry or thirsty — check `score`, not just
  the footer, if `rest` doesn't seem to be working.
- Buying even a cheap weapon (wielded, not just carried) measurably reduces miss rate versus bare
  hands — worth the ~15-80 gold before serious grinding.
