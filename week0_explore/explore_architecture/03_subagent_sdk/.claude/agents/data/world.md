# World

Map, mobs, and hazards. Hand-maintained — `update_memory.py` does not touch
this file. Append as you explore.

Most of what follows was learned in the Architecture 2 sessions and recovered
from `docs/technical_journal.md`; the original `world.md` was not carried over
when the skill became an agent. Anything marked **unverified** has not been
re-confirmed since the port.

## Ground truth beats exploration

The generated world data is the single most useful resource here, and it beats
blind `look`/`scan` outright:

```
week0_explore/preview/data/world/{wld,mob,zon}/*.json
```

- `wld/<zone>.json` — every room's exits as `{dir, room_linked}`. Enough to BFS
  a path between any two room ids.
- `zon/<zone>.json` — the file that actually answers "what can I fight, and
  where": concrete `{mob, room, max}` spawn placements.
- `mob/<zone>.json` — mob *templates* only (level, aliases, xp) keyed by id.
  Useless for location on its own; you need the `zon` file to place them.

These are `.gitignore`'d as build output. Regenerate with `week0_explore/bin/convert-world`.

## Midgaard, observed

| Room | Exits | Notes |
|---|---|---|
| The Temple Of Midgaard | n e s w d | Start/respawn point. ATM in the wall, donation room east, Reading Room west. **No fountain here.** |
| Temple Square | — | Has the fountain (free food/water fix). See hazards below. |
| Market Square | n e s w | Statue in the middle. N to temple square, S to common square, E/W main street. |
| The Common Square | n e s w | W poor alley, E dark alley, N market square, S the dump. |
| The Dump (room 3030) | n d | One door from the main farming area; `d` leads into the sewers. |

## Safe farming

All level 1, all grade "The perfect match!" on `consider`:

- beastly fido (four known spawn rooms)
- janitor
- beggar
- odif yltsaeb

Roughly 760 xp was farmed in one sitting cycling between the fido rooms plus
the janitor/beggar spots. Exact spawn rooms are in `zon/30.json`.

## Hazards

- **Town guards join fights they are not part of.** A Peacekeeper standing
  passively in a room joined a fight against a fido and took HP from 22 to 3 in
  a couple of rounds. Peacekeeper, cityguard, and knight all police *any*
  violence they witness. `consider` grades the target only — it will never warn
  you about a bystander.
- **Effective no-fight rooms** (multiple guards stacked): the East Gate, the
  Guild of Swordsmen entrance, the Grunting Boar bar.
- **A level-20 green gelatinous blob wanders through Temple Square.** Instantly
  lethal at level 1, and it moves — so a room that was safe last visit may not
  be. `consider` would have caught it; check before engaging anything.
- **Darkness is a trap, not an inconvenience.** In an unlit room `look` and
  `scan` return only "It is pitch black..." — no room name, no mob names,
  nothing to act on. `kill <guess>` against ~20 plausible mob names all failed.
  Carry and `hold` a light source before going underground.
- **`reset` does not rescue you from a bad location.** tbaMUD stores character
  position server-side, so quit+reconnect drops you into the same dark room. It
  fixes dropped links, not wrong places.

## Escape route: sewers → Midgaard

Walked and verified on the first attempt. The sewer complex under the Guild of
Swordsmen spans zones 70/71/73.

```
Zone 73 room 7345  ──10 moves──▶  Zone 73 room 7300
                   ──up──────────▶  Zone 71
                   ──up──────────▶  Zone 70 room 7004
                   ──5 moves─────▶  Zone 70 room 7030
                   ──up──────────▶  Midgaard room 3030 ("The Dump")
```

Technique that made this work in the dark: the in-game `exits` command still
lists direction *letters* with no light (just not descriptions), which is
enough to execute a pre-computed path blindly. The moment the path reaches a
lit room, `exits` also prints neighbor room *names* — grep those against the
`wld` json to re-confirm exact position before continuing.

## Shops and services

- **Weapon Shop, Main Street** — small sword, 78g. Worth buying immediately;
  bare-fisted attacks miss constantly at level 1.
- **Temple Square fountain** — free water.
- **ATM**, Temple of Midgaard — banking.

## Targets

- **Massive Minotaur**, Newbie zone — the primary goal, needs level 7.
  **Unverified:** exact room. Look it up in the Newbie zone's `zon` json before
  setting out rather than hunting for it live.
