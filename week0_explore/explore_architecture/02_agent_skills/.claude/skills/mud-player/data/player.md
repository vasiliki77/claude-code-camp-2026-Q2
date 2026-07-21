# Player State

## Character
- **Name**: Dummy
- **Class**: Swordpupil
- **Level**: 1
- **Experience**: 760 / 2000 (need 1240 more for level 2)
- **Gold**: 22

## Vitals (last known, full-rest values)
- **HP**: 22 / 22
- **Mana**: 100 / 100
- **Moves**: 83 / 83

## Location (as of end of session 2026-07-21)
- **Current Room**: Midgaard, somewhere in the Common Square / Dump / Poor Alley loop
- **Zone**: Midgaard (zone 30) — successfully escaped the Zone 70/71/73 sewer dungeon complex

## Skills
- kick (poor)

## Equipment
- **Wielded**: a small sword (bought from the Weapon Shop on Main Street, 78 gold)
  - Bare-handed combat missed constantly ("You swing your fist... but miss him!"). Getting a
    weapon early is a high-value move, not optional flavor — do it before grinding seriously.

## Inventory
- 5x piece of meat (from fido corpses via autoloot — free food, always keep a few banked)
- a key of dull metal (from a beggar corpse, unidentified use — hang onto it)

## Goals
- [ ] Reach level 2 (760/2000 exp — in progress, ~62% there)
- [ ] Reach level 7
- [ ] Defeat the Massive Minotaur (Newbie zone, north of Midgaard)

## How to pick this back up next session
1. `start`, then `status` to confirm you're not mid-fight or on a menu.
2. `score` immediately — trust this over any stale HP/moves footer (see Known Issues below).
3. If in Midgaard: go straight back to farming beastly fido (see world.md "Safe grinding loop").
4. If somehow back in the Zone 70/71/73 dungeon: see world.md "Dungeon escape route" — it's a
   known, tested path, don't re-explore from scratch.

## What worked this session (2026-07-21)
- **Escaped the pitch-black sewer dungeon (Zones 70/71/73)** that a previous session got stuck in.
  The breakthrough was reading the actual world data files instead of relying on in-game `look`:
  - `week0_explore/preview/data/world/wld/<zone>.json` — room definitions and exits (`dir`:
    0=N,1=E,2=S,3=W,4=U,5=D; `room_linked` is the destination room id).
  - `week0_explore/preview/data/world/zon/<zone>.json` — **this is the one that actually matters
    for finding mobs**: it lists `{"mob": <mob_id>, "room": <room_id>, "max": N}`, i.e. exactly
    which mob spawns in which room and how many can exist at once. The `wld`/`mob` files alone
    only give you templates and static descriptions, not placement.
  - `week0_explore/preview/data/world/mob/<zone>.json` — mob stats/aliases/level, keyed by id.
  - Even in a pitch-black room, `exits` still lists direction letters (just not descriptions), and
    once you find a lit room, `exits` shows the neighbor room *names* — cross-reference those
    names against the `wld` json to pin down exactly which room id you're standing in, then you
    can BFS a path in the json data to any destination room id.
  - Full working escape path (in case reset drops the character back in the dungeon): see
    "Dungeon escape route" in world.md.
- **Farmed the escape point into real levels.** Landed via the escape route into Midgaard's "The
  Dump" (room 3030), one door from the Common Square where beastly fido spawn. 760 exp earned in
  one sitting, entirely from beastly fido / janitor / beggar (all confirmed level 1, all
  "The perfect match!" on `consider`).
- **Bought a weapon.** Bare-fisted combat had a high miss rate. 78g small sword from the Weapon
  Shop (Main Street, north of the western Main Street junction) noticeably improved things.

## Known issues / traps to avoid next time
- **Peacekeepers and cityguards will jump into your fights.** A Peacekeeper standing passively in
  a room joined a fight against a fido and dropped HP from 22 to 3 in a couple of rounds when I
  fled — this is a near-death experience, not a minor annoyance. Rule of thumb: **never fight
  while a Peacekeeper, cityguard, or knight is in the room**, even if the actual target is a safe
  mob. Check `look` before engaging, not just `consider`.
- **Some rooms stack multiple dangerous guards** — the East Gate had 5 cityguards at once, the
  Guild of Swordsmen entrance had a cityguard + a knight. Route around these, don't try to farm
  near them.
- **There's a level-20 "green gelatinous blob" that wanders into Temple Square.** Instantly fatal
  if provoked. Don't attack unidentified mobs without checking `consider` or the mob json first.
- **Mercenaries (Dark Alley, room 3026) are level 5 and can stack up to 5 in one room.** Not worth
  the risk for a level 1 character even though the odif-yltsaeb (a safe level-1 fido joke-mob)
  also spawns there.
- **Mob respawns are not instant.** After clearing a spawn point, it can take several minutes of
  real time before that room repopulates (zone lifespan value in the `zon` json, e.g. 15 for zone
  30, is in minutes). Don't just stand in one room spamming `look` — cycle through the other known
  spawn rooms (see world.md) while waiting, and only backtrack once you've made a full circuit.
- **HP/moves in the `[hp | mana | moves]` footer can look stale/wrong immediately after a big
  event (fleeing, a rest finishing).** If a number looks alarming or suspicious, run `score` — it
  is always authoritative, the footer is parsed from the last prompt line and can lag.
- **Hunger/thirst silently caps HP and movement regeneration**, even while resting. If `rest`
  stops producing HP gains, check `score` for "You are hungry"/"You are thirsty" and fix both
  before assuming something else is wrong. Free water: fountain at Temple Square (`drink
  fountain`). Food: eat banked meat from fido kills (`eat meat`), or the General Store on Main
  Street sells non-food items only (torches, lanterns, bags) — no bread there, check the Bakery
  (world.md) if meat runs out.
- **Fleeing from combat can itself cost significant HP** (took a large hit mid-flee once). Don't
  wait until HP is critical to disengage — retreat while still comfortably above the wimpy
  threshold, not at it.
